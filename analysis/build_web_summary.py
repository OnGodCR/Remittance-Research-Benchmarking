#!/usr/bin/env python3
"""Shrink the study's dataset into the one small file the public website loads.

WHY THIS EXISTS
---------------
The cleaned dataset is ~700 MB -- far too big for a web page. The website only
needs two things from it:

  1. The published results table, one row per (system, test arm, amount, load).
  2. Enough of each individual run to RE-DRAW it: how many payments it sent, how
     many succeeded, its distribution of settlement times, and how settlement
     unfolded over the five minutes.

Item 2 is what makes the simulator honest. A replayed test picks a whole
recorded run at random and draws payments from inside it (cluster sampling),
so the run-to-run variation the study actually observed is preserved. Keeping
each run separate in this file is what allows that.

SAME NUMBERS AS THE PAPER
-------------------------
Every per-run and per-cell figure is computed by importing
`analysis/results.py` -- the script the paper's tables come from --
rather than re-implementing it. A website that computed its own numbers could
quietly disagree with the paper. The build then checks the published headline
figures and refuses to write the file if any fails to reproduce.

USAGE (from the repository root)
    .venv/bin/python analysis/build_web_summary.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

RESEARCH = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RESEARCH / "analysis"))
import results  # noqa: E402  the paper's own analysis code

CLEAN = RESEARCH / "data" / "clean" / "all_runs_clean.parquet"
RAW_NEAR = RESEARCH / "data" / "raw" / "parts" / "raw-near.parquet"
#: Copied to the RemitBridge website's public/data/remitbench/ after each rebuild.
OUT = RESEARCH / "data" / "web" / "results.json"

COLS = ["run_id", "architecture", "arm", "tx_size_usd", "target_tps",
        "repeat_index", "window_seconds", "succeeded", "latency_s",
        "gas_used", "route_hops", "scheduled_offset", "submitted_offset",
        "confirmed_offset", "status"]

#: Settlement-time distribution kept per run: every half-percentile. 201 points
#: reproduce p50/p95/p99 to within rounding and are tiny next to the raw rows.
QUANTILES = np.linspace(0, 100, 201)
#: Time-series resolution for the replay animation.
BIN_S = 5.0

#: Published headline figures the build must reproduce (COMPARISON.md §1, §3).
#: (system, arm, amount, load) -> (achieved/sec, failure %, pooled p95 s)
PUBLISHED = {
    ("polygon", "baseline", 200.0, 200.0): (200.9, 0.00, 4.77),
    ("polygon", "baseline", 200.0, 300.0): (270.5, 9.97, 24.26),
    ("near", "baseline", 200.0, 150.0): (150.1, 0.15, 19.20),
    ("near", "baseline", 200.0, 200.0): (47.5, 76.30, 57.85),
    ("polygon", "adversarial", 200.0, 200.0): (148.4, 26.11, None),
    ("near", "adversarial", 200.0, 150.0): (35.4, 76.36, None),
}
#: The NEAR 300/sec step, rule-excluded and reported from raw as sensitivity
#: data (NEAR_ANALYSIS.md §1b): 9.9/sec achieved, 96.7% failures at $200.
PUBLISHED_NEAR_300 = (9.9, 96.69)


def r(x, nd=3):
    return None if x is None or not np.isfinite(x) else round(float(x), nd)


def run_detail(g: pd.DataFrame) -> dict:
    """What the simulator needs to re-draw one run."""
    ok = g["succeeded"].to_numpy()
    lat = np.sort(g.loc[ok, "latency_s"].dropna().to_numpy())
    sub = g["submitted_offset"].to_numpy()
    conf = g["confirmed_offset"].to_numpy()
    window = float(g["window_seconds"].iloc[0])
    edges = np.arange(10.0, window + 60.0 + BIN_S, BIN_S)
    submitted, _ = np.histogram(sub, edges)
    failed, _ = np.histogram(sub[~ok], edges)
    settled, _ = np.histogram(conf[ok & np.isfinite(conf)], edges)
    return {
        "quantiles": [r(v) for v in np.percentile(lat, QUANTILES)] if len(lat) else [],
        "series": {"start": 10.0, "bin": BIN_S,
                   "submitted": submitted.tolist(),
                   "failed": failed.tolist(),
                   "settled": settled.tolist()},
    }


def summarise(df: pd.DataFrame, source: str) -> tuple[list, pd.DataFrame]:
    runs = results.per_run_metrics(df)
    details = {rid: run_detail(g) for rid, g in df.groupby("run_id", observed=True)}
    out = []
    for _, row in runs.iterrows():
        d = details[row["run_id"]]
        out.append({
            "id": row["run_id"], "system": row["architecture"], "arm": row["arm"],
            "amount": row["tx_size_usd"], "load": row["target_tps"],
            "repeat": int(row["repeat_index"]), "source": source,
            "payments": int(row["payments"]),
            "achieved": r(row["achieved_tps"]), "failure_pct": r(row["failure_pct"]),
            "p50": r(row["p50_s"]), "p95": r(row["p95_s"]), "p99": r(row["p99_s"]),
            **d,
        })
    return out, runs


def cells_json(agg: pd.DataFrame, source: str) -> list:
    out = []
    for _, c in agg.iterrows():
        out.append({
            "system": c["architecture"], "arm": c["arm"], "amount": c["tx_size_usd"],
            "load": c["target_tps"], "repeats": int(c["n_repeats"]), "source": source,
            "achieved": r(c["achieved_tps_mean"]),
            "achieved_ci": [r(c["achieved_tps_ci_lo"]), r(c["achieved_tps_ci_hi"])],
            "achieved_range": [r(c["achieved_tps_min"]), r(c["achieved_tps_max"])],
            "failure_pct": r(c["failure_pct_mean"]),
            "failure_ci": [r(c["failure_pct_ci_lo"]), r(c["failure_pct_ci_hi"])],
            "p50": r(c.get("p50_pooled", np.nan)), "p95": r(c.get("p95_pooled", np.nan)),
            "p99": r(c.get("p99_pooled", np.nan)),
            "cross_shard_share": (r(c["route_hops_mean_mean"])
                                  if c["architecture"] == "near" else None),
        })
    return out


def near_300_sensitivity() -> pd.DataFrame:
    """The 20 NEAR 300/sec runs, from raw, with the clean set's warm-up cut."""
    ids = [ln.split(":", 1)[1].strip()
           for ln in (RESEARCH / "data/clean/exclusions.log").read_text().splitlines()
           if ln.strip().startswith("target") and "near-baseline-" in ln
           and "-tps300-" in ln]
    assert len(ids) == 20, f"expected 20 NEAR 300/sec runs, found {len(ids)}"
    raw_cols = [c for c in COLS if c in pq.ParquetFile(RAW_NEAR).schema_arrow.names]
    t = pq.read_table(RAW_NEAR, columns=raw_cols, filters=[("run_id", "in", ids)])
    df = t.to_pandas()
    df["run_id"] = df["run_id"].astype(str)
    for c in ("architecture", "arm"):
        df[c] = df[c].astype(str)
    # Apply the clean set's own rules, exactly as analysis/export.py does:
    # success means confirmed within 60 seconds (amendment 11), and the
    # warm-up cut is on the SCHEDULED send time, per payment (rule 6).
    df["succeeded"] = (df["status"].astype(str) == "confirmed") & (df["latency_s"] <= 60.0)
    return df[df["scheduled_offset"] >= 10.0].copy()


