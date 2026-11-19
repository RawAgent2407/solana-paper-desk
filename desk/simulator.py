"""Paper execution simulator + portfolio. All results are SIMULATED."""
from dataclasses import dataclass
from .config import Config
from .models import Trade
from .risk import manage


def spread_pct(liq: float) -> float:
    return min(0.15, max(0.003, 2000.0 / liq)) if liq > 0 else 0.15


@dataclass
class _Open:
    exit_t: int
    cost: float
    net_value: float
    trade: Trade


class Portfolio:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.cash = cfg.start_balance
        self.open = []
        self.closed = []
        self.curve = [(0, cfg.start_balance)]

    def exposure(self):
        return sum(o.cost for o in self.open)

    def equity(self):
        return self.cash + self.exposure()

    def settle(self, now):
        for o in sorted([o for o in self.open if o.exit_t <= now], key=lambda o: o.exit_t):
            self.open.remove(o)
            self.cash += o.net_value
            self.closed.append(o.trade)
            self.curve.append((o.exit_t, self.equity()))

    def try_open(self, ev, entry_time, rng):
        """Returns (status, Trade|None). Uses ticks at/after entry_time only (no look-ahead)."""
        cfg = self.cfg
        size = round(self.equity() * cfg.max_position_pct, 2)
        if size < 1 or size > self.cash:
            return "SKIPPED_CASH", None
        if self.exposure() + size > cfg.max_exposure_pct * self.equity():
            return "SKIPPED_EXPOSURE_LIMIT", None
        later = [tk for tk in ev.path if tk.t >= entry_time]
        if not later:
            return "NO_PRICE_DATA", None
        tk0, rest = later[0], later[1:]
        if rng.random() < cfg.missed_fill_prob:
            return "MISSED_FILL", None
        if tk0.liquidity < 4 * size:
            return "MISSED_FILL_NO_DEPTH", None
        entry = tk0.price * (1 + spread_pct(tk0.liquidity) / 2 + min(0.5, size / tk0.liquidity))
        shares = size * (1 - cfg.fee_pct) / entry
        ex = manage(rest, entry, cfg, tk0.t)
        if ex.price is None:
            net, exit_price = 0.0, None
        else:
            val = shares * ex.price
            exit_price = ex.price * (1 - spread_pct(ex.liquidity) / 2 - min(0.9, val / ex.liquidity))
            net = shares * exit_price * (1 - cfg.fee_pct)
        fees = size * cfg.fee_pct + (net / (1 - cfg.fee_pct) * cfg.fee_pct if net else 0)
        trade = Trade(ev.snapshot.pool_id, ev.snapshot.symbol, ev.scenario, tk0.t, ex.t, size,
                      entry, exit_price, ex.reason, round(fees, 4), round(net - size, 4),
                      round((net - size) / size * 100, 2))
        self.cash -= size
        self.open.append(_Open(ex.t, size, net, trade))
        return "FILLED", trade
