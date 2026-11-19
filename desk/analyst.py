from .models import Snapshot, Score


def _clip(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


class MockScorer:
    """Transparent heuristic. NOT a probability of profit and NOT calibrated."""

    def score(self, s: Snapshot) -> Score:
        parts = {
            "buy/sell pressure": (0.25, _clip((s.buy_sell_ratio - 0.8) / 1.0)),
            "unique buyers": (0.20, _clip(s.unique_buyers / 400)),
            "liquidity depth": (0.20, _clip(s.liquidity_usd / 150_000)),
            "moderate momentum": (0.20, _clip(1 - abs(s.momentum_1h - 0.3) / 0.7)),
            "pool age": (0.15, _clip(s.age_min / 60)),
        }
        value = sum(w * v for w, v in parts.values())
        rationale = [f"{k}: {v:.2f} (w={w})" for k, (w, v) in parts.items()]
        return Score(round(value, 3), rationale,
                     "Heuristic ranking only; no calibrated win probability; social/cluster data not used.")
