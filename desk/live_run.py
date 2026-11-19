"""Forward PAPER trading on live read-only data. SIMULATED fills. Never sends orders."""
import argparse
import csv
import json
import os
import random
import time
from dataclasses import asdict
from .config import Config
from .models import Trade
from .scout import scout_check
from .filters import apply_filters
from .analyst import MockScorer
from .reviewer import review
from . import approvals, live
from .simulator import spread_pct
from .report import stats, BANNER

MAX_DRIFT = 0.05


class LivePortfolio:
    def __init__(self, cfg):
        self.cfg, self.cash, self.open, self.closed = cfg, cfg.start_balance, [], []
        self.curve = [(0, cfg.start_balance)]

    def equity(self):
        return self.cash + sum(p["size"] for p in self.open)


def log(path, row):
    with open(path, "a") as f:
        f.write(json.dumps(row) + "\n")


def close(port, pos, now, exit_price, reason):
    cfg = port.cfg
    net = pos["shares"] * exit_price * (1 - cfg.fee_pct) if exit_price else 0.0
    fees = pos["size"] * cfg.fee_pct + (net / (1 - cfg.fee_pct) * cfg.fee_pct if net else 0)
    t = Trade(pos["addr"], pos["symbol"], "LIVE", pos["entry_t"], now, pos["size"], pos["entry"],
              exit_price, reason, round(fees, 4), round(net - pos["size"], 4),
              round((net - pos["size"]) / pos["size"] * 100, 2))
    port.open.remove(pos)
    port.cash += net
    port.closed.append(t)
    port.curve.append((now, port.equity()))
    return t


def update_positions(port, cfg, prices, now, out):
    for pos in list(port.open):
        p = prices.get(pos["addr"])
        price = live._f(p.get("priceUsd")) if p else None
        liq = live._f((p.get("liquidity") or {}).get("usd")) if p else None
        if price is None:
            price, liq = pos["last_price"], 0.0
        else:
            pos["last_price"], pos["last_liq"] = price, liq if liq is not None else pos.get("last_liq", 0.0)
            liq = pos["last_liq"]
        pos["ticks"] += 1
        pos["peak"] = max(pos["peak"], price)
        pnl = price / pos["entry"] - 1
        if pnl >= cfg.trail_trigger:
            pos["trailing"] = True
        stop = pnl <= -cfg.stop_loss
        trail = pos["trailing"] and price <= pos["peak"] * (1 - cfg.trail_gap)
        timeup = pos["ticks"] >= cfg.max_hold_ticks
        if (stop or trail or timeup) and liq and liq > 0:
            ep = price * (1 - spread_pct(liq) / 2 - min(0.9, pos["shares"] * price / liq))
            t = close(port, pos, now, ep, "STOP" if stop else "TRAIL" if trail else "TIME")
            print(f"  [EXIT SIM] {t.symbol} {t.exit_reason} net ${t.net_pnl:+.2f} ({t.ret_pct:+.1f}%)")
            log(out, {"ev": "exit", **asdict(t)})
        elif timeup and (not liq or liq <= 0) and pos["ticks"] >= cfg.max_hold_ticks + 30:
            t = close(port, pos, now, None, "STUCK_NO_EXIT")
            print(f"  [EXIT SIM] {t.symbol} STUCK_NO_EXIT written off")
            log(out, {"ev": "exit", **asdict(t)})


