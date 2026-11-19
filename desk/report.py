from collections import Counter

BANNER = "*** ALL RESULTS ARE SIMULATED / PAPER ONLY - NOT REAL TRADES, NOT FINANCIAL ADVICE ***"


def stats(port, cfg, trades=None):
    trades = port.closed if trades is None else trades
    pnl = [t.net_pnl for t in trades]
    wins = [p for p in pnl if p > 0]
    losses = [p for p in pnl if p <= 0]
    peak, mdd = port.curve[0][1], 0.0
    for _, e in port.curve:
        peak = max(peak, e)
        mdd = max(mdd, (peak - e) / peak if peak else 0)
    return {
        "trades": len(trades), "wins": len(wins), "losses": len(losses),
        "win_rate": (len(wins) / len(trades) * 100) if trades else 0.0,
        "net_pnl": sum(pnl), "end_equity": port.equity(),
        "return_pct": (port.equity() / cfg.start_balance - 1) * 100,
        "max_dd_pct": mdd * 100, "fees": sum(t.fees for t in trades),
        "avg_win": (sum(wins) / len(wins)) if wins else 0.0,
        "avg_loss": (sum(losses) / len(losses)) if losses else 0.0,
        "worst": min(pnl) if pnl else 0.0,
        "stuck": sum(1 for t in trades if t.exit_reason == "STUCK_NO_EXIT"),
    }


def _stat_line(name, s):
    return (f"{name:<22} trades={s['trades']:<3} win%={s['win_rate']:5.1f} net=${s['net_pnl']:8.2f} "
            f"ret={s['return_pct']:7.1f}% maxDD={s['max_dd_pct']:5.1f}% worst=${s['worst']:7.2f} stuck={s['stuck']}")


def build(decisions, port, base_decisions, base_port, cfg, seed, multi):
    L = [BANNER, "", f"SOLANA PAPER DESK  seed={seed}  start balance ${cfg.start_balance:.2f} (SIMULATED)", ""]
    funnel = Counter()
    for d in decisions:
        funnel["events received"] += 1
        if d.stage == "SCOUT":
            continue
        funnel["passed scout"] += 1
        if d.stage == "FILTER":
            continue
        funnel["passed filters"] += 1
        if d.verdict == "PAPER-TEST":
            funnel["PAPER-TEST verdict"] += 1
        if d.approval == "APPROVED":
            funnel["human approved"] += 1
        if d.trade_status == "FILLED":
            funnel["simulated fills"] += 1
    L.append("SCREENING FUNNEL")
    for k in ["events received", "passed scout", "passed filters", "PAPER-TEST verdict",
              "human approved", "simulated fills"]:
        L.append(f"  {k:<22}{funnel[k]}")
    rej = Counter(r.split(":")[0] if r.startswith("UNVERIFIED") else r
                  for d in decisions if d.verdict == "REJECT" and d.stage in ("SCOUT", "FILTER") for r in d.reasons)
    L += ["", "REJECTION REASONS (a token can have several)"]
    L += [f"  {k:<26}{v}" for k, v in rej.most_common()]
    wl = Counter(d.verdict for d in decisions if d.stage == "REVIEW")
    L += ["", f"REVIEWER (passed filters, not traded): {dict(wl)}"]
    skips = Counter(d.trade_status for d in decisions if d.stage == "SIM" and d.trade_status != "FILLED")
    L += [f"EXECUTION MISSES: {dict(skips)}", ""]

    L.append("AGENT OUTPUTS - candidates that reached the analyst")
    L.append(f"  {'pool':<14}{'scenario':<14}{'score':<7}{'verdict':<11}{'approval':<10}{'trade'}")
    for d in decisions:
        if d.score is not None:
            L.append(f"  {d.pool_id:<14}{d.scenario:<14}{d.score:<7}{d.verdict:<11}{d.approval or '-':<10}{d.trade_status or '-'}")
    L += ["", "  Dissent preserved on every PAPER-TEST candidate, e.g.:"]
    ex = next((d for d in decisions if d.verdict == "PAPER-TEST"), None)
    if ex:
        L += [f"    {ex.pool_id}: " + " | ".join(ex.dissent)]

    L += ["", "SIMULATED TRADES"]
    L.append(f"  {'pool':<14}{'scenario':<14}{'size':>7}{'exit':>15}{'net P&L':>10}{'ret%':>8}")
    for t in port.closed:
        L.append(f"  {t.pool_id:<14}{t.scenario:<14}{t.size:7.2f}{t.exit_reason:>15}{t.net_pnl:10.2f}{t.ret_pct:8.1f}")
    s, b = stats(port, cfg), stats(base_port, cfg)
    L += ["", "RESULTS (SIMULATED, net of spread, impact, fees, missed fills)",
          _stat_line("DESK (full pipeline)", s), _stat_line("BASELINE (scout only)", b),
          f"  fees paid ${s['fees']:.2f} | avg win ${s['avg_win']:.2f} | avg loss ${s['avg_loss']:.2f} | "
          f"end equity ${s['end_equity']:.2f}"]

    cut = sorted(d.received_at for d in decisions)[len(decisions) // 2] if decisions else 0
    for label, p in (("DESK", port), ("BASELINE", base_port)):
        a = [t for t in p.closed if t.entry_t < cut]
        h = [t for t in p.closed if t.entry_t >= cut]
        L.append(f"  {label}: first-half trades={len(a)} net=${sum(t.net_pnl for t in a):.2f} | "
                 f"HOLDOUT second-half trades={len(h)} net=${sum(t.net_pnl for t in h):.2f}")
    L += ["", f"ACROSS SEEDS (different synthetic markets)", f"  {'seed':<6}{'desk net$':>11}{'baseline net$':>15}{'desk trades':>13}{'desk maxDD%':>13}"]
    for sd, ds, bs in multi:
        L.append(f"  {sd:<6}{ds['net_pnl']:11.2f}{bs['net_pnl']:15.2f}{ds['trades']:13}{ds['max_dd_pct']:13.1f}")
    if multi:
        L.append(f"  mean desk net ${sum(m[1]['net_pnl'] for m in multi)/len(multi):.2f} | "
                 f"mean baseline net ${sum(m[2]['net_pnl'] for m in multi)/len(multi):.2f}")
    L += ["", "HONEST NOTES",
          "  - Mock data: scenario mix and price paths are invented; results say nothing about real markets.",
          "  - Thresholds come from the guides and were NOT tuned on this data.",
          "  - Scorer is a heuristic, not a probability. Cluster/bundled-wallet risk is UNCHECKED.",
          "  - The original $197->$3,789 claim is unverified and is NOT reproduced here.",
          "  - Human approvals are AUTO in this run (use --interactive to approve each one).", "", BANNER]
    return "\n".join(L)
