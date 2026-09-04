# Daily 1% Screener

A stock screener that runs after market close and flags up to 10 liquid stocks
whose structure makes a +1% move plausible for the next session. Each pick comes
with a pre-computed profit target (+1%) and stop (-0.6%).

**What it does:** flags candidates and enforces a written trade plan.
**What it doesn't do:** guarantee profits, place trades, or replace judgment.

## Files

| File | What it is |
|---|---|
| `config.py` | Every threshold, in one place. Tune here, never in the logic. |
| `data.py` | Downloads prices (yfinance). The only file that touches the internet. |
| `indicators.py` | ATR%, RSI, moving averages, volume ratio, breakout distance. |
| `screener.py` | The filter chain: regime -> universe -> setup -> score. |
| `run_daily.py` | The entry point. Run this. |
| `universe.txt` | The stocks to scan (~80 starter names; expand freely). |
| `test_pipeline.py` | Offline self-test with synthetic data. Run any time. |

## Setup (one time)

Requires Python 3.10+.

```bash
cd stock-screener
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install yfinance pandas numpy
```

## Verify the logic (no internet needed)

```bash
python test_pipeline.py           # expect: 13 passed, 0 failed
```

## Run the screener (after 4:30 PM ET on a trading day)

```bash
python run_daily.py
```

Three possible outcomes, all correct behavior:

1. **A watchlist** — printed and saved as `watchlist_YYYY-MM-DD.csv`, ranked by
   score, with target and stop prices per ticker.
2. **"NO-TRADE DAY"** — the regime filter vetoed the day (SPY below its 20-day
   MA, or VIX outside 12-28). The tool telling you to sit out is it working.
3. **"No stocks passed"** — regime was fine but nothing met the setup criteria.

## If you use Claude Code

Open this folder in Claude Code and paste:

> Set up a Python virtual environment in this folder, install yfinance, pandas
> and numpy, run test_pipeline.py to confirm 13 tests pass, then run
> run_daily.py and help me interpret the output. If anything errors, fix it.

## Tuning

Everything lives in `config.py`. The trade-off that matters most:
`TARGET_PCT` vs `STOP_PCT`. At 1.0/0.6 the reward-to-risk is 1:1.67, so the
system breaks even around a 40% win rate before costs. Tighter stops need
lower win rates but get hit more often.

If the screener returns very few stocks for many days in a row (in a calm bull
market), the usual first loosening steps are `MIN_VOLUME_RATIO` (1.3 -> 1.2)
or `MAX_DIST_FROM_HIGH20` (2.0 -> 3.0). Change one thing at a time.

## Before trading real money — the gate

1. **Backtest** the filter chain over 2-3 years including down markets
   (not built yet — a natural next step).
2. **Paper trade** the live list for 4-8 weeks in a simulated account.
3. Only then go live, small, risking a fixed 0.5-1% of the account per trade,
   sized from the stop distance.

## Honest limitations

- Free yfinance data is end-of-day and occasionally messy. Fine for this
  design; not fine for intraday execution decisions.
- Expect 40-55% of flagged trades to stop out even in a good system. The edge,
  if there is one, is the reward/risk asymmetry across many trades — proven by
  backtest, not assumed.
- Filter performance decays. Re-validate quarterly.
- Short-term gains are taxed as ordinary income, which meaningfully reduces
  net compounding versus the clean math.
