#!/usr/bin/env python3
"""Compute every reported figure from the clean dataset, with intervals.

WHY THIS EXISTS
---------------
Until now no script produced the study's results tables. The Polygon figures in
`POLYGON_ANALYSIS.md` were computed ad hoc, and `POLYGON_ANALYSIS.md` §"Confidence
intervals" records the consequence: "Results above are means with observed
ranges. The pre-registered protocol calls for bootstrap 95% intervals." Realism
technique #8 (claude.md §5) requires ranges, not single numbers, in *every*
results table. That obligation has not yet been met for any architecture.

Two further reasons this has to be one script rather than three analyses:

1. **Figures carried forward drift.** Every number in the paper should be
   recomputable from `data/clean/all_runs_clean.parquet` by running one command.
   A figure that exists only in a markdown table cannot be checked against the
   data it came from, and quietly stops matching it.

2. **Phase 6 compares architectures.** If Polygon's numbers and NEAR's numbers
   come out of different code, the comparison inherits the difference between
   two analyses as well as the difference between two blockchains. The same
   objection the project already accepted for measurement -- which is why
   Caliper was dropped in favour of one harness -- applies to analysis.

WHAT IT PRODUCES
----------------
One row per (architecture, arm, transaction size, offered load), aggregating the
five repeats:

    achieved TPS, failure rate, p50/p95/p99 settlement, gas per payment,
    and for NEAR the cross-shard share

each with a **bootstrap 95% confidence interval** over the repeats, plus the
observed min-max range for continuity with the tables already written.

THE HONEST LIMITATION OF A BOOTSTRAP AT n=5
-------------------------------------------
Resampling five values cannot manufacture information that five runs do not
contain. With n=5 the bootstrap distribution is coarse -- it can only ever take
a limited number of distinct values -- and the interval is better read as "the
spread these five runs support" than as a precise 95% coverage statement. It is
what the analysis plan pre-registered, it is honest about uncertainty in the way
a bare mean is not, and the observed range is reported beside it so a reader can
see the raw spread. The adversarial arm is where this matters most: at 300/sec
Polygon's repeats ranged from 93.2 to 203.0 payments per second, and any single
run could have reported either extreme.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not re-apply exclusions. The clean parquet is already the post-cleaning
dataset, exclusions having been applied by `analysis/export.py` and logged to
`data/clean/exclusions.log`. Re-filtering here would mean two places could
disagree about what the dataset is.

USAGE
    ./.venv/bin/python analysis/results.py                      # every architecture
    ./.venv/bin/python analysis/results.py --architecture near
    ./.venv/bin/python analysis/results.py --csv results.csv
    ./.venv/bin/python analysis/results.py --verify-polygon     # reproduce published figures
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
CLEAN = REPO / "data" / "clean" / "all_runs_clean.parquet"

#: Resamples for the bootstrap. 10,000 is far more than n=5 needs to converge,
#: and costs milliseconds.
N_BOOT = 10_000
#: Fixed so the same dataset always yields the same interval. An interval that
#: moved between runs of the analysis would be indefensible.
BOOT_SEED = 20260812


def bootstrap_ci(values: np.ndarray, confidence: float = 0.95,
                 n_boot: int = N_BOOT, seed: int = BOOT_SEED) -> tuple[float, float]:
    """Percentile bootstrap interval over the per-repeat values.

    Resamples the REPEATS, not the individual payments. The unit of replication
    in this study is the run: five runs sample arrival-pattern variability,
    which is the thing the interval is meant to express. Resampling millions of
    payments within a run would instead measure within-run variation and
    produce intervals far too narrow -- the same error the analysis plan guards
    against in amendment 4, where replays with identical arrival seeds would
    have inflated n without adding evidence.
    """
    v = np.asarray([x for x in values if np.isfinite(x)], dtype=float)
    if len(v) == 0:
        return float("nan"), float("nan")
    if len(v) == 1:
        return float(v[0]), float(v[0])
    rng = np.random.default_rng(seed)
    means = rng.choice(v, size=(n_boot, len(v)), replace=True).mean(axis=1)
    lo = float(np.percentile(means, 100 * (1 - confidence) / 2))
    hi = float(np.percentile(means, 100 * (1 + confidence) / 2))
    return lo, hi


def per_run_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse payments to one row per run.

    Every metric here is defined the same way for all architectures, which is
    what makes the Phase 6 comparison a comparison rather than three reports.
    """
    rows = []
    for run_id, g in df.groupby("run_id", observed=True):
        first = g.iloc[0]
        ok = g["succeeded"]
        n = len(g)
        n_ok = int(ok.sum())

        # Achieved throughput counts SUCCESSFUL payments only (claude.md §7).
        # The measured window is the run window minus the discarded warm-up,
        # not the wall-clock span of the surviving rows -- using the latter
        # would shrink the denominator on runs that failed early and flatter
        # them.
        window = float(first["window_seconds"]) - 10.0
        lat = g.loc[ok, "latency_s"].to_numpy()

        rows.append({
            "architecture": first["architecture"],
            "arm": first["arm"],
            "tx_size_usd": float(first["tx_size_usd"]),
            "target_tps": float(first["target_tps"]),
            "repeat_index": int(first["repeat_index"]),
            "run_id": run_id,
            "payments": n,
            "achieved_tps": n_ok / window if window > 0 else np.nan,
            "failure_pct": 100.0 * (n - n_ok) / n if n else np.nan,
            "p50_s": float(np.percentile(lat, 50)) if len(lat) else np.nan,
            "p95_s": float(np.percentile(lat, 95)) if len(lat) else np.nan,
            "p99_s": float(np.percentile(lat, 99)) if len(lat) else np.nan,
            "gas_mean": float(g.loc[ok, "gas_used"].mean()) if n_ok else np.nan,
            # route_hops carries shard boundaries crossed on NEAR (0 same-shard,
            # 1 cross-shard) and real route length on Lightning. Reported as a
            # mean, which is the cross-shard SHARE for NEAR and mean hop count
            # for Lightning -- labelled per architecture at print time.
            "route_hops_mean": (float(g.loc[ok, "route_hops"].mean())
                                if n_ok and g.loc[ok, "route_hops"].notna().any()
                                else np.nan),
        })
    return pd.DataFrame(rows)


