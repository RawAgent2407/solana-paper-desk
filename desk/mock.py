"""Synthetic scenario generator (seeded). No network, no credentials."""
import random
from dataclasses import replace
from .models import Snapshot, Tick, Event

SCENARIOS = {
    "healthy": 30, "low_liquidity": 15, "pump_collapse": 12, "bundled_rug": 6,
    "concentration": 12, "wash_volume": 8, "unsellable": 5, "missing_data": 8,
    "stale": 6, "duplicate": 6, "malformed": 4,
}
N_TICKS = 90


def _walk(rng, t0, liq, mu=0.0, sigma=0.015, start=1.0):
    p, out = start, []
    for k in range(N_TICKS):
        p *= max(0.05, 1 + rng.gauss(mu, sigma))
        out.append(Tick(t0 + 60 * (k + 1), p, liq * rng.uniform(0.95, 1.05)))
    return out


def _healthy_snap(rng, pid, t):
    return Snapshot(
        pool_id=pid, symbol=pid[:5].upper(), observed_at=t, received_at=t + rng.randint(1, 20),
        price=1.0, liquidity_usd=rng.uniform(60_000, 200_000), volume_h1=rng.uniform(60_000, 300_000),
        top10_pct=rng.uniform(6, 18), mint_revoked=True, freeze_revoked=True,
        lp_locked_pct=rng.uniform(95, 100), sellable=True, buy_sell_ratio=rng.uniform(1.0, 2.0),
        unique_buyers=rng.randint(150, 600), momentum_1h=rng.uniform(0.05, 0.5),
        age_min=rng.uniform(15, 120))


def generate_events(seed: int, n: int = 120, span_s: int = 86_400):
    rng = random.Random(seed)
    names, weights = zip(*SCENARIOS.items())
    events = []
    for i in range(n):
        sc = rng.choices(names, weights)[0]
        t = rng.randint(0, span_s)
        pid = f"pool{seed}_{i:03d}"
        s = _healthy_snap(rng, pid, t)
        liq = s.liquidity_usd
        path = _walk(rng, t, liq, mu=rng.choice([-0.002, 0.0, 0.001, 0.003]))

        if sc == "low_liquidity":
            s = replace(s, liquidity_usd=rng.uniform(3_000, 20_000), volume_h1=rng.uniform(5_000, 40_000))
            path = _walk(rng, t, s.liquidity_usd)
        elif sc in ("pump_collapse", "bundled_rug"):
            c = rng.randint(10, 25)
            path = _walk(rng, t, liq, mu=0.02 if sc == "pump_collapse" else 0.002, sigma=0.01)
            if sc == "bundled_rug":
                s = replace(s, top10_pct=rng.uniform(8, 14))  # bundled wallets hide concentration
            path = tuple(
                tk if k < c else Tick(tk.t, tk.price * (0.35 if sc == "pump_collapse" else 0.03),
                                      liq * 0.03 if sc == "pump_collapse" else 0.0)
                for k, tk in enumerate(path))
        elif sc == "concentration":
            s = replace(s, top10_pct=rng.uniform(30, 60))
        elif sc == "wash_volume":
            s = replace(s, volume_h1=rng.uniform(300_000, 900_000), unique_buyers=rng.randint(4, 12))
        elif sc == "unsellable":
            s = replace(s, sellable=False)
            path = [Tick(tk.t, tk.price, 0.0) for tk in path]
        elif sc == "missing_data":
            for f in rng.sample(["top10_pct", "mint_revoked", "freeze_revoked", "lp_locked_pct",
                                 "sellable", "volume_h1"], rng.randint(1, 2)):
                s = replace(s, **{f: None})
        elif sc == "stale":
            s = replace(s, received_at=t + 600)
        elif sc == "malformed":
            s = replace(s, price=rng.choice([None, -1.0, 0.0]))
        elif sc == "duplicate" and events:
            base = rng.choice(events).snapshot
            rt = base.received_at + rng.randint(30, 300)
            s = replace(base, observed_at=rt - 2, received_at=rt)
            path = events[0].path
        events.append(Event(s, tuple(path), sc))
    events.sort(key=lambda e: e.snapshot.received_at)
    return events
