"""Correctness tests. Run:  python tests/test_lookahead.py   (or:  pytest tests)

1. signals/trades must not change when FUTURE data is removed  -> proves there is no look-ahead leak
2. the fill logic must match hand-calculated examples (gaps, stop-vs-target ordering, end-of-day flatten)
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from make_synthetic import make
from smt_lab.config import Account, Costs, Params
from smt_lab.data import NY, build_pair
from smt_lab.engine import run_backtest
from smt_lab.signals import compute_signals

TICK = 0.25


def _pair(days=60, seed=3):
    a, b = make(days=days, seed=seed)
    return build_pair(a, b, "5min")


# ------------------------------------------------------------------ 1. look-ahead tests
def _evenly(positions, k):
    positions = np.asarray(positions)
    return positions[np.linspace(0, len(positions) - 1, min(k, len(positions))).astype(int)]


def test_signals_do_not_depend_on_the_future():
    """Cut the data so the window ENDS exactly on a signal bar. Cutting at arbitrary points would miss a
    one-bar peek into the future, because the leak only shows on the last bar of the window."""
    df, p = _pair(), Params()
    full = compute_signals(df, p, TICK)
    sig_pos = np.flatnonzero(full["side"].to_numpy() != 0)
    assert len(sig_pos) > 10, "too few signals for the test to mean anything"
    for s in _evenly(sig_pos, 25):
        cut = int(s) + 1
        part = compute_signals(df.iloc[:cut], p, TICK)
        pd.testing.assert_frame_equal(full.iloc[:cut], part, check_exact=False, rtol=1e-9, atol=1e-9)


def test_trades_do_not_depend_on_the_future():
    """Engine-level leaks (fills/exits peeking at later bars): cut the data right at trade entries and exits.
    Signal-level leaks are covered by the test above; this one covers what happens after a signal exists."""
    df = _pair()
    p, costs, acct = Params(), Costs(), Account()
    full = run_backtest(df, compute_signals(df, p, TICK), p, costs, acct)
    assert len(full) >= 10, f"only {len(full)} trades - test would be vacuous"
    entry_cols = ["entry_time", "side", "entry", "stop", "target", "size"]
    exit_cols = ["exit_time", "exit", "reason"]
    cuts = set()
    for k in _evenly(range(len(full)), 12):
        for col in ("entry_time", "exit_time"):
            cuts.add(int(df.index.get_loc(full.iloc[int(k)][col])) + 1)
    for cut in sorted(c for c in cuts if c < len(df)):
        part_df = df.iloc[:cut]
        part = run_backtest(part_df, compute_signals(part_df, p, TICK), p, costs, acct)
        exp = full[full["entry_time"] < df.index[cut]].reset_index(drop=True)
        assert len(part) == len(exp), f"cut {cut}: {len(part)} trades vs {len(exp)} in the full run"
        # every trade ENTERED inside the window must be identical, even if it was still open at the cut
        pd.testing.assert_frame_equal(part[entry_cols], exp[entry_cols], check_exact=False, rtol=1e-9)
        # a trade that had already CLOSED inside the window must be closed in BOTH runs, and exit identically
        # (an exit that peeks at a later bar would be closed in the full run but still open in the cut run)
        done = (part["reason"] != "end_of_data").to_numpy()
        closed_in_full = (exp["exit_time"] < df.index[cut]).to_numpy()
        assert (done == closed_in_full).all(), f"cut {cut}: a trade closes differently when future bars are hidden"
        pd.testing.assert_frame_equal(part.loc[done, exit_cols].reset_index(drop=True),
                                      exp.loc[done, exit_cols].reset_index(drop=True),
                                      check_exact=False, rtol=1e-9)


# ------------------------------------------------------------------ 2. hand-checked fills
def _frame(start, bars):
    idx = pd.date_range(start, periods=len(bars), freq="5min", tz=NY).tz_convert("UTC")
    arr = np.array(bars, float)
    return pd.DataFrame({"a_open": arr[:, 0], "a_high": arr[:, 1], "a_low": arr[:, 2], "a_close": arr[:, 3],
                         "blocked": False}, index=idx)


def _sig(df, bar, side, trigger, stop):
    s = pd.DataFrame({"side": 0, "trigger": np.nan, "stop": np.nan}, index=df.index)
    s.iloc[bar, 0], s.iloc[bar, 1], s.iloc[bar, 2] = side, trigger, stop
    return s


P0 = Params(sessions=(("00:00", "24:00"),), entry_valid_bars=3, rr=2.0, max_trades_per_day=5)
C0 = Costs(commission_per_side=0.0, slippage_ticks=0.0, target_through_ticks=0)


def _one(df, sig):
    t = run_backtest(df, sig, P0, C0, Account(), "MNQ")
    assert len(t) == 1, t
    return t.iloc[0]


def test_long_hits_target_for_exactly_2R():
    df = _frame("2024-03-04 09:00", [(100, 100.2, 99.8, 100.1),     # signal bar
                                     (100.1, 100.5, 100.0, 100.4),  # trigger 100.25 taken -> long @100.25
                                     (100.4, 103.0, 100.3, 102.9)])  # target 102.75 hit
    t = _one(df, _sig(df, 0, 1, 100.25, 99.0))
    assert t["reason"] == "target" and t["entry"] == 100.25 and abs(t["exit"] - 102.75) < 1e-9
    assert abs(t["r"] - 2.0) < 1e-9


def test_short_stop_gap_fills_at_the_worse_open():
    df = _frame("2024-03-04 09:00", [(100.5, 100.8, 100.2, 100.4),
                                     (100.1, 100.2, 99.9, 100.0),    # short @100.0
                                     (101.5, 101.6, 101.0, 101.2)])  # gaps above the 101.0 stop
    t = _one(df, _sig(df, 0, -1, 100.0, 101.0))
    assert t["reason"] == "stop" and t["exit"] == 101.5
    assert abs(t["r"] - (-1.5)) < 1e-9


def test_stop_and_target_in_same_bar_counts_as_stop():
    df = _frame("2024-03-04 09:00", [(100, 100.2, 99.8, 100.1),
                                     (100.1, 100.5, 100.0, 100.4),
                                     (100.4, 103.0, 98.5, 100.0)])   # range covers BOTH stop 99 and target 102.75
    t = _one(df, _sig(df, 0, 1, 100.25, 99.0))
    assert t["reason"] == "stop" and abs(t["r"] - (-1.0)) < 1e-9


def test_gap_through_entry_trigger_fills_at_open():
    df = _frame("2024-03-04 09:00", [(100, 100.2, 99.8, 100.1),
                                     (100.75, 101.0, 100.6, 100.9),  # opens above the 100.25 buy-stop
                                     (100.9, 105.0, 100.8, 104.9)])
    t = _one(df, _sig(df, 0, 1, 100.25, 99.0))
    assert t["entry"] == 100.75                                     # worse than the trigger, as in real life


def test_positions_are_flattened_at_flat_time():
    df = _frame("2024-03-04 15:45", [(100, 100.2, 99.8, 100.1),     # 15:45 signal
                                     (100.1, 100.5, 100.0, 100.4),  # 15:50 fill
                                     (100.6, 100.9, 100.5, 100.8)])  # 15:55 -> forced flat at the open
    t = _one(df, _sig(df, 0, 1, 100.25, 99.0))
    assert t["reason"] == "flat" and t["exit"] == 100.6


def test_unfilled_order_expires():
    df = _frame("2024-03-04 09:00", [(100, 100.2, 99.8, 100.1)] + [(100.0, 100.1, 99.9, 100.0)] * 6 +
                [(100.0, 101.0, 99.9, 100.9)])                      # would trigger, but only after expiry
    t = run_backtest(df, _sig(df, 0, 1, 100.25, 99.0), P0, C0, Account(), "MNQ")
    assert len(t) == 0


def test_commission_and_slippage_reduce_pnl():
    df = _frame("2024-03-04 09:00", [(100, 100.2, 99.8, 100.1),
                                     (100.1, 100.5, 100.0, 100.4),
                                     (100.4, 103.0, 100.3, 102.9)])
    sig = _sig(df, 0, 1, 100.25, 99.0)
    free = run_backtest(df, sig, P0, C0, Account(), "MNQ").iloc[0]
    paid = run_backtest(df, sig, P0, Costs(commission_per_side=1.0, slippage_ticks=1.0, target_through_ticks=0),
                        Account(), "MNQ").iloc[0]
    assert paid["pnl_usd"] < free["pnl_usd"] and paid["entry"] > free["entry"]


def test_contract_roll_days_are_blocked():
    """Continuous futures files have a fake price gap at each roll. We must not open trades on those days."""
    a, b = make(days=60, seed=5)
    flip = a.index[len(a) // 2]
    a["instrument_id"] = np.where(a.index < flip, 111, 222)
    b["instrument_id"] = np.where(b.index < flip + pd.Timedelta(hours=2), 333, 444)   # B rolls a little later
    df = build_pair(a, b, "5min")
    assert df["blocked"].sum() > 0, "roll was not detected"
    cal_days = df.index[df["blocked"]].tz_convert(NY).normalize().unique()
    assert 2 <= len(cal_days) <= 6, f"unexpected number of blocked days: {len(cal_days)}"
    p = Params()
    trades = run_backtest(df, compute_signals(df, p, TICK), p, Costs(), Account())
    assert len(trades) > 0
    assert not set(trades["entry_time"]) & set(df.index[df["blocked"]]), "traded on a roll-blocked bar"


if __name__ == "__main__":
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
