from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    start_balance: float = 197.0
    stale_after_s: int = 120
    min_volume_h1: float = 50_000
    min_liquidity: float = 25_000
    min_lp_locked: float = 95.0
    max_top10: float = 20.0
    max_volume_per_buyer: float = 5_000  # wash-volume heuristic
    score_paper: float = 0.60
    score_watch: float = 0.45
    max_position_pct: float = 0.08
    max_exposure_pct: float = 0.40
    stop_loss: float = 0.06
    trail_trigger: float = 0.12
    trail_gap: float = 0.06
    max_hold_ticks: int = 60
    fee_pct: float = 0.01
    approval_delay_s: int = 30
    approval_ttl_s: int = 120
    latency_s: int = 15
    missed_fill_prob: float = 0.10