METRICS = ["achieved_tps", "failure_pct", "p50_s", "p95_s", "p99_s",
           "gas_mean", "route_hops_mean"]


def pooled_percentiles(df: pd.DataFrame) -> pd.DataFrame:
    """Settlement percentiles over ALL payments in a cell, repeats combined.

    TWO DEFINITIONS, AND BOTH ARE NEEDED
    A cell's p95 can mean either of two things, and they do not agree:

      pooled     -- the 95th percentile of every payment in the five repeats
                    taken together. Reads as "95% of payments settled within
                    X seconds", weights each run by how many payments it
                    carried, and is what the published Polygon tables report.
      per-run    -- the mean of each run's own p95. Treats the five runs as
                    five equally-weighted observations.

    The pooled figure is the right POINT ESTIMATE: it is the statement a reader
    takes from a latency column, and it is what is already in the paper. The
    per-run figures are the right basis for the INTERVAL, because the unit of
    replication is the run -- five runs is the sample, and a bootstrap has to
    resample the thing that varies.

    Reporting the pooled point estimate beside a per-run interval is not
    inconsistent, but it must be stated, because the interval is then not a
    bootstrap OF the point estimate. On this dataset the two definitions differ
    by about 0.5% at the worst load step (p95 24.26s pooled vs 24.38s per-run at
    300/sec, $200), which is why the discrepancy was easy to miss.
    """
    rows = []
    keys = ["architecture", "arm", "tx_size_usd", "target_tps"]
    for key, g in df[df["succeeded"]].groupby(keys, observed=True):
        lat = g["latency_s"].dropna().to_numpy()
        row = dict(zip(keys, key))
        for p in (50, 95, 99):
            row[f"p{p}_pooled"] = (float(np.percentile(lat, p))
                                   if len(lat) else np.nan)
        rows.append(row)
    return pd.DataFrame(rows)


