"""Apply the saturation criterion uniformly to every run in the study.

    python -m analysis.reevaluate_saturation [--dry-run]

WHY THIS EXISTS
---------------
The project's saturation criterion changed once, on 9 Aug 2026, from an
absolute lag threshold to a growth-based one (ANALYSIS_PLAN.md S13). Runs
recorded before that change carry a verdict from the old rule.

Leaving them that way would mean the study judged different runs by different
standards -- which is a far worse problem than the original threshold being
imperfect. A reviewer finding two criteria in one dataset has found a real
flaw. So every run is re-judged here by the single current criterion, whatever
that does to the verdict.

THE CRITERION
-------------
A run is unusable when the generator's median scheduling lag GROWS by more
than 50 ms between the first and last quarter of the run.

Growth rather than magnitude, because a constant offset is harmless fixed
overhead -- the load offered still matches the load intended -- whereas lag
that climbs means the generator is progressively falling behind and the
arrival pattern being delivered has drifted from the Poisson process that was
scheduled.

WHAT THIS DOES NOT TOUCH
------------------------
Exclusions for any other reason -- non-result phases, spot preemption,
infrastructure faults -- are left exactly as they are. Only saturation
verdicts are recomputed.

Nothing is deleted. Runs that change verdict keep a reason string recording
that they were re-judged and why.
"""

from __future__ import annotations

import argparse
import sqlite3
import statistics as st
import sys
from pathlib import Path

from harness.core.arrival import SATURATION_GROWTH_SECONDS, SATURATION_MIN_SAMPLES

REPO = Path(__file__).resolve().parent.parent
DB = REPO / "data" / "working" / "runs.sqlite"

_REASON = (
    "generator saturated: scheduling lag grew {growth:.0f}ms across the run "
    "(threshold {threshold:.0f}ms). Re-judged 9 Aug 2026 under the study's "
    "single saturation criterion; see ANALYSIS_PLAN.md S13."
)


def lag_growth(conn: sqlite3.Connection, run_id: str) -> float | None:
    """Median lag in the last quarter minus the first. None if too few samples."""
    rows = conn.execute(
        "SELECT submitted_offset - scheduled_offset FROM transactions "
        "WHERE run_id = ? AND submitted_offset IS NOT NULL "
        "ORDER BY scheduled_offset",
        (run_id,),
    ).fetchall()
    if len(rows) < SATURATION_MIN_SAMPLES:
        return None
    v = [r[0] for r in rows]
    q = len(v) // 4
    return st.median(v[-q:]) - st.median(v[:q])


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true", help="report changes, write nothing")
    p.add_argument("--db", default=str(DB))
    args = p.parse_args()

    conn = sqlite3.connect(args.db, isolation_level=None)
    runs = conn.execute(
        "SELECT run_id, phase, target_tps, tx_size_usd, invalidated, invalidation_reason "
        "FROM runs ORDER BY phase, target_tps"
    ).fetchall()

    now_invalid = now_valid = unchanged = skipped = 0
    changes: list[str] = []

    for run_id, phase, tps, amount, was_invalid, reason in runs:
        # Only saturation verdicts are ours to revise. Anything excluded for a
        # different reason stays excluded.
        #
        # Matches both the current wording ("generator saturated: scheduling
        # lag grew...") and the superseded 8 Aug magnitude-threshold wording
        # ("p95 scheduling lag ... exceeds the tightened 40ms threshold"),
        # which never contained the word "saturat" and was silently skipped
        # by an earlier version of this check -- leaving runs invalidated
        # under a threshold that no longer exists. Every saturation-related
        # reason recorded by the harness mentions "lag"; the one other reason
        # ever written to this column (a client misconfiguration) does not.
        was_saturation = bool(reason and "lag" in reason.lower())
        if was_invalid and not was_saturation:
            unchanged += 1
            continue

        growth = lag_growth(conn, run_id)
        if growth is None:
            skipped += 1
            continue

        is_saturated = growth > SATURATION_GROWTH_SECONDS

        if is_saturated and not was_invalid:
            now_invalid += 1
            changes.append(f"  NOW INVALID  {phase[:26]:<26} {tps:>5.0f}/sec ${amount:g} "
                           f"lag grew {growth*1000:+.1f}ms")
            if not args.dry_run:
                conn.execute(
                    "UPDATE runs SET invalidated = 1, invalidation_reason = ? WHERE run_id = ?",
                    (_REASON.format(growth=growth * 1000,
                                    threshold=SATURATION_GROWTH_SECONDS * 1000), run_id),
                )
        elif not is_saturated and was_invalid:
            now_valid += 1
            changes.append(f"  NOW VALID    {phase[:26]:<26} {tps:>5.0f}/sec ${amount:g} "
                           f"lag grew {growth*1000:+.1f}ms")
            if not args.dry_run:
                conn.execute(
                    "UPDATE runs SET invalidated = 0, invalidation_reason = NULL "
                    "WHERE run_id = ?", (run_id,),
                )
        else:
            unchanged += 1
            if is_saturated and not args.dry_run:
                # Keep the reason text current even where the verdict is the same.
                conn.execute(
                    "UPDATE runs SET invalidation_reason = ? WHERE run_id = ?",
                    (_REASON.format(growth=growth * 1000,
                                    threshold=SATURATION_GROWTH_SECONDS * 1000), run_id),
                )

    print(f"Re-judged {len(runs)} runs under a single saturation criterion "
          f"(lag growth > {SATURATION_GROWTH_SECONDS*1000:.0f}ms)\n")
    for line in changes:
        print(line)
    if changes:
        print()
    print(f"  verdict changed to INVALID : {now_invalid}")
    print(f"  verdict changed to VALID   : {now_valid}")
    print(f"  unchanged                  : {unchanged}")
    print(f"  too few samples to judge   : {skipped}")

    if args.dry_run:
        print("\n(dry run -- nothing written)")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
