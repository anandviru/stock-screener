"""
accounts.py — minimal email/password accounts, backed by Postgres (Supabase).

Named accounts.py rather than auth.py: Streamlit Community Cloud's own
hosting layer appears to reserve/inject something at the top-level module
name "auth" (observed as a `KeyError: 'auth'` crash reachable only via the
anonymous/public viewer path, not when signed in as the app owner) --
colliding with a user module of that name.

Passwords are never stored in plain text — only a salted PBKDF2-SHA256
hash, using the stdlib (no extra dependency for the hashing itself).

Connection info comes from environment variables (PGHOST, PGPORT, PGDATABASE,
PGUSER, PGPASSWORD) — the standard mechanism on any host (DigitalOcean App
Platform, a Docker container, etc.), set once in that platform's dashboard.
Locally, falls back to st.secrets["postgres"] (.streamlit/secrets.toml,
gitignored) so nothing extra is needed for local dev. A short-lived
connection is opened per call rather than held open, since Streamlit
reruns the script on every interaction.
"""

import hashlib
import os
import re
import secrets

import psycopg2
import streamlit as st

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PBKDF2_ROUNDS = 200_000


def _connection_params() -> dict:
    if os.environ.get("PGHOST"):
        return {
            "host": os.environ["PGHOST"],
            "port": os.environ.get("PGPORT", 5432),
            "dbname": os.environ.get("PGDATABASE", "postgres"),
            "user": os.environ["PGUSER"],
            "password": os.environ["PGPASSWORD"],
        }
    return dict(st.secrets["postgres"])


def _connect():
    return psycopg2.connect(**_connection_params(), sslmode="require")


def _hash_password(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt_hex), PBKDF2_ROUNDS
    ).hex()


def sign_up(email: str, password: str) -> tuple[bool, str]:
    """Create a new account. Returns (success, message)."""
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        return False, "Enter a valid email address."
    if len(password) < 8:
        return False, "Password must be at least 8 characters."

    salt = secrets.token_hex(16)
    password_hash = _hash_password(password, salt)

    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM users WHERE email = %s", (email,))
            if cur.fetchone() is not None:
                return False, "An account with that email already exists."

            cur.execute(
                "INSERT INTO users (email, salt, hash) VALUES (%s, %s, %s)",
                (email, salt, password_hash),
            )
            conn.commit()
    except psycopg2.Error as e:
        return False, f"Couldn't reach the database ({e.pgcode or 'connection error'})."

    return True, "Account created."


def log_in(email: str, password: str) -> tuple[bool, str]:
    """Check credentials. Returns (success, message)."""
    email = email.strip().lower()

    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT salt, hash FROM users WHERE email = %s", (email,))
            record = cur.fetchone()
    except psycopg2.Error as e:
        return False, f"Couldn't reach the database ({e.pgcode or 'connection error'})."

    if record is None:
        return False, "No account with that email. Try signing up instead."
    salt, stored_hash = record
    if _hash_password(password, salt) != stored_hash:
        return False, "Incorrect password."
    return True, "Signed in."
