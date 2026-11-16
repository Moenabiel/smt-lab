"""Bar-by-bar backtester for instrument A, driven by the signals from signals.py.

Execution rules (all deliberately pessimistic - a backtest that flatters you is worse than useless):
  * A signal is known at the CLOSE of bar t. The stop-entry order exists from bar t+1 onward.
  * Stop-entry fill = the trigger, or the bar's open if price gapped through it, then +/- slippage.
  * If a stop and a target are both inside the same bar, the STOP is assumed to have been hit first.
  * On the entry bar itself, a bar whose range reaches the stop counts as stopped out.
  * Limit targets only fill if price trades through them by `target_through_ticks`; no slippage on them.
  * Stops that gap are filled at the (worse) open.
  * Position size comes from the real fill-to-stop distance, so slippage can't secretly raise your risk.
  * Everything is flattened at `flat_time` (default 15:55 ET), before the 17:00-18:00 ET maintenance break.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import INSTRUMENTS, Account, Costs, Params
from .data import NY

TRADE_COLS = ["entry_time", "exit_time", "side", "entry", "exit", "stop", "target",
              "size", "risk_usd", "pnl_usd", "r", "reason", "bars"]


def _hm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def _utc(ts) -> pd.Timestamp:
    ts = pd.Timestamp(ts)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def session_arrays(index: pd.DatetimeIndex, p: Params):
    ny = index.tz_convert(NY).tz_localize(None)  # wall-clock time, so DST can't confuse the arithmetic
    minute = ny.hour.to_numpy().astype(np.int64) * 60 + ny.minute.to_numpy().astype(np.int64)
    td = ny + pd.Timedelta(hours=6)              # trading day rolls over at 18:00 ET
    tkey = (td.year.to_numpy().astype(np.int64) * 10000
            + td.month.to_numpy().astype(np.int64) * 100
            + td.day.to_numpy().astype(np.int64))
    in_sess = np.zeros(len(index), dtype=bool)
    for start, end in p.sessions:
        in_sess |= (minute >= _hm(start)) & (minute < _hm(end))
    flat_zone = (minute >= _hm(p.flat_time)) & (minute < 18 * 60)
    return tkey, in_sess, flat_zone


def run_backtest(df: pd.DataFrame, sig: pd.DataFrame, p: Params, costs: Costs, acct: Account,
                 trade_symbol: str = "MNQ", trade_from=None) -> pd.DataFrame:
    """Returns one row per closed trade (see TRADE_COLS). `trade_from` blocks new setups before that time
    (used by walk-forward so warm-up bars are visible to indicators but never traded)."""
    inst = INSTRUMENTS[trade_symbol]
    tick, pv = inst.tick_size, inst.point_value
    idx = df.index
    n = len(idx)

    tkey, in_sess, flat_zone = session_arrays(idx, p)
    allowed = in_sess & ~flat_zone & ~df["blocked"].to_numpy(dtype=bool)
    if trade_from is not None:
        allowed &= np.asarray(idx >= _utc(trade_from))

    o = df["a_open"].to_numpy().tolist()
    h = df["a_high"].to_numpy().tolist()
    l = df["a_low"].to_numpy().tolist()
    c = df["a_close"].to_numpy().tolist()
    side = sig["side"].to_numpy().tolist()
    trig = sig["trigger"].to_numpy().tolist()
    stp = sig["stop"].to_numpy().tolist()
    allowed_l, flat_l, tkey_l = allowed.tolist(), flat_zone.tolist(), tkey.tolist()

    slip = costs.slippage_ticks * tick
    thr = costs.target_through_ticks * tick
    comm = costs.commission_per_side
    risk_budget = acct.equity * acct.risk_pct / 100.0

    trades: list = []
    pos = 0
    entry = stop = target = risk_usd = 0.0
    size = entry_i = entry_tk = 0
    pend = None            # (side, trigger, stop, last_valid_bar)
    cur_tk, day_n, day_r = None, 0, 0.0

    def book(i: int, px: float, reason: str) -> float:
        gross = pos * (px - entry) * pv * size
        net = gross - 2.0 * comm * size
        trades.append((idx[entry_i], idx[i], pos, entry, px, stop, target, size, risk_usd, net,
                       net / risk_usd, reason, i - entry_i))
        return net / risk_usd

    for i in range(n):
        tk = tkey_l[i]
        if tk != cur_tk:                       # new trading day: reset the daily counters
            cur_tk, day_n, day_r = tk, 0, 0.0
        if pos == 0 and pend is None and side[i] == 0:
            continue                           # nothing open, nothing pending, nothing new

        # 1) manage the open position with this bar -------------------------------------------
        if pos != 0:
            if flat_l[i] or tk != entry_tk:    # end of day -> out at the open
                day_r += book(i, o[i] - pos * slip, "flat")
                pos = 0
            else:
                hit = None
                if pos == 1:
                    if o[i] <= stop:             hit = (o[i] - slip, "stop")
                    elif l[i] <= stop:           hit = (stop - slip, "stop")
                    elif o[i] >= target + thr:   hit = (o[i], "target")
                    elif h[i] >= target + thr:   hit = (target, "target")
                else:
                    if o[i] >= stop:             hit = (o[i] + slip, "stop")
                    elif h[i] >= stop:           hit = (stop + slip, "stop")
                    elif o[i] <= target - thr:   hit = (o[i], "target")
                    elif l[i] <= target - thr:   hit = (target, "target")
                if hit is not None:
                    day_r += book(i, hit[0], hit[1])
                    pos = 0

        # 2) pending stop-entry order -----------------------------------------------------------
        if pos == 0 and pend is not None:
            s_, trig_, stp_, last_i = pend
            if flat_l[i] or i > last_i:
                pend = None
            else:
                fill = None
                if s_ == -1 and l[i] <= trig_:
                    fill = min(o[i], trig_) - slip
                elif s_ == 1 and h[i] >= trig_:
                    fill = max(o[i], trig_) + slip
                if fill is not None:
                    pend = None
                    risk_pts = abs(fill - stp_)
                    contracts = int(risk_budget // (risk_pts * pv)) if risk_pts > 0 else 0
                    contracts = min(contracts, acct.max_contracts)
                    if contracts >= 1 and (fill - stp_) * s_ > 0:   # stop must sit on the losing side
                        pos, entry, stop, size = s_, fill, stp_, contracts
                        target = fill + s_ * p.rr * risk_pts
                        risk_usd = risk_pts * pv * size
                        entry_i, entry_tk = i, tk
                        day_n += 1
                        hit = None             # same-bar exit, stop assumed first
                        if pos == 1:
                            if l[i] <= stop:             hit = (stop - slip, "stop")
                            elif h[i] >= target + thr:   hit = (target, "target")
                        else:
                            if h[i] >= stop:             hit = (stop + slip, "stop")
                            elif l[i] <= target - thr:   hit = (target, "target")
                        if hit is not None:
                            day_r += book(i, hit[0], hit[1])
                            pos = 0

        # 3) new setup from this bar's close -> order becomes live next bar ----------------------
        if (pos == 0 and pend is None and side[i] != 0 and allowed_l[i]
                and day_n < p.max_trades_per_day and day_r > -p.daily_loss_limit_r):
            pend = (side[i], trig[i], stp[i], i + p.entry_valid_bars)

    if pos != 0:
        book(n - 1, c[n - 1], "end_of_data")

    out = pd.DataFrame(trades, columns=TRADE_COLS)
    return out
