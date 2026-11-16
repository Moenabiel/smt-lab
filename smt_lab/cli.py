"""Command-line plumbing shared by run_backtest.py and run_walkforward.py."""
from __future__ import annotations

import argparse
from dataclasses import replace

from .config import INSTRUMENTS, Account, Costs, Params


def add_common_args(ap: argparse.ArgumentParser) -> None:
    g = ap.add_argument_group("data")
    g.add_argument("--a", default="data/NQ_1m.parquet", help="file for instrument A (the one you trade the signal on)")
    g.add_argument("--b", default="data/ES_1m.parquet", help="file for instrument B (the divergence partner)")
    g.add_argument("--tf", default="5min", help="signal timeframe, e.g. 1min, 5min, 15min")
    g.add_argument("--start", help="YYYY-MM-DD (UTC, inclusive)")
    g.add_argument("--end", help="YYYY-MM-DD (UTC, exclusive)")
    g.add_argument("--trade-symbol", default="MNQ", choices=sorted(INSTRUMENTS), help="contract used for sizing/costs")
    g.add_argument("--out", default="results")

    s = ap.add_argument_group("strategy overrides (defaults live in smt_lab/config.py)")
    s.add_argument("--lookback", type=int)
    s.add_argument("--div-window", type=int)
    s.add_argument("--rr", type=float)
    s.add_argument("--min-stop-atr", type=float)
    s.add_argument("--max-stop-atr", type=float)
    s.add_argument("--stop-buffer-ticks", type=int)
    s.add_argument("--max-trades-per-day", type=int)
    s.add_argument("--no-rejection", action="store_true", help="count any sweep, not only sweep-and-close-back")
    s.add_argument("--sessions", help='NY-time windows, e.g. "02:00-05:00,08:30-11:00"')

    c = ap.add_argument_group("costs & account")
    c.add_argument("--commission", type=float, help="USD per contract per side")
    c.add_argument("--slippage-ticks", type=float)
    c.add_argument("--equity", type=float)
    c.add_argument("--risk-pct", type=float)


def build_settings(args):
    p, costs, acct = Params(), Costs(), Account()
    over = {
        "lookback": args.lookback, "div_window": args.div_window, "rr": args.rr,
        "min_stop_atr": args.min_stop_atr, "max_stop_atr": args.max_stop_atr,
        "stop_buffer_ticks": args.stop_buffer_ticks, "max_trades_per_day": args.max_trades_per_day,
    }
    over = {k: v for k, v in over.items() if v is not None}
    if args.no_rejection:
        over["require_rejection"] = False
    if args.sessions:
        over["sessions"] = tuple(tuple(w.strip().split("-")) for w in args.sessions.split(","))
    p = replace(p, **over)
    if args.commission is not None or args.slippage_ticks is not None:
        costs = replace(costs,
                        commission_per_side=costs.commission_per_side if args.commission is None else args.commission,
                        slippage_ticks=costs.slippage_ticks if args.slippage_ticks is None else args.slippage_ticks)
    if args.equity is not None or args.risk_pct is not None:
        acct = replace(acct,
                       equity=acct.equity if args.equity is None else args.equity,
                       risk_pct=acct.risk_pct if args.risk_pct is None else args.risk_pct)
    return p, costs, acct


def synthetic_banner(*paths) -> str:
    if any("synth" in str(p).lower() for p in paths):
        return ("\n*** SYNTHETIC RANDOM-WALK DATA: this only tests the plumbing. A correct backtest should show\n"
                "*** zero or negative edge here. Positive results on this data would mean a bug.\n")
    return ""
