#!/usr/bin/env python3
"""Did NEAR really stop at 200 payments a second, or did we just stop being able to see them?

    .venv/bin/python analysis/near_endpoint_ab.py
    .venv/bin/python analysis/near_endpoint_ab.py --verify-published
    .venv/bin/python analysis/near_endpoint_ab.py --csv near_ab.csv

WHAT THE EXPERIMENT ASKS
------------------------
We published that NEAR settles 150 payments a second and then does not merely
level off but *collapses*: 47.5 a second settled when 200 a second were offered,
with 76% of payments failing. That is the most striking sentence in the NEAR
chapter, and the whole comparison against Polygon leans on it.

The same claim about Polygon turned out to be about our own equipment rather
than the chain. Every question of the form "has this payment finished yet?" was
sent to a single one of the computers running the blockchain, and *that* machine
ran out of capacity, not the network. Asking four machines instead of one --
changing nothing else -- turned a published 270.5 a second with 10% failures at
300 offered into 300.4 a second with no failures at all
(`POLYGON_RPC_BOTTLENECK.md` §5d).

NEAR's failures say the same thing in words. They read `reached EXECUTED, not
FINAL`: the chain took the payment and carried it out, and what did not happen
inside our 60-second budget was our *seeing* it become final. At 200 a second
roughly 4,000 payments are unfinished at any moment, every one of them being
asked after over and over, and all of those questions went to one machine.

So the experiment runs the identical workload two ways -- asking one machine,
and asking four, one in each region -- at 200 a second, plus a 100-a-second
control step. Payments are still SENT through one machine in both arms; only
where the answers are sought changes. `scripts/run_near_endpoint_ab.sh` has the
full rationale and runs the collection.

THE CONTROL IS THE PART THAT CAN FAIL, AND IT COMES FIRST
---------------------------------------------------------
100 a second is a load at which nothing is under strain, and the published
matrix puts it at 100.0 settled a second with 0.16% failing. If the two arms
disagree *there*, then something other than where-we-ask differs between them,
and no 200-a-second number from this experiment may be read against the
published one. On Polygon this check failed twice, and both times the fault was
ours. A check that cannot fail is not a check, so this script prints the control
verdict before it prints anything about 200 a second.

WHY THIS READS THE RAW FILE AND NOT THE CLEAN ONE
-------------------------------------------------
Every phase-6 supplementary phase is deliberately held out of
`data/clean/all_runs_clean.parquet`, because a changed measuring method must
never be quietly mixed into the published results tables (ANALYSIS_PLAN.md §13,
amendments 14 and 15). These two phases belong in that same held-out category,
so the figures here are computed from `data/raw/all_runs_raw.parquet` with the
pre-registered rules applied here instead -- exactly as the Polygon endpoint
figures in `POLYGON_RPC_BOTTLENECK.md` §5d were.

The rules applied, all of them pre-registered and none of them invented here:

  * a run the harness flagged unusable is set aside, and the flag's own wording
    is printed (ANALYSIS_PLAN.md §7 and amendment 1: the sending program's
    scheduling lag GREW by more than 50 ms across the run);
  * a run flagged by the validator-liveness audit is set aside the same way,
    because `analysis/apply_validator_liveness.py` writes its verdict into the
    same flag (a run measured while the set of blockchain computers was
    incomplete is not a measurement of the architecture);
  * a run with no end timestamp is set aside -- it was cut off, so its payments
    are a truncated and non-random sample (amendment 9);
  * where the same cell was measured twice, the first completed run stands
    (amendment 4);
  * the first 10 seconds of every run are discarded, keyed on when a payment was
    *scheduled* (§7 and amendment 8);
  * a payment counts as settled only if it settled within 60 seconds; one that
    finalised at 91 seconds is a failure by the study's own definition, not a
    slow success (§6.2 and amendment 11).

Every run set aside is printed, with the rule that set it aside. Nothing is
dropped silently -- that is the single easiest way for a benchmarking paper to
become quietly wrong, and it is the thing a reviewer will look for first.

HOW THE NUMBERS ARE WORKED OUT
------------------------------
Identically to `analysis/results.py`, which produces every other results table
in the study: the mean over the repeats, a 95% band from resampling the RUNS
(not the individual payments, because a run is the thing that varies), and the
lowest-to-highest spread beside it. The interval code is imported from that
script rather than copied, so the two can never drift apart.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

REPO = Path(__file__).resolve().parent.parent
# So this runs both as `python analysis/near_endpoint_ab.py` and as
# `python -m analysis.near_endpoint_ab`. The imports below matter: the study's
# thresholds and its interval maths must come from the one place that already
# defines them, never from a second copy that can drift.
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from analysis.export import TIMEOUT_SECONDS, WARMUP_SECONDS  # noqa: E402
from analysis.results import BOOT_SEED, N_BOOT, bootstrap_ci  # noqa: E402
from harness.core.arrival import (  # noqa: E402
    SATURATION_GROWTH_SECONDS,
    SATURATION_MIN_SAMPLES,
)

RAW = REPO / "data" / "raw" / "all_runs_raw.parquet"
PARTS = REPO / "data" / "raw" / "parts"
CLEAN = REPO / "data" / "clean" / "all_runs_clean.parquet"

#: The two phase labels the collection script writes. Kept identical to
#: `scripts/run_near_endpoint_ab.sh`; if that script's labels ever change, this
#: is the one place here that has to change with them.
PHASE_ONE = "phase-6-near-endpoints-one"
PHASE_FOUR = "phase-6-near-endpoints-four"
PHASES = {PHASE_ONE: "one", PHASE_FOUR: "four"}

ARM_TITLE = {
    "one": "asking ONE machine",
    "four": "asking FOUR machines",
}
ARM_SHORT = {"one": "one machine", "four": "four machines"}

#: The design, from ANALYSIS_PLAN.md §13 amendment 15.
AMOUNT = 200.0            # the World Bank benchmark transfer size
WINDOW = 300.0            # seconds of sustained load per run
CONTROL_TPS = 100.0       # the step that proves the arms are otherwise identical
CRITICAL_TPS = 200.0      # the step the published collapse claim lives at
EXPECTED_REPEATS = 6      # six, not five, so arm order splits exactly 3/3

#: Published NEAR figures for $200, from `NEAR_ANALYSIS.md` (recomputed there
#: from the same raw data under the same rules). offered -> (settled per second,
#: failure %, 95% band). These are what the new runs are read against.
PUBLISHED = {
    100.0: (100.0, 0.16, (99.3, 100.7)),
    150.0: (150.1, 0.15, (149.6, 150.6)),
    200.0: (47.5, 76.30, (26.3, 68.7)),
}

#: "Materially more than 47.5" was fixed BEFORE the runs at 68.7 -- the top of
#: the published cell's own 95% band (amendment 15). Taking the line from a
#: number already in print is what stops it being moved afterwards to suit
#: whatever came back.
MATERIAL_LINE = 68.7

#: The pre-registered bar for calling a load level sustainable (§2): settled
#: throughput at least 90% of what was offered, AND under 5% of payments
#: failing. Both, not either.
SUSTAINABLE_FRACTION = 0.90
SUSTAINABLE_FAILURE_PCT = 5.0


# ---------------------------------------------------------------------------
# Why a payment did not count
#
# The distinction that matters here is not a footnote, it is the finding. A
# payment REFUSED at the door never entered the chain: no money moved and the
# sender can simply try again. A payment ACCEPTED and carried out but never seen
# to finish is a different animal entirely -- the chain did the work and our
# equipment lost track of it, which is exactly the fault this experiment tests
# for. Reporting one number for "failures" would hide the difference.
# ---------------------------------------------------------------------------
REFUSED = "Refused at the door -- never entered the chain"
UNSEEN = "Accepted by the chain, but never seen to finish inside 60 seconds"
LATE = "Finished, but after the 60-second deadline (our rule counts this a failure)"
NO_OUTCOME = "No outcome recorded before the run's window closed"
#: A message this script has never seen goes here rather than into one of the
#: buckets above. Guessing would quietly inflate whichever heading it landed
#: under, and the headings are the finding.
UNKNOWN = "Not recognised by this script -- read these before quoting anything"

BUCKET_ORDER = [REFUSED, UNSEEN, LATE, NO_OUTCOME, UNKNOWN]

#: First match wins, so the order is load-bearing: "EXECUTED_OPTIMISTIC" has to
#: be tested before "EXECUTED", "INCLUDED_FINAL" before "INCLUDED", and the
#: error-carrying messages before the bare one they all start with.
_ERROR_RULES: list[tuple[str, str, str]] = [
    ("never broadcast", REFUSED,
     "the chain never took it in (never broadcast inside the deadline)"),
    ("reached EXECUTED_OPTIMISTIC", UNSEEN,
     "carried out provisionally, never confirmed as final"),
    ("reached EXECUTED", UNSEEN,
     "accepted and carried out, but never seen to become final"),
    ("reached INCLUDED_FINAL", UNSEEN,
     "in a settled block, but the payment's own result never settled"),
    ("reached INCLUDED", UNSEEN,
     "in a block, but not carried out inside the deadline"),
    ("InternalError", UNSEEN,
     "the machine we asked answered with an error while we waited"),
    ("not FINAL within 60s", UNSEEN,
     "not final inside the deadline, with no further detail recorded"),
]


def classify_error(text: object) -> tuple[str, str]:
    """Turn one recorded error message into (headline bucket, plain-words reason)."""
    if text is None or (isinstance(text, float) and np.isnan(text)):
        return NO_OUTCOME, "no reason was recorded"
    s = str(text)
    for needle, bucket, label in _ERROR_RULES:
        if needle in s:
            return bucket, label
    # Never quietly bucket something unrecognised. Show it, truncated, so a new
    # failure mode announces itself instead of hiding inside "other".
    return UNKNOWN, s[:70]


def failure_reasons(payments: pd.DataFrame) -> pd.DataFrame:
    """Count why each payment in a cell did not settle in time.

    Works off the distinct error strings rather than the several million rows,
    because NEAR's messages embed the payment's own identifier and expanding
    them row by row is what killed an earlier export on an 8 GB laptop.
    """
    status = payments["status"].astype(str).to_numpy()
    latency = payments["latency_s"].to_numpy(dtype=float)
    codes, uniques = pd.factorize(payments["error"], use_na_sentinel=False)
    mapped = [classify_error(u) for u in uniques]
    buckets = np.array([m[0] for m in mapped], dtype=object)[codes]
    labels = np.array([m[1] for m in mapped], dtype=object)[codes]

    # Settled, but too slowly to count. The chain did finish it; our own
    # 60-second rule is what makes it a failure, so it is named as its own case
    # rather than mixed in with payments that never finished at all.
    late = (status == "confirmed") & (latency > TIMEOUT_SECONDS)
    buckets = np.where(late, LATE, buckets)
    labels = np.where(late, f"settled after {TIMEOUT_SECONDS:.0f} seconds", labels)

    # A payment the chain answered with an outright error was refused at the
    # door, whatever the message says.
    refused = (status == "failed") & ~late
    buckets = np.where(refused, REFUSED, buckets)

    # Left 'pending' means the run's window closed with no verdict either way.
    pending = (status == "pending") & ~late
    buckets = np.where(pending, NO_OUTCOME, buckets)
    labels = np.where(pending, "still unfinished when the run ended", labels)

    ok = (status == "confirmed") & (latency <= TIMEOUT_SECONDS)
    frame = pd.DataFrame({"bucket": buckets, "reason": labels})[~ok]
    if frame.empty:
        return frame.assign(payments=0).head(0)
    return (frame.groupby(["bucket", "reason"], observed=True).size()
                 .reset_index(name="payments")
                 .sort_values("payments", ascending=False))


# ---------------------------------------------------------------------------
# Reading and rule-checking
# ---------------------------------------------------------------------------
COLUMNS = ["run_id", "phase", "arm", "tx_size_usd", "target_tps", "repeat_index",
           "window_seconds", "t0_wall", "ended_wall", "invalidated",
           "invalidation_reason", "scheduled_offset", "submitted_offset",
           "status", "latency_s", "error"]


def read_payments(raw_path: Path, phases: list[str]) -> pd.DataFrame:
    """Read only the phases asked for, only the columns needed.

    The raw dataset is several gigabytes and this laptop has 8. Filtering inside
    the reader means the rest of the study never enters memory at all.
    """
    table = pq.read_table(raw_path, columns=COLUMNS,
                          filters=[("phase", "in", phases)])
    df = table.to_pandas()
    # Recomputed here rather than read from the file's `succeeded` column, so
    # this script is right even against a raw file exported before the
    # 60-second rule existed (amendment 11 was added on 12 Aug, after some data
    # had already been collected). The formula is character-for-character the
    # one in analysis/export.py.
    df["settled_in_time"] = ((df["status"] == "confirmed")
                             & (df["latency_s"] <= TIMEOUT_SECONDS))
    return df


def lag_growth_ms(g: pd.DataFrame) -> float:
    """How much further behind schedule the sending program fell across a run.

    A cross-check, not an exclusion rule. The harness already judges this per
    worker process while the run happens and flags the run itself; this pools
    every worker together, so the two figures need not match exactly. It exists
    to catch the case where a run that should have been flagged was not --
    because the flag is the pre-registered mechanism, and a missing flag would
    otherwise be invisible.
    """
    sub = g.dropna(subset=["submitted_offset"]).sort_values("scheduled_offset")
    if len(sub) < SATURATION_MIN_SAMPLES:
        return float("nan")
    lag = (sub["submitted_offset"] - sub["scheduled_offset"]).to_numpy()
    q = len(lag) // 4
    return float(np.median(lag[-q:]) - np.median(lag[:q])) * 1000.0


def per_run(df: pd.DataFrame) -> pd.DataFrame:
    """One row per run: what it was, and what it measured."""
    rows = []
    for run_id, g in df.groupby("run_id", observed=True):
        first = g.iloc[0]
        kept = g[g["scheduled_offset"] >= WARMUP_SECONDS]   # §7 warm-up discard
        n = len(kept)
        n_ok = int(kept["settled_in_time"].sum())
        # The denominator is the intended window minus the discarded warm-up,
        # not the span of the surviving payments. Using the latter would shrink
        # the denominator on a run that died early and flatter it.
        window = float(first["window_seconds"]) - WARMUP_SECONDS
        lat = kept.loc[kept["settled_in_time"], "latency_s"].to_numpy()
        rows.append({
            "run_id": run_id,
            "endpoints": PHASES.get(str(first["phase"]), "?"),
            "phase": str(first["phase"]),
            "arm": str(first["arm"]),
            "amount": float(first["tx_size_usd"]),
            "offered": float(first["target_tps"]),
            "repeat": int(first["repeat_index"]),
            "window_seconds": float(first["window_seconds"]),
            "t0_wall": float(first["t0_wall"]),
            "ended_wall": first["ended_wall"],
            "invalidated": int(first["invalidated"] or 0),
            "invalidation_reason": (None if pd.isna(first["invalidation_reason"])
                                    else str(first["invalidation_reason"])),
            "payments": n,
            "settled": n_ok,
            "achieved": n_ok / window if window > 0 else np.nan,
            "failure_pct": 100.0 * (n - n_ok) / n if n else np.nan,
            "p50_s": float(np.percentile(lat, 50)) if len(lat) else np.nan,
            "p95_s": float(np.percentile(lat, 95)) if len(lat) else np.nan,
            "lag_growth_ms": lag_growth_ms(g),
        })
    return pd.DataFrame(rows).sort_values(["offered", "endpoints", "repeat"])


def apply_rules(runs: pd.DataFrame) -> tuple[pd.DataFrame, list[tuple[str, str, str]]]:
    """Set aside runs the pre-registered rules exclude. Returns (kept, reasons)."""
    setaside: list[tuple[str, str, str]] = []   # (run id, rule, reason)
    keep = runs.copy()

    # Rule: the harness or the validator-liveness audit flagged the run unusable.
    # Both write into the same flag, and the recorded wording says which.
    for _, r in keep[keep["invalidated"] == 1].iterrows():
        setaside.append((r["run_id"], "flagged unusable when it was measured",
                         r["invalidation_reason"] or "no reason recorded"))
    keep = keep[keep["invalidated"] != 1]

    # Rule (amendment 9): a run that never recorded an end was cut off, so its
    # payments are a truncated sample of a window that was meant to be 300s --
    # and runs get cut off precisely when something is going wrong.
    unfinished = keep[keep["ended_wall"].isna()]
    for _, r in unfinished.iterrows():
        setaside.append((r["run_id"], "the run never finished",
                         "no end timestamp: it was interrupted, so its payments "
                         "are a truncated and non-random sample of the window"))
    keep = keep[keep["ended_wall"].notna()]

    # Rule (amendment 4): where one cell was measured more than once, the FIRST
    # completed run stands. Mechanical, and fixed before the numbers are seen --
    # the alternative is choosing among measurements after looking at them.
    keep = keep.sort_values("t0_wall")
    dupe = keep.duplicated(subset=["endpoints", "offered", "amount", "repeat"], keep="first")
    for _, r in keep[dupe].iterrows():
        setaside.append((r["run_id"], "the same run was measured twice",
                         f"{ARM_SHORT[r['endpoints']]} at {r['offered']:.0f}/sec "
                         f"repeat {r['repeat']} was already measured; the first "
                         f"completed run stands"))
    keep = keep[~dupe]

    return keep.sort_values(["offered", "endpoints", "repeat"]), setaside


# ---------------------------------------------------------------------------
# Aggregating and printing
# ---------------------------------------------------------------------------
def cell_summary(kept: pd.DataFrame, payments: pd.DataFrame) -> pd.DataFrame:
    """One row per (offered load, arm), the repeats combined."""
    rows = []
    for (offered, endpoints), g in kept.groupby(["offered", "endpoints"], observed=True):
        v = g["achieved"].to_numpy(dtype=float)
        lo, hi = bootstrap_ci(v)
        # Settlement times are pooled over every payment in the cell -- the
        # definition the published tables use, so the two are comparable.
        pool = payments[payments["run_id"].isin(set(g["run_id"]))]
        pool = pool[(pool["scheduled_offset"] >= WARMUP_SECONDS) & pool["settled_in_time"]]
        lat = pool["latency_s"].to_numpy(dtype=float)
        rows.append({
            "offered": offered,
            "endpoints": endpoints,
            "runs": len(g),
            "achieved": float(np.mean(v)),
            "ci_lo": lo,
            "ci_hi": hi,
            "lowest": float(np.min(v)),
            "highest": float(np.max(v)),
            "failure_pct": float(g["failure_pct"].mean()),
            "worst_failure_pct": float(g["failure_pct"].max()),
            "p50_s": float(np.percentile(lat, 50)) if len(lat) else np.nan,
            "p95_s": float(np.percentile(lat, 95)) if len(lat) else np.nan,
            "p99_s": float(np.percentile(lat, 99)) if len(lat) else np.nan,
            "payments": int(g["payments"].sum()),
        })
    return pd.DataFrame(rows).sort_values(["offered", "endpoints"])


def bootstrap_difference(a: np.ndarray, b: np.ndarray,
                         n_boot: int = N_BOOT, seed: int = BOOT_SEED) -> tuple[float, float]:
    """95% band for (mean of a) minus (mean of b), resampling the runs.

    Two separate bands that happen to overlap is a weaker and blunter test than
    putting a band on the DIFFERENCE itself: two overlapping bands can still
    hide a real difference, and two barely-separated ones can exaggerate a
    small one. The difference is the quantity the reader actually cares about,
    so it is the quantity that gets the band.
    """
    a = np.asarray([x for x in a if np.isfinite(x)], dtype=float)
    b = np.asarray([x for x in b if np.isfinite(x)], dtype=float)
    if len(a) == 0 or len(b) == 0:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    diffs = (rng.choice(a, size=(n_boot, len(a)), replace=True).mean(axis=1)
             - rng.choice(b, size=(n_boot, len(b)), replace=True).mean(axis=1))
    return float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))


def rule(title: str = "", char: str = "=") -> None:
    print("\n" + char * 78)
    if title:
        print(title)
        print(char * 78)


def print_cell_table(summary: pd.DataFrame, offered: float) -> None:
    sel = summary[summary["offered"] == offered]
    print(f"  {'':<22}{'runs':>5} {'settled/sec':>12} {'95% band':>17} "
          f"{'lowest-highest':>18} {'failed':>8} {'half by':>9} {'95% by':>8}")
    for endpoints in ("one", "four"):
        r = sel[sel["endpoints"] == endpoints]
        if r.empty:
            print(f"  {ARM_TITLE[endpoints]:<22}{'--':>5} {'no usable runs':>12}")
            continue
        r = r.iloc[0]
        print(f"  {ARM_TITLE[endpoints]:<22}{r['runs']:>5.0f} {r['achieved']:>12.1f} "
              f"[{r['ci_lo']:>7.1f},{r['ci_hi']:>7.1f}] "
              f"{r['lowest']:>8.1f} -{r['highest']:>8.1f} "
              f"{r['failure_pct']:>7.2f}% {r['p50_s']:>8.1f}s {r['p95_s']:>7.1f}s")


def print_failure_reasons(payments: pd.DataFrame, kept: pd.DataFrame,
                          offered: float, endpoints: str) -> None:
    runs = kept[(kept["offered"] == offered) & (kept["endpoints"] == endpoints)]
    if runs.empty:
        return
    pool = payments[payments["run_id"].isin(set(runs["run_id"]))]
    pool = pool[pool["scheduled_offset"] >= WARMUP_SECONDS]
    total = len(pool)
    table = failure_reasons(pool)
    failed = int(table["payments"].sum()) if len(table) else 0
    print(f"\n  {ARM_TITLE[endpoints]}")
    print(f"    {total:,} payments after the warm-up cut, of which {failed:,} "
          f"did not count ({100.0 * failed / total if total else 0:.2f}%)")
    if not failed:
        print("    Every payment settled inside 60 seconds.")
        return
    for bucket in BUCKET_ORDER:
        part = table[table["bucket"] == bucket]
        if part.empty:
            continue
        n = int(part["payments"].sum())
        print(f"    {bucket}")
        print(f"      {n:>12,}  ({100.0 * n / total:5.2f}% of all payments, "
              f"{100.0 * n / failed:5.1f}% of the failures)")
        for _, r in part.head(5).iterrows():
            print(f"        {r['payments']:>10,}  {r['reason']}")
        if len(part) > 5:
            print(f"        {'':>10}  + {len(part) - 5} further kind(s)")


# ---------------------------------------------------------------------------
# The verdicts
# ---------------------------------------------------------------------------
def control_verdict(summary: pd.DataFrame, kept: pd.DataFrame) -> bool:
    """The 100-a-second check, printed before anything else. True if it passes."""
    rule("THE CONTROL FIRST: at 100 payments a second the two arms must agree")
    print("""
  This step exists to prove the two arms differ in nothing but where the
  harness looks for answers. At 100 a second nothing is under strain, so both
  should land on the published figure of 100.0 settled a second with 0.16%
  failing. IF THEY DO NOT, THE 200-A-SECOND COMPARISON BELOW MEANS NOTHING --
  the rebuilt cluster would differ from the published one in some way we have
  not identified, and the two could not be read against each other.
