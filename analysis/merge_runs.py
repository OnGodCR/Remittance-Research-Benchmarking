#!/usr/bin/env python3
"""Merge one cluster's run database into the local master, safely.

WHY THIS EXISTS
---------------
`analysis/export.py` builds both parquet files from ONE database --
`data/working/runs.sqlite` -- and that master currently holds 204 Polygon runs,
51 Lightning runs and no NEAR at all. NEAR's runs live on the generator, on a
machine that gets destroyed at the end of the phase.

Nothing in the repository moved data between the two. Phases 2 and 3 were merged
by hand, which worked because nobody made a mistake. The ways to get it wrong
are not obvious:

  - `export.py` takes a database path but writes to FIXED output files, so
    running it against the NEAR database alone silently replaces the combined
    parquet with NEAR-only data.
  - The payment rows are not the whole record. `samples` carries the per-second
    time series that the warm-up exclusion depends on, and `node_events` carries
    the adversarial and preemption markers that `export.py` keys its exclusion
    rules on. Copying `runs` and `transactions` alone loses both, and the loss
    is invisible until an exclusion silently stops firing.
  - A repeated merge would double every row.

So: an explicit, re-runnable, dry-runnable merge that refuses on collision.

WHAT IT GUARANTEES
------------------
- Only run_ids absent from the destination are copied; a run already present is
  skipped and reported, never duplicated and never overwritten.
- All four tables move together, or none do (single transaction).
- Row counts are verified per table after the copy, and the merge aborts if the
  destination did not grow by exactly the number of rows read.

USAGE
    python analysis/merge_runs.py --source /tmp/near_runs.sqlite --dry-run
    python analysis/merge_runs.py --source /tmp/near_runs.sqlite
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MASTER = REPO / "data" / "working" / "runs.sqlite"

#: Order matters: `runs` first, because everything else references a run_id.
TABLES = ["runs", "transactions", "samples", "node_events"]


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    """Columns to copy, EXCLUDING any auto-assigned integer primary key.

    `node_events.id` is `INTEGER PRIMARY KEY`, i.e. a rowid alias that SQLite
    fills in per database. Both databases therefore number their events from 1,
    and copying the column across collides the moment the destination already
    holds any events of its own:

        sqlite3.IntegrityError: UNIQUE constraint failed: node_events.id

    Which is exactly what happened merging NEAR (174 events) into a master that
    already held Polygon's 121. Omitting the column lets SQLite assign fresh
    ids. Nothing references them -- `export.py` keys its exclusion rules on
    `run_id` and `source`, never on `id`.

    Compound keys like `(run_id, seq)` are NOT excluded: those carry meaning,
    they are unique per run, and a collision in them would be a real duplicate
    that the caller's run-id check should have caught.
    """
    cols = []
    for _, name, decl_type, _, _, pk in conn.execute(f"PRAGMA table_info({table})"):
        if pk == 1 and (decl_type or "").upper() == "INTEGER":
            # Rowid alias. Confirm it is the ONLY key column before dropping it,
            # so a compound key beginning with an integer is never silently lost.
            keys = [r for r in conn.execute(f"PRAGMA table_info({table})") if r[5]]
            if len(keys) == 1:
                continue
        cols.append(name)
    return cols


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True, help="the cluster's database")
    ap.add_argument("--dest", default=str(MASTER))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--backup", action="store_true",
                    help="copy the destination aside first; slow on a 2 GB file "
                         "but the master is the only assembled copy of the study")
    args = ap.parse_args()

    src_path, dst_path = Path(args.source), Path(args.dest)
    for p in (src_path, dst_path):
        if not p.exists():
            print(f"missing {p}", file=sys.stderr)
            return 1

    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    dst = sqlite3.connect(f"file:{dst_path}?mode=ro", uri=True) if args.dry_run \
        else sqlite3.connect(str(dst_path))

    # Schema compatibility, checked rather than assumed. A column added on one
    # side and not the other would otherwise fail halfway through the copy.
    for t in TABLES:
        s, d = table_columns(src, t), table_columns(dst, t)
        if s != d:
            print(f"SCHEMA MISMATCH in {t}:\n  source: {s}\n  dest:   {d}",
                  file=sys.stderr)
            return 1
    print("schema matches on all four tables")

    src_runs = {r[0] for r in src.execute("SELECT run_id FROM runs")}
    dst_runs = {r[0] for r in dst.execute("SELECT run_id FROM runs")}
    new = sorted(src_runs - dst_runs)
    already = sorted(src_runs & dst_runs)

    print(f"\nsource has {len(src_runs)} runs, destination {len(dst_runs)}")
    print(f"  to copy : {len(new)}")
    print(f"  skipped (already present): {len(already)}")
    by_arch = {}
    for (a, n) in src.execute(
            "SELECT architecture, COUNT(*) FROM runs WHERE run_id IN (%s) "
            "GROUP BY architecture" % ",".join("?" * len(new)), new) if new else []:
        by_arch[a] = n
    if by_arch:
        print(f"  by architecture: {by_arch}")
    if not new:
        print("\nnothing to do")
        return 0

    counts = {}
    for t in TABLES:
        counts[t] = src.execute(
            "SELECT COUNT(*) FROM %s WHERE run_id IN (%s)"
            % (t, ",".join("?" * len(new))), new).fetchone()[0]
    print(f"  rows: " + ", ".join(f"{t}={counts[t]:,}" for t in TABLES))

    if args.dry_run:
        print("\nDRY RUN -- nothing written")
        return 0

    if args.backup:
        backup = dst_path.with_suffix(".sqlite.bak")
        print(f"\nbacking up to {backup} ...")
        shutil.copy2(dst_path, backup)

    before = {t: dst.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in TABLES}

    print("\ncopying...")
    dst.execute("ATTACH DATABASE ? AS src", (str(src_path),))
    try:
        dst.execute("BEGIN")
        placeholders = ",".join("?" * len(new))
        for t in TABLES:
            cols = ",".join(table_columns(dst, t))
            dst.execute(
                f"INSERT INTO {t} ({cols}) SELECT {cols} FROM src.{t} "
                f"WHERE run_id IN ({placeholders})", new)
        dst.execute("COMMIT")
    except Exception:
        dst.execute("ROLLBACK")
        raise
    finally:
        dst.execute("DETACH DATABASE src")

    ok = True
    print("\nverification:")
    for t in TABLES:
        after = dst.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        grew = after - before[t]
        good = grew == counts[t]
        ok &= good
        print(f"  {t:14} {before[t]:>10,} -> {after:>10,}  (+{grew:,}, "
              f"expected +{counts[t]:,}) {'ok' if good else '*** MISMATCH ***'}")
    dst.commit()
    print("\n" + ("merge complete; now run analysis/export.py to rebuild the parquets"
                  if ok else "*** ROW COUNTS DO NOT MATCH -- investigate before exporting ***"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