def check(agg: pd.DataFrame, s300: pd.DataFrame) -> None:
    bad = []
    for (sys_, arm, amt, load), (tps, fail, p95) in PUBLISHED.items():
        row = agg[(agg.architecture == sys_) & (agg.arm == arm)
                  & (agg.tx_size_usd == amt) & (agg.target_tps == load)].iloc[0]
        got = (row.achieved_tps_mean, row.failure_pct_mean, row.get("p95_pooled"))
        ok = abs(got[0] - tps) <= 0.15 and abs(got[1] - fail) <= 0.05
        if p95 is not None:
            ok = ok and abs(got[2] - p95) <= 0.02
        print(f"  {sys_:8} {arm:12} ${amt:<4g} {load:>4g}/s  "
              f"{got[0]:7.1f}/{tps:<6} {got[1]:6.2f}/{fail:<6} {'ok' if ok else 'MISMATCH'}")
        if not ok:
            bad.append((sys_, arm, amt, load))
    row = s300[s300.tx_size_usd == 200.0].iloc[0]
    ok = (abs(row.achieved_tps_mean - PUBLISHED_NEAR_300[0]) < 0.05
          and abs(row.failure_pct_mean - PUBLISHED_NEAR_300[1]) <= 0.05)
    print(f"  near     baseline(raw) $200  300/s  {row.achieved_tps_mean:7.1f}/"
          f"{PUBLISHED_NEAR_300[0]:<6} {row.failure_pct_mean:6.2f}/"
          f"{PUBLISHED_NEAR_300[1]:<6} {'ok' if ok else 'MISMATCH'}")
    if not ok:
        bad.append("near-300-sensitivity")
    if bad:
        sys.exit(f"published figures do not reproduce: {bad} -- not writing {OUT}")


def main() -> None:
    print(f"reading {CLEAN}")
    df = pd.read_parquet(CLEAN, columns=COLS)
    for c in ("run_id", "architecture", "arm"):
        df[c] = df[c].astype(str)
    print(f"  {len(df):,} payments across {df['run_id'].nunique()} runs")
    run_rows, runs = summarise(df, "clean")
    agg = results.aggregate(runs, payments=df)
    del df

    print(f"reading the 20 NEAR 300/sec runs from {RAW_NEAR.name}")
    raw300 = near_300_sensitivity()
    s_rows, s_runs = summarise(raw300, "raw-sensitivity")
    s_agg = results.aggregate(s_runs, payments=raw300)

    print("checking published figures")
    check(agg, s_agg)

    payload = {
        "built_from": "data/clean/all_runs_clean.parquet "
                      "(+ 20 NEAR 300/sec runs from data/raw, marked raw-sensitivity)",
        "quantile_points": QUANTILES.tolist(),
        "cells": cells_json(agg, "clean") + cells_json(s_agg, "raw-sensitivity"),
        "runs": run_rows + s_rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.2f} MB, "
          f"{len(payload['cells'])} cells, {len(payload['runs'])} runs)")


if __name__ == "__main__":
    main()
