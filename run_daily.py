"""
run_daily.py — the entry point. Run after market close (~4:30 PM ET):

    python run_daily.py

Fetches data, runs the filter chain, prints the watchlist, and saves it
to watchlist_YYYY-MM-DD.csv with a pre-computed target and stop for
every flagged ticker.
"""

from datetime import date, timedelta

import pandas as pd

import config as C
from data import (
    fetch_history,
    fetch_market_cap,
    fetch_market_context,
    fetch_next_earnings_date,
    load_universe,
)
from screener import run_screen


def run_pipeline(progress=lambda msg: None) -> dict:
    """
    Run the full pipeline and return a structured result instead of printing.
    `progress(msg)` is called with a short status string at each stage, so
    callers (CLI, web UI) can surface progress however they like.

    Returns a dict with:
      date, universe_count, clean_count, regime_ok, regime_reasons,
      funnel, skipped_earnings, results_df (DataFrame or None), watchlist_path
    """
    today = date.today().isoformat()

    progress("Loading universe...")
    tickers = load_universe()

    progress(f"Fetching price history for {len(tickers)} tickers (this takes a minute)...")
    histories = fetch_history(tickers, C.LOOKBACK_DAYS)

    progress("Fetching SPY and VIX for the regime check...")
    spy, vix = fetch_market_context(C.LOOKBACK_DAYS)

    if C.MIN_MARKET_CAP > 0:
        progress(f"Checking market caps (mega-cap only, >= ${C.MIN_MARKET_CAP/1e9:g}B)...")
    results, reasons, funnel, scanned = run_screen(
        histories, spy, vix,
        market_cap_fetcher=fetch_market_cap if C.MIN_MARKET_CAP > 0 else None,
    )

    scanned_df = None
    if scanned:
        scanned_df = pd.DataFrame(scanned)[
            ["ticker", "price", "prev_close", "change", "change_pct",
             "day_low", "day_high"]
        ].round(2)

    out = {
        "date": today,
        "universe_count": len(tickers),
        "clean_count": len(histories),
        "regime_ok": results is not None,
        "regime_reasons": reasons,
        "funnel": funnel,
        "scanned_df": scanned_df,
        "skipped_earnings": [],
        "results_df": None,
        "watchlist_path": None,
    }

    if results is None:
        return out

    progress("Checking earnings dates on finalists...")
    kept = []
    for m in results:
        if C.EXCLUDE_EARNINGS_WITHIN_DAYS > 0:
            cutoff = pd.Timestamp(date.today() + timedelta(days=C.EXCLUDE_EARNINGS_WITHIN_DAYS))
            earnings = fetch_next_earnings_date(m["ticker"])
            if earnings is not None and pd.Timestamp(date.today()) <= earnings <= cutoff:
                out["skipped_earnings"].append((m["ticker"], str(earnings.date())))
                continue
        kept.append(m)

    if not kept:
        return out

    df = pd.DataFrame(kept)[
        ["ticker", "score", "price", "atr_pct", "volume_ratio",
         "dist_high20", "rsi", "ret20"]
    ].round(2)

    # The trade plan, decided now — not in the heat of the moment.
    df["target"] = (df["price"] * (1 + C.TARGET_PCT / 100)).round(2)
    df["stop"] = (df["price"] * (1 - C.STOP_PCT / 100)).round(2)

    out_path = f"watchlist_{today}.csv"
    df.to_csv(out_path, index=False)

    out["results_df"] = df
    out["watchlist_path"] = out_path
    return out


def main() -> None:
    print(f"=== Daily 1% Screener — {date.today().isoformat()} ===\n")

    result = run_pipeline(progress=lambda msg: print(msg))
    print(f"  {result['clean_count']} / {result['universe_count']} tickers with clean data")

    if not result["regime_ok"]:
        print(f"\nNO-TRADE DAY — regime filter veto:")
        for r in result["regime_reasons"]:
            print(f"  - {r}")
        print("\nThis is the tool working, not failing. Sit today out.")
        return

    f = result["funnel"]
    for ticker, edate in result["skipped_earnings"]:
        print(f"  (skipping {ticker}: earnings on {edate})")
    print(f"\nFilter funnel: {f['input']} in -> "
          f"{f['universe']} passed universe -> "
          f"{f['mega_cap']} passed mega-cap -> "
          f"{f['setup']} passed setup -> "
          f"top {0 if result['results_df'] is None else len(result['results_df'])} kept\n")

    if result["results_df"] is None:
        print("No stocks passed all filters today. Also a valid outcome.")
        if result["scanned_df"] is not None:
            print(f"\nMega-cap stocks scanned ({len(result['scanned_df'])}):")
            print(result["scanned_df"].to_string(index=False))
        return

    df = result["results_df"]
    print(df.to_string(index=False))
    print(f"\nSaved to {result['watchlist_path']}")
    print(f"Trade plan per ticker: target +{C.TARGET_PCT}%, stop -{C.STOP_PCT}%, "
          f"time-stop at end of day if neither hits.")


if __name__ == "__main__":
    main()
