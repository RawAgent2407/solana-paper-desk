import hashlib
from dataclasses import dataclass, field, asdict
from typing import Optional, List


@dataclass(frozen=True)
class Tick:
    t: int
    price: float
    liquidity: float


@dataclass(frozen=True)
class Snapshot:
    """What the agents are allowed to see at observation time."""
    pool_id: str
    symbol: str
    observed_at: int
    received_at: int
    price: Optional[float]
    liquidity_usd: Optional[float]
    volume_h1: Optional[float]
    top10_pct: Optional[float]
    mint_revoked: Optional[bool]
    freeze_revoked: Optional[bool]
    lp_locked_pct: Optional[float]
    sellable: Optional[bool]
    buy_sell_ratio: Optional[float]
    unique_buyers: Optional[int]
    momentum_1h: Optional[float]
    age_min: Optional[float]


@dataclass(frozen=True)
class Event:
    snapshot: Snapshot
    path: tuple          # future ticks; simulator only, never given to agents
    scenario: str        # mock label; used for reporting only


def fingerprint(s: Snapshot) -> str:
    return hashlib.sha256(repr(sorted(asdict(s).items())).encode()).hexdigest()[:16]


@dataclass
class Score:
    value: float
    rationale: List[str]
    uncertainty: str
    formula: Optional[float] = None   # formula score, kept for side-by-side comparison
    source: str = "formula"


@dataclass
class Review:
    verdict: str                 # REJECT / WATCH / PAPER-TEST
    reasons: List[str]
    dissent: List[str]


@dataclass
class Decision:
    idx: int
    pool_id: str
    symbol: str
    scenario: str
    received_at: int
    stage: str = ""              # SCOUT / FILTER / REVIEW / APPROVAL / SIM
    verdict: str = ""
    reasons: List[str] = field(default_factory=list)
    score: Optional[float] = None
    rationale: List[str] = field(default_factory=list)
    dissent: List[str] = field(default_factory=list)
    approval: str = ""
    trade_status: str = ""


@dataclass
class Trade:
    pool_id: str
    symbol: str
    scenario: str
    entry_t: int
    exit_t: int
    size: float
    entry_price: float
    exit_price: Optional[float]
    exit_reason: str
    fees: float
    net_pnl: float
    ret_pct: float
