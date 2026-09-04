"""
indicators.py — technical indicator math.
Every function takes a DataFrame with columns: Open, High, Low, Close, Volume.
compute_metrics() returns the LATEST value of each metric (today's snapshot).
"""

import pandas as pd


def atr_pct(df: pd.DataFrame, period: int = 14) -> float:
    """Average True Range as a percentage of the closing price."""
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = true_range.rolling(period).mean()
    return float((atr / df["Close"] * 100).iloc[-1])


def rsi(df: pd.DataFrame, period: int = 14) -> float:
    """Relative Strength Index (0-100). Below ~30 is 'oversold'."""
    delta = df["Close"].diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, float("nan"))
    value = (100 - 100 / (1 + rs)).iloc[-1]
    return float(value) if pd.notna(value) else 100.0


def compute_metrics(df: pd.DataFrame) -> dict:
    """Today's snapshot of every metric the filter chain needs."""
    close = df["Close"]
    high20 = close.rolling(20).max().iloc[-1]
    return {
        "price": float(close.iloc[-1]),
        "ma20": float(close.rolling(20).mean().iloc[-1]),
        "ma50": float(close.rolling(50).mean().iloc[-1]),
        "atr_pct": atr_pct(df),
        "rsi": rsi(df),
        "volume_ratio": float(
            df["Volume"].iloc[-1] / df["Volume"].rolling(20).mean().iloc[-1]
        ),
        "dollar_volume": float(
            (close * df["Volume"]).rolling(20).mean().iloc[-1]
        ),
        "dist_high20": float((high20 - close.iloc[-1]) / high20 * 100),
        "ret20": float((close.iloc[-1] / close.iloc[-21] - 1) * 100),
    }
