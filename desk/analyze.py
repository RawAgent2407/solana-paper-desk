"""Mistake review + walk-forward optimiser over recorded (or mock) data. Free: no model calls, no network."""
import argparse
import itertools
import json
import os
import random
from collections import defaultdict
from dataclasses import replace
from .config import Config
from .models import Snapshot, Tick, Event
from .pipeline import run
from .simulator import Portfolio
from .mock import generate_events
from .report import stats, BANNER

GRID = {
    "stop_loss": [0.06, 0.10, 0.15],
    "trail_trigger": [0.12, 0.20],
    "trail_gap": [0.06, 0.10],
    "score_paper": [0.60, 0.70],
    "min_volume_h1": [50_000, 100_000],
    "max_top10": [20.0, 30.0],
    "max_hold_ticks": [30, 60],
}


def load_recording(path):
    snaps, ticks = {}, defaultdict(list)
    with open(path) as f:
        for line in f:
            j = json.loads(line)
            if j["type"] == "snap":
                snaps[j["snap"]["pool_id"]] = Snapshot(**j["snap"])
            else:
                ticks[j["addr"]].append(j)
    events = []
    for addr, s in snaps.items():
        path_, last = [], s.price
        for tk in sorted(ticks.get(addr, []), key=lambda x: x["t"]):
            if tk["price"] is None:
                path_.append(Tick(tk["t"], last or 0.0, 0.0))  # vanished pair: no exit liquidity
            else:
                last = tk["price"]
                path_.append(Tick(tk["t"], tk["price"], tk["liq"] if tk["liq"] is not None else 0.0))
        if len(path_) >= 5:
            events.append(Event(s, tuple(path_), "REC"))
    return sorted(events, key=lambda e: e.snapshot.received_at)


def classify(trade, event, cfg):
    """Label why a trade lost (or won)."""
    if trade.net_pnl > 0:
        return "WIN"
    if trade.exit_reason == "STUCK_NO_EXIT":
        return "STUCK_RUG_OR_NO_LIQUIDITY"
    if trade.ret_pct < -3 * cfg.stop_loss * 100:
        return "COLLAPSE_GAP_THROUGH_STOP"
    later = [tk.price for tk in event.path if tk.t > trade.exit_t][:30]
    if trade.exit_reason == "STOP" and later and max(later) >= trade.entry_price:
        return "WHIPSAW_STOPPED_THEN_RECOVERED"
    if trade.exit_reason in ("TIME", "TRAIL") or abs(trade.ret_pct) < 8:
        return "COST_DRAG_SMALL_MOVE"
    return "STOP_NORMAL_LOSS"


def mistakes(events, cfg):
    dec, port = run(events, cfg, "desk", seed=1)
    by_id = {e.snapshot.pool_id: e for e in events}
    out = defaultdict(list)
    for t in port.closed:
        out[classify(t, by_id[t.pool_id], cfg)].append(t.net_pnl)
    return dec, port, by_id, out


def counterfactual(dec, by_id, cfg):
    """What WOULD each rejected token have returned if the desk had bought it? (per rejection reason)"""
    nf = replace(cfg, missed_fill_prob=0.0)
    res = defaultdict(list)
    for d in dec:
        if d.stage == "FILTER":
            keys = {r.split(":")[0] for r in d.reasons}
        elif d.stage == "REVIEW" and d.verdict != "PAPER-TEST":
            keys = {"SCORE_BELOW_THRESHOLD"}
        else:
            continue
        st, tr = Portfolio(nf).try_open(by_id[d.pool_id], d.received_at + cfg.latency_s, random.Random(1))
        if st == "FILLED":
            for k in keys:
                res[k].append(tr.ret_pct)
    return res


def evaluate(events, cfg):
    _, port = run(events, cfg, "desk", seed=1)
    s = stats(port, cfg)
    return s["net_pnl"], s["trades"], s["max_dd_pct"]


def optimise(events, cfg, min_trades):
    cut = int(len(events) * 0.6)
    train, test = events[:cut], events[cut:]
    keys = list(GRID)
    rows = []
    for combo in itertools.product(*GRID.values()):
        c = replace(cfg, **dict(zip(keys, combo)))
        pnl, n, dd = evaluate(train, c)
        if n >= min_trades:
            rows.append((pnl, combo, c))
    rows.sort(key=lambda r: -r[0])
    base_train, base_test = evaluate(train, cfg), evaluate(test, cfg)
    top = [(r, evaluate(test, r[2])) for r in rows[:3]]
    return len(rows), base_train, base_test, top, keys


