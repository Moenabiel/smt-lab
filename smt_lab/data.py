"""Loading and aligning market data. Bars are stamped with their OPEN time (Databento and yfinance both do this)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

NY = "America/New_York"
_OHLC = ("open", "high", "low", "close")


# ----------------------------------------------------------------------------- file I/O
def save_frame(df: pd.DataFrame, path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".parquet":
        df.to_parquet(path)  # needs pyarrow (in requirements.txt)
    else:
        df.to_csv(path)


def read_frame(path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"{path} not found - run fetch_data.py or make_synthetic.py first")
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path, index_col=0)


def clean_frame(df: pd.DataFrame) -> pd.DataFrame:
    """UTC DatetimeIndex, lower-case columns, sorted, no duplicate timestamps."""
    df = df.copy()
    df.columns = [str(c).lower() for c in df.columns]
    missing = [c for c in _OHLC if c not in df.columns]
    if missing:
        raise ValueError(f"missing columns {missing}; got {list(df.columns)}")
    df.index = pd.to_datetime(df.index, utc=True)
    df.index.name = "ts"
    df = df.sort_index()
    return df[~df.index.duplicated(keep="last")]


def resample_ohlc(df: pd.DataFrame, tf: str) -> pd.DataFrame:
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    if "volume" in df.columns:
        agg["volume"] = "sum"
    if "instrument_id" in df.columns:
        agg["instrument_id"] = "last"
    out = df[list(agg)].resample(tf, label="left", closed="left").agg(agg)
    return out.dropna(subset=list(_OHLC))


# ----------------------------------------------------------------------------- contract rolls
def roll_block_mask(index: pd.DatetimeIndex, id_series: list, block_days: int = 2) -> np.ndarray:
    """True for every bar on a trading day that contains a contract roll, plus the following day(s).

    Continuous-futures files splice contracts together, which leaves a fake price gap at each roll.
    We simply refuse to trade those days instead of pretending the gap is real.
    """
    n = len(index)
    roll = np.zeros(n, dtype=bool)
    for ids in id_series:
        s = pd.Series(np.asarray(ids), index=index)
        prev = s.shift(1)
        roll |= ((s != prev) & prev.notna()).to_numpy()
    if not roll.any():
        return roll
    ny = index.tz_convert(NY).tz_localize(None)
    tday = (ny + pd.Timedelta(hours=6)).normalize()  # futures "trading day" starts 18:00 ET
    days = pd.Index(tday.unique()).sort_values()
    blocked = set()
    for d in pd.Index(tday[roll].unique()):
        p = days.get_loc(d)
        blocked.update(days[p : p + block_days])
    return np.asarray(tday.isin(list(blocked)))


# ----------------------------------------------------------------------------- pair builder
def build_pair(a: pd.DataFrame, b: pd.DataFrame, tf: str = "5min", block_roll_days: int = 2) -> pd.DataFrame:
    """Align two OHLC frames (e.g. NQ and ES) on identical bar timestamps -> one wide frame."""
    a = resample_ohlc(clean_frame(a), tf)
    b = resample_ohlc(clean_frame(b), tf)
    idx = a.index.intersection(b.index)
    if len(idx) == 0:
        raise ValueError("the two instruments share no timestamps")
    a, b = a.loc[idx], b.loc[idx]
    df = pd.DataFrame(index=idx)
    for c in _OHLC:
        df[f"a_{c}"] = a[c].astype(float)
        df[f"b_{c}"] = b[c].astype(float)
    ids = [x["instrument_id"] for x in (a, b) if "instrument_id" in x.columns]
    df["blocked"] = roll_block_mask(idx, ids, block_roll_days) if ids else False
    return df.dropna()


def load_pair(path_a, path_b, tf="5min", start=None, end=None, block_roll_days=2) -> pd.DataFrame:
    df = build_pair(read_frame(path_a), read_frame(path_b), tf, block_roll_days)
    if start:
        df = df[df.index >= pd.Timestamp(start, tz="UTC")]
    if end:
        df = df[df.index < pd.Timestamp(end, tz="UTC")]
    if len(df) < 1000:
        raise ValueError(f"only {len(df)} aligned bars after filtering - need far more than that to test anything")
    return df


def describe(df: pd.DataFrame) -> str:
    gaps = df.index.to_series().diff().dt.total_seconds().div(3600)
    return (f"{len(df):,} aligned bars | {df.index[0]:%Y-%m-%d} -> {df.index[-1]:%Y-%m-%d} | "
            f"largest gap {gaps.max():.1f}h | roll-blocked bars {int(df['blocked'].sum()):,}")
