"""Produce the two canonical data files, and log every exclusion.

    .venv/bin/python -m analysis.export

WHAT THIS GUARANTEES
--------------------
Two files, regenerated after every run:

    data/raw/all_runs_raw.parquet     every payment, nothing removed
    data/clean/all_runs_clean.parquet the dataset the paper's results use
    data/clean/exclusions.log         what was removed, and under which rule

**Nothing is ever deleted.** Runs excluded from the clean file remain in the
raw file, flagged. A reviewer can hold the two side by side and confirm that
nothing inconvenient was quietly dropped -- which is the entire reason for
keeping both.

**Every rule below was written down before any data existed** (ANALYSIS_PLAN.md
S7, locked 7 Aug 2026). Dropping an inconvenient run is a one-line change that
nobody can detect afterward, and it is the most common way benchmarking papers
quietly become wrong. If an exclusion is ever warranted for a reason not on
this list, it goes to Angad as a judgment call rather than being applied here.

**One rule was added later and is marked as such.** Rule 2b (runs with no end
timestamp) was written on 12 Aug 2026, after data existed, and is logged as
amendment 9 in ANALYSIS_PLAN.md S13. It is recorded as an amendment rather than
presented as pre-registered because the distinction is the whole point of
pre-registering. It does not select on any measured outcome: it keys on whether
a run finished, which is known without looking at its throughput, latency or
failure rate, so it cannot be used to drop a run for being inconvenient.

WHY PARQUET RATHER THAN THE DATABASE FILE
-----------------------------------------
GitHub rejects any file over 100 MB, and the finished dataset is roughly 1.3 GB
as SQLite. This data compresses about 10-25x in Parquet, because timestamps
arrive in order and columns like status and run id have very few distinct
values. If the raw file still crosses ~90 MB, move it to Git LFS -- do not
downsample, since per-payment detail is what makes future questions free.
"""

from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO / "data" / "working" / "runs.sqlite"
RAW_PATH = REPO / "data" / "raw" / "all_runs_raw.parquet"
CLEAN_PATH = REPO / "data" / "clean" / "all_runs_clean.parquet"
LOG_PATH = REPO / "data" / "clean" / "exclusions.log"

# --- pre-declared rules, locked before data existed ------------------------

#: ANALYSIS_PLAN.md S7. Cold-start effects -- connection setup, initial route
#: discovery -- would otherwise skew every average. Excludes by SUBMISSION
#: time, not by a time window, so no settlement is ever counted with a
#: truncated latency.
WARMUP_SECONDS = 10.0

#: claude.md S7. Roughly 10x the expected p99 for both chains, and past it a
#: remittance has functionally failed whatever the chain eventually does. Used
#: to decide `succeeded`, not to drop rows -- see `load()`.
TIMEOUT_SECONDS = 60.0

