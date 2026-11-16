"""Rolling walk-forward: choose parameters on N train months, then trade ONLY the next unseen test month(s).

Only the stitched out-of-sample trades count. The in-sample numbers are shown purely so you can see how much
optimisation flatters a strategy (the gap between in-sample and out-of-sample is the overfitting).
"""
from __future__ import annotations

import itertools
from dataclasses import replace

import numpy as np
import pandas as pd

from .config import INSTRUMENTS, Account, Costs, Params
from .engine import TRADE_COLS, run_backtest
from .metrics import summarize
from .signals import compute_signals

DEFAULT_GRID = {
    "lookback": [24, 48, 96],
    "div_window": [2, 3, 5],
    "rr": [1.5, 2.0, 3.0],
    "min_stop_atr": [0.3, 0.6],
}
QUICK_GRID = {"lookback": [48, 96], "rr": [1.5, 2.5]}


def _month_keys(index: pd.DatetimeIndex) -> np.ndarray:
    naive = index.tz_convert("UTC").tz_localize(None)
    return naive.year.to_numpy().astype(np.int64) * 12 + naive.month.to_numpy().astype(np.int64) - 1


def _slice(df, keys_all, keys, warmup):
    pos = np.flatnonzero(np.isin(keys_all, keys))
    first, last = int(pos[0]), int(pos[-1])
    return df.iloc[max(first - warmup, 0): last + 1], df.index[first]


def _run(df_slice, trade_from, p, costs, acct, trade_symbol):
    sig = compute_signals(df_slice, p, INSTRUMENTS[trade_symbol].tick_size)
    return run_backtest(df_slice, sig, p, costs, acct, trade_symbol, trade_from=trade_from)


def walk_forward(df, base: Params, costs: Costs, acct: Account, trade_symbol: str = "MNQ", grid=None,
                 train_months: int = 6, test_months: int = 1, min_trades: int = 30,
                 warmup_bars: int = 500, verbose: bool = True):
    """Returns (oos_trades, window_log). Selection score = in-sample t-stat of avg R (needs >= min_trades)."""
    grid = grid or DEFAULT_GRID
    keys_all = _month_keys(df.index)
    months = np.unique(keys_all)
    combos = [dict(zip(grid, vals)) for vals in itertools.product(*grid.values())]
    if len(months) < train_months + test_months:
        raise ValueError(f"need at least {train_months + test_months} months of data, have {len(months)}")

    oos, log = [], []
    for w in range(train_months, len(months) - test_months + 1, test_months):
        tr_df, tr_from = _slice(df, keys_all, months[w - train_months:w], warmup_bars)
        te_df, te_from = _slice(df, keys_all, months[w:w + test_months], warmup_bars)
        label = f"{te_from:%Y-%m}"

        best, best_score, best_stats = None, -np.inf, None
        for cd in combos:
            stats = summarize(_run(tr_df, tr_from, replace(base, **cd), costs, acct, trade_symbol), acct.equity)
            if stats["trades"] < min_trades or not np.isfinite(stats.get("t_stat", np.nan)):
                continue
            if stats["t_stat"] > best_score:
                best, best_score, best_stats = cd, stats["t_stat"], stats

        if best is None:
            log.append({"test_month": label, "chosen": "(none qualified - stood aside)", "is_trades": 0,
                        "is_avg_r": np.nan, "oos_trades": 0, "oos_avg_r": np.nan})
            if verbose:
                print(f"{label}: no parameter set reached {min_trades} train trades - no trading")
            continue

        t_oos = _run(te_df, te_from, replace(base, **best), costs, acct, trade_symbol)
        s_oos = summarize(t_oos, acct.equity)
        oos.append(t_oos)
        log.append({"test_month": label, "chosen": best, "is_trades": best_stats["trades"],
                    "is_avg_r": best_stats["avg_r"], "oos_trades": s_oos["trades"],
                    "oos_avg_r": s_oos.get("avg_r", np.nan)})
        if verbose:
            print(f"{label}: chose {best} | in-sample avgR {best_stats['avg_r']:+.2f} ({best_stats['trades']} tr)"
                  f" -> out-of-sample avgR {s_oos.get('avg_r', float('nan')):+.2f} ({s_oos['trades']} tr)")

    oos_all = pd.concat(oos, ignore_index=True) if oos else pd.DataFrame(columns=TRADE_COLS)
    return oos_all, pd.DataFrame(log)