""".rstrip())
    print()
    print_cell_table(summary, CONTROL_TPS)

    sel = summary[summary["offered"] == CONTROL_TPS]
    one = sel[sel["endpoints"] == "one"]
    four = sel[sel["endpoints"] == "four"]
    if one.empty or four.empty:
        print("\n  VERDICT: CANNOT BE JUDGED -- the control step is missing an arm.")
        return False

    pub_mean, pub_fail, pub_band = PUBLISHED[CONTROL_TPS]
    print(f"\n  published for comparison: {pub_mean:.1f} settled/sec, "
          f"{pub_fail:.2f}% failed, band [{pub_band[0]:.1f}, {pub_band[1]:.1f}]")

    # Two checks. The plan fixes no numeric tolerance for "reproduces the
    # published cell", so both checks below use only numbers already in print
    # -- the published band, and the pre-registered sustainability bar -- rather
    # than a tolerance invented here after the fact.
    print("\n  Check 1 -- does each arm reproduce the published 100/sec cell?")
    reproduced = True
    for endpoints, r in (("one", one.iloc[0]), ("four", four.iloc[0])):
        inside = pub_band[0] <= r["achieved"] <= pub_band[1]
        healthy = (r["achieved"] >= SUSTAINABLE_FRACTION * CONTROL_TPS
                   and r["failure_pct"] < SUSTAINABLE_FAILURE_PCT)
        ok = inside and healthy
        reproduced &= ok
        print(f"    {ARM_SHORT[endpoints]:<14} {r['achieved']:6.1f}/sec, "
              f"{r['failure_pct']:5.2f}% failed  -- "
              f"{'inside' if inside else 'OUTSIDE'} the published band, "
              f"{'meets' if healthy else 'FAILS'} the study's bar "
              f"(90% of offered and under 5% failing)  -> {'ok' if ok else 'NOT ok'}")

    print("\n  Check 2 -- do the two arms agree with each other?")
    at_control = kept[kept["offered"] == CONTROL_TPS]
    lo, hi = bootstrap_difference(
        at_control[at_control["endpoints"] == "four"]["achieved"].to_numpy(),
        at_control[at_control["endpoints"] == "one"]["achieved"].to_numpy())
    gap = four.iloc[0]["achieved"] - one.iloc[0]["achieved"]
    agree = bool(np.isfinite(lo) and lo <= 0.0 <= hi)
    print(f"    four machines minus one machine: {gap:+.2f}/sec, "
          f"band [{lo:+.2f}, {hi:+.2f}]")
    print(f"    -> the band {'includes' if agree else 'EXCLUDES'} zero, so the "
          f"arms are {'indistinguishable' if agree else 'DIFFERENT'} here")
    print("    (with six runs an agreement is weak evidence of sameness, not "
          "proof of it --")
    print("     it can only fail to find a difference, never establish there is none)")

    passed = bool(reproduced and agree)
    rule("CONTROL PASSED -- the arms are equivalent at 100 payments a second,\n"
         "so the 200-a-second comparison below can be read against the published\n"
         "figures." if passed else
         "CONTROL FAILED -- the arms are NOT equivalent at 100 payments a second.\n"
         "NOTHING BELOW MAY BE READ AGAINST THE PUBLISHED 47.5/sec. Find out what\n"
         "else differs between the arms before quoting any number from this run.",
         char="*")
    return passed


def critical_verdict(summary: pd.DataFrame, kept: pd.DataFrame) -> None:
    """The 200-a-second comparison, against the published collapse."""
    rule("AT 200 PAYMENTS A SECOND: is the published collapse still there?")
    pub_mean, pub_fail, pub_band = PUBLISHED[CRITICAL_TPS]
    print(f"""
  Published, from the five-repeat matrix: {pub_mean:.1f} settled a second against
  200 offered, {pub_fail:.2f}% of payments failing, band
  [{pub_band[0]:.1f}, {pub_band[1]:.1f}]. The line for "materially more" was fixed at
  {MATERIAL_LINE:.1f}/sec BEFORE these runs -- the top of that published band.
