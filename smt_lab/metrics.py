"""Performance statistics. The bootstrap and Monte Carlo helpers exist to stop you trusting one lucky equity curve."""
from __future__ import annotations

import numpy as np
import pandas as pd


def summarize(trades: pd.DataFrame, start_equity: float) -> dict:
    n = len(trades)
    if n == 0:
        return {"trades": 0}
    pnl = trades["pnl_usd"].to_numpy(float)
    r = trades["r"].to_numpy(float)
    gross_win, gross_loss = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
    eq = np.r_[start_equity, start_equity + np.cumsum(pnl)]
    peak = np.maximum.accumulate(eq)
    dd = peak - eq
    streak = worst = 0
    for x in pnl:
        streak = streak + 1 if x < 0 else 0
        worst = max(worst, streak)
    se = r.std(ddof=1) / np.sqrt(n) if n > 1 else np.nan
    days = trades["exit_time"].dt.tz_convert("America/New_York").dt.date.nunique()
    return {
        "trades": n,
        "win_rate": float((pnl > 0).mean()),
        "avg_r": float(r.mean()),
        "t_stat": float(r.mean() / se) if np.isfinite(se) and se > 0 else np.nan,
        "profit_factor": float(gross_win / gross_loss) if gross_loss > 0 else np.inf,
        "net_usd": float(pnl.sum()),
        "max_dd_usd": float(dd.max()),
        "max_dd_pct": float((dd / peak).max() * 100),
        "worst_losing_streak": int(worst),
        "trades_per_day": float(n / max(days, 1)),
    }


def bootstrap_avg_r(r, n_boot: int = 5000, seed: int = 0):
    """Resample trades with replacement. Returns the 95% interval of average R and P(avg R <= 0)."""
    r = np.asarray(r, float)
    if len(r) < 10:
        return None
    rng = np.random.default_rng(seed)
    means = np.empty(n_boot)
    chunk = 250
    for s in range(0, n_boot, chunk):
        m = min(chunk, n_boot - s)
        means[s:s + m] = rng.choice(r, size=(m, len(r)), replace=True).mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return {"ci_low": float(lo), "ci_high": float(hi), "p_avg_r_le_0": float((means <= 0).mean())}


def monte_carlo_drawdown(pnl, start_equity: float, n_sims: int = 2000, seed: int = 0):
    """Shuffle the order of the same trades: how bad could the drawdown have been with different luck?"""
    pnl = np.asarray(pnl, float)
    if len(pnl) < 10:
        return None
    rng = np.random.default_rng(seed)
    dds = np.empty(n_sims)
    for i in range(n_sims):
        eq = np.r_[start_equity, start_equity + np.cumsum(rng.permutation(pnl))]
        dds[i] = (np.maximum.accumulate(eq) - eq).max()
    return {"median": float(np.median(dds)), "p95": float(np.percentile(dds, 95))}


def format_report(trades: pd.DataFrame, start_equity: float, title: str = "RESULTS") -> str:
    s = summarize(trades, start_equity)
    lines = [f"===== {title} ====="]
    if s["trades"] == 0:
        return "\n".join(lines + ["no trades"])
    lines += [
        f"trades            {s['trades']}   ({s['trades_per_day']:.2f}/day)",
        f"win rate          {s['win_rate']*100:.1f}%",
        f"avg R / trade     {s['avg_r']:+.3f}   (t-stat {s['t_stat']:+.2f}; |t| < 2 means 'could be luck')",
        f"profit factor     {s['profit_factor']:.2f}",
        f"net P&L           ${s['net_usd']:,.0f}",
        f"max drawdown      ${s['max_dd_usd']:,.0f}  ({s['max_dd_pct']:.1f}%)",
        f"worst loss streak {s['worst_losing_streak']}",
    ]
    bs = bootstrap_avg_r(trades["r"])
    if bs:
        lines.append(f"bootstrap 95% CI  avg R in [{bs['ci_low']:+.3f}, {bs['ci_high']:+.3f}]   "
                     f"P(avg R <= 0) = {bs['p_avg_r_le_0']*100:.1f}%")
    mc = monte_carlo_drawdown(trades["pnl_usd"], start_equity)
    if mc:
        lines.append(f"Monte Carlo DD    median ${mc['median']:,.0f} | 95th pct ${mc['p95']:,.0f}  (same trades, shuffled order)")
    return "\n".join(lines)


def plot_equity(trades: pd.DataFrame, start_equity: float, path, title: str = "Equity (closed trades)") -> bool:
    if len(trades) == 0:
        return False
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    eq = start_equity + trades["pnl_usd"].cumsum()
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(pd.to_datetime(trades["exit_time"]).to_numpy(), eq.to_numpy(), lw=1.2)
    ax.axhline(start_equity, color="grey", lw=0.8, ls="--")
    ax.set_title(title)
    ax.set_ylabel("USD")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return True
