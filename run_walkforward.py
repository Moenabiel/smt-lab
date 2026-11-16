"""Walk-forward test: optimise on 6 months, trade the next unseen month, roll forward, stitch the unseen months.

Example:
    python run_walkforward.py --a data/NQ_1m.parquet --b data/ES_1m.parquet --tf 5min
    python run_walkforward.py --quick      # smaller parameter grid, much faster
"""
import argparse
from pathlib import Path

import numpy as np

from smt_lab.cli import add_common_args, build_settings, synthetic_banner
from smt_lab.data import describe, load_pair
from smt_lab.metrics import format_report, plot_equity
from smt_lab.walkforward import DEFAULT_GRID, QUICK_GRID, walk_forward


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_args(ap)
    ap.add_argument("--train-months", type=int, default=6)
    ap.add_argument("--test-months", type=int, default=1)
    ap.add_argument("--min-trades", type=int, default=30, help="a parameter set needs this many train trades to qualify")
    ap.add_argument("--quick", action="store_true", help="use a tiny parameter grid")
    args = ap.parse_args()
    p, costs, acct = build_settings(args)

    df = load_pair(args.a, args.b, args.tf, args.start, args.end)
    print(synthetic_banner(args.a, args.b) + describe(df) + "\n")
    grid = QUICK_GRID if args.quick else DEFAULT_GRID
    print(f"grid: {grid}\n")

    oos, log = walk_forward(df, p, costs, acct, args.trade_symbol, grid, args.train_months,
                            args.test_months, args.min_trades)
    print()
    print(format_report(oos, acct.equity, "OUT-OF-SAMPLE (stitched test months only)"))
    if len(log):
        traded = log.dropna(subset=["oos_avg_r"])
        if len(traded):
            print(f"\nmean in-sample avg R {np.nanmean(traded['is_avg_r']):+.3f}  vs  "
                  f"mean out-of-sample avg R {np.nanmean(traded['oos_avg_r']):+.3f}   "
                  "<- the gap is how much optimisation flattered the strategy")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    oos.to_csv(out / "wf_oos_trades.csv", index=False)
    log.to_csv(out / "wf_windows.csv", index=False)
    plot_equity(oos, acct.equity, out / "wf_equity.png", "Walk-forward OUT-OF-SAMPLE equity")
    print(f"\nsaved wf_oos_trades.csv, wf_windows.csv, wf_equity.png in {out}/")


if __name__ == "__main__":
    main()
