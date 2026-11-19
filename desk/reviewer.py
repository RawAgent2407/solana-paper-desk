from .config import Config
from .models import Snapshot, Score, Review


def review(s: Snapshot, filter_reasons, score: Score, cfg: Config) -> Review:
    if filter_reasons:
        return Review("REJECT", list(filter_reasons), [])
    if score.value >= cfg.score_paper:
        verdict = "PAPER-TEST"
    elif score.value >= cfg.score_watch:
        verdict = "WATCH"
    else:
        verdict = "REJECT"
    dissent = ["UNCHECKED: bundled-wallet cluster risk and dev-wallet history (not verifiable here)"]
    if s.momentum_1h > 0.6:
        dissent.append("parabolic 1h momentum: late-entry / collapse risk")
    if s.age_min < 10:
        dissent.append("very new pool: limited history")
    return Review(verdict, [f"score={score.value}"], dissent)
