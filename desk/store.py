import csv
import json
import sqlite3
from dataclasses import asdict


def save(outdir, decisions, port):
    db = sqlite3.connect(f"{outdir}/desk.db")
    db.executescript("""
    DROP TABLE IF EXISTS decisions; DROP TABLE IF EXISTS trades; DROP TABLE IF EXISTS equity;
    CREATE TABLE decisions(idx, pool_id, symbol, scenario, received_at, stage, verdict, reasons,
        score, rationale, dissent, approval, trade_status);
    CREATE TABLE trades(pool_id, symbol, scenario, entry_t, exit_t, size, entry_price, exit_price,
        exit_reason, fees, net_pnl, ret_pct);
    CREATE TABLE equity(t, equity);""")
    for d in decisions:
        r = asdict(d)
        for k in ("reasons", "rationale", "dissent"):
            r[k] = json.dumps(r[k])
        db.execute("INSERT INTO decisions VALUES(:idx,:pool_id,:symbol,:scenario,:received_at,:stage,"
                   ":verdict,:reasons,:score,:rationale,:dissent,:approval,:trade_status)", r)
    for t in port.closed:
        db.execute("INSERT INTO trades VALUES(:pool_id,:symbol,:scenario,:entry_t,:exit_t,:size,"
                   ":entry_price,:exit_price,:exit_reason,:fees,:net_pnl,:ret_pct)", asdict(t))
    db.executemany("INSERT INTO equity VALUES(?,?)", port.curve)
    db.commit()
    db.close()
    with open(f"{outdir}/trades.csv", "w", newline="") as f:
        rows = [asdict(t) for t in port.closed]
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    with open(f"{outdir}/decisions.csv", "w", newline="") as f:
        rows = [asdict(d) for d in decisions]
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            for k in ("reasons", "rationale", "dissent"):
                r[k] = "; ".join(r[k])
            w.writerow(r)