""".rstrip())
    print()
    print_cell_table(summary, CRITICAL_TPS)

    sel = summary[summary["offered"] == CRITICAL_TPS]
    one = sel[sel["endpoints"] == "one"]
    four = sel[sel["endpoints"] == "four"]

    if not one.empty:
        r = one.iloc[0]
        inside = pub_band[0] <= r["achieved"] <= pub_band[1]
        print(f"\n  Asking one machine, as published: {r['achieved']:.1f}/sec, "
              f"{r['failure_pct']:.2f}% failed")
        print(f"    -> {'reproduces' if inside else 'DOES NOT reproduce'} the "
              f"published cell (its mean lands "
              f"{'inside' if inside else 'outside'} [{pub_band[0]:.1f}, {pub_band[1]:.1f}])")
        if not inside:
            print("    -> a one-machine arm that does not reproduce the published")
            print("       number is itself a finding, and has to be explained before")
            print("       the four-machine number can be used.")

    if four.empty:
        print("\n  No valid four-machine runs at 200/sec: no verdict is possible.")
        return

    r = four.iloc[0]
    achieved, failure = r["achieved"], r["failure_pct"]
    print(f"\n  Asking four machines: {achieved:.1f}/sec, {failure:.2f}% failed")

    if not one.empty:
        lo, hi = bootstrap_difference(
            kept[(kept["offered"] == CRITICAL_TPS) & (kept["endpoints"] == "four")]["achieved"].to_numpy(),
            kept[(kept["offered"] == CRITICAL_TPS) & (kept["endpoints"] == "one")]["achieved"].to_numpy())
        gap = achieved - one.iloc[0]["achieved"]
        print(f"    four machines minus one machine: {gap:+.1f}/sec, "
              f"band [{lo:+.1f}, {hi:+.1f}]"
              f"  ({'a real difference' if np.isfinite(lo) and lo > 0 else 'not separable from zero'})")

    # The ladder below was written down in ANALYSIS_PLAN.md §13 amendment 15
    # before any of these runs existed, including which outcome means what. It
    # is reproduced here in code so the reading cannot drift from the plan.
    print("\n  Against the pre-registered outcomes (amendment 15):")
    sustainable = (achieved >= SUSTAINABLE_FRACTION * CRITICAL_TPS
                   and failure < SUSTAINABLE_FAILURE_PCT)
    if achieved <= MATERIAL_LINE:
        print(f"    (4) NOT materially more than the published {pub_mean:.1f}/sec.")
        print("        The collapse is NOT an artefact of asking one machine too")
        print("        many questions. It is a property of NEAR as deployed --")
        print("        finality genuinely falling behind execution -- and the NEAR")
        print("        chapter stands as written, with this alternative explanation")
        print("        now tested and excluded rather than merely unconsidered.")
        print("        Check the failure reasons below: this reading depends on them")
        print("        still being dominated by 'accepted, never seen to finish'.")
    elif sustainable:
        print("    (2) At or above 180/sec with under 5% failing: 200 a second is a")
        print("        SUSTAINABLE step under the study's own bar, and NEAR's")
        print("        published ceiling of 150/sec MOVES.")
        print("        No new ceiling may be claimed from two load levels -- the rest")
        print("        of the ramp (250, 300) has to be measured first:")
        print("            ./scripts/run_near_endpoint_ab.sh --loads \"250 300\" --arms four")
    elif achieved >= SUSTAINABLE_FRACTION * CRITICAL_TPS or failure < SUSTAINABLE_FAILURE_PCT:
        print("    (3) A mixed result: one of the two conditions is met and the")
        print("        other is not. Both figures get reported as they are, and the")
        print("        ceiling stays at 150/sec, because the bar requires both.")
    else:
        print(f"    (1) Materially more than {MATERIAL_LINE:.1f}/sec, but still short of the")
        print("        study's bar. The published 150/sec ceiling stands, AND the")
        print("        SIZE of the collapse at 200/sec was partly our own instrument.")
        print("        Every document quoting the 47.5/sec cell has to re-describe it.")


def final_summary(summary: pd.DataFrame, control_ok: bool) -> None:
    """Repeat the answer at the end.

    The output above is long, and the control verdict is the thing a reader
    must not miss. Someone who scrolls to the bottom should still meet it.
    """
    rule("IN ONE PARAGRAPH")
    at200 = summary[summary["offered"] == CRITICAL_TPS]
    one = at200[at200["endpoints"] == "one"]
    four = at200[at200["endpoints"] == "four"]
    if not control_ok:
        print("  The control at 100 payments a second did NOT come out the same in")
        print("  both arms, so the two arms differ in something besides where the")
        print("  harness looks for answers. Whatever the 200-a-second numbers say,")
        print("  they cannot be compared with the published ones until that is")
        print("  explained. Treat everything above as diagnostic, not as a result.")
        return
    print("  At 100 payments a second the two arms are indistinguishable, which is")
    print("  what makes the comparison at 200 readable at all.")
    if one.empty or four.empty:
        print("  At 200 a second one of the two arms has no usable runs, so the")
        print("  question the experiment asks is still open.")
        return
    o, f = one.iloc[0], four.iloc[0]
    pub_mean = PUBLISHED[CRITICAL_TPS][0]
    print(f"\n  At 200 offered, asking one machine settled {o['achieved']:.1f} payments a second")
    print(f"  ({o['failure_pct']:.2f}% of payments failing) against the published {pub_mean:.1f}.")
    print(f"  Asking four machines settled {f['achieved']:.1f} a second ({f['failure_pct']:.2f}% failing).")
    if f["achieved"] > MATERIAL_LINE:
        print(f"\n  That is above the {MATERIAL_LINE:.1f}-a-second line fixed before the runs, so part")
        print("  of the published collapse was our own measuring equipment and every")
        print("  document quoting that cell has to be revisited.")
    else:
        print(f"\n  That is not above the {MATERIAL_LINE:.1f}-a-second line fixed before the runs, so the")
        print("  collapse is NEAR's own and the chapter stands as written -- with one")
        print("  more explanation now tested and ruled out.")


def print_setaside(setaside: list[tuple[str, str, str]]) -> None:
    rule("RUNS SET ASIDE, AND THE RULE THAT SET EACH ONE ASIDE")
    if not setaside:
        print("  None. Every run collected is used below.")
        return
    print("  Nothing is deleted: these runs stay in the raw data file, flagged.")
    for run_id, rule_name, reason in setaside:
        print(f"\n  {run_id}")
        print(f"    rule  : {rule_name}")
        print(f"    reason: {reason}")


def print_inventory(runs: pd.DataFrame, kept: pd.DataFrame, loads: list[float]) -> list[str]:
    """Show what was collected against what was planned. Returns what is missing.

    Only the two pre-registered load steps are counted against the plan. Any
    other step present is a follow-on that the plan sets no repeat count for, so
    holding it to six repeats would raise a false alarm.
    """
    rule("WHAT WAS COLLECTED")
    print(f"  {'offered/sec':>12}  {'asking one machine':>22}  {'asking four machines':>22}")
    missing: list[str] = []
    planned = [CONTROL_TPS, CRITICAL_TPS]
    for offered in sorted(set(loads) | set(planned)):
        cells = []
        for endpoints in ("one", "four"):
            found = len(runs[(runs["offered"] == offered) & (runs["endpoints"] == endpoints)])
            usable = len(kept[(kept["offered"] == offered) & (kept["endpoints"] == endpoints)])
            note = f"{usable} usable"
            if found != usable:
                note += f" of {found}"
            cells.append(note)
            if offered in planned and usable < EXPECTED_REPEATS:
                missing.append(f"{offered:.0f}/sec asking {ARM_SHORT[endpoints]}: "
                               f"{usable} usable run(s), {EXPECTED_REPEATS} planned")
        tail = "" if offered in planned else "   <- follow-on step, no fixed plan"
        print(f"  {offered:>12.0f}  {cells[0]:>22}  {cells[1]:>22}{tail}")
    print(f"\n  The experiment plans {EXPECTED_REPEATS} repeats per arm at "
          f"{CONTROL_TPS:.0f} and {CRITICAL_TPS:.0f} a second (amendment 15).")
    return missing


def lag_tripwire(kept: pd.DataFrame) -> None:
    """Warn if a kept run looks saturated but was never flagged."""
    suspect = kept[kept["lag_growth_ms"] > SATURATION_GROWTH_SECONDS * 1000.0]
    if suspect.empty:
        return
    rule("WARNING: a run was kept whose sending program fell further behind", char="!")
    print("  The study excludes a run when the program sending the payments falls")
    print(f"  more than {SATURATION_GROWTH_SECONDS * 1000:.0f} ms further behind its own schedule across the run,")
    print("  because the load actually offered has then drifted from the load")
    print("  intended. These runs were NOT flagged when they were measured, but")
    print("  recomputing the figure here says they should have been:")
    for _, r in suspect.iterrows():
        print(f"    {r['run_id']}  {r['offered']:.0f}/sec {ARM_SHORT[r['endpoints']]}: "
              f"lag grew {r['lag_growth_ms']:+.1f} ms")
    print("\n  This script does not exclude them on its own -- the flag written when")
    print("  the run was measured is the pre-registered mechanism. Re-judge them")
    print("  the sanctioned way before quoting anything:")
    print("      .venv/bin/python -m analysis.reevaluate_saturation --dry-run")


def liveness_note(runs: pd.DataFrame) -> None:
    """The validator-liveness audit leaves a fingerprint. Say if there is none."""
    flagged = runs["invalidation_reason"].fillna("").str.contains("validator set", case=False)
    if flagged.any():
        return
    rule("CHECK BEFORE QUOTING: was the validator-liveness audit run?", char="!")
    print("  No run here carries a validator-liveness flag. That means either every")
    print("  run passed the audit, or the audit was never run against this")
    print("  collection -- and the data cannot tell those two apart.")
    print("  A run measured while the set of blockchain computers was incomplete")
    print("  must not be used. Confirm the audit ran:")
    print("      .venv/bin/python analysis/apply_validator_liveness.py \\")
    print("          --db data/working/runs.sqlite \\")
    print("          --liveness data/working/validator_liveness.jsonl \\")
    print("          --phase phase-6-near-endpoints-four --dry-run")
    print("  (then the same for -one), re-export, and run this again.")


def config_warnings(runs: pd.DataFrame) -> None:
    """Anything that says these runs were not the experiment we designed."""
    problems = []
    odd_amount = runs[runs["amount"] != AMOUNT]
    if len(odd_amount):
        problems.append(f"{len(odd_amount)} run(s) did not move ${AMOUNT:.0f}: "
                        f"{sorted(set(odd_amount['amount']))}")
    odd_window = runs[runs["window_seconds"] != WINDOW]
    if len(odd_window):
        problems.append(f"{len(odd_window)} run(s) did not use a {WINDOW:.0f}-second "
                        f"window: {sorted(set(odd_window['window_seconds']))}")
    odd_arm = runs[runs["arm"] != "baseline"]
    if len(odd_arm):
        problems.append(f"{len(odd_arm)} run(s) were not recorded as baseline runs: "
                        f"{sorted(set(odd_arm['arm']))}")
    if not problems:
        return
    rule("WARNING: some runs were not configured the way the experiment says", char="!")
    for p in problems:
        print(f"  {p}")
    print("  They are still counted below. Decide deliberately whether they belong.")


def clean_leak_check() -> None:
    """These phases must stay out of the published results dataset."""
    if not CLEAN.exists():
        return
    try:
        n = pq.read_table(CLEAN, columns=["phase"],
                          filters=[("phase", "in", list(PHASES))]).num_rows
    except Exception:
        return
    if n:
        rule("WARNING: these runs have leaked into the published results dataset",
             char="!")
        print(f"  {n:,} payments from these two phases are in")
        print(f"  {CLEAN.relative_to(REPO)}, so they are being averaged into the")
        print("  published $200 cells alongside the five-repeat matrix. They use a")
        print("  changed measuring method and must be held out (amendment 15).")
        print("  Add both phase names to NON_RESULT_PHASES in analysis/export.py")
        print("  and rebuild the clean dataset.")


# ---------------------------------------------------------------------------
# Self-test: does this script's machinery reproduce the published NEAR figures?
# ---------------------------------------------------------------------------
def verify_published(raw_path: Path) -> bool:
    """Recompute the published NEAR $200 cells with this script's own code.

    The point is not the published numbers -- they are already in the paper. It
    is that the rule-applying and interval maths in THIS file, run over data
    that has been through review, land exactly where the paper landed. If it
    reproduces those, its answers about the new runs can be trusted too.
    """
    rule("SELF-TEST: reproducing the published NEAR $200 figures with this code")
    df = pq.read_table(raw_path, columns=COLUMNS,
                       filters=[("phase", "=", "phase-4-full-stack"),
                                ("tx_size_usd", "=", AMOUNT)]).to_pandas()
    if df.empty:
        print("  The published phase-4 runs are not in this file. Cannot self-test.")
        return False
    df["settled_in_time"] = ((df["status"] == "confirmed")
                             & (df["latency_s"] <= TIMEOUT_SECONDS))
    runs = per_run(df)
    runs["endpoints"] = "published"          # one arm; the rules do not care
    kept, setaside = apply_rules(runs)
    print(f"  {len(runs)} runs read, {len(setaside)} set aside by the rules, "
          f"{len(kept)} used")

    ok = True
    print(f"\n  {'offered':>8} {'runs':>5} {'settled/sec':>12} {'95% band':>16} "
          f"{'failed':>8}   published")
    for offered, (exp_tps, exp_fail, exp_band) in sorted(PUBLISHED.items()):
        g = kept[kept["offered"] == offered]
        if g.empty:
            print(f"  {offered:>8.0f}   MISSING from this file")
            ok = False
            continue
        v = g["achieved"].to_numpy(dtype=float)
        lo, hi = bootstrap_ci(v)
        fail = float(g["failure_pct"].mean())
        # A tenth of a payment per second, and a hundredth of a percentage
        # point: the published figures are quoted to exactly that precision, so
        # anything larger is a real disagreement rather than rounding.
        bad = (abs(v.mean() - exp_tps) > 0.05 or abs(fail - exp_fail) > 0.005
               or abs(lo - exp_band[0]) > 0.05 or abs(hi - exp_band[1]) > 0.05)
        ok &= not bad
        print(f"  {offered:>8.0f} {len(g):>5} {v.mean():>12.1f} "
              f"[{lo:>6.1f},{hi:>7.1f}] {fail:>7.2f}%   "
              f"{exp_tps:.1f}/sec {exp_fail:.2f}% [{exp_band[0]:.1f}, {exp_band[1]:.1f}]"
              f"  {'MISMATCH' if bad else 'ok'}")

    print("\n  " + ("the published NEAR figures reproduce exactly from this code"
                    if ok else
                    "*** the published figures do NOT reproduce -- this script's "
                    "answers about the new runs cannot be trusted until that is "
                    "understood ***"))
    return ok


# ---------------------------------------------------------------------------
def missing_data_notice(raw_path: Path, why: str) -> int:
    rule("NOTHING TO REPORT YET", char="!")
    print(f"  {why}\n")
    print("  The experiment is collected on the cluster and only reaches this")
    print("  laptop when the results are exported. In order:")
    print("    1. the runs finish on the generator")
    print("         ./scripts/run_near_endpoint_ab.sh")
    print("    2. the validator-liveness audit is applied to them")
    print("         .venv/bin/python analysis/apply_validator_liveness.py \\")
    print("             --db data/working/runs.sqlite \\")
    print("             --liveness data/working/validator_liveness.jsonl")
    print("    3. the data files are rebuilt")
    print("         .venv/bin/python -m analysis.export")
    print("    4. then this script has something to read")
    print(f"\n  Looked in: {raw_path}")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Compare settled payments per second on NEAR when the "
                    "harness asks one machine whether payments finished, "
                    "against asking four.")
    ap.add_argument("--raw", default=str(RAW),
                    help="the raw dataset (default: data/raw/all_runs_raw.parquet)")
    ap.add_argument("--csv", default=None, help="also write the summary table here")
    ap.add_argument("--verify-published", action="store_true",
                    help="check this script reproduces the published NEAR $200 "
                         "figures before reading anything new")
    args = ap.parse_args()

    raw_path = Path(args.raw)
    rule("NEAR: ASKING ONE MACHINE, OR ASKING FOUR\n"
         "Does NEAR really stop at 200 payments a second?")

    if not raw_path.exists():
        hint = f"There is no raw dataset at {raw_path}."
        if PARTS.exists():
            hint += ("\n  It is stored split across data/raw/parts/ and has to be "
                     "put back together first:\n"
                     "      .venv/bin/python -m analysis.rebuild_raw")
        return missing_data_notice(raw_path, hint)

    exit_code = 0
    if args.verify_published and not verify_published(raw_path):
        exit_code = 1

    print(f"\nreading {raw_path}")
    payments = read_payments(raw_path, list(PHASES))
    if payments.empty:
        return missing_data_notice(
            raw_path,
            "Neither of this experiment's two phases is in the raw dataset yet:\n"
            f"    {PHASE_ONE}\n    {PHASE_FOUR}")

    runs = per_run(payments)
    print(f"  {len(payments):,} payments across {len(runs)} runs in the two arms")

    clean_leak_check()
    config_warnings(runs)
    liveness_note(runs)

    kept, setaside = apply_rules(runs)
    loads = sorted(set(runs["offered"]))
    missing = print_inventory(runs, kept, loads)
    print_setaside(setaside)
    lag_tripwire(kept)

    if kept.empty:
        rule("Every run was set aside by a rule. There is nothing to compare.",
             char="!")
        return 1

    summary = cell_summary(kept, payments)

    rule("HOW TO READ THE TABLES")
    print("""
  asking ONE        every "has this payment finished yet?" question went to a
    machine         single one of the computers running the blockchain, which is
                    what the published runs did.
  asking FOUR       the same questions spread across four of those computers,
    machines        one in each region. Payments are still SENT through one
                    machine in both arms; only the asking changes.

  settled/sec       payments that reached final settlement within 60 seconds,
                    per second, averaged over the repeats. Payments that did
                    not make the deadline are NOT counted here.
  95% band          the range these repeats support, worked out by resampling
                    the runs themselves. With six runs it is a fair summary of
                    the spread, not a precise guarantee.
  lowest-highest    the best and worst single run, so the raw spread is visible
                    beside the averaged one.
  failed            share of payments that did not settle within 60 seconds --
                    including any that settled later, which our own rule counts
                    as failures rather than slow successes.
  half by / 95% by  how long settlement took: the time by which half, and 95%,
                    of the settled payments had arrived.