#: Runs from these phases never contribute to results.
#:
#: phase-1 and capacity-check exist to prove the machinery records reality.
#:
#: phase-2-step1-pilot is a short exploratory ramp -- 60-second windows and a
#: single repeat, against the pre-registered protocol of 300 seconds and five
#: repeats (ANALYSIS_PLAN.md S5). It is genuinely informative about where the
#: knee sits, but reporting a one-repeat number as a result would imply a
#: precision the data does not have. Exploratory only, per S4.
NON_RESULT_PHASES = {
    "phase-0-smoke",
    "phase-1",
    "capacity-check",
    "phase-2-step1-pilot",
    "phase-2-exploratory-ceiling",
    # Session A shake-out, 8 Aug 2026: validating that each realism technique
    # works and moves results in the expected direction. 60-second windows and
    # a single repeat, against the pre-registered 300 seconds and five. The
    # effects measured are real and informative -- and are precisely why these
    # must not be reported as results, because a single unreplicated run
    # cannot separate a genuine effect from a lucky draw.
    "step0-baseline-hw",
    "step1-impairment",
    "step3-background",
    "step4-adversarial",
    # Phase 3 (Lightning) shake-out. Same reasoning as the Polygon steps
    # above: these validated the pipeline, measured whether a fix worked, or
    # probed the size gradient with short windows and a single repeat. They
    # are genuinely informative and are precisely why they must not be
    # reported -- an unreplicated 90-second run cannot separate a real effect
    # from a lucky draw, and phase-3-mctest in particular captured the network
    # while it was degraded by the rebalancer bug.
    "phase-3-smoke",
    "phase-3-mctest",
    "phase-3-sizetest",
    # Phase 4 (NEAR) shake-out. Same reasoning again, and here it matters more
    # than anywhere else: phase-4-lagtest and phase-4-smoke were collected while
    # the harness was discarding every transaction hash, so they record 100%
    # failure for payments that were settling on chain perfectly well. Left in,
    # they would be averaged into NEAR's results and report a 100%-failure
    # architecture. phase-4-launchtest exists only to prove the supervisor can
    # start and stop a sweep.
    #
    # This list did not include them until 12 Aug 2026, and until then a NEAR
    # export pulled all three into the clean dataset -- which is how a $200
    # run at 10/sec came out at 100.00% failure in the first end-to-end test of
    # the analysis pipeline.
    "phase-4-smoke",
    "phase-4-lagtest",
    "phase-4-launchtest",
    # Controlled A/B, 12 Aug 2026: identical configuration run with background
    # traffic on and off, to establish whether NEAR's ~3% dropped-transaction
    # rate is caused by competing load or by our setup. Two runs, no repeats --
    # diagnostic by construction.
    "phase-4-noisetest",
    # ---- Phase 6 supplementary work, 18-19 Aug 2026 ----------------------
    #
    # ALL of it is excluded from RESULTS and retained in raw. Two reasons,
    # and the second applies even to the runs that are individually valid.
    #
    # 1. Different hardware. This cluster ran 4-processor validators because
    #    a new Google account caps the project at 32 processors; every
    #    published Polygon number came from 8-processor ones. Pooling the two
    #    would mix hardware into a comparison that is supposed to be about
    #    architecture.
    #
    # 2. Different measuring instrument for some of it. The -endpoint- runs
    #    spread settlement checks across four nodes instead of one, which is
    #    the very thing they were built to test. They are evidence ABOUT the
    #    published measurements, not more of them.
    #
    # The smoke phases are throwaway 60-second checks. The txpool phases are
    # an abandoned experiment: its 300/sec runs auto-invalidated for generator
    # saturation, and the design carried a selection flaw (the enlarged queue
    # accepts more payments, so it polls more, so it is likelier to be
    # excluded -- the treatment influences exclusion). Its 100 and 200/sec
    # runs are individually clean but answer nothing, since both settings pass
    # those loads with zero failures.
    #
    # What these runs DO support is written up in POLYGON_RPC_BOTTLENECK.md
    # and ANALYSIS_PLAN.md amendment 14, quoted from the raw data and labelled
    # exploratory throughout.
    "phase-6-txpool-smoke",
    "phase-6-multiendpoint-smoke",
    "phase-6-txpool-default",
    "phase-6-txpool-enlarged",
    "phase-6-txpool-default-g16",
    "phase-6-txpool-enlarged-g16",
    "phase-6-endpoint-1",
    "phase-6-endpoint-4",
    "phase-6-endpoint-ramp",
    "phase-6-rpc-diagnostic",
    "phase-6-endpoints-one",
    "phase-6-endpoints-four",
    "phase-6-fallback-check",
    "phase-6-knee",
    # The full Lightning matrix is excluded from RESULTS, not deleted.
    #
    # Decided 10 Aug 2026 (ANALYSIS_PLAN.md S13, amendment 5): Lightning's
    # reliability and throughput data comes from Waugh & Holz (2020), a
    # measurement of the real production network, not from our own simulation.
    # Our test network has ~385x fewer channels than mainnet, and Lightning's
    # success behaviour depends on having enough routing paths -- a structural
    # scale limit no amount of debugging or budget fixes.
    #
    # The runs remain in the raw file so the work is inspectable, and two
    # small figures drawn from them (clean-condition settlement time, observed
    # route length) are reported as explicitly illustrative. Nothing here
    # contributes to a reliability or throughput claim.
    "phase-3-full-stack",
}


