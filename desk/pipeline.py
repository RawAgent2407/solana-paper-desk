import random
from .config import Config
from .models import Decision, fingerprint
from .scout import scout_check
from .filters import apply_filters
from .analyst import MockScorer
from .reviewer import review
from . import approvals
from .simulator import Portfolio


def auto_human(item, snapshot):
    """Stand-in for the human reviewer in non-interactive runs (clearly logged as AUTO)."""
    return True


def interactive_human(item, snapshot):
    ans = input(f"  APPROVE simulated buy of {snapshot.symbol} ({snapshot.pool_id})? [y/N] ")
    return ans.strip().lower() == "y"


def run(events, cfg: Config, mode="desk", human=auto_human, seed=1, scorer=None):
    """mode='desk': full pipeline. mode='baseline': scout-only, buy everything valid."""
    rng = random.Random(seed * 7919 + 1)
    scorer = scorer or MockScorer()
    port, seen, decisions = Portfolio(cfg), set(), []
    for i, ev in enumerate(sorted(events, key=lambda e: e.snapshot.received_at)):
        s, now = ev.snapshot, ev.snapshot.received_at
        port.settle(now)
        d = Decision(i, s.pool_id, s.symbol, ev.scenario, now)
        decisions.append(d)
        ok, why = scout_check(s, seen, cfg)
        if not ok:
            d.stage, d.verdict, d.reasons = "SCOUT", "REJECT", [why]
            continue
        seen.add(s.pool_id)
        entry_time = now + cfg.latency_s
        if mode == "desk":
            fr = apply_filters(s, cfg)
            if fr:
                d.stage, d.verdict, d.reasons = "FILTER", "REJECT", fr
                continue
            sc = scorer.score(s)
            rv = review(s, fr, sc, cfg)
            d.score, d.rationale, d.dissent = sc.value, sc.rationale, rv.dissent
            d.stage, d.verdict, d.reasons = "REVIEW", rv.verdict, rv.reasons
            if rv.verdict != "PAPER-TEST":
                continue
            item = approvals.submit(s, now, cfg)
            at = now + cfg.approval_delay_s
            d.approval = approvals.decide(item, human(item, s), at, s)
            d.stage = "APPROVAL"
            if d.approval != "APPROVED":
                continue
            entry_time = at + cfg.latency_s
        else:
            d.verdict = "BASELINE-BUY"
        status, trade = port.try_open(ev, entry_time, rng)
        d.stage, d.trade_status = "SIM", status
    port.settle(10 ** 12)
    return decisions, port