def build_report(events, cfg, min_trades, label):
    dec, port, by_id, mist = mistakes(events, cfg)
    s = stats(port, cfg)
    L = [BANNER, "", f"ANALYSIS ({label}): {len(events)} tokens, desk trades={s['trades']}, net=${s['net_pnl']:.2f}", "",
         "1) WHY TRADES LOST OR WON (count, total $)"]
    for k, v in sorted(mist.items(), key=lambda kv: sum(kv[1])):
        L.append(f"  {k:<32}{len(v):>4}  ${sum(v):8.2f}")
    L += ["", "2) FILTER CHECK: what rejected tokens WOULD have returned if bought (sim, same costs)",
          f"  {'reason':<26}{'n':>4}{'avg ret%':>10}{'win%':>7}   reading"]
    cf = counterfactual(dec, by_id, cfg)
    for k, v in sorted(cf.items(), key=lambda kv: -len(kv[1])):
        avg, win = sum(v) / len(v), sum(1 for x in v if x > 0) / len(v) * 100
        note = "n<10: too few to conclude" if len(v) < 10 else ("blocks WINNERS - consider loosening" if avg > 0 else "protects capital")
        L.append(f"  {k:<26}{len(v):>4}{avg:>10.1f}{win:>7.0f}   {note}")
    n_ok, btr, bte, top, keys = optimise(events, cfg, min_trades)
    L += ["", f"3) WALK-FORWARD OPTIMISER ({n_ok} configs tried; tuned on first 60% by time, judged on last 40%)",
          f"  DEFAULT   train net=${btr[0]:.2f} (n={btr[1]})   TEST net=${bte[0]:.2f} (n={bte[1]}, maxDD {bte[2]:.1f}%)"]
    verdict = "KEEP DEFAULTS: no tuned config beat the defaults on unseen data."
    for (pnl, combo, c), (tp, tn, tdd) in top:
        L.append(f"  TUNED     train net=${pnl:.2f}   TEST net=${tp:.2f} (n={tn}, maxDD {tdd:.1f}%)  "
                 + ", ".join(f"{k}={v}" for k, v in zip(keys, combo)))
    if top:
        (pnl, combo, c), (tp, tn, tdd) = top[0]
        if tp > bte[0] and tp > 0 and tn >= min_trades:
            verdict = ("CANDIDATE (not proof): best tuned config beat defaults AND was profitable on the unseen 40%. "
                       "Re-check on a NEW recording before adopting: " + ", ".join(f"{k}={v}" for k, v in zip(keys, combo)))
        elif tp > bte[0]:
            verdict = "NO RELIABLE IMPROVEMENT: best tuned config loses less than defaults on unseen data but still loses money."
    L += ["", f"VERDICT: {verdict}", "",
          "CAUTION: many configs were tried, so the best train score is inflated by luck. Only the TEST column counts,",
          "and small samples mislead. Nothing here changes config.py automatically.", "", BANNER]
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Mistake review + walk-forward optimiser (free, offline)")
    ap.add_argument("--input", default="output/recording.jsonl")
    ap.add_argument("--mock", action="store_true", help="use synthetic data (tool test only; results meaningless)")
    ap.add_argument("--min-trades", type=int, default=8)
    ap.add_argument("--out", default="output/analysis.txt")
    a = ap.parse_args(argv)
    cfg = Config()
    if a.mock:
        events, label = generate_events(1, 400), "MOCK DATA - TOOL TEST ONLY"
    else:
        if not os.path.exists(a.input):
            raise SystemExit(f"No recording at {a.input}. Run: python3 -m desk.record --minutes 240")
        events, label = load_recording(a.input), "recorded live data"
    if len(events) < 30:
        raise SystemExit(f"Only {len(events)} usable tokens; record longer (need 30+, ideally hundreds).")
    text = build_report(events, cfg, a.min_trades, label)
    print(text)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w") as f:
        f.write(text + "\n")


if __name__ == "__main__":
    main()
