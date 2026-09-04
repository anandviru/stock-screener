"""
config.py — every tunable threshold in one place.
Change values here; never hard-code numbers in the logic files.
"""

# --- Universe filters (can this stock even move 1% cleanly?) ---
MIN_PRICE = 15.0                      # dollars; avoids spread-heavy cheap stocks
MIN_AVG_DOLLAR_VOLUME = 30_000_000    # 20-day average daily dollar volume
MIN_ATR_PCT = 2.0                     # ATR(14) as % of price; stock must "breathe" 2x target
MAX_ATR_PCT = 8.0                     # too volatile = stops get blown through

# --- Setup filters, momentum flavor (is the move likely soon?) ---
MIN_VOLUME_RATIO = 1.3                # today's volume / 20-day average volume
MAX_DIST_FROM_HIGH20 = 2.0            # % below the 20-day high (breakout proximity)
MIN_RELATIVE_STRENGTH = 0.0           # stock 20d return minus SPY 20d return, in %

# --- Mean-reversion alternative (enable ONE style at a time) ---
USE_MEAN_REVERSION = False
RSI_OVERSOLD = 30

# --- Regime filters (should we trade at all today?) ---
SPY_MUST_BE_ABOVE_MA20 = True
VIX_MIN = 12.0
VIX_MAX = 28.0

# --- Trade plan written into the output ---
TARGET_PCT = 1.0                      # profit target, %
STOP_PCT = 0.6                        # stop loss, % (1:1.67 reward-to-risk)

# --- Earnings exclusion ---
EXCLUDE_EARNINGS_WITHIN_DAYS = 3      # skip stocks reporting soon (checked on finalists)

# --- Output ---
TOP_N = 10                            # max stocks on the daily watchlist
LOOKBACK_DAYS = 120                   # history needed for indicators
