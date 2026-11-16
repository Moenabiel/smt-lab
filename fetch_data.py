"""Download two futures symbols (default NQ and ES) and save them where run_backtest.py expects them.

DATABENTO (recommended: real CME data, years of 1-minute bars)
    PowerShell:  $env:DATABENTO_API_KEY = "your_databento_api_key_here"
    python fetch_data.py databento --start 2023-01-01 --end 2025-01-01
  It prints the exact price BEFORE downloading and asks for confirmation. 1-minute OHLCV bars are tiny next to
  tick/order-book data, so a couple of years of NQ+ES is normally cheap, but always read the estimate.
  New accounts get free credit; check https://databento.com/pricing for what applies to you today.

YFINANCE (free, no key, but only ~60 days of 5-minute bars and patchy quality - fine for a first look)
    python fetch_data.py yfinance
    python run_backtest.py --a data/NQ_5m.parquet --b data/ES_5m.parquet --tf 5min
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

from smt_lab.data import save_frame


def fetch_databento(symbols, start, end, out: Path, roll: str, ext: str, assume_yes: bool) -> None:
    try:
        import databento as db
    except ImportError:
        sys.exit("databento is not installed - run setup again (pip install databento)")
    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        sys.exit('Set your key first.  PowerShell:  $env:DATABENTO_API_KEY = "your_databento_api_key_here"   (bash: export DATABENTO_API_KEY=db-...)')

    client = db.Historical(key)
    dataset, schema = "GLBX.MDP3", "ohlcv-1m"
    cont = [f"{s}.{roll}.0" for s in symbols]            # continuous front contract, e.g. NQ.v.0 (volume roll)
    cost = client.metadata.get_cost(dataset=dataset, symbols=cont, stype_in="continuous",
                                    schema=schema, start=start, end=end)
    print(f"Databento estimate for {cont} {schema} {start} -> {end}:  ${cost:,.2f}")
    if not assume_yes and input("Download? [y/N] ").strip().lower() != "y":
        print("Cancelled - nothing downloaded, nothing charged.")
        return

    for sym, csym in zip(symbols, cont):
        store = client.timeseries.get_range(dataset=dataset, symbols=[csym], stype_in="continuous",
                                            schema=schema, start=start, end=end)
        df = store.to_df()
        keep = [c for c in ("open", "high", "low", "close", "volume", "instrument_id") if c in df.columns]
        path = out / f"{sym}_1m.{ext}"
        save_frame(df[keep], path)
        print(f"saved {path}  ({len(df):,} bars, {df.index[0]:%Y-%m-%d} -> {df.index[-1]:%Y-%m-%d})")


def fetch_yfinance(symbols, out: Path, ext: str) -> None:
    try:
        import yfinance as yf
    except ImportError:
        sys.exit("yfinance is not installed - run setup again (pip install yfinance)")
    for sym in symbols:
        df = yf.download(f"{sym}=F", period="60d", interval="5m", auto_adjust=False, progress=False)
        if df is None or df.empty:
            sys.exit(f"yfinance returned nothing for {sym}=F (rate limit or outage) - try again later")
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [str(c).lower() for c in df.columns]
        df = df[["open", "high", "low", "close", "volume"]].dropna()
        df.index = pd.to_datetime(df.index, utc=True)
        path = out / f"{sym}_5m.{ext}"
        save_frame(df, path)
        print(f"saved {path}  ({len(df):,} bars)")
    print("\nNote: continuous Yahoo futures are not roll-adjusted, and 60 days is far too little to conclude anything.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="provider", required=True)

    d = sub.add_parser("databento", help="CME 1-minute bars from Databento")
    d.add_argument("--start", required=True, help="YYYY-MM-DD")
    d.add_argument("--end", required=True, help="YYYY-MM-DD (exclusive)")
    d.add_argument("--roll", default="v", choices=["v", "c", "n"],
                   help="continuous contract rule: v=volume, c=calendar, n=open interest")
    d.add_argument("--yes", action="store_true", help="skip the confirmation prompt")

    sub.add_parser("yfinance", help="free ~60 days of 5-minute bars")

    for sp in (d, sub.choices["yfinance"]):
        sp.add_argument("--symbols", nargs=2, default=["NQ", "ES"], metavar=("A", "B"))
        sp.add_argument("--out", default="data")
        sp.add_argument("--ext", choices=["parquet", "csv"], default="parquet")

    args = ap.parse_args()
    out = Path(args.out)
    if args.provider == "databento":
        fetch_databento(args.symbols, args.start, args.end, out, args.roll, args.ext, args.yes)
    else:
        fetch_yfinance(args.symbols, out, args.ext)


if __name__ == "__main__":
    main()
