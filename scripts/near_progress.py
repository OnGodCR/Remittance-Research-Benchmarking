#!/usr/bin/env python3
"""Phase 4 progress and health, from the database. Runs ON THE GENERATOR.

WHY A FILE
Every attempt to ask this question through `gcloud ssh --command "python -c ..."`
has been mangled by quoting across three shell layers -- an f-string containing
a quoted dict key is precisely the shape that breaks, and it broke three times
in one night. The traps file says it plainly: write a script, copy it, run it.

WHAT IT ANSWERS
  - how many runs are genuinely complete (ended AND not invalidated)
  - what the newest runs actually recorded, rather than what was intended
  - whether the cross-shard mix is holding near (S-1)/S, which is the silent
    failure that makes a sharding measurement worthless while looking healthy
  - which realism conditions the runs claim, so the claim can be checked against
    the cluster rather than believed
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time

DB = "/opt/benchmark/data/working/runs.sqlite"
MATRIX_TOTAL = 140


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=DB)
    ap.add_argument("--phase", default="phase-4-full-stack")
    ap.add_argument("--recent", type=int, default=5)
    args = ap.parse_args()

    c = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row

    done = c.execute(
        "SELECT COUNT(*) FROM runs WHERE phase=? AND ended_wall IS NOT NULL "
        "AND invalidated=0", (args.phase,)).fetchone()[0]
    invalid = c.execute(
        "SELECT COUNT(*) FROM runs WHERE phase=? AND invalidated=1",
        (args.phase,)).fetchone()[0]
    print(f"PROGRESS: {done}/{MATRIX_TOTAL} valid completed "
          f"({100*done/MATRIX_TOTAL:.0f}%), {invalid} invalidated\n")

    print(f"newest {args.recent} runs:")
    rows = c.execute(
        "SELECT run_id,tx_size_usd,target_tps,repeat_index,ended_wall,"
        "invalidated,t0_wall FROM runs WHERE phase=? ORDER BY t0_wall DESC "
        "LIMIT ?", (args.phase, args.recent)).fetchall()
    for r in rows:
        st = dict(c.execute(
            "SELECT status,COUNT(*) FROM transactions WHERE run_id=? "
            "GROUP BY status", (r["run_id"],)).fetchall())
        x = c.execute(
            "SELECT COUNT(*) n, AVG(confirmed_offset-submitted_offset) lat, "
            "AVG(gas_used) g, AVG(route_hops) cs FROM transactions "
            "WHERE run_id=? AND status='confirmed'", (r["run_id"],)).fetchone()
        state = ("invalid" if r["invalidated"]
                 else "done" if r["ended_wall"] else "RUNNING")
        when = time.strftime("%H:%M:%S", time.gmtime(r["t0_wall"]))
        amount = r["tx_size_usd"]
        tps = r["target_tps"]
        print(f"  {when} ${amount:>3.0f} @ {tps:>3.0f}/s rep{r['repeat_index']} "
              f"{state:8} {st}")
        if x["n"]:
            cs = 100 * x["cs"] if x["cs"] is not None else float("nan")
            print(f"      settled {x['n']:,}  latency {x['lat']:.2f}s  "
                  f"gas {x['g']:,.0f}  cross-shard {cs:.1f}%")

    # Cross-shard mix, VALID runs only. Including invalidated runs mixes in the
    # old 64-account pool with a different shard distribution and reports a
    # false alarm -- which it did, at 62.9% against a true 74.6%.
    d = dict(c.execute(
        "SELECT t.route_hops, COUNT(*) FROM transactions t "
        "JOIN runs r ON t.run_id=r.run_id "
        "WHERE r.phase=? AND r.invalidated=0 AND t.status='confirmed' "
        "GROUP BY t.route_hops", (args.phase,)).fetchall())
    same, cross = d.get(0, 0), d.get(1, 0)
    if same + cross:
        share = 100 * cross / (same + cross)
        ok = abs(share - 75) < 10
        print(f"\ncross-shard mix (valid runs): {share:.1f}% of {same+cross:,} "
              f"payments  {'OK' if ok else '*** OFF EXPECTATION (want ~75%) ***'}")
    else:
        print("\ncross-shard mix: no confirmed payments in valid runs yet")

    r = c.execute("SELECT config_json FROM runs WHERE phase=? "
                  "ORDER BY t0_wall DESC LIMIT 1", (args.phase,)).fetchone()
    realism = (json.loads(r["config_json"]).get("realism") or {}) if r and r["config_json"] else {}
    if realism:
        flags = ", ".join(f"{k}={v.get('enabled')}" for k, v in realism.items()
                          if isinstance(v, dict) and "enabled" in v)
        print(f"conditions recorded on the newest run: {flags}")
    else:
        print("*** newest run records NO realism conditions ***")
    return 0


if __name__ == "__main__":
    sys.exit(main())
