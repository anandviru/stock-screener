"""
test_pipeline.py — validates the filter chain with synthetic data (no internet).
Run: python test_pipeline.py
Builds fake stocks with known personalities and checks the screener
keeps/rejects the right ones, and that the regime veto works.
"""

import numpy as np
import pandas as pd

import config as C
from indicators import compute_metrics
from screener import check_regime, run_screen


def make_stock(days=120, start=100.0, drift=0.001, vol=0.02,
               vol_surge=1.0, base_volume=2_000_000, seed=0):
    """Generate synthetic OHLCV with a given trend (drift) and volatility."""
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, vol, days)
    close = start * np.cumprod(1 + rets)
    high = close * (1 + np.abs(rng.normal(0, vol / 2, days)))
    low = close * (1 - np.abs(rng.normal(0, vol / 2, days)))
    open_ = np.roll(close, 1)
    open_[0] = start
    volume = rng.integers(int(base_volume * 0.7), int(base_volume * 1.3), days).astype(float)
    volume[-1] *= vol_surge  # today's volume surge, if any
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=idx,
    )


def make_vix(level=18.0, days=120):
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)
    return pd.DataFrame({"Close": np.full(days, level)}, index=idx)


def run():
    passed, failed = 0, 0

    def check(name, condition):
        nonlocal passed, failed
        status = "PASS" if condition else "FAIL"
        if condition:
            passed += 1
        else:
            failed += 1
        print(f"  [{status}] {name}")

    print("1. Indicator sanity on a trending stock:")
    trending = make_stock(drift=0.004, vol=0.018, vol_surge=1.8, seed=1)
    m = compute_metrics(trending)
    check("price above MA20 in an uptrend", m["price"] > m["ma20"])
    check("ATR% in a sane range (0.5–10)", 0.5 < m["atr_pct"] < 10)
    check("volume ratio reflects surge (>1.3)", m["volume_ratio"] > 1.3)
    check("RSI within 0–100", 0 <= m["rsi"] <= 100)

    print("\n2. Regime veto — bear market:")
    spy_bear = make_stock(drift=-0.004, vol=0.012, seed=2)
    ok, reasons = check_regime(spy_bear, make_vix(18))
    check("downtrending SPY vetoes the day", not ok and len(reasons) > 0)

    print("\n3. Regime veto — VIX too high:")
    spy_bull = make_stock(drift=0.003, vol=0.010, seed=3)
    ok, reasons = check_regime(spy_bull, make_vix(35))
    check("VIX 35 vetoes the day", not ok)

    print("\n4. Regime pass — calm bull market:")
    ok, reasons = check_regime(spy_bull, make_vix(18))
    check("uptrending SPY + VIX 18 allows trading", ok)

    print("\n5. Full screen keeps the right stocks:")
    histories = {
        # Should PASS: uptrend, decent vol, volume surge, near highs
        "GOODMO": make_stock(drift=0.004, vol=0.016, vol_surge=1.8,
                             base_volume=5_000_000, seed=10),
        # Should FAIL setup: downtrend
        "DOWNTR": make_stock(drift=-0.004, vol=0.016, vol_surge=1.8,
                             base_volume=5_000_000, seed=11),
        # Should FAIL universe: too quiet (ATR% below minimum)
        "SLEEPY": make_stock(drift=0.001, vol=0.004, vol_surge=1.8,
                             base_volume=5_000_000, seed=12),
        # Should FAIL universe: illiquid (tiny dollar volume)
        "ILLIQD": make_stock(drift=0.004, vol=0.016, vol_surge=1.8,
                             base_volume=20_000, seed=13),
        # Should FAIL setup: no volume surge
        "NOVOLM": make_stock(drift=0.004, vol=0.016, vol_surge=0.9,
                             base_volume=5_000_000, seed=14),
    }
    results, reasons, funnel, scanned = run_screen(histories, spy_bull, make_vix(18))
    kept = {r["ticker"] for r in (results or [])}
    print(f"  funnel: {funnel}, kept: {kept or '{}'}")
    check("trending stock with surge is kept", "GOODMO" in kept)
    check("downtrending stock rejected", "DOWNTR" not in kept)
    check("low-ATR stock rejected", "SLEEPY" not in kept)
    check("illiquid stock rejected", "ILLIQD" not in kept)
    check("no-volume-surge stock rejected", "NOVOLM" not in kept)
    check("results are scored and sorted",
          all(results[i]["score"] >= results[i + 1]["score"]
              for i in range(len(results) - 1)) if results else True)

    print(f"\n{'=' * 40}\n{passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    import sys
    sys.exit(0 if run() else 1)