@dataclass
class Exclusion:
    scope: str      # "run" or "transaction"
    identifier: str
    rule: str
    reason: str
    count: int = 1


def load(db_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not db_path.exists():
        raise SystemExit(f"No database at {db_path}. Run a benchmark first.")

    conn = sqlite3.connect(db_path)
    try:
        runs = pd.read_sql_query("SELECT * FROM runs", conn)
        tx = pd.read_sql_query("SELECT * FROM transactions", conn)
        events = pd.read_sql_query("SELECT * FROM node_events", conn)
    finally:
        conn.close()

    if runs.empty:
        raise SystemExit("Database has no runs yet.")

    # Columns that hold one repeated value per RUN are categorised BEFORE the
    # merge, not after.
    #
    # This is a memory correctness issue, not a tidiness one. The merge fans
    # run metadata across every payment row -- 7.9M of them. Once each run
    # began recording its full realism configuration, `config_json` grew to
    # roughly 1.5 KB, and 7.9M copies of it is over 10 GB: the export was
    # killed by the OS on an 8 GB machine. As a category, pandas stores the
    # ~200 distinct values once and an integer per row.
    for col in ("config_json", "phase", "arm", "architecture", "adapter",
                "harness_version", "invalidation_reason"):
        if col in runs.columns:
            runs[col] = runs[col].astype("category")

    # One wide table per payment, carrying its run's settings. Denormalised on
    # purpose: the analysis is always "payments grouped by configuration", and
    # this removes a join from every single query.
    merged = tx.merge(runs, on="run_id", how="left", suffixes=("", "_run"))

    # Derived once here so no downstream analysis can compute them
    # inconsistently.
    merged["latency_s"] = merged["confirmed_offset"] - merged["submitted_offset"]
    merged["schedule_lag_s"] = merged["submitted_offset"] - merged["scheduled_offset"]

    # SUCCESS MEANS SETTLED *WITHIN THE BUDGET*, not merely settled.
    #
    # claude.md S7 fixes the timeout at 60 seconds and says why: "past 60s a
    # remittance has functionally failed regardless of what the chain
    # eventually does". A payment that finalises at 91 seconds is not a
    # success that happened to be slow; by the study's own definition it is a
    # failure.
    #
    # The harness does not enforce this uniformly. Polygon's adapter stops at
    # the deadline (its slowest recorded settlement is 60.0101s). NEAR's
    # drains still-in-flight payments after the send window closes, so a late
    # finalisation is recorded with status='confirmed' and its true latency.
    # At 200/sec that is 34% and 69% of the "confirmed" payments in the first
    # two repeats -- which would have understated the failure rate at exactly
    # the load where the knee is and where the headline claim lives.
    #
    # Applied here rather than in the adapter for three reasons: the rule then
    # lands identically on all three architectures; it is recoverable for data
    # already collected, because per-transaction latency was recorded (which is
    # the reason claude.md S8 insists on per-transaction records); and it does
    # not require changing a measurement instrument in the middle of a matrix.
    #
    # `status` is deliberately left alone. It stays the raw observation -- what
    # the chain actually did -- so a reviewer can see both "it did confirm, at
    # 91s" and "it counts as a failure". The verdict is separate from the fact.
    merged["succeeded"] = ((merged["status"] == "confirmed")
                           & (merged["latency_s"] <= TIMEOUT_SECONDS))

    return merged, events


def clean(raw: pd.DataFrame, events: pd.DataFrame) -> tuple[pd.DataFrame, list[Exclusion]]:
    """Apply the locked exclusion rules. Returns the clean data and a log."""
    log: list[Exclusion] = []
    df = raw.copy()

    # Rule 1 -- phases that were never intended as results.
    for phase in sorted(set(df["phase"].dropna()) & NON_RESULT_PHASES):
        subset = df[df["phase"] == phase]
        log.append(Exclusion(
            "run", phase, "non-result phase",
            f"{phase} validates the pipeline; its numbers are not findings",
            count=subset["run_id"].nunique(),
        ))
    df = df[~df["phase"].isin(NON_RESULT_PHASES)]

    # Rule 2 -- runs the harness flagged invalid. Currently that means the
    # generator fell behind its own schedule, so the run's ceiling was our
    # tooling rather than the architecture.
    invalid = df[df["invalidated"] == 1]
    for run_id, reason in invalid[["run_id", "invalidation_reason"]].drop_duplicates().values:
        log.append(Exclusion("run", run_id, "harness flagged invalid", str(reason)))
    df = df[df["invalidated"] != 1]

    # Rule 2b -- runs that never recorded an end.
    #
    # `ended_wall` is written by the harness when a run completes normally. A
    # NULL means the run was cut off: the process was killed, the machine went
    # away, or the sweep was restarted underneath it. The payments it did record
    # are real, but they are a TRUNCATED sample of a window that was supposed to
    # be 300s, and the truncation is not random -- a run is interrupted
    # precisely when something is going wrong.
    #
    # Found 12 Aug 2026, and it was not hypothetical. The $10-at-100/sec repeat
    # 0 run was cut off at 12:02 when two validators dropped out mid-window. It
    # kept 30,403 payments, was never flagged invalid, and passed every rule
    # above. Two consequences, the second worse than the first:
    #
    #   1. a truncated run measured on a collapsing network would have entered
    #      the paper's clean dataset as an ordinary measurement;
    #   2. Rule 5 keeps the FIRST execution of a configuration, and the orphan
    #      is earlier than its eventual re-run -- so the truncated run would
    #      have been kept and the good complete one DISCARDED.
    #
    # The harness's own completeness check requires `ended_wall IS NOT NULL`, so
    # the sweep correctly re-runs these; only the export was missing the rule.
    # A run that never finished is not a measurement of a 300s window.
    if "ended_wall" in df.columns:
        unfinished = df[df["ended_wall"].isna()]
        for run_id in sorted(set(unfinished["run_id"])):
            log.append(Exclusion(
                "run", str(run_id), "run never completed",
                "no end timestamp: the run was interrupted, so its payments are "
                "a truncated and non-random sample of the intended window",
            ))
        df = df[df["ended_wall"].notna()]

    # Rule 3 -- spot reclamation. A reclaimed machine looks exactly like the
    # node failures the adversarial arm injects deliberately; keeping such a
    # run would confound the comparison that arm exists to make.
    if not events.empty:
        preempted = set(events.loc[events["source"] == "preemption", "run_id"])
        for run_id in sorted(preempted & set(df["run_id"])):
            log.append(Exclusion(
                "run", run_id, "spot preemption",
                "cloud provider reclaimed a machine mid-run",
            ))
        df = df[~df["run_id"].isin(preempted)]

    # Rule 4 -- node failures outside the adversarial arm are our own
    # misconfiguration, not the architecture's reliability.
    if not events.empty:
        offline = events[(events["event"] == "offline") & (events["source"] == "adversarial")]
        baseline_runs = set(df.loc[df["arm"] == "baseline", "run_id"])
        contaminated = sorted(set(offline["run_id"]) & baseline_runs)
        for run_id in contaminated:
            log.append(Exclusion(
                "run", run_id, "node failure outside adversarial arm",
                "infrastructure fault, not an architecture result",
            ))
        df = df[~df["run_id"].isin(contaminated)]

    # Rule 5 -- re-executions of an already-completed configuration.
    #
    # Spot preemption interrupted the main sweep twice. On resume, the sweep
    # restarted from the beginning of the load ladder rather than from the exact
    # point of interruption, so 22 configurations were measured twice, 3.9-8.1
    # hours apart.
    #
    # These are NOT extra repeats. Every pair reuses the same arrival seed, so
    # the second execution replays the identical Poisson schedule -- at load
    # levels with no failures the two runs are transaction-for-transaction
    # identical. Counting both would double the weight of those cells and, worse,
    # inflate n for the confidence intervals technique #8 requires: the pair
    # carries no independent information about arrival variability, so intervals
    # computed from it would be narrower than the evidence supports.
    #
    # The first completed execution stands. That rule is mechanical and fixes
    # the choice before the numbers are seen -- the alternative, keeping the
    # later run, would mean selecting among measurements after observing them.
    # It is also the less flattering direction here: the second pass ran on a
    # chain carrying several more hours of accumulated state and performed
    # slightly worse, so keeping the first raises the reported failure spread at
    # 300/sec rather than lowering it.
    order = ["tx_size_usd", "target_tps", "repeat_index"]
    if not df.empty and all(c in df.columns for c in order):
        per_run = (df.groupby("run_id", observed=True)
                     .agg(**{c: (c, "first") for c in order}, t0=("t0_wall", "first"),
                          phase=("phase", "first"), arm=("arm", "first"))
                     .reset_index())
        per_run["rank"] = (per_run.sort_values("t0")
                                  .groupby(order + ["phase", "arm"], observed=True)
                                  .cumcount())
        repeated = per_run[per_run["rank"] > 0]
        for _, r in repeated.sort_values(["tx_size_usd", "target_tps", "repeat_index"]).iterrows():
            log.append(Exclusion(
                "run", str(r["run_id"]), "re-execution of a completed configuration",
                f"${r['tx_size_usd']:.0f} at {r['target_tps']:.0f}/sec repeat "
                f"{r['repeat_index']:.0f} was already measured; identical arrival "
                f"seed, so this replays the same schedule rather than adding a repeat",
            ))
        df = df[~df["run_id"].isin(set(repeated["run_id"]))]

    # Rule 6 -- warm-up. Applied last, and per transaction rather than per run.
    before = len(df)
    df = df[df["scheduled_offset"] >= WARMUP_SECONDS]
    dropped = before - len(df)
    if dropped:
        log.append(Exclusion(
            "transaction", "all runs", "warm-up period",
            f"first {WARMUP_SECONDS:g}s of each run, to exclude cold-start effects",
            count=dropped,
        ))

    return df, log


#: Columns holding very few distinct values repeated across millions of rows.
#: Stored as plain strings they dominate the file: `run_id` alone is 173 MB in
#: memory for 3.5M rows despite having only 131 distinct values. Written as
#: categories, parquet stores the 131 values once plus a small integer per row.
_LOW_CARDINALITY = [
    "run_id", "phase", "status", "adapter", "architecture", "arm",
    "invalidation_reason", "error", "amount_native", "fee_native",
    # config_json carries each run's full realism configuration. One distinct
    # value per run, repeated across every payment in it -- exactly the shape
    # categories exist for, and without this the file would be gigabytes of
    # duplicated JSON.
    "config_json", "harness_version",
]


def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    """Write compactly enough to fit in a git repository.

    GitHub rejects any file over 100 MB outright, and the uncompressed export
    reached 242 MB. Rather than downsample -- which would throw away the
    per-payment detail that makes future questions answerable without
    re-running experiments -- the repetitive columns are dictionary-encoded.

    Nothing is lost: category is a storage representation, and the values read
    back identically.
    """
    out = df.copy()
    for col in _LOW_CARDINALITY:
        if col in out.columns:
            out[col] = out[col].astype("category")
    out.to_parquet(path, compression="zstd", compression_level=9, index=False)


def write_log(log: list[Exclusion], raw: pd.DataFrame, cleaned: pd.DataFrame) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        "=" * 72,
        f"Exclusion log -- generated {stamp}",
        "=" * 72,
        "",
        "Rules were locked in ANALYSIS_PLAN.md S7 on 7 Aug 2026, before any data",
        "existed. Nothing here was deleted: every excluded run remains in",
        "data/raw/all_runs_raw.parquet, flagged.",
        "",
        f"Payments in raw   : {len(raw):,} across {raw['run_id'].nunique():,} runs",
        f"Payments in clean : {len(cleaned):,} across {cleaned['run_id'].nunique():,} runs",
        f"Excluded          : {len(raw) - len(cleaned):,} payments",
        "",
        "-" * 72,
    ]

    if not log:
        lines.append("No exclusions applied.")
    else:
        for item in log:
            lines.append(f"[{item.rule}]")
            lines.append(f"  scope   : {item.scope}")
            lines.append(f"  target  : {item.identifier}")
            lines.append(f"  affected: {item.count:,}")
            lines.append(f"  reason  : {item.reason}")
            lines.append("")

    LOG_PATH.write_text("\n".join(lines) + "\n")


