"""Repair two metadata gaps found on 9 Aug 2026, and import node-outage logs.

WHY THIS EXISTS
---------------
Two things that should have been recorded during runs were not:

**1. Which realism techniques were active.** Every run's `config_json` was
written as an empty object. The only surviving record of the test conditions
was the phase name -- a label someone chose, not evidence. A year from now
"phase-2-full-stack" tells a reader nothing about whether packet loss was
injected, at what rate background traffic ran, or how many validators there
were. Results become uninterpretable at exactly the moment the paper needs to
describe them.

**2. Node outages went to a text file, never the database.** The adversarial
script logged every stop and start with a timestamp, but into
`data/working/node_events_*.log` rather than the `node_events` table. Since
the entire purpose of logging outages is correlating them against performance
dips in the transaction data, a log the data cannot be joined to is close to
useless.

WHY BACKFILLING IS LEGITIMATE HERE
----------------------------------
This does not invent data. The realism configuration was constant across the
whole phase, is recorded independently in METHODOLOGY_LOG.md, and is being
copied from there. The node events are being moved from one file we wrote to
another place we wrote -- the timestamps are original.

Backfilled runs are marked with `backfilled: true` in their configuration so a
reader can tell recorded-at-the-time from reconstructed-afterwards. That
distinction matters more than the tidiness of hiding it.

USAGE
    python -m analysis.backfill --realism      # stamp the realism config
    python -m analysis.backfill --node-events  # import outage logs
"""

from __future__ import annotations

import argparse
import glob
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DB = REPO / "data" / "working" / "runs.sqlite"

#: Copied from METHODOLOGY_LOG.md S4. These were the conditions in force for
#: every phase-2-full-stack run.
FULL_STACK_REALISM = {
    "multi_region": {
        "enabled": True,
        "regions": ["us-east4", "asia-south1", "asia-southeast1", "europe-west2"],
        "validators": 4,
    },
    "injected_impairment": {
        "enabled": True,
        "scope": "validator-to-validator only; measurement path unimpaired",
        "per_validator": [
            {"region": "us-east4", "delay_ms": 20, "jitter_ms": 4, "loss_pct": 0.10},
            {"region": "asia-south1", "delay_ms": 45, "jitter_ms": 12, "loss_pct": 0.40},
            {"region": "asia-southeast1", "delay_ms": 40, "jitter_ms": 10, "loss_pct": 0.30},
            {"region": "europe-west2", "delay_ms": 25, "jitter_ms": 6, "loss_pct": 0.15},
        ],
    },
    "background_traffic": {
        "enabled": True,
        "base_tps": 60, "peak_tps": 115, "mean_tps": 88,
        "tx_type": "native transfer, 21000 gas",
        "calibrated_to": "Polygon mainnet ~87 tx/sec (7.5M/day)",
    },
    "hardware_matched": {
        "enabled": True, "machine_type": "n2-standard-8", "vcpu": 8, "ram_gb": 32,
        "note": "CPU/RAM matched to published Polygon validator specs; "
                "storage deliberately not matched",
    },
    "adversarial_nodes": {"enabled": False, "note": "separate arm"},
    "repeats": 5,
    "backfilled": True,
    "backfill_source": "METHODOLOGY_LOG.md S4",
    "backfill_date": "2026-08-09",
}

#: Conditions during the Session A shake-out, where techniques were added one
#: at a time. Each phase had a different subset active.
SESSION_A = {
    "step0-baseline-hw": {"multi_region": True, "hardware_matched": True,
                          "injected_impairment": False, "background_traffic": False},
    "step1-impairment": {"multi_region": True, "hardware_matched": True,
                         "injected_impairment": True, "background_traffic": False},
    "step3-background": {"multi_region": True, "hardware_matched": True,
                         "injected_impairment": True, "background_traffic": True},
    "step4-adversarial": {"multi_region": True, "hardware_matched": True,
                          "injected_impairment": True, "background_traffic": True,
                          "adversarial_nodes": True},
}


