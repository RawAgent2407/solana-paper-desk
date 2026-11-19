from .config import Config
from .models import Snapshot


def apply_filters(s: Snapshot, cfg: Config):
    """Deterministic gate. Returns list of reject reasons (empty = PASS).
    Any value that cannot be verified is a rejection, never an assumption of safety."""
    r = []
    need = ["liquidity_usd", "volume_h1", "top10_pct", "mint_revoked", "freeze_revoked",
            "lp_locked_pct", "sellable", "buy_sell_ratio", "unique_buyers", "momentum_1h", "age_min"]
    for f in need:
        if getattr(s, f) is None:
            r.append(f"UNVERIFIED:{f}")
    if r:
        return r
    if s.mint_revoked is not True:
        r.append("MINT_AUTHORITY_ACTIVE")
    if s.freeze_revoked is not True:
        r.append("FREEZE_AUTHORITY_ACTIVE")
    if s.lp_locked_pct < cfg.min_lp_locked:
        r.append("LP_NOT_LOCKED")
    if s.top10_pct > cfg.max_top10:
        r.append("TOP10_CONCENTRATION")
    if s.volume_h1 < cfg.min_volume_h1:
        r.append("LOW_VOLUME")
    if s.liquidity_usd < cfg.min_liquidity:
        r.append("LOW_LIQUIDITY")
    if s.sellable is not True:
        r.append("NOT_SELLABLE")
    if s.unique_buyers > 0 and s.volume_h1 / s.unique_buyers > cfg.max_volume_per_buyer:
        r.append("WASH_VOLUME_SUSPECT")
    return r
