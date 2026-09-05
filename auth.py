"""
auth.py — minimal email/password accounts, stored as a salted-hash JSON file.

Storage note: this is a local file, not a database. On Streamlit Community
Cloud's free tier, the local filesystem resets on every redeploy (every git
push) and whenever the app sleeps from inactivity and restarts — accounts
created here will NOT survive that. Fine for local use and casual demos;
swap in a real database (e.g. Postgres/Supabase) before durability matters.

Passwords are never stored in plain text — only a salted PBKDF2-SHA256
hash, using the stdlib (no extra dependency).
"""

import hashlib
import json
import os
import re
import secrets

USERS_FILE = "users.json"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PBKDF2_ROUNDS = 200_000


def _load_users() -> dict:
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE) as f:
        return json.load(f)


def _save_users(users: dict) -> None:
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


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

    users = _load_users()
    if email in users:
        return False, "An account with that email already exists."

    salt = secrets.token_hex(16)
    users[email] = {"salt": salt, "hash": _hash_password(password, salt)}
    _save_users(users)
    return True, "Account created."


def log_in(email: str, password: str) -> tuple[bool, str]:
    """Check credentials. Returns (success, message)."""
    email = email.strip().lower()
    users = _load_users()
    record = users.get(email)
    if record is None:
        return False, "No account with that email. Try signing up instead."
    if _hash_password(password, record["salt"]) != record["hash"]:
        return False, "Incorrect password."
    return True, "Signed in."
