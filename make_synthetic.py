"""Generate two correlated RANDOM-WALK futures series (NQ-like and ES-like) as 1-minute bars.

Purpose: prove the pipeline runs end to end and that the backtester has no look-ahead leak.
Random walks contain no edge, so a correct backtest MUST come out flat-to-negative (costs make it negative).
If a strategy "makes money" on this data, you have a bug, not an edge.
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from smt_lab.data import NY, save_frame


def _bars(p0: float, inc: np.ndarray):
    t, sub = inc.shape
    lvl = p0 * np.exp(np.cumsum(inc.reshape(-1)).reshape(t, sub))
    close = lvl[:, -1]
    open_ = np.r_[p0, close[:-1]]
    path = np.concatenate([open_[:, None], lvl], axis=1)
    rnd = lambda x: np.round(x * 4.0) / 4.0   # 0.25 tick grid
    return rnd(open_), rnd(path.max(axis=1)), rnd(path.min(axis=1)), rnd(close)


def make(days: int = 200, seed: int = 7):
    rng = np.random.default_rng(seed)
    bdays = pd.bdate_range("2023-01-02", periods=days)
    naive = pd.DatetimeIndex(np.concatenate([pd.date_range(d, periods=1440, freq="1min").values for d in bdays]))
    naive = naive[naive.hour != 17]                                  # 17:00-18:00 ET maintenance break
    idx = naive.tz_localize(NY, ambiguous="NaT", nonexistent="NaT")
    idx = idx[~idx.isna()].tz_convert("UTC")
    t, sub = len(idx), 4

    common = rng.normal(0.0, 2.4e-4, (t, sub))                       # shared factor -> high correlation
    inc_a = common + rng.normal(0.0, 1.2e-4, (t, sub))
    inc_b = 0.85 * common + rng.normal(0.0, 1.2e-4, (t, sub))        # idiosyncratic noise -> occasional divergences

    frames = []
    for p0, inc in ((15000.0, inc_a), (4500.0, inc_b)):
        o, h, l, c = _bars(p0, inc)
        vol = rng.integers(50, 2000, t)
        frames.append(pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": vol}, index=idx))
    return frames[0], frames[1]


def main() -> None:
    try:
        import pyarrow  # noqa: F401
        default_ext = "parquet"
    except ImportError:
        default_ext = "csv"
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=200, help="business days of 1-minute data (>= 190 for walk-forward)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--ext", choices=["parquet", "csv"], default=default_ext)
    ap.add_argument("--out", default="data")
    args = ap.parse_args()

    a, b = make(args.days, args.seed)
    for name, frame in (("NQ", a), ("ES", b)):
        path = f"{args.out}/synth_{name}_1m.{args.ext}"
        save_frame(frame, path)
        print(f"wrote {path}  ({len(frame):,} bars)")


if __name__ == "__main__":
    main()
