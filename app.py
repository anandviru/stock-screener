"""
app.py — Streamlit web UI for the Daily 1% Screener.

Run locally with:
    streamlit run app.py

Wraps run_daily.run_pipeline() and backtest.run_backtest() — the same
logic the CLI uses — with a browser dashboard: a run button, regime
status, filter funnel, a styled watchlist table, a browsable history of
past runs, and a walk-forward backtest tab.
"""

import glob
import os
from datetime import date

# Run from this file's own directory regardless of the caller's cwd, so
# universe.txt / watchlist_*.csv / config.py resolve the same way whether
# this is launched via `streamlit run app.py` locally or by a host.
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import streamlit as st

import auth
import config as C
from backtest import run_backtest, summarize
from run_daily import run_pipeline

st.set_page_config(
    page_title="Daily 1% Screener",
    page_icon="📈",
    layout="wide",
)

# ---------- style ----------
st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; max-width: 1100px; }
    div[data-testid="stMetric"] {
        background: rgba(127,127,127,0.08);
        border-radius: 10px;
        padding: 12px 16px;
    }
    .veto-box {
        background: rgba(220,50,50,0.10);
        border: 1px solid rgba(220,50,50,0.35);
        border-radius: 10px;
        padding: 16px 20px;
        margin: 8px 0 16px 0;
    }
    .empty-box {
        background: rgba(127,127,127,0.08);
        border-radius: 10px;
        padding: 16px 20px;
        margin: 8px 0 16px 0;
    }
    .logo-row {
        display: flex;
        align-items: center;
        gap: 10px;
        height: 38px;
    }
    .logo-badge {
        background: #16A34A;
        color: white;
        font-weight: 800;
        font-size: 13px;
        width: 34px;
        height: 34px;
        border-radius: 9px;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
    }
    .logo-title {
        font-size: 21px;
        font-weight: 700;
        color: #111827;
        white-space: nowrap;
    }
    /* Refresh Screener / Backtest read as green ghost buttons */
    div[data-testid="stButton"] button[kind="secondary"] {
        border-color: #16A34A;
        color: #16A34A;
    }
    div[data-testid="stButton"] button[kind="secondary"]:hover {
        border-color: #15803D;
        color: #15803D;
        background-color: rgba(22,163,74,0.06);
    }
    /* Sign In reads as a solid dark button, distinct from the theme green */
    .st-key-signin_btn button {
        background-color: #111827 !important;
        color: white !important;
        border-color: #111827 !important;
    }
    .st-key-signin_btn button:hover {
        background-color: #1F2937 !important;
        border-color: #1F2937 !important;
        color: white !important;
    }
</style>
""", unsafe_allow_html=True)

if "result" not in st.session_state:
    st.session_state.result = None
if "backtest_trades" not in st.session_state:
    st.session_state.backtest_trades = None
if "view" not in st.session_state:
    st.session_state.view = "screener"
if "user" not in st.session_state:
    st.session_state.user = None


def _run_screener_now():
    st.session_state.view = "screener"
    progress_area = st.empty()
    with st.spinner("Running..."):
        def show(msg):
            progress_area.info(msg)
        st.session_state.result = run_pipeline(progress=show)
    progress_area.empty()


@st.dialog("Sign in")
def _auth_dialog():
    mode = st.radio("Mode", ["Sign In", "Sign Up"], horizontal=True, label_visibility="collapsed")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    password2 = st.text_input("Confirm password", type="password") if mode == "Sign Up" else None

    if st.button("Create account" if mode == "Sign Up" else "Sign in",
                 type="primary", use_container_width=True):
        if mode == "Sign Up":
            if password != password2:
                st.error("Passwords don't match.")
            else:
                ok, msg = auth.sign_up(email, password)
                if ok:
                    st.session_state.user = email.strip().lower()
                    st.rerun()
                else:
                    st.error(msg)
        else:
            ok, msg = auth.log_in(email, password)
            if ok:
                st.session_state.user = email.strip().lower()
                st.rerun()
            else:
                st.error(msg)

    st.caption(
        "Demo accounts only — stored locally and may reset when the app restarts."
    )


# ---------- header ----------
col_title, col_run, col_nav, col_auth = st.columns(
    [4.5, 1.7, 1.1, 1.1], vertical_alignment="center"
)
with col_title:
    st.markdown(
        '<div class="logo-row"><div class="logo-badge">1%</div>'
        '<div class="logo-title">Daily 1% Screener</div></div>',
        unsafe_allow_html=True,
    )
with col_run:
    if st.button("🔄 Refresh Screener", type="secondary", use_container_width=True):
        _run_screener_now()
with col_nav:
    if st.button("🧪 Backtest", type="secondary", use_container_width=True):
        st.session_state.view = "backtest"
with col_auth:
    if st.session_state.user:
        if st.button(f"👤 {st.session_state.user.split('@')[0]} (Sign out)", use_container_width=True):
            st.session_state.user = None
            st.rerun()
    else:
        if st.button("Sign In", use_container_width=True, key="signin_btn"):
            _auth_dialog()

st.caption(
    "Flags up to 10 liquid stocks whose structure makes a +1% move plausible "
    "for the next session, each with a pre-computed target and stop. "
    "It flags candidates and enforces a written trade plan — it doesn't "
    "guarantee profits, place trades, or replace judgment."
)

# ---------- sidebar (thresholds + history) ----------
with st.sidebar:
    st.header("Current thresholds")
    market_cap_line = (
        f"- **Market cap** ≥ ${C.MIN_MARKET_CAP/1e9:g}B (mega-cap only)\n"
        if C.MIN_MARKET_CAP > 0 else ""
    )
    st.markdown(f"""
