#!/usr/bin/env python3
"""Import node outage events into the database, attributed to the right runs.

Runs ON THE GENERATOR.

WHY THIS EXISTS AS A SCRIPT RATHER THAN A MANUAL STEP
-----------------------------------------------------
`analysis/backfill.py` opens by recording that phase 2's node outages "went to a
text file, never the database" -- the adversarial arm's whole point is the
difference between two arms, and the events that define one of them sat in
`data/working/node_events_*.log` where no analysis could see them. That had to be
corrected afterwards.

The correction is not to remember harder. `analysis/export.py` keys two of its
exclusion rules on `node_events`, and an empty table means those rules silently
never fire: a node failure outside the adversarial arm stops being detected as
an infrastructure fault, and the adversarial runs stop being distinguishable
from the clean ones.

WHAT ATTRIBUTION MEANS HERE
---------------------------
`node_events.offset` is seconds from the START OF THE RUN the event fell in, so
an outage can be lined up against the per-second throughput series. An event is
attributed to a run when its wall-clock time lies between that run's `t0_wall`
and `ended_wall`. Events falling between runs are kept with the run that was
about to start -- an outage in the 20-second gap still shapes the beginning of
the next run -- and flagged with a negative offset so that is visible rather
than hidden.

USAGE
    ./.venv/bin/python scripts/near_import_events.py --events /tmp/near_node_events.tsv
    ... --phase phase-4-adversarial --dry-run
"""

from __future__ import annotations

import argparse
import calendar
import sqlite3
import sys
import time
from pathlib import Path

DB = "/opt/benchmark/data/working/runs.sqlite"


def parse_stamp(s: str) -> float:
    """UTC ISO8601 with a trailing Z -> epoch seconds."""
    return calendar.timegm(time.strptime(s, "%Y-%m-%dT%H:%M:%SZ"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--events", required=True)
    ap.add_argument("--db", default=DB)
    ap.add_argument("--phase", default="phase-4-adversarial")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    path = Path(args.events)
    if not path.exists():
        print(f"missing {path}", file=sys.stderr)
        return 1

    rows = []
    for line in path.read_text().splitlines():
        parts = line.strip().split("\t")
        if len(parts) != 4:
            continue
        ts, node_id, event, source = parts
        try:
            rows.append((parse_stamp(ts), node_id, event, source))
        except ValueError:
            print(f"  unparseable timestamp, skipped: {ts}")
    print(f"{len(rows)} events in {path}")
    if not rows:
        return 1

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    runs = conn.execute(
        "SELECT run_id, t0_wall, ended_wall, target_tps, repeat_index FROM runs "
        "WHERE phase = ? AND architecture = 'near' ORDER BY t0_wall",
        (args.phase,)).fetchall()
    print(f"{len(runs)} runs in {args.phase}")
    if not runs:
        print("no runs to attribute events to -- import the events AFTER the arm",
              file=sys.stderr)
        return 1

    existing = conn.execute(
        "SELECT COUNT(*) FROM node_events WHERE run_id IN (%s)"
        % ",".join("?" * len(runs)), [r["run_id"] for r in runs]).fetchone()[0]
    if existing:
        print(f"REFUSING: {existing} events already attributed to these runs. "
              f"Importing again would double-count every outage.", file=sys.stderr)
        return 1

    to_insert, unattributed = [], 0
    for t, node_id, event, source in rows:
        placed = False
        for r in runs:
            end = r["ended_wall"] or (r["t0_wall"] + 400)
            if r["t0_wall"] <= t <= end:
                to_insert.append((r["run_id"], t - r["t0_wall"], node_id, event, source))
                placed = True
                break
        if placed:
            continue
        # Between runs: attribute to the next run that started, with a negative
        # offset. An outage in the inter-run gap still shapes the start of the
        # next run, and dropping it would understate the arm's fault load.
        nxt = next((r for r in runs if r["t0_wall"] > t), None)
        if nxt is not None:
            to_insert.append((nxt["run_id"], t - nxt["t0_wall"], node_id, event, source))
        else:
            unattributed += 1

    print(f"  attributed {len(to_insert)}, unattributable {unattributed}")
    inside = sum(1 for x in to_insert if x[1] >= 0)
    print(f"  of those, {inside} inside a run and {len(to_insert)-inside} in a gap "
          f"before one (negative offset)")

    if args.dry_run:
        print("\nDRY RUN -- nothing written")
        return 0

    conn.executemany(
        "INSERT INTO node_events (run_id, offset, node_id, event, source) "
        "VALUES (?, ?, ?, ?, ?)", to_insert)
    conn.commit()

    check = conn.execute(
        "SELECT COUNT(*) FROM node_events WHERE run_id IN (%s)"
        % ",".join("?" * len(runs)), [r["run_id"] for r in runs]).fetchone()[0]
    ok = check == len(to_insert)
    print(f"\nnode_events now holds {check} rows for this arm "
          f"({'ok' if ok else '*** EXPECTED %d ***' % len(to_insert)})")
    per_run = conn.execute(
        "SELECT run_id, COUNT(*) n FROM node_events WHERE run_id IN (%s) "
        "GROUP BY run_id" % ",".join("?" * len(runs)),
        [r["run_id"] for r in runs]).fetchall()
    empty = len(runs) - len(per_run)
    if empty:
        print(f"  NOTE: {empty} of {len(runs)} runs carry no outage event. In an "
              f"arm defined by node failure that is worth checking, not assuming.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
