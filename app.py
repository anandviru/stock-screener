"""
app.py — Streamlit web UI for the Daily 1% Screener.

Run locally with:
    streamlit run app.py

Wraps run_daily.run_pipeline() — the same logic the CLI uses — with a
browser dashboard: a run button, regime status, filter funnel, a styled
watchlist table, and a browsable history of past runs.
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

import config as C
from run_daily import run_pipeline

st.set_page_config(
    page_title="Daily 1% Screener",
    page_icon="📈",
    layout="wide",
)

# ---------- style ----------
st.markdown("""
<style>
    .block-container { padding-top: 2rem; max-width: 1100px; }
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
</style>
""", unsafe_allow_html=True)

st.title("📈 Daily 1% Screener")
st.caption(
    "Flags up to 10 liquid stocks whose structure makes a +1% move plausible "
    "for the next session, each with a pre-computed target and stop. "
    "It flags candidates and enforces a written trade plan — it doesn't "
    "guarantee profits, place trades, or replace judgment."
)

if "result" not in st.session_state:
    st.session_state.result = None

# ---------- sidebar ----------
with st.sidebar:
    st.header("Run")
    run_clicked = st.button("▶ Run screener now", type="primary", use_container_width=True)

    st.divider()
    st.header("Current thresholds")
    st.caption("Edit `config.py` to change these, then re-run.")
    st.markdown(f"""
- **Price** ≥ ${C.MIN_PRICE:g}
- **Avg $ volume** ≥ ${C.MIN_AVG_DOLLAR_VOLUME/1e6:g}M
- **ATR%** {C.MIN_ATR_PCT:g}–{C.MAX_ATR_PCT:g}%
- **Volume ratio** ≥ {C.MIN_VOLUME_RATIO:g}x
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

# ---------- run pipeline ----------
if run_clicked:
    progress_area = st.empty()
    with st.spinner("Running..."):
        def show(msg):
            progress_area.info(msg)
        st.session_state.result = run_pipeline(progress=show)
    progress_area.empty()

result = st.session_state.result

# ---------- render latest result ----------
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
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Universe scanned", f["input"])
        c2.metric("Passed universe filter", f["universe"])
        c3.metric("Passed setup filter", f["setup"])
        c4.metric("Kept on watchlist", n_kept)

        for ticker, edate in result["skipped_earnings"]:
            st.caption(f"⏭️ Skipped {ticker} — earnings on {edate}")

        if result["results_df"] is None:
            st.markdown('<div class="empty-box">', unsafe_allow_html=True)
            st.markdown("### No stocks passed all filters today")
            st.markdown("Also a valid outcome — no forced trades on a quiet tape.")
            st.markdown('</div>', unsafe_allow_html=True)
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
    st.info("Click **Run screener now** in the sidebar to fetch today's data and screen the universe.")

# ---------- history viewer ----------
if chosen != "(none)" and os.path.exists(chosen):
    st.divider()
    st.subheader(f"📜 {chosen}")
    hist_df = pd.read_csv(chosen)
    if hist_df.empty:
        st.caption("Empty file — no stocks passed that day.")
    else:
        st.dataframe(hist_df, use_container_width=True, hide_index=True)

st.divider()
with st.expander("Honest limitations"):
    st.markdown("""
- Free yfinance data is end-of-day and occasionally messy. Fine for this
  design; not fine for intraday execution decisions.
- Expect 40-55% of flagged trades to stop out even in a good system. The edge,
  if there is one, is the reward/risk asymmetry across many trades — proven by
  backtest, not assumed.
- Filter performance decays. Re-validate quarterly.
- Short-term gains are taxed as ordinary income, which meaningfully reduces
  net compounding versus the clean math.
- **Before trading real money:** backtest the filter chain over 2-3 years,
  then paper trade the live list for 4-8 weeks. Only then go live, small.
""")