def main(argv=None):
    ap = argparse.ArgumentParser(description="LIVE-DATA PAPER trading (SIMULATED, read-only data)")
    ap.add_argument("--minutes", type=float, default=30)
    ap.add_argument("--poll", type=int, default=60, help="seconds between cycles (= 1 'candle')")
    ap.add_argument("--balance", type=float, default=197.0)
    ap.add_argument("--max-new", type=int, default=8, help="new tokens examined per cycle")
    ap.add_argument("--interactive", action="store_true")
    ap.add_argument("--scorer", choices=["formula", "claude"], default="formula")
    ap.add_argument("--model", default="haiku", help="Claude Code model alias for the Analyst")
    ap.add_argument("--llm-budget", type=int, default=30, help="max Claude calls this run")
    ap.add_argument("--out", default="output")
    a = ap.parse_args(argv)
    cfg = Config(start_balance=a.balance)
    os.makedirs(a.out, exist_ok=True)
    out = f"{a.out}/live_log.jsonl"
    scorer = MockScorer()
    if a.scorer == "claude":
        from .claude_analyst import ClaudeScorer
        scorer = ClaudeScorer(a.model, a.llm_budget, f"{a.out}/claude_cache.json")
    rng, port, seen = random.Random(), LivePortfolio(cfg), set()
    end = time.time() + a.minutes * 60
    funnel = {k: 0 for k in ("examined", "scout_rej", "filter_rej", "watch/reject", "paper-test", "filled")}
    rejects = {}
    print(BANNER, f"\nLIVE-DATA paper run: {a.minutes} min, poll {a.poll}s, balance ${a.balance} (SIMULATED)\n")
    try:
        while time.time() < end:
            now = int(time.time())
            if port.open:
                update_positions(port, cfg, live.fetch_pairs([p["addr"] for p in port.open]), now, out)
            new = [x for x in live.fetch_candidates() if x not in seen][: a.max_new]
            pairs = live.fetch_pairs(new) if new else {}
            for addr in new:
                seen.add(addr)
                pair = pairs.get(addr)
                if not pair:
                    continue
                funnel["examined"] += 1
                s = live.build_snapshot(addr, pair, live.fetch_rug(addr), now)
                ok, why = scout_check(s, set(), cfg)
                if not ok:
                    funnel["scout_rej"] += 1
                    rejects[why] = rejects.get(why, 0) + 1
                    continue
                fr = apply_filters(s, cfg)
                if fr:
                    funnel["filter_rej"] += 1
                    for r in fr:
                        rejects[r] = rejects.get(r, 0) + 1
                    log(out, {"ev": "reject", "t": now, "symbol": s.symbol, "addr": addr, "reasons": fr})
                    continue
                sc = scorer.score(s)
                rv = review(s, fr, sc, cfg)
                log(out, {"ev": "review", "t": now, "symbol": s.symbol, "addr": addr, "score": sc.value, "formula_score": sc.formula, "source": sc.source, "rationale": sc.rationale,
                          "verdict": rv.verdict, "dissent": rv.dissent, "snapshot": asdict(s)})
                if rv.verdict != "PAPER-TEST":
                    funnel["watch/reject"] += 1
                    continue
                funnel["paper-test"] += 1
                print(f"[CANDIDATE] {s.symbol} score={sc.value} liq=${s.liquidity_usd:,.0f} vol1h=${s.volume_h1:,.0f}")
                print(f"   analyst={sc.source} | " + " | ".join(x for x in sc.rationale if not x.startswith(('buy/', 'unique', 'liquidity', 'moderate', 'pool'))))
                print("   dissent:", " | ".join(rv.dissent))
                item = approvals.submit(s, now, cfg)
                if a.interactive:
                    ok_h = input("   APPROVE simulated buy? [y/N] ").strip().lower() == "y"
                else:
                    ok_h = True
                status = approvals.decide(item, ok_h, int(time.time()), s)
                recheck = live.fetch_pairs([addr]).get(addr)
                p2 = live._f((recheck or {}).get("priceUsd"))
                if status == "APPROVED" and (p2 is None or abs(p2 / s.price - 1) > MAX_DRIFT):
                    status = "DENIED_PRICE_MOVED"
                if status != "APPROVED":
                    print(f"   -> {status}")
                    continue
                size = round(port.equity() * cfg.max_position_pct, 2)
                expo = sum(p["size"] for p in port.open)
                if size > port.cash or expo + size > cfg.max_exposure_pct * port.equity():
                    print("   -> SKIPPED (cash/exposure limit)")
                    continue
                liq = live._f((recheck.get("liquidity") or {}).get("usd")) or s.liquidity_usd
                if rng.random() < cfg.missed_fill_prob or liq < 4 * size:
                    print("   -> MISSED FILL (simulated)")
                    continue
                entry = p2 * (1 + spread_pct(liq) / 2 + min(0.5, size / liq))
                port.cash -= size
                port.open.append({"addr": addr, "symbol": s.symbol, "entry_t": int(time.time()), "size": size,
                                  "shares": size * (1 - cfg.fee_pct) / entry, "entry": entry, "peak": entry,
                                  "trailing": False, "ticks": 0, "last_price": p2, "last_liq": liq})
                funnel["filled"] += 1
                print(f"   -> SIMULATED BUY ${size:.2f} of {s.symbol} @ {entry:.8g}")
                log(out, {"ev": "entry", "t": int(time.time()), "symbol": s.symbol, "addr": addr, "size": size, "entry": entry})
            time.sleep(max(0, a.poll - (time.time() - now)))
    except KeyboardInterrupt:
        print("\nStopped by user.")
    final = live.fetch_pairs([p["addr"] for p in port.open]) if port.open else {}
    unreal = 0.0
    for p in port.open:
        pr = live._f((final.get(p["addr"]) or {}).get("priceUsd")) or p["last_price"]
        unreal += p["shares"] * pr - p["size"]
    s = stats(port, cfg)
    lines = [BANNER, "", "LIVE-DATA PAPER RUN SUMMARY (SIMULATED)",
             f"funnel: {funnel}", f"reject reasons: {dict(sorted(rejects.items(), key=lambda x: -x[1]))}",
             f"closed trades={s['trades']} wins={s['wins']} net(realized)=${s['net_pnl']:.2f} maxDD={s['max_dd_pct']:.1f}%",
             f"open positions={len(port.open)} unrealized(mark, before exit costs)=${unreal:.2f}",
             f"equity (cash + open at cost)=${port.equity():.2f}",
             "Short runs prove nothing about profitability. Fills assume displayed price + modeled costs (optimistic).", "", BANNER]
    print("\n".join(lines))
    with open(f"{a.out}/live_report.txt", "w") as f:
        f.write("\n".join(lines) + "\n")
    if port.closed:
        with open(f"{a.out}/live_trades.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(asdict(port.closed[0]).keys()))
            w.writeheader()
            w.writerows(asdict(t) for t in port.closed)


if __name__ == "__main__":
    main()
