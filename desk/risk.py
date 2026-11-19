from dataclasses import dataclass
from typing import Optional
from .config import Config


@dataclass
class Exit:
    t: int
    price: Optional[float]
    liquidity: float
    reason: str


def manage(ticks, entry_price: float, cfg: Config, entry_t: int) -> Exit:
    """-6% stop judged on 1-min CLOSES (gaps can exceed the stop), +12% arms a 6% trail,
    time stop after max_hold_ticks. If liquidity is 0 the position cannot exit."""
    ticks = list(ticks)[: cfg.max_hold_ticks]
    if not ticks:
        return Exit(entry_t, None, 0.0, "STUCK_NO_EXIT")
    peak, trailing = entry_price, False
    for tk in ticks:
        peak = max(peak, tk.price)
        pnl = tk.price / entry_price - 1
        if pnl >= cfg.trail_trigger:
            trailing = True
        stop = pnl <= -cfg.stop_loss
        trail = trailing and tk.price <= peak * (1 - cfg.trail_gap)
        if (stop or trail) and tk.liquidity > 0:
            return Exit(tk.t, tk.price, tk.liquidity, "STOP" if stop else "TRAIL")
    last = ticks[-1]
    if last.liquidity <= 0:
        return Exit(last.t, None, 0.0, "STUCK_NO_EXIT")
    return Exit(last.t, last.price, last.liquidity, "TIME")
