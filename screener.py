"""
screener.py — the filter chain: regime -> universe -> setup -> score.
Filters run cheapest-first. The regime check can veto the entire day:
a "no-trade day" is valid, important output, not a failure.
"""

from typing import Callable, Optional

import pandas as pd

import config as C
from indicators import compute_metrics


def check_regime(spy: pd.DataFrame, vix: pd.DataFrame) -> tuple[bool, list[str]]:
    """Should the tool trade at all today?"""
    reasons = []
    spy_close = float(spy["Close"].iloc[-1])
    spy_ma20 = float(spy["Close"].rolling(20).mean().iloc[-1])
    vix_now = float(vix["Close"].iloc[-1])

    if C.SPY_MUST_BE_ABOVE_MA20 and spy_close < spy_ma20:
        reasons.append(f"SPY {spy_close:.2f} below its 20-day MA {spy_ma20:.2f}")
    if not (C.VIX_MIN <= vix_now <= C.VIX_MAX):
        reasons.append(f"VIX {vix_now:.1f} outside [{C.VIX_MIN}, {C.VIX_MAX}]")

    return len(reasons) == 0, reasons


def passes_universe(m: dict) -> bool:
    """Can this stock even deliver a clean 1% move?"""
    return (
        m["price"] >= C.MIN_PRICE
        and m["dollar_volume"] >= C.MIN_AVG_DOLLAR_VOLUME
        and C.MIN_ATR_PCT <= m["atr_pct"] <= C.MAX_ATR_PCT
    )


def passes_mega_cap(market_cap: float | None) -> bool:
    """Is this stock large enough to count as mega-cap?"""
    return market_cap is not None and market_cap >= C.MIN_MARKET_CAP


def passes_setup(m: dict, spy_ret20: float) -> bool:
    """Is the move likely soon? Momentum by default, mean-reversion optional."""
    if C.USE_MEAN_REVERSION:
        return m["rsi"] <= C.RSI_OVERSOLD and m["price"] > m["ma50"]
    return (
        m["price"] > m["ma20"]
        and m["price"] > m["ma50"]
        and m["volume_ratio"] >= C.MIN_VOLUME_RATIO
        and m["dist_high20"] <= C.MAX_DIST_FROM_HIGH20
        and (m["ret20"] - spy_ret20) >= C.MIN_RELATIVE_STRENGTH
        and m["rsi"] <= C.MAX_RSI
    )


def score(m: dict) -> float:
    """Rank survivors: reward volume surge, breakout proximity, healthy ATR."""
    return (
        min(m["volume_ratio"], 3.0) * 2.0
        + (C.MAX_DIST_FROM_HIGH20 - m["dist_high20"])
        + min(m["atr_pct"], 4.0)
    )


def run_screen(
    histories: dict[str, pd.DataFrame],
    spy: pd.DataFrame,
    vix: pd.DataFrame,
    market_cap_fetcher: Optional[Callable[[str], Optional[float]]] = None,
) -> tuple[list[dict] | None, list[str], dict[str, int], dict[str, list[dict]]]:
    """
    Apply the full chain. Returns (results, reasons, funnel, stages):
      results: top-N metric dicts, or None on a no-trade day
      reasons: why the day was vetoed (empty otherwise)
      funnel:  how many tickers survived each stage (for tuning)
      stages:  metric dicts for every ticker at each stage boundary, keyed
        "all" (every ticker with clean data), "universe" (passed the cheap
        universe filter), "mega_cap" (passed the mega-cap filter too, or
        identical to "universe" when that filter is off) — lets callers
        show the full list at any stage, not just the final watchlist.

    market_cap_fetcher: optional ticker -> market_cap lookup, called only on
      tickers that already passed the cheap universe filters. Left as None
      (mega-cap filter skipped) by default so this stays network-free —
      test_pipeline.py relies on that. run_daily.py wires in the real
      fetch_market_cap from data.py when C.MIN_MARKET_CAP > 0.
    """
    funnel = {"input": len(histories), "universe": 0, "mega_cap": 0, "setup": 0}
    stages: dict[str, list[dict]] = {"all": [], "universe": [], "mega_cap": []}

    regime_ok, reasons = check_regime(spy, vix)
    if not regime_ok:
        return None, reasons, funnel, stages

    spy_ret20 = float((spy["Close"].iloc[-1] / spy["Close"].iloc[-21] - 1) * 100)

    survivors = []
    for ticker, df in histories.items():
        m = compute_metrics(df)
        entry = dict(m)
        entry["ticker"] = ticker
        stages["all"].append(entry)

        if not passes_universe(m):
            continue
        funnel["universe"] += 1
        stages["universe"].append(dict(entry))

        if market_cap_fetcher is not None:
            m["market_cap"] = market_cap_fetcher(ticker)
            if not passes_mega_cap(m["market_cap"]):
                continue
        funnel["mega_cap"] += 1
        mega_entry = dict(m)
        mega_entry["ticker"] = ticker
        stages["mega_cap"].append(mega_entry)

        if not passes_setup(m, spy_ret20):
            continue
        funnel["setup"] += 1
        m["ticker"] = ticker
        m["score"] = score(m)
        survivors.append(m)

    survivors.sort(key=lambda r: r["score"], reverse=True)
    for rows in stages.values():
        rows.sort(key=lambda r: r["ticker"])
    return survivors[: C.TOP_N], [], funnel, stages
