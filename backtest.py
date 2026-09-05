"""
backtest.py — walk-forward backtest of the filter chain over historical data.

Re-runs the exact same screen (screener.run_screen) on each historical
trading day using only data available up to that day, then simulates the
next-session trade plan (target / stop / time-stop) against that day's
actual high/low/close. No network calls happen inside the day-by-day loop
— price history and market caps are fetched once up front.

Known simplifications (illustrative backtest, not a production-grade one):
  - Market cap uses TODAY's value as a stand-in for every historical day,
    since free historical market-cap data isn't available. A stock's
    mega-cap status may have been different in the past.
  - If both target and stop are touched within the same session, the stop
    is assumed to have hit first (the conservative case) — daily OHLC
    can't reveal the actual intraday order of events.
  - No slippage, commissions, or position-sizing/capital constraints.
    Every signal is treated as an independent, fully-sized trade.
"""

import pandas as pd

import config as C
from data import fetch_history, fetch_market_cap, fetch_market_context, load_universe
from screener import run_screen


def run_backtest(years: float = 2.0, progress=lambda msg: None) -> pd.DataFrame:
    """Returns a DataFrame of individual trades, one row per (date, ticker) signal."""
    tickers = load_universe()
    total_days = int(years * 365) + C.LOOKBACK_DAYS + 30

    progress(f"Fetching {years:g} years of price history for {len(tickers)} tickers...")
    histories = fetch_history(tickers, total_days)

    progress("Fetching SPY and VIX history for the regime check...")
    spy, vix = fetch_market_context(total_days)

    market_caps = {}
    if C.MIN_MARKET_CAP > 0:
        progress("Fetching current market caps (used as a proxy for the whole window)...")
        for t in histories:
            market_caps[t] = fetch_market_cap(t)

    dates = spy.index
    start_pos = C.LOOKBACK_DAYS
    if start_pos >= len(dates) - 1:
        progress("Not enough history for the requested window.")
        return pd.DataFrame()

    backtest_dates = dates[start_pos:-1]  # need a following day to simulate the trade
    trades = []
    market_cap_fetcher = (lambda tk: market_caps.get(tk)) if C.MIN_MARKET_CAP > 0 else None

    for i, day in enumerate(backtest_dates):
        if i % 40 == 0:
            progress(f"Backtesting... day {i + 1}/{len(backtest_dates)} ({day.date()})")

        day_histories = {}
        for t, df in histories.items():
            sliced = df.loc[:day]
            if len(sliced) >= 60:
                day_histories[t] = sliced

        spy_slice = spy.loc[:day]
        vix_slice = vix.loc[:day]
        if len(spy_slice) < 21:
            continue

        results, _, _, _ = run_screen(
            day_histories, spy_slice, vix_slice,
            market_cap_fetcher=market_cap_fetcher,
        )
        if not results:
            continue

        next_pos = dates.get_loc(day) + 1
        if next_pos >= len(dates):
            continue
        next_day = dates[next_pos]

        for r in results:
            ticker = r["ticker"]
            full_df = histories.get(ticker)
            if full_df is None or next_day not in full_df.index:
                continue

            entry = r["price"]
            target = entry * (1 + C.TARGET_PCT / 100)
            stop = entry * (1 - C.STOP_PCT / 100)
            nxt = full_df.loc[next_day]
            hi, lo, cl = float(nxt["High"]), float(nxt["Low"]), float(nxt["Close"])

            hit_target = hi >= target
            hit_stop = lo <= stop
            if hit_stop:
                exit_price = stop
                outcome = "stop (both hit — worst-case assumed)" if hit_target else "stop"
            elif hit_target:
                exit_price = target
                outcome = "target"
            else:
                exit_price = cl
                outcome = "time-stop"

            trades.append({
                "date": day.date(),
                "ticker": ticker,
                "score": round(r["score"], 2),
                "entry": round(entry, 2),
                "target": round(target, 2),
                "stop": round(stop, 2),
                "exit": round(exit_price, 2),
                "outcome": outcome,
                "return_pct": round((exit_price / entry - 1) * 100, 3),
                # Signal-time metrics, kept for diagnosing what actually
                # predicts a winning trade vs. a stopped-out one.
                "atr_pct": round(r["atr_pct"], 2),
                "volume_ratio": round(r["volume_ratio"], 2),
                "dist_high20": round(r["dist_high20"], 2),
                "rsi": round(r["rsi"], 1),
                "ret20": round(r["ret20"], 2),
                "dollar_volume": round(r["dollar_volume"], 0),
            })

    progress("Backtest complete.")
    return pd.DataFrame(trades)


def summarize(trades: pd.DataFrame) -> dict:
    """Aggregate stats plus a simple equal-weighted daily equity curve."""
    if trades.empty:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "avg_return_pct": 0.0,
            "target_hits": 0,
            "stop_hits": 0,
            "time_stops": 0,
            "best_trade": None,
            "worst_trade": None,
            "cumulative_return_pct": 0.0,
            "equity_curve": pd.Series(dtype=float),
        }

    wins = int((trades["return_pct"] > 0).sum())
    target_hits = int(trades["outcome"].str.startswith("target").sum())
    stop_hits = int(trades["outcome"].str.startswith("stop").sum())
    time_stops = int((trades["outcome"] == "time-stop").sum())

    daily_avg_return = trades.groupby("date")["return_pct"].mean() / 100
    equity_curve = (1 + daily_avg_return).cumprod() - 1

    return {
        "total_trades": len(trades),
        "win_rate": 100 * wins / len(trades),
        "avg_return_pct": float(trades["return_pct"].mean()),
        "target_hits": target_hits,
        "stop_hits": stop_hits,
        "time_stops": time_stops,
        "best_trade": trades.loc[trades["return_pct"].idxmax()].to_dict(),
        "worst_trade": trades.loc[trades["return_pct"].idxmin()].to_dict(),
        "cumulative_return_pct": 100 * equity_curve.iloc[-1] if len(equity_curve) else 0.0,
        "equity_curve": equity_curve,
    }
