"""Reality check: how good does this EXACT pipeline look on data that contains no edge at all?

Searching a parameter grid and stitching a few test months will produce flattering results from pure noise.
This script repeats your walk-forward on many random-walk datasets (same length, same grid, same settings)
and shows the spread of out-of-sample results that luck alone produces. Your real result only means something
if it beats that spread by a wide margin.

    python run_walkforward.py                    # note the out-of-sample t-stat it prints, e.g. +2.4
    python noise_check.py --days 500 --my-t 2.4  # same grid flags as your real run (--quick, --lookback ...)

--days should roughly match the span of your real data in business days (~21 per month).
"""
import argparse

import numpy as np

from make_synthetic import make
from smt_lab.cli import add_common_args, build_settings
from smt_lab.data import build_pair
from smt_lab.metrics import summarize
from smt_lab.walkforward import DEFAULT_GRID, QUICK_GRID, walk_forward


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_args(ap)
    ap.add_argument("--runs", type=int, default=20, help="number of random datasets (more = steadier estimate)")
    ap.add_argument("--days", type=int, default=330, help="business days per random dataset")
    ap.add_argument("--seed0", type=int, default=1000)
    ap.add_argument("--train-months", type=int, default=6)
    ap.add_argument("--test-months", type=int, default=1)
    ap.add_argument("--min-trades", type=int, default=30)
    ap.add_argument("--quick", action="store_true", help="MUST match how you ran run_walkforward.py")
    ap.add_argument("--my-t", type=float, help="your real out-of-sample t-stat, to get an empirical p-value")
    args = ap.parse_args()
    p, costs, acct = build_settings(args)
    grid = QUICK_GRID if args.quick else DEFAULT_GRID

    print(f"{args.runs} random datasets x {args.days} business days | grid {grid}\n")
    res = []
    for i in range(args.runs):
        a, b = make(args.days, args.seed0 + i)
        df = build_pair(a, b, args.tf)
        oos, _ = walk_forward(df, p, costs, acct, args.trade_symbol, grid, args.train_months,
                              args.test_months, args.min_trades, verbose=False)
        s = summarize(oos, acct.equity)
        if s["trades"] < 10:
            continue
        res.append((s["t_stat"], s["avg_r"], s["profit_factor"], s["trades"]))
        print(f"run {i + 1:2d}: {s['trades']:4d} OOS trades | avg R {s['avg_r']:+.3f} | "
              f"t {s['t_stat']:+.2f} | PF {s['profit_factor']:.2f}")

    if not res:
        raise SystemExit("no usable runs (too little data per run?)")
    t, r, pf, n = (np.array(x, float) for x in zip(*res))
    print("\n===== what pure NOISE produces through this pipeline =====")
    print(f"out-of-sample t-stat : median {np.median(t):+.2f} | 90th pct {np.percentile(t, 90):+.2f} | "
          f"95th pct {np.percentile(t, 95):+.2f} | max {t.max():+.2f}")
    print(f"out-of-sample avg R  : median {np.median(r):+.3f} | 95th pct {np.percentile(r, 95):+.3f}")
    print(f"profit factor        : median {np.median(pf):.2f} | 95th pct {np.percentile(pf, 95):.2f}")
    print(f"runs with PF > 1.3 on pure noise: {(pf > 1.3).sum()}/{len(pf)}")
    if args.my_t is not None:
        p_emp = (np.sum(t >= args.my_t) + 1) / (len(t) + 1)
        print(f"\nyour t-stat {args.my_t:+.2f}: noise matched or beat it in {np.sum(t >= args.my_t)}/{len(t)} runs "
              f"(empirical p ~ {p_emp:.2f})")
        print("-> " + ("NOT distinguishable from luck." if p_emp > 0.05 else
                       "better than most noise, but treat as 'worth a paper-trading test', not proof."))
    print("\nCaveat: synthetic noise only approximates real NQ/ES volatility and microstructure.")


if __name__ == "__main__":
    main()
