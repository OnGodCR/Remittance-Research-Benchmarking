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

    # One wide table per payment, carrying its run's settings. Denormalised on
    # purpose: the analysis is always "payments grouped by configuration", and
    # this removes a join from every single query.
    merged = tx.merge(runs, on="run_id", how="left", suffixes=("", "_run"))

    # Derived once here so no downstream analysis can compute them
    # inconsistently.
    merged["latency_s"] = merged["confirmed_offset"] - merged["submitted_offset"]
    merged["schedule_lag_s"] = merged["submitted_offset"] - merged["scheduled_offset"]
    merged["succeeded"] = merged["status"] == "confirmed"

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
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DB
    print(f"reading {db_path}")

    raw, events = load(db_path)
    cleaned, log = clean(raw, events)

    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    CLEAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    _write_parquet(raw, RAW_PATH)
    _write_parquet(cleaned, CLEAN_PATH)
    write_log(log, raw, cleaned)

    raw_mb = RAW_PATH.stat().st_size / 1e6
    clean_mb = CLEAN_PATH.stat().st_size / 1e6

    print(f"\n  raw   {len(raw):>10,} payments  {raw['run_id'].nunique():>4} runs  "
          f"{raw_mb:>6.1f} MB  -> {RAW_PATH.relative_to(REPO)}")
    print(f"  clean {len(cleaned):>10,} payments  {cleaned['run_id'].nunique():>4} runs  "
          f"{clean_mb:>6.1f} MB  -> {CLEAN_PATH.relative_to(REPO)}")
    print(f"  log   {len(log)} exclusion rule(s) applied "
          f"-> {LOG_PATH.relative_to(REPO)}")

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