def backfill_realism(conn: sqlite3.Connection) -> int:
    updated = 0
    # The adversarial arm ran the identical stack with node failures ON. It is
    # listed separately rather than folded in because `adversarial_nodes` is
    # exactly the variable that distinguishes the two arms -- the whole reason
    # claude.md S5 #6 keeps them apart is so "degrades under load" can be told
    # from "degrades under node failure".
    adversarial = dict(FULL_STACK_REALISM)
    adversarial["adversarial_nodes"] = {
        "enabled": True,
        "nodes_affected": 1,
        "of_total": 4,
        "note": "one validator at a time cycled offline; ~130x more hostile "
                "than real Polygon -- see METHODOLOGY_LOG.md S4 technique #6",
    }

    for phase, realism in [("phase-2-full-stack", FULL_STACK_REALISM),
                           ("phase-2-adversarial", adversarial)] + [
        (p, {**v, "backfilled": True, "backfill_source": "METHODOLOGY_LOG.md S4",
             "backfill_date": "2026-08-09"})
        for p, v in SESSION_A.items()
    ]:
        rows = conn.execute(
            "SELECT run_id, config_json FROM runs WHERE phase = ?", (phase,)
        ).fetchall()
        for run_id, cfg_json in rows:
            try:
                cfg = json.loads(cfg_json) if cfg_json else {}
            except json.JSONDecodeError:
                cfg = {}
            # Never overwrite a realism record captured at run time -- that one
            # is evidence, this one is reconstruction.
            if cfg.get("realism"):
                continue
            cfg["realism"] = realism
            conn.execute("UPDATE runs SET config_json = ? WHERE run_id = ?",
                         (json.dumps(cfg, sort_keys=True), run_id))
            updated += 1
    return updated


def import_node_events(conn: sqlite3.Connection) -> int:
    """Move adversarial outage logs into the table the data can be joined to.

    Each log line is: <ISO timestamp>\\t<node>\\t<offline|online>\\t<source>

    Events are matched to whichever run was in flight at that wall-clock
    moment. Runs record `t0_wall` (epoch at start) and `ended_wall`, so an
    event's offset within its run is recoverable -- which is what makes
    correlating an outage against a latency spike possible at all.
    """
    logs = sorted(glob.glob(str(REPO / "data" / "working" / "node_events_*.log")))
    if not logs:
        print("  no node event logs found")
        return 0

    runs = conn.execute(
        "SELECT run_id, t0_wall, ended_wall FROM runs "
        "WHERE ended_wall IS NOT NULL ORDER BY t0_wall"
    ).fetchall()

    imported = unmatched = 0
    for path in logs:
        for line in Path(path).read_text().splitlines():
            parts = line.strip().split("\t")
            if len(parts) != 4:
                continue
            stamp, node, event, source = parts
            # Tolerate a malformed fractional part. The generating script used
            # `date +%...%3N`, which the remote `date` does not support -- it
            # emitted the literal characters "3N", producing timestamps like
            # "2026-08-08T19:20:04.3NZ". Second precision is ample here:
            # outages last 15-45 seconds, so sub-second accuracy adds nothing
            # to correlating them against latency spikes.
            clean = stamp.split(".")[0].rstrip("Z")
            try:
                ts = datetime.fromisoformat(clean).replace(
                    tzinfo=timezone.utc).timestamp()
            except ValueError:
                continue

            run = next((r for r in runs if r[1] <= ts <= (r[2] or r[1])), None)
            if run is None:
                unmatched += 1
                continue
            conn.execute(
                "INSERT INTO node_events (run_id, offset, node_id, event, source) "
                "VALUES (?,?,?,?,?)",
                (run[0], ts - run[1], node, event, source),
            )
            imported += 1

    if unmatched:
        print(f"  {unmatched} events fell outside any run window (kept in the log files)")
    return imported


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--realism", action="store_true", help="stamp the realism configuration")
    p.add_argument("--node-events", action="store_true", help="import outage logs")
    p.add_argument("--db", default=str(DB))
    args = p.parse_args()

    if not (args.realism or args.node_events):
        p.error("choose --realism, --node-events, or both")

    conn = sqlite3.connect(args.db, isolation_level=None)

    if args.realism:
        n = backfill_realism(conn)
        print(f"realism configuration stamped onto {n} runs")

    if args.node_events:
        n = import_node_events(conn)
        print(f"node outage events imported: {n}")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
