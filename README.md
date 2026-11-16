# smt_lab: a local lab for testing an SMT-divergence strategy

A small, honest research setup that runs on your own PC. It does **not** print money. It tells you, as truthfully
as a backtest can, whether an SMT-divergence idea has any edge, *before* you risk real money on it. That
is the valuable part. Most strategies fail this test, and finding out here is free.

Not financial advice. This is research tooling.

## Quick start (Windows PowerShell)

```powershell
cd smt_lab
powershell -ExecutionPolicy Bypass -File .\setup.ps1          # makes .venv, installs packages, runs self-tests
.\.venv\Scripts\python.exe make_synthetic.py                  # random-walk data, no edge by construction
.\.venv\Scripts\python.exe run_backtest.py --a data\synth_NQ_1m.parquet --b data\synth_ES_1m.parquet
```

macOS/Linux: `bash setup.sh`, then the same commands with `.venv/bin/python`.

**What you should see on the synthetic data:** roughly zero or negative average R, t-stat near 0. That means the
plumbing is honest. If it ever shows a big profit on random data, there is a bug.

## Real data

**Databento** (real CME data; it shows the price and asks before charging you):

```powershell
$env:DATABENTO_API_KEY = "db-..."                              # your key from databento.com
.\.venv\Scripts\python.exe fetch_data.py databento --start 2023-01-01 --end 2025-01-01
```

**Free option** (only ~60 days of 5-minute bars, good for a first look, useless for conclusions):

```powershell
.\.venv\Scripts\python.exe fetch_data.py yfinance
.\.venv\Scripts\python.exe run_backtest.py --a data\NQ_5m.parquet --b data\ES_5m.parquet --tf 5min
```

## The workflow that keeps you honest

1. `run_walkforward.py` optimises on 6 months, then trades only the next unseen month, and repeats. Only the
   stitched unseen months count. Use `--quick` for a small grid.
2. `noise_check.py` runs the *same* pipeline on many random-walk datasets. Searching parameters on noise
   produces convincing winners, so your result only means something if it clearly beats that spread:
   `python noise_check.py --days 500 --my-t <your out-of-sample t-stat>` (match `--quick` and your other flags).
3. Paper trade it. 50+ trades, with real fills and your real costs, before any live money, and then tiny size.

Rough bar before taking a result seriously: hundreds of out-of-sample trades, a t-stat well above what noise
reaches in step 2, results that survive changing parameters by +/-30%, and a profit that survives doubling the costs
(`--commission`, `--slippage-ticks`).

## What the strategy is (smt_lab/signals.py: change it freely)

- **Level**: highest high / lowest low of the previous `lookback` bars, per instrument (A = NQ, B = ES).
- **Bearish SMT**: one instrument sweeps the high and closes back below it, while the two did *not* both sweep their
  highs within `div_window` bars. One confirmed the move, the other failed. Bullish is the mirror image on the lows.
- **Entry**: stop order beyond the signal candle's extreme on A. **Stop**: beyond the recent extreme plus a buffer.
  **Target**: `rr` x risk. Sessions, daily loss limit, max trades per day and the 15:55 ET flatten are in `config.py`.

This is one mechanical reading of SMT. Yours may differ, which is exactly why the code is meant to be edited.

## What is verified, and what is not

Verified by `tests/test_lookahead.py` (10 tests, run by setup):
- Signals and trades do not change when future bars are removed. I confirmed the test **fails** when I deliberately
  inject seven different look-ahead leaks (signal peeks, entry/stop/target peeks).
- Fill rules match hand calculations: gaps through stops and entries, stop-before-target in the same bar, end-of-day
  flatten, order expiry, costs, roll-day blocking.
- On ~10,000 trades across 60 random-walk datasets the gross average R is ~0 (+0.016 +/- 0.014) and net of costs it is
  negative (-0.036), which is correct for data with no edge.

**Not verified by me** (I could not run these here): reading/writing `.parquet` files (pyarrow was not in my test
environment; CSV was), the live Databento and yfinance downloads (written against their documented APIs), and
NautilusTrader integration (not included). If `fetch_data.py` errors, send me the message.

## Limits you should know about

- Fills are simulated from bar OHLC. If a stop and a target fall in the same bar, the stop is assumed first. Real
  queue position and tick-level behaviour are not modelled.
- `commission_per_side` in `config.py` is a placeholder. Put your broker's real all-in number there.
- Continuous futures have fake gaps at contract rolls. Days around a roll are blocked from trading when Databento's
  `instrument_id` is present. Yahoo data has no such flag.
- Sizing uses fixed equity (no compounding) so R-statistics stay comparable.

## Optional real GitHub projects (see requirements-optional.txt)

- `nautechsystems/nautilus_trader`: production engine; port a *surviving* strategy here for live execution.
- `joshyattridge/smart-money-concepts`: FVG, order blocks, BOS/CHoCH. Add as confluence filters, then re-run the noise check.
- `quantstats`, `optuna`, `duckdb` as needed.

## Files

| File | Purpose |
|---|---|
| `fetch_data.py` | download NQ/ES from Databento or yfinance |
| `make_synthetic.py` | random-walk data for smoke tests |
| `run_backtest.py` | one pass over all data (a sanity check, not proof) |
| `run_walkforward.py` | out-of-sample validation |
| `noise_check.py` | how lucky does noise get through your pipeline? |
| `smt_lab/` | config, data, signals, engine, metrics, walk-forward |
| `tests/test_lookahead.py` | look-ahead and fill-logic tests |
