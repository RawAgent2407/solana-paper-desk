from dataclasses import dataclass
from .config import Config
from .models import Snapshot, fingerprint


@dataclass
class ApprovalItem:
    pool_id: str
    created_at: int
    expires_at: int
    fp: str


def submit(s: Snapshot, now: int, cfg: Config) -> ApprovalItem:
    return ApprovalItem(s.pool_id, now, now + cfg.approval_ttl_s, fingerprint(s))


def decide(item: ApprovalItem, approve: bool, at: int, current: Snapshot):
    """Returns (status, time). Expired or changed approvals are denied."""
    if not approve:
        return "REJECTED_BY_HUMAN"
    if at > item.expires_at:
        return "DENIED_EXPIRED"
    if fingerprint(current) != item.fp:
        return "DENIED_CHANGED"
    return "APPROVED"