- **Price** ≥ ${C.MIN_PRICE:g}
- **Avg $ volume** ≥ ${C.MIN_AVG_DOLLAR_VOLUME/1e6:g}M
- **ATR%** {C.MIN_ATR_PCT:g}–{C.MAX_ATR_PCT:g}%
{market_cap_line}- **Volume ratio** ≥ {C.MIN_VOLUME_RATIO:g}x
- **Dist from 20d high** ≤ {C.MAX_DIST_FROM_HIGH20:g}%
- **Style** {'Mean-reversion' if C.USE_MEAN_REVERSION else 'Momentum'}
- **Regime** SPY > MA20{', ' if C.SPY_MUST_BE_ABOVE_MA20 else ' (off), '}VIX {C.VIX_MIN:g}–{C.VIX_MAX:g}
- **Target / Stop** +{C.TARGET_PCT:g}% / -{C.STOP_PCT:g}%
""")

    st.divider()
    st.header("History")
    past_files = sorted(glob.glob("watchlist_*.csv"), reverse=True)
    if past_files:
        chosen = st.selectbox(
            "View a past watchlist",
            options=["(none)"] + past_files,
        )
    else:
        chosen = "(none)"
        st.caption("No saved watchlists yet.")

# ================= Screener view =================
if st.session_state.view == "screener":
    result = st.session_state.result

    if result is not None:
        st.subheader(f"Run — {result['date']}")
        st.caption(f"{result['clean_count']} / {result['universe_count']} tickers had clean data")

        if not result["regime_ok"]:
            st.markdown('<div class="veto-box">', unsafe_allow_html=True)
            st.markdown("### 🚫 NO-TRADE DAY — regime filter veto")
            for r in result["regime_reasons"]:
                st.markdown(f"- {r}")
            st.markdown("*This is the tool working, not failing. Sit today out.*")
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            f = result["funnel"]
            n_kept = 0 if result["results_df"] is None else len(result["results_df"])
            cols = st.columns(5 if C.MIN_MARKET_CAP > 0 else 4)
            cols[0].metric("Universe scanned", f["input"])
            cols[1].metric("Passed universe filter", f["universe"])
            i = 2
            if C.MIN_MARKET_CAP > 0:
                cols[i].metric(f"Mega-cap (≥${C.MIN_MARKET_CAP/1e9:g}B)", f["mega_cap"])
                i += 1
            cols[i].metric("Passed setup filter", f["setup"])
            cols[i + 1].metric("Kept on watchlist", n_kept)

            for ticker, edate in result["skipped_earnings"]:
                st.caption(f"⏭️ Skipped {ticker} — earnings on {edate}")

            if result["results_df"] is None:
                st.markdown('<div class="empty-box">', unsafe_allow_html=True)
                st.markdown("### No stocks passed all filters today")
                st.markdown("Also a valid outcome — no forced trades on a quiet tape.")
                st.markdown('</div>', unsafe_allow_html=True)

                scanned_df = result.get("scanned_df")
                if scanned_df is not None and not scanned_df.empty:
                    st.subheader(f"Mega-cap stocks scanned ({len(scanned_df)})")
                    display_df = scanned_df.rename(columns={
                        "ticker": "Ticker",
                        "price": "Current Price",
                        "prev_close": "Yesterday's Close",
                        "change": "Change ($)",
                        "change_pct": "Change (%)",
                        "day_low": "Today's Low",
                        "day_high": "Today's High",
                    })

                    def _color_change(v):
                        if v > 0:
                            return "color: #16A34A"
                        if v < 0:
                            return "color: #DC2626"
                        return ""

                    st.dataframe(
                        display_df.style.format({
                            "Current Price": "${:.2f}", "Yesterday's Close": "${:.2f}",
                            "Change ($)": "{:+.2f}", "Change (%)": "{:+.2f}%",
                            "Today's Low": "${:.2f}", "Today's High": "${:.2f}",
                        }).map(_color_change, subset=["Change ($)", "Change (%)"]),
                        use_container_width=True,
                        hide_index=True,
                    )
            else:
                df = result["results_df"]
                st.dataframe(
                    df.style.format({
                        "score": "{:.2f}", "price": "${:.2f}",
                        "atr_pct": "{:.2f}%", "volume_ratio": "{:.2f}x",
                        "dist_high20": "{:.2f}%", "rsi": "{:.1f}",
                        "ret20": "{:+.2f}%", "target": "${:.2f}", "stop": "${:.2f}",
                    }).background_gradient(subset=["score"], cmap="Greens"),
                    use_container_width=True,
                    hide_index=True,
                )
                st.download_button(
                    "⬇ Download watchlist CSV",
                    data=df.to_csv(index=False),
                    file_name=result["watchlist_path"] or f"watchlist_{result['date']}.csv",
                    mime="text/csv",
                )
                st.caption(
                    f"Trade plan per ticker: target +{C.TARGET_PCT:g}%, stop -{C.STOP_PCT:g}%, "
                    "time-stop at end of day if neither hits."
                )
    else:
        st.info("Click **Refresh Screener** above to fetch today's data and screen the universe.")

    # ---------- history viewer ----------
    if chosen != "(none)" and os.path.exists(chosen):
        st.divider()
        st.subheader(f"📜 {chosen}")
        hist_df = pd.read_csv(chosen)
        if hist_df.empty:
            st.caption("Empty file — no stocks passed that day.")
        else:
            st.dataframe(hist_df, use_container_width=True, hide_index=True)

# ================= Backtest view =================
else:
    st.caption(
        "Walk-forward test: re-runs the exact same filter chain on each historical "
        "trading day using only data available up to that day, then checks whether "
        "the next session's target or stop would have hit. A 2-year window takes "
        "roughly 5 minutes — it re-downloads history and steps through it one day "
        "at a time."
    )

    years = st.slider("Backtest window (years)", min_value=0.5, max_value=5.0, value=2.0, step=0.5)
    backtest_clicked = st.button("▶ Run backtest", type="primary")

    if backtest_clicked:
        progress_area = st.empty()
        progress_bar = st.progress(0.0)
        with st.spinner("Backtesting..."):
            def show_bt(msg):
                progress_area.info(msg)
                if "day" in msg and "/" in msg:
                    try:
                        frac = msg.split("day ")[1].split("/")
                        progress_bar.progress(min(int(frac[0]) / int(frac[1].split()[0]), 1.0))
                    except Exception:
                        pass
            st.session_state.backtest_trades = run_backtest(years=years, progress=show_bt)
        progress_area.empty()
        progress_bar.empty()

    trades = st.session_state.backtest_trades

    if trades is None:
        st.info("Click **Run backtest** to simulate the strategy over historical data.")
    elif trades.empty:
        st.warning("No trades were generated in this window — regime or setup filters vetoed every day.")
    else:
        s = summarize(trades)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total trades", s["total_trades"])
        c2.metric("Win rate", f"{s['win_rate']:.1f}%")
        c3.metric("Avg return / trade", f"{s['avg_return_pct']:+.2f}%")
        c4.metric("Cumulative return*", f"{s['cumulative_return_pct']:+.1f}%")

        c5, c6, c7 = st.columns(3)
        c5.metric("Target hits", s["target_hits"])
        c6.metric("Stop hits", s["stop_hits"])
        c7.metric("Time-stops", s["time_stops"])

        if len(s["equity_curve"]) > 1:
            st.subheader("Equity curve*")
            st.line_chart(s["equity_curve"] * 100)

        st.subheader(f"All trades ({len(trades)})")
        st.dataframe(
            trades.sort_values("date", ascending=False).style.format({
                "entry": "${:.2f}", "target": "${:.2f}", "stop": "${:.2f}",
                "exit": "${:.2f}", "return_pct": "{:+.2f}%",
            }),
            use_container_width=True,
            hide_index=True,
        )
        st.download_button(
            "⬇ Download trades CSV",
            data=trades.to_csv(index=False),
            file_name=f"backtest_{years:g}y_{date.today().isoformat()}.csv",
            mime="text/csv",
        )

        st.caption(
            "*Equal-weighted across same-day signals, no position sizing or capital "
            "limits — an illustrative curve, not a fund-grade backtest."
        )
        with st.expander("Methodology & known simplifications"):
            st.markdown("""
- **Market cap** uses *today's* value as a stand-in for every historical day
  (free historical market-cap data isn't available), so a stock's mega-cap
  status may have differed in the past.
- **Ambiguous days:** if a stock's target *and* stop were both touched in the
  same session, the stop is assumed to have hit first — the conservative
  read, since daily OHLC can't reveal the actual intraday order.
- **No slippage, commissions, or position sizing.** Every signal is treated
  as an independent, fully-sized trade with a clean fill at the target/stop
  price.
- **No overlap/capital constraints.** The equity curve assumes you could take
  every signal on every day, even multiple at once.
""")
