import argparse
import os
from .config import Config
from .mock import generate_events
from .pipeline import run, auto_human, interactive_human
from .report import build, stats
from .store import save


def main(argv=None):
    ap = argparse.ArgumentParser(description="PAPER-ONLY Solana desk (SIMULATED)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--seeds", type=int, default=5, help="extra synthetic markets for robustness table")
    ap.add_argument("--events", type=int, default=120)
    ap.add_argument("--balance", type=float, default=197.0)
    ap.add_argument("--interactive", action="store_true", help="approve each simulated trade by hand")
    ap.add_argument("--out", default="output")
    a = ap.parse_args(argv)
    cfg = Config(start_balance=a.balance)
    os.makedirs(a.out, exist_ok=True)
    human = interactive_human if a.interactive else auto_human

    ev = generate_events(a.seed, a.events)
    dec, port = run(ev, cfg, "desk", human, a.seed)
    bdec, bport = run(ev, cfg, "baseline", auto_human, a.seed)
    multi = []
    for sd in range(1, a.seeds + 1):
        e = generate_events(sd, a.events)
        _, p = run(e, cfg, "desk", auto_human, sd)
        _, bp = run(e, cfg, "baseline", auto_human, sd)
        multi.append((sd, stats(p, cfg), stats(bp, cfg)))
    text = build(dec, port, bdec, bport, cfg, a.seed, multi)
    print(text)
    with open(f"{a.out}/report.txt", "w") as f:
        f.write(text + "\n")
    if port.closed:
        save(a.out, dec, port)


if __name__ == "__main__":
    main()
