# Solana Paper Desk (PAPER ONLY / SIMULATED)

Local, stdlib-only (Python 3.11+) research pipeline: Scout -> Filter -> Analyst -> Reviewer -> Approval -> Simulator/Risk -> Report.
No wallet, keys, network or live-trading code exists (a test enforces this).

    python3 -m desk.run                 # full report, 5-seed robustness table
    python3 -m desk.run --interactive   # approve each simulated buy yourself
    python3 -m desk.run --balance 197 --seed 2 --events 200
    python3 -m unittest discover -s tests

Outputs in `output/`: report.txt, trades.csv, decisions.csv (full agent audit log), desk.db (SQLite).

Limits: data is synthetic; scorer is a heuristic, not a probability; cluster/bundled-wallet risk is unchecked;
thresholds come from the source guides and were not tuned. Results are not evidence of real-world profit.

## Live-data paper trading (read-only public data, still SIMULATED)

    python3 -m desk.live_run --minutes 120 --poll 60            # auto-approves (stand-in for you)
    python3 -m desk.live_run --minutes 120 --interactive        # you approve every simulated buy

Data: DexScreener + RugCheck public GET endpoints (no keys, no wallet). Output: output/live_report.txt,
live_log.jsonl (every decision), live_trades.csv. Only desk/live.py touches the network (a test enforces it).
Caveats: `sellable` is a RugCheck-flag PROXY (no sell simulation); `unique_buyers` is the 1h buy count;
boosted tokens are paid promotion; bundled-wallet risk is UNCHECKED; fills at displayed price are optimistic.

## Claude Code as the Analyst (no API key; uses your Claude Code login)

    python3 -m desk.live_run --minutes 120 --scorer claude --llm-budget 30 --model haiku

Only tokens that already passed the deterministic filters are scored, from numbers only. Invalid output, errors or an
exhausted budget fall back to the formula (flagged). Both scores are logged in live_log.jsonl for comparison.

## Learn from mistakes (free, offline)

    python3 -m desk.record --minutes 240      # collect live data (tokens + 1-min prices), no trading
    python3 -m desk.analyze                   # loss classification, filter check, walk-forward tuning
