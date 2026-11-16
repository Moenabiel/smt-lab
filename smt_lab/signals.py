"""SMT divergence signals.

Definition used here (mechanical, so it can be tested - tweak it to match your own reading of SMT):

  Liquidity level  : highest high / lowest low of the previous `lookback` bars, per instrument.
  Sweep            : a bar trades beyond that level.  With require_rejection it must also CLOSE back inside.
  Bearish SMT      : one instrument sweeps-and-rejects the high on this bar while the pair has NOT
                     both swept their highs within the last `div_window` bars  -> one confirmed, one failed.
  Bullish SMT      : mirror image on the lows.
  Entry            : stop order just beyond the signal bar's extreme on instrument A (break of the rejection candle).
  Stop             : beyond the highest high / lowest low of the last `div_window` bars on A, plus a buffer.

Everything here uses only bars up to and including bar t, so the signal is known at the CLOSE of bar t.
tests/test_lookahead.py proves that by chopping the data and checking the signals don't change.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Params


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int) -> pd.Series:
    prev = close.shift(1)
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def _recent(flag: pd.Series, k: int) -> pd.Series:
    """True if `flag` was True on any of the last k bars (including this one)."""
    return flag.astype(int).rolling(k, min_periods=1).max() > 0


def compute_signals(df: pd.DataFrame, p: Params, tick: float) -> pd.DataFrame:
    n, k = p.lookback, p.div_window
    f = {}
    for x in ("a", "b"):
        h, l, c = df[f"{x}_high"], df[f"{x}_low"], df[f"{x}_close"]
        ref_hi = h.shift(1).rolling(n).max()   # shift(1): the current bar is never part of its own reference
        ref_lo = l.shift(1).rolling(n).min()
        sw_hi, sw_lo = h > ref_hi, l < ref_lo
        f[x] = {
            "rej_hi": (sw_hi & (c < ref_hi)) if p.require_rejection else sw_hi,
            "rej_lo": (sw_lo & (c > ref_lo)) if p.require_rejection else sw_lo,
            "rec_hi": _recent(sw_hi, k),
            "rec_lo": _recent(sw_lo, k),
        }

    bear = (f["a"]["rej_hi"] | f["b"]["rej_hi"]) & ~(f["a"]["rec_hi"] & f["b"]["rec_hi"])
    bull = (f["a"]["rej_lo"] | f["b"]["rej_lo"]) & ~(f["a"]["rec_lo"] & f["b"]["rec_lo"])
    bear = bear & ~bear.shift(1, fill_value=False)   # fire once per divergence, not on every bar
    bull = bull & ~bull.shift(1, fill_value=False)
    both = bear & bull                               # contradictory bar -> stand aside
    bear, bull = bear & ~both, bull & ~both

    ah, al, ac = df["a_high"], df["a_low"], df["a_close"]
    a_atr = atr(ah, al, ac, p.atr_len)
    buf = p.stop_buffer_ticks * tick

    s_trig = al - tick                                   # short: enter on a break of the signal bar's low
    s_stop = ah.rolling(k, min_periods=1).max() + buf
    l_trig = ah + tick                                   # long: enter on a break of the signal bar's high
    l_stop = al.rolling(k, min_periods=1).min() - buf
    s_risk, l_risk = s_stop - s_trig, l_trig - l_stop

    ok_s = bear & (s_risk >= p.min_stop_atr * a_atr) & (s_risk <= p.max_stop_atr * a_atr)
    ok_l = bull & (l_risk >= p.min_stop_atr * a_atr) & (l_risk <= p.max_stop_atr * a_atr)

    out = pd.DataFrame(index=df.index)
    out["side"] = np.where(ok_s, -1, np.where(ok_l, 1, 0))
    out["trigger"] = np.where(ok_s, s_trig, np.where(ok_l, l_trig, np.nan))
    out["stop"] = np.where(ok_s, s_stop, np.where(ok_l, l_stop, np.nan))
    return out
