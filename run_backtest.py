"""Run one backtest of the SMT strategy.

Example (after fetch_data.py):
    python run_backtest.py --a data/NQ_1m.parquet --b data/ES_1m.parquet --tf 5min --start 2024-01-01
Smoke test (random-walk data, should NOT be profitable):
    python make_synthetic.py && python run_backtest.py --a data/synth_NQ_1m.parquet --b data/synth_ES_1m.parquet
"""
import argparse
from pathlib import Path

from smt_lab.cli import add_common_args, build_settings, synthetic_banner
from smt_lab.config import INSTRUMENTS
from smt_lab.data import describe, load_pair
from smt_lab.engine import run_backtest
from smt_lab.metrics import format_report, plot_equity
from smt_lab.signals import compute_signals


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_args(ap)
    args = ap.parse_args()
    p, costs, acct = build_settings(args)

    df = load_pair(args.a, args.b, args.tf, args.start, args.end)
    print(synthetic_banner(args.a, args.b) + describe(df))
    print(f"params: {p}\ncosts : {costs}\nrisk  : {acct.risk_pct}% of ${acct.equity:,.0f} per trade on {args.trade_symbol}\n")

    sig = compute_signals(df, p, INSTRUMENTS[args.trade_symbol].tick_size)
    print(f"raw SMT setups found: {int((sig['side'] != 0).sum())}")
    trades = run_backtest(df, sig, p, costs, acct, args.trade_symbol)
    print(format_report(trades, acct.equity, "BACKTEST (single pass over ALL data - not out-of-sample!)"))

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    trades.to_csv(out / "trades.csv", index=False)
    if plot_equity(trades, acct.equity, out / "equity.png"):
        print(f"\nsaved {out/'trades.csv'} and {out/'equity.png'}")
    print("\nREMINDER: one pass over all data with fixed params is NOT proof of anything. Use run_walkforward.py.")


if __name__ == "__main__":
    main()
