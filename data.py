"""
data.py — downloads price history for the ticker universe plus SPY and VIX.
This is the only file that talks to the internet. If you ever switch data
providers (Polygon, Alpaca, Tiingo), only this file changes.
"""

import pandas as pd
import yfinance as yf


def load_universe(path: str = "universe.txt") -> list[str]:
    """Read ticker symbols from a text file, one per line. '#' starts a comment."""
    tickers = []
    with open(path) as f:
        for line in f:
            symbol = line.split("#")[0].strip().upper()
            if symbol:
                tickers.append(symbol)
    return tickers


def _extract_ticker_frame(batch: pd.DataFrame, ticker: str) -> pd.DataFrame | None:
    """Pull one ticker's OHLCV out of a yfinance batch download."""
    try:
        df = batch[ticker].dropna(how="all")
    except KeyError:
        return None
    df = df.dropna()
    return df if len(df) >= 60 else None  # need enough history for MA50/ATR


def fetch_history(tickers: list[str], days: int = 120) -> dict[str, pd.DataFrame]:
    """
    Batch-download daily OHLCV for all tickers.
    Returns {ticker: DataFrame} for tickers with sufficient clean history.
    """
    batch = yf.download(
        tickers,
        period=f"{days}d",
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        threads=True,
        progress=False,
    )
    histories = {}
    for t in tickers:
        df = _extract_ticker_frame(batch, t)
        if df is not None:
            histories[t] = df
    return histories


def fetch_market_context(days: int = 120) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Download SPY (market trend) and VIX (volatility regime)."""
    spy = yf.download("SPY", period=f"{days}d", interval="1d",
                      auto_adjust=True, progress=False)
    vix = yf.download("^VIX", period=f"{days}d", interval="1d", progress=False)
    # yfinance sometimes returns MultiIndex columns even for single tickers
    for frame in (spy, vix):
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = frame.columns.get_level_values(0)
    return spy, vix


def fetch_next_earnings_date(ticker: str):
    """
    Return the next earnings date for a ticker, or None if unavailable.
    Slow (one HTTP call per ticker) — only call this on the shortlist.
    """
    try:
        cal = yf.Ticker(ticker).calendar
        if isinstance(cal, dict):
            dates = cal.get("Earnings Date")
            if dates:
                return pd.Timestamp(dates[0])
        elif cal is not None and not cal.empty:
            return pd.Timestamp(cal.loc["Earnings Date"].iloc[0])
    except Exception:
        pass
    return None
