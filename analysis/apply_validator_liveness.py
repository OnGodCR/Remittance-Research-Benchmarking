#!/usr/bin/env python3
"""Invalidate any run measured while the validator set was not whole.

WHAT THIS ENFORCES
------------------
claude.md S8: a run touched by spot preemption is auto-invalidated and
re-queued, because a validator disappearing mid-run is the adversarial arm's
condition (technique #6) appearing inside the clean baseline. The deleted RESUME_HERE.md (in git history)
recorded the same rule for phases 2 and 3.

`scripts/near_liveness_watch.py` samples the chain every ~10s and writes one
JSON object per sample with an `ok` flag: True only when the full validator set
is present and every shard has at least two producers. This script cross-
references those samples against each run's wall-clock window and invalidates
anything that overlaps a degraded sample.

TWO REASONS A RUN IS REJECTED, AND WHY BOTH ARE NEEDED
------------------------------------------------------
1. `degraded`  -- at least one sample inside the run window had ok=False. The
   network was demonstrably short a validator, or a shard was down to one
   producer, while the run was being measured.

2. `unproven`  -- the samples do not cover the run window densely enough to
   show it was healthy: either no samples at all, or a gap longer than
   --max-gap. This is deliberately strict. Absence of evidence of degradation
   is not evidence of health, and a study that discards only the failures it
   happened to observe is making a claim its data does not support. Treating
   gaps as unproven is the conservative direction: it can throw away a run that
   was actually fine, but it can never keep one that was not.

NOTHING IS DELETED. Runs are marked `invalidated` with the reason recorded, per
the standing rule that a reviewer must be able to see the untouched data beside
the cleaned data. A `node_events` row with source='preemption' is also written
for each degraded run, which is the signal `analysis/export.py` already keys on
-- so the existing export path picks these up without modification.

USAGE
    python analysis/apply_validator_liveness.py \
        --db data/working/runs.sqlite \
        --liveness data/working/validator_liveness.jsonl \
        --phase phase-4-full-stack
    # add --dry-run to see what would happen without writing
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

REASON_DEGRADED = "validator set incomplete during run (liveness watch)"
REASON_UNPROVEN = "validator set health unproven during run (liveness gap)"


def load_samples(path: Path) -> list[dict]:
    samples = []
    if not path.exists():
        return samples
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                s = json.loads(line)
            except json.JSONDecodeError:
                # A torn final line is expected if the watcher was killed
                # mid-write. Skip it rather than abort the whole audit.
                continue
            if "t" in s:
                samples.append(s)
    samples.sort(key=lambda s: s["t"])
    return samples


def sample_ok(s: dict, arm: str, expected_validators: int, min_per_shard: int,
              min_peers: int) -> bool:
    """Is this sample acceptable FOR THIS ARM?

    The verdict is recomputed here rather than read from the watcher's own `ok`
    field, because the two arms are not judged by the same rule.

    The baseline requires the network to be whole in every sense, including a
    full peer count -- that is what catches a validator which has gone dark but
    is still listed in the set, which the protocol will keep listing for up to
    two epochs.

    The adversarial arm takes a validator offline deliberately, so the peer
    count is SUPPOSED to dip. Applying the baseline rule there would invalidate
    every run in the arm for successfully doing the thing the arm exists to do.
    What still must hold is that the validator set itself is intact and every
    shard has its producers -- i.e. nothing was expelled mid-arm, which would
    shrink the network permanently and make later runs incomparable to earlier
    ones.
    """
    if s.get("error"):
        return False
    if s.get("syncing"):
        return False
    if s.get("validators", 0) < expected_validators:
        return False
    shards = s.get("shards") or {}
    if not shards or any(n < min_per_shard for n in shards.values()):
        return False
    if arm != "adversarial":
        peers = s.get("peers")
        if peers is None or peers < min_peers:
            return False
    return True


def judge(run_start: float, run_end: float, samples: list[dict],
          max_gap: float, arm: str = "baseline",
          expected_validators: int = 8, min_per_shard: int = 2,
          min_peers: int = 7) -> tuple[str | None, dict]:
    """Return (reason, detail) -- reason is None when the run is acceptable."""
    window = [s for s in samples if run_start <= s["t"] <= run_end]

    bad = [s for s in window
           if not sample_ok(s, arm, expected_validators, min_per_shard, min_peers)]
    if bad:
        first = bad[0]
        return REASON_DEGRADED, {
            "n_bad": len(bad),
            "n_samples": len(window),
            "first_bad_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                           time.gmtime(first["t"])),
            "validators": first.get("validators"),
            "shards": first.get("shards"),
            "peers": first.get("peers"),
            "error": first.get("error"),
        }

    if not window:
        return REASON_UNPROVEN, {"n_samples": 0, "gap": run_end - run_start}

    # Coverage check: the run window must be bracketed by samples with no gap
    # longer than max_gap anywhere inside it, including the lead-in from before
    # the run started and the trail-out after it ended.
    before = [s["t"] for s in samples if s["t"] <= run_start]
    after = [s["t"] for s in samples if s["t"] >= run_end]
    edges = ([max(before)] if before else []) + [s["t"] for s in window] \
        + ([min(after)] if after else [])
    if not before or not after:
        return REASON_UNPROVEN, {
            "n_samples": len(window),
            "detail": "run window not bracketed by samples on both sides",
        }
    worst = max(b - a for a, b in zip(edges, edges[1:]))
    if worst > max_gap:
        return REASON_UNPROVEN, {
            "n_samples": len(window),
            "worst_gap_seconds": round(worst, 1),
        }

    return None, {"n_samples": len(window)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/working/runs.sqlite")
    ap.add_argument("--liveness", default="data/working/validator_liveness.jsonl")
    ap.add_argument("--phase", default=None,
                    help="restrict to one phase; default is every NEAR run")
    ap.add_argument("--max-gap", type=float, default=120.0,
                    help="longest tolerated gap between samples, seconds")
    ap.add_argument("--expected-validators", type=int, default=8)
    ap.add_argument("--min-per-shard", type=int, default=2)
    ap.add_argument("--min-peers", type=int, default=7,
                    help="baseline runs only; the adversarial arm is exempt "
                         "because it takes a validator offline on purpose")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    samples = load_samples(Path(args.liveness))
    print(f"{len(samples)} liveness samples from {args.liveness}")
    if samples:
        span = (time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(samples[0]['t'])),
                time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(samples[-1]['t'])))
        n_bad = sum(1 for s in samples if not s.get("ok"))
        print(f"  covering {span[0]} .. {span[1]}, {n_bad} flagged by the "
              f"watcher (arm-specific rules applied per run below)")

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    sql = ("SELECT run_id, phase, arm, tx_size_usd, target_tps, repeat_index, "
           "t0_wall, ended_wall, invalidated, invalidation_reason "
           "FROM runs WHERE architecture = 'near' AND ended_wall IS NOT NULL")
    params: tuple = ()
    if args.phase:
        sql += " AND phase = ?"
        params = (args.phase,)
    rows = conn.execute(sql + " ORDER BY t0_wall", params).fetchall()
    print(f"{len(rows)} finished NEAR runs to audit"
          f"{' in ' + args.phase if args.phase else ''}\n")

    counts = {"kept": 0, "already": 0, REASON_DEGRADED: 0, REASON_UNPROVEN: 0}
    for r in rows:
        if r["invalidated"]:
            counts["already"] += 1
            continue
        reason, detail = judge(r["t0_wall"], r["ended_wall"], samples,
                               args.max_gap, arm=r["arm"] or "baseline",
                               expected_validators=args.expected_validators,
                               min_per_shard=args.min_per_shard,
                               min_peers=args.min_peers)
        label = (f"[{r['arm']}] ${r['tx_size_usd']:g} @ {r['target_tps']:g}/sec "
                 f"rep {r['repeat_index']}")
        if reason is None:
            counts["kept"] += 1
            continue

        counts[reason] += 1
        print(f"  INVALIDATE {label}: {reason}")
        print(f"              {json.dumps(detail)}")
        if args.dry_run:
            continue

        conn.execute(
            "UPDATE runs SET invalidated = 1, invalidation_reason = ? "
            "WHERE run_id = ?", (reason, r["run_id"]))
        if reason == REASON_DEGRADED:
            # export.py drops any run with a preemption node_event. Writing one
            # here means the existing export path needs no change, and the
            # exclusion is visible in the same place as every other one.
            conn.execute(
                "INSERT INTO node_events (run_id, offset, node_id, event, source) "
                "VALUES (?, ?, ?, ?, ?)",
                (r["run_id"], 0.0, "validator-set", "offline", "preemption"))

    if not args.dry_run:
        conn.commit()
    conn.close()

    print(f"\nkept {counts['kept']}, already invalid {counts['already']}, "
          f"newly invalidated {counts[REASON_DEGRADED]} degraded + "
          f"{counts[REASON_UNPROVEN]} unproven"
          f"{'  (DRY RUN, nothing written)' if args.dry_run else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
