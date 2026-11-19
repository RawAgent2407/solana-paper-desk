# Solana Paper Desk — PLAN (PAPER ONLY / SIMULATED)

Goal: local pipeline Scout -> Filter -> Analyst -> Reviewer -> Approval -> Simulator/Risk -> Logger/Report.
Stdlib-only Python 3.11+. No wallet, keys, swap client, or live trading code exists in this package.

Rules
- Deterministic code does ALL safety filtering. Missing/unverifiable data => REJECT.
- Scorer is a transparent heuristic (mock); NOT a probability of profit.
- Decision code sees only the snapshot at observation time; price paths are used only by the
  simulator AFTER a simulated entry delay (no look-ahead).
- Costs modeled: spread (from liquidity), price impact, 1% fee/side, latency, missed fills, stuck exits.
- Position cap 8% equity, exposure cap 40%, one entry per token, -6% stop on 1-min close, +12% trail 6%.
- Everything is labeled SIMULATED. Thresholds are fixed from the guide and never tuned on the data.

Validation: chronological in-sample / holdout halves, baseline (scout-only, no filters), multi-seed runs.
Output: CLI report + output/report.txt, trades.csv, decisions.csv, desk.db.
