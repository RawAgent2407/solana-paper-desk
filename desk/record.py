"""Records live read-only market data for offline replay/optimisation. No trading, no model calls."""
import argparse
import json
import os
import time
from dataclasses import asdict
from . import live


def append(path, row):
    with open(path, "a") as f:
        f.write(json.dumps(row) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Record live Solana token data for replay (read-only)")
    ap.add_argument("--minutes", type=float, default=240)
    ap.add_argument("--poll", type=int, default=60, help="keep 60: risk rules assume 1-min closes")
    ap.add_argument("--max-new", type=int, default=10)
    ap.add_argument("--track-minutes", type=int, default=90, help="how long each token's price is followed")
    ap.add_argument("--out", default="output/recording.jsonl")
    a = ap.parse_args(argv)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    seen, tracked, end = set(), {}, time.time() + a.minutes * 60
    n_snap = n_tick = 0
    try:
        while time.time() < end:
            now = int(time.time())
            if tracked:
                pairs = live.fetch_pairs(list(tracked))
                for addr in list(tracked):
                    p = pairs.get(addr)
                    price = live._f((p or {}).get("priceUsd"))
                    liq = live._f(((p or {}).get("liquidity") or {}).get("usd"))
                    append(a.out, {"type": "tick", "addr": addr, "t": now, "price": price, "liq": liq})
                    n_tick += 1
                    if now - tracked[addr] > a.track_minutes * 60:
                        del tracked[addr]
            new = [x for x in live.fetch_candidates() if x not in seen][: a.max_new]
            pairs = live.fetch_pairs(new) if new else {}
            for addr in new:
                seen.add(addr)
                if addr in pairs:
                    s = live.build_snapshot(addr, pairs[addr], live.fetch_rug(addr), now)
                    append(a.out, {"type": "snap", "snap": asdict(s)})
                    tracked[addr] = now
                    n_snap += 1
            print(f"[{time.strftime('%H:%M:%S')}] snapshots={n_snap} ticks={n_tick} tracking={len(tracked)}", flush=True)
            time.sleep(max(0, a.poll - (time.time() - now)))
    except KeyboardInterrupt:
        print("Stopped.")
    print(f"Saved to {a.out}")


if __name__ == "__main__":
    main()