""".rstrip())

    control_ok = (control_verdict(summary, kept) if CONTROL_TPS in loads
                  else _no_control())
    if CRITICAL_TPS in loads:
        critical_verdict(summary, kept)
    else:
        rule("The 200-a-second step is not in this data, so the question the "
             "experiment asks\nis unanswered.", char="!")

    rule("WHY PAYMENTS DID NOT COUNT")
    print("  The split below is the substance, not the bookkeeping. A payment")
    print("  refused at the door never entered the chain and can simply be sent")
    print("  again. A payment the chain accepted and carried out, which we then")
    print("  never saw finish, is the opposite case -- the work was done and our")
    print("  equipment lost sight of it. That second kind is what this whole")
    print("  experiment is about.")
    print("\n  The percentages below pool every payment in a cell together, so they")
    print("  can differ slightly from the 'failed' column above, which gives each")
    print("  run equal weight regardless of how many payments it carried.")
    for offered in loads:
        print(f"\n  --- {offered:.0f} payments a second offered "
              f"{'-' * 44}")
        for endpoints in ("one", "four"):
            print_failure_reasons(payments, kept, offered, endpoints)

    extra = [t for t in loads if t not in (CONTROL_TPS, CRITICAL_TPS)]
    if extra:
        rule("FURTHER LOAD STEPS FOUND IN THIS DATA")
        print("  These are the follow-on steps. No ceiling may be claimed from two")
        print("  load levels, so they are reported without a verdict.")
        for offered in extra:
            print(f"\n  {offered:.0f} offered")
            print_cell_table(summary, offered)

    if args.csv:
        summary.to_csv(args.csv, index=False)
        print(f"\nwrote {args.csv} ({len(summary)} rows)")

    if CONTROL_TPS in loads and CRITICAL_TPS in loads:
        final_summary(summary, control_ok)

    if missing:
        rule("INCOMPLETE -- DO NOT QUOTE THESE NUMBERS YET", char="!")
        for m in missing:
            print(f"  {m}")
        print("\n  The experiment is not finished, or some runs were set aside and")
        print("  need re-running. Re-run the missing repeats and export again:")
        print("      ./scripts/run_near_endpoint_ab.sh --from-repeat N")
        exit_code = 1

    if not control_ok:
        exit_code = 1
    return exit_code


def _no_control() -> bool:
    rule("NO CONTROL STEP IN THIS DATA", char="!")
    print("  The 100-a-second control is what proves the two arms differ in")
    print("  nothing but where the harness looks for answers. Without it, no")
    print("  200-a-second figure here may be read against the published one.")
    return False


if __name__ == "__main__":
    sys.exit(main())
