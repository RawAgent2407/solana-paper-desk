from .config import Config
from .models import Snapshot


def scout_check(s: Snapshot, seen: set, cfg: Config):
    """Reject malformed, stale or duplicate observations. Returns (ok, reason)."""
    if s.price is None or s.price <= 0 or (s.liquidity_usd is not None and s.liquidity_usd < 0):
        return False, "MALFORMED"
    if s.received_at - s.observed_at > cfg.stale_after_s:
        return False, "STALE"
    if s.pool_id in seen:
        return False, "DUPLICATE"
    return True, ""