def aggregate(runs: pd.DataFrame, payments: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per cell, with mean, bootstrap CI, and observed range."""
    out = []
    keys = ["architecture", "arm", "tx_size_usd", "target_tps"]
    for key, g in runs.groupby(keys, observed=True):
        row = dict(zip(keys, key))
        row["n_repeats"] = len(g)
        for m in METRICS:
            v = g[m].to_numpy(dtype=float)
            finite = v[np.isfinite(v)]
            row[f"{m}_mean"] = float(finite.mean()) if len(finite) else np.nan
            lo, hi = bootstrap_ci(v)
            row[f"{m}_ci_lo"], row[f"{m}_ci_hi"] = lo, hi
            row[f"{m}_min"] = float(finite.min()) if len(finite) else np.nan
            row[f"{m}_max"] = float(finite.max()) if len(finite) else np.nan
        out.append(row)
    agg = pd.DataFrame(out).sort_values(keys).reset_index(drop=True)
    if payments is not None:
        agg = agg.merge(pooled_percentiles(payments), on=keys, how="left")
    return agg


def print_table(agg: pd.DataFrame, architecture: str, arm: str,
                amount: float) -> None:
    sel = agg[(agg["architecture"] == architecture) & (agg["arm"] == arm)
              & (agg["tx_size_usd"] == amount)]
    if sel.empty:
        return
    hops_label = {"near": "x-shard", "lightning": "hops"}.get(architecture)
    print(f"\n{architecture} / {arm} / ${amount:g}")
    header = (f"  {'offered':>7} {'n':>2} {'achieved':>9} {'95% CI':>17} "
              f"{'range':>15} {'fail%':>7} {'p50':>7} {'p95':>7} {'p99':>7}")
    if hops_label:
        header += f" {hops_label:>8}"
    print(header)
    for _, r in sel.iterrows():
        line = (f"  {r['target_tps']:>7.0f} {r['n_repeats']:>2.0f} "
                f"{r['achieved_tps_mean']:>9.1f} "
                f"[{r['achieved_tps_ci_lo']:>6.1f},{r['achieved_tps_ci_hi']:>7.1f}] "
                f"{r['achieved_tps_min']:>6.1f}-{r['achieved_tps_max']:>7.1f} "
                f"{r['failure_pct_mean']:>7.2f} "
                f"{r.get('p50_pooled', r['p50_s_mean']):>7.2f} "
                f"{r.get('p95_pooled', r['p95_s_mean']):>7.2f} "
                f"{r.get('p99_pooled', r['p99_s_mean']):>7.2f}")
        if hops_label:
            val = r["route_hops_mean_mean"]
            line += f" {val:>8.3f}" if np.isfinite(val) else f" {'-':>8}"
        print(line)


def sustainable(agg: pd.DataFrame, architecture: str, arm: str,
                amount: float) -> float | None:
    """Highest offered load meeting the pre-registered bar.

    ANALYSIS_PLAN §4: achieved >= 90% of offered AND failures < 5%. Computed
    here rather than read off a table, so the headline number in the paper and
    the number in the dataset cannot disagree.
    """
    sel = agg[(agg["architecture"] == architecture) & (agg["arm"] == arm)
              & (agg["tx_size_usd"] == amount)].sort_values("target_tps")
    best = None
    for _, r in sel.iterrows():
        if (r["achieved_tps_mean"] >= 0.90 * r["target_tps"]
                and r["failure_pct_mean"] < 5.0):
            best = r["target_tps"]
    return best


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--clean", default=str(CLEAN))
    ap.add_argument("--architecture", default=None)
    ap.add_argument("--csv", default=None, help="write the full table here")
    ap.add_argument("--verify-polygon", action="store_true",
                    help="check the published Polygon $200 figures still "
                         "reproduce from the data")
    args = ap.parse_args()

    path = Path(args.clean)
    if not path.exists():
        print(f"missing {path}. Run analysis/export.py first.", file=sys.stderr)
        return 1

    cols = ["run_id", "architecture", "arm", "tx_size_usd", "target_tps",
            "repeat_index", "window_seconds", "succeeded", "latency_s",
            "gas_used", "route_hops"]
    print(f"reading {path}")
    df = pd.read_parquet(path, columns=cols)
    if args.architecture:
        df = df[df["architecture"] == args.architecture]
    print(f"  {len(df):,} payments across {df['run_id'].nunique()} runs")

    runs = per_run_metrics(df)
    agg = aggregate(runs, payments=df)

    for arch in sorted(agg["architecture"].unique()):
        for arm in sorted(agg[agg["architecture"] == arch]["arm"].unique()):
            amounts = sorted(agg[(agg["architecture"] == arch)
                                 & (agg["arm"] == arm)]["tx_size_usd"].unique())
            for amt in amounts:
                print_table(agg, arch, arm, amt)
            s = sustainable(agg, arch, arm, 200.0)
            if s is not None:
                print(f"\n  sustainable throughput at $200 ({arch}/{arm}): "
                      f"{s:g}/sec  [achieved >= 90% of offered, failures < 5%]")

    if args.csv:
        agg.to_csv(args.csv, index=False)
        print(f"\nwrote {args.csv} ({len(agg)} cells)")

    if args.verify_polygon:
        print("\n" + "=" * 68)
        print("VERIFYING published Polygon $200 baseline figures against the data")
        print("(POLYGON_ANALYSIS.md / RESUME_HERE.md §3)")
        # achieved TPS, failure %, p50, p95, p99 -- exactly as printed in
        # RESUME_HERE.md S3 and POLYGON_ANALYSIS.md. Latency is checked against
        # the POOLED percentile, which is the definition those tables used.
        published = {10:  (9.9,   0.00,  3.19,  4.16,  4.40),
                     25:  (25.0,  0.00,  3.19,  4.17,  4.39),
                     50:  (50.0,  0.00,  3.20,  4.22,  4.46),
                     100: (100.1, 0.00,  3.23,  4.25,  4.52),
                     150: (150.3, 0.00,  3.31,  4.38,  4.70),
                     200: (200.9, 0.00,  3.43,  4.77,  6.35),
                     300: (270.5, 9.97, 10.61, 24.26, 30.49)}
        ok = True
        for tps, (exp_tps, exp_fail, e50, e95, e99) in published.items():
            r = agg[(agg["architecture"] == "polygon") & (agg["arm"] == "baseline")
                    & (agg["tx_size_usd"] == 200.0) & (agg["target_tps"] == tps)]
            if r.empty:
                print(f"  {tps:>3}/sec  MISSING from the dataset")
                ok = False
                continue
            row = r.iloc[0]
            got_tps, got_fail = row["achieved_tps_mean"], row["failure_pct_mean"]
            g50, g95, g99 = row["p50_pooled"], row["p95_pooled"], row["p99_pooled"]
            bad = (abs(got_tps - exp_tps) > 0.15 or abs(got_fail - exp_fail) > 0.05
                   or abs(g50 - e50) > 0.02 or abs(g95 - e95) > 0.02
                   or abs(g99 - e99) > 0.02)
            if bad:
                ok = False
            print(f"  {tps:>3}/sec  tps {got_tps:7.1f}/{exp_tps:<6.1f} "
                  f"fail {got_fail:5.2f}/{exp_fail:<5.2f} "
                  f"p50 {g50:5.2f}/{e50:<5.2f} p95 {g95:5.2f}/{e95:<5.2f} "
                  f"p99 {g99:5.2f}/{e99:<5.2f}  {'MISMATCH' if bad else 'ok'}")
        print("\n  " + ("all published figures reproduce from the data"
                        if ok else
                        "*** figures do not reproduce -- investigate before "
                        "publishing anything further ***"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
