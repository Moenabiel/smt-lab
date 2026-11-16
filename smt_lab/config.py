"""All tunable settings live here. Every run script can also override them from the command line."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Instrument:
    tick_size: float
    point_value: float  # USD per 1.0 price point, per contract


# Micros track the full-size contract's price, so signals use NQ/ES prices and sizing uses MNQ/MES.
INSTRUMENTS = {
    "NQ": Instrument(0.25, 20.0),
    "MNQ": Instrument(0.25, 2.0),
    "ES": Instrument(0.25, 50.0),
    "MES": Instrument(0.25, 5.0),
    "YM": Instrument(1.0, 5.0),
    "MYM": Instrument(1.0, 0.5),
}


@dataclass(frozen=True)
class Params:
    # --- SMT signal definition -------------------------------------------------------------
    lookback: int = 48            # liquidity level = highest high / lowest low of the previous N bars
    div_window: int = 3           # "the other instrument did NOT sweep" is judged over the last K bars
    require_rejection: bool = True  # the sweeping bar must close back inside the level (failed breakout)
    # --- risk geometry ---------------------------------------------------------------------
    atr_len: int = 14
    min_stop_atr: float = 0.5     # skip setups whose stop is tighter than this many ATRs
    max_stop_atr: float = 3.0     # skip setups whose stop is wider than this many ATRs
    stop_buffer_ticks: int = 2    # stop goes this far beyond the sweep extreme
    entry_valid_bars: int = 6     # stop-entry order expires after this many bars
    rr: float = 2.0               # target = rr * initial risk
    # --- when we're allowed to trade (America/New_York wall clock) --------------------------
    sessions: tuple = (("02:00", "05:00"), ("08:30", "11:00"))
    flat_time: str = "15:55"      # everything is closed from here until the 18:00 re-open
    max_trades_per_day: int = 2
    daily_loss_limit_r: float = 2.0  # stop trading for the day after losing this many R


@dataclass(frozen=True)
class Costs:
    commission_per_side: float = 0.75   # PLACEHOLDER: use your broker's all-in cost per micro contract per side
    slippage_ticks: float = 1.0         # applied to market/stop fills (entries, stops, forced exits), not to limit targets
    target_through_ticks: int = 1       # a limit target only fills if price trades THROUGH it by this much


@dataclass(frozen=True)
class Account:
    equity: float = 25_000.0     # fixed (no compounding) so R-statistics stay clean
    risk_pct: float = 0.5        # % of equity risked per trade at the stop
    max_contracts: int = 20