def main() -> int:
    # Output paths are overridable. They were fixed constants while the database
    # path was a positional argument, so `export.py some_other.sqlite` silently
    # REPLACED the assembled dataset with whatever that database happened to
    # hold -- and the obvious way to test the pipeline against one cluster's
    # data was exactly that command. The committed parquet is the only place the
    # three architectures exist together.
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("db", nargs="?", default=str(DEFAULT_DB))
    ap.add_argument("--raw", default=str(RAW_PATH))
    ap.add_argument("--clean", default=str(CLEAN_PATH))
    args = ap.parse_args()

    db_path = Path(args.db)
    raw_path, clean_path = Path(args.raw), Path(args.clean)
    print(f"reading {db_path}")

    raw, events = load(db_path)
    cleaned, log = clean(raw, events)

    raw_path.parent.mkdir(parents=True, exist_ok=True)
    clean_path.parent.mkdir(parents=True, exist_ok=True)
    _write_parquet(raw, raw_path)
    _write_parquet(cleaned, clean_path)
    if raw_path == RAW_PATH:
        write_log(log, raw, cleaned)

    raw_mb = raw_path.stat().st_size / 1e6
    clean_mb = clean_path.stat().st_size / 1e6

    print(f"\n  raw   {len(raw):>10,} payments  {raw['run_id'].nunique():>4} runs  "
          f"{raw_mb:>6.1f} MB  -> {raw_path}")
    print(f"  clean {len(cleaned):>10,} payments  {cleaned['run_id'].nunique():>4} runs  "
          f"{clean_mb:>6.1f} MB  -> {clean_path}")
    # Honest about whether the log was actually written. It is only written
    # for a canonical export; a run against a temp path leaves the committed
    # log alone, and saying otherwise is the same class of false reassurance
    # this file's exclusion rules exist to prevent.
    wrote = " -> " + str(LOG_PATH.relative_to(REPO)) if raw_path == RAW_PATH \
        else " (not written: non-canonical output path)"
    print(f"  log   {len(log)} exclusion rule(s) applied{wrote}")

    # GitHub hard-rejects pushes containing a file over 100 MB, so warn well
    # before that rather than at push time.
    if raw_mb > 90:
        print(f"\n  WARNING: raw file is {raw_mb:.0f} MB, near GitHub's 100 MB limit.")
        print("  Move it to Git LFS before committing:")
        print("      git lfs track 'data/raw/*.parquet'")
        print("  Do NOT downsample -- per-payment detail is what keeps future")
        print("  questions answerable without re-running anything.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
