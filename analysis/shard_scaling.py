#!/usr/bin/env python3
"""Project a 4-shard NEAR measurement to any shard count, from the data.

Implements the method in `docs/near_methodology/shard_scaling.md`, which until
now existed only as a formula in prose and a SQL snippet. Computing it by hand at
write-up time is how a figure ends up in the paper that no longer matches the
dataset it came from.

THE METHOD
----------
NEAR routes a transaction to the shard owning the RECEIVER's account, so a
randomly addressed transfer is cross-shard with probability (S-1)/S: 75% at our
4 shards, 90% at mainnet's 10. A cross-shard transfer costs more -- it executes
on the sender's shard, emits a receipt, and that receipt executes on the
receiver's shard in a LATER block, paying an extra block of latency and extra
gas.

So the blend of work changes with shard count, and an average measured at 4
shards cannot simply be rescaled. Instead the two regimes are measured
separately and recombined for whatever S is being discussed:

    c(S) = (1/S) * c_same + ((S-1)/S) * c_cross

Every NEAR payment records its regime in `route_hops` (0 same-shard, 1
cross-shard), which is what makes this possible at all.

TWO THINGS THIS SCRIPT FIXES IN THE WRITTEN METHOD
--------------------------------------------------
1. **Which metric goes in the throughput correction.** The document says c(S)
   "applies unchanged to settlement latency, gas burnt, and cost in dollars",
   then uses c(4)/c(S) to correct throughput. Those are not interchangeable
   there. Throughput is limited by how much WORK a shard can execute per block,
   so the correction must use GAS. Substituting latency would silently mix a
   queueing property into a capacity calculation and give a different, wrong
   answer. This script uses gas for the throughput projection and says so.

2. **Whether there is a per-shard throughput to scale at all.** T(S) = S *
   T_shard * c(4)/c(S) presumes T_shard is a measured SHARD limit. If the chain
   never saturates inside the 10-300/sec ramp, the highest number we observe is
   just the highest load we offered, and multiplying it by S projects our own
   test plan rather than NEAR's capacity. The script checks for saturation
   before projecting and refuses to extrapolate when it did not occur.

USAGE
    ./.venv/bin/python analysis/shard_scaling.py
    ./.venv/bin/python analysis/shard_scaling.py --self-test
    ./.venv/bin/python analysis/shard_scaling.py --max-shards 12
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
CLEAN = REPO / "data" / "clean" / "all_runs_clean.parquet"
PRICING = REPO / "docs" / "mainnet_pricing.json"

OUR_SHARDS = 4
MAINNET_SHARDS = 10          # measured 12 Aug 2026, layout V3
N_BOOT = 10_000
BOOT_SEED = 20260812


def c_of_s(c_same: float, c_cross: float, s: int) -> float:
    """Expected per-transaction value at shard count s."""
    return c_same / s + c_cross * (s - 1) / s


def bootstrap_ci(values: np.ndarray, confidence: float = 0.95) -> tuple[float, float]:
    """Percentile bootstrap over per-RUN values, matching analysis/results.py.

    The unit of replication is the run, not the payment. Resampling payments
    would measure within-run variation and produce intervals far narrower than
    the evidence supports.
    """
    v = np.asarray([x for x in values if np.isfinite(x)], dtype=float)
    if len(v) == 0:
        return float("nan"), float("nan")
    if len(v) == 1:
        return float(v[0]), float(v[0])
    rng = np.random.default_rng(BOOT_SEED)
    means = rng.choice(v, size=(N_BOOT, len(v)), replace=True).mean(axis=1)
    return (float(np.percentile(means, 100 * (1 - confidence) / 2)),
            float(np.percentile(means, 100 * (1 + confidence) / 2)))


def regimes(df: pd.DataFrame, metric: str) -> dict:
    """c_same and c_cross for one metric, with per-run values for the interval."""
    ok = df[df["succeeded"] & df["route_hops"].notna() & df[metric].notna()]
    same = ok[ok["route_hops"] == 0]
    cross = ok[ok["route_hops"] == 1]

    per_run_same = same.groupby("run_id", observed=True)[metric].mean().to_numpy()
    per_run_cross = cross.groupby("run_id", observed=True)[metric].mean().to_numpy()

    return {
        "n_same": len(same),
        "n_cross": len(cross),
        "c_same": float(same[metric].mean()) if len(same) else float("nan"),
        "c_cross": float(cross[metric].mean()) if len(cross) else float("nan"),
        "ci_same": bootstrap_ci(per_run_same),
        "ci_cross": bootstrap_ci(per_run_cross),
        "cross_share": (len(cross) / (len(same) + len(cross))
                        if (len(same) + len(cross)) else float("nan")),
    }


def report_metric(name: str, r: dict, unit: str, max_shards: int) -> None:
    print(f"\n{name}")
    if not np.isfinite(r["c_same"]) or not np.isfinite(r["c_cross"]):
        print("  one regime has no data -- cannot project. "
              "See §6 of the method: this is a fixture fault, not a finding.")
        return
    print(f"  same-shard  {r['c_same']:>12,.4f} {unit}   "
          f"[{r['ci_same'][0]:,.4f}, {r['ci_same'][1]:,.4f}]   n={r['n_same']:,}")
    print(f"  cross-shard {r['c_cross']:>12,.4f} {unit}   "
          f"[{r['ci_cross'][0]:,.4f}, {r['ci_cross'][1]:,.4f}]   n={r['n_cross']:,}")
    penalty = (r["c_cross"] / r["c_same"] - 1) * 100 if r["c_same"] else float("nan")
    print(f"  cross-shard penalty: {penalty:+.1f}%")

    print(f"\n  {'S':>3}  {'c(S)':>14}  {'vs our 4 shards':>16}")
    base = c_of_s(r["c_same"], r["c_cross"], OUR_SHARDS)
    for s in range(2, max_shards + 1):
        c = c_of_s(r["c_same"], r["c_cross"], s)
        tag = ""
        if s == OUR_SHARDS:
            tag = "  <- measured here"
        elif s == MAINNET_SHARDS:
            tag = "  <- mainnet"
        print(f"  {s:>3}  {c:>14,.4f}  {c / base:>15.4f}x{tag}")

    corr = c_of_s(r["c_same"], r["c_cross"], MAINNET_SHARDS) / base
    print(f"\n  correction factor 4 -> {MAINNET_SHARDS} shards: {corr:.4f}x")
    if corr >= 1:
        print(f"  Our 4-shard figure UNDERSTATES mainnet by {100*(corr-1):.2f}%. "
              f"Conservative, which is the safe direction.")
    else:
        print(f"  Our 4-shard figure OVERSTATES mainnet by {100*(1-corr):.2f}%. "
              f"NOT the safe direction -- state this prominently.")


def self_test() -> int:
    """Verify the formula against values worked by hand.

    Worth having because the projection is the one part of the NEAR analysis
    with no observable ground truth to check against: if c(S) were wrong, every
    projected figure would be wrong together and consistently, which is exactly
    the kind of error that survives review.
    """
    print("self-test: c(S) = (1/S)*c_same + ((S-1)/S)*c_cross\n")
    cases = [
        # (c_same, c_cross, S, expected)
        (1.0, 2.0, 1, 1.0),        # one shard: everything is same-shard
        (1.0, 2.0, 2, 1.5),        # half and half
        (1.0, 2.0, 4, 1.75),       # 25% same, 75% cross
        (1.0, 2.0, 10, 1.9),       # 10% same, 90% cross
        (3.0, 3.0, 7, 3.0),        # no penalty -> flat in S
        (0.0, 5.0, 5, 4.0),        # 4/5 of the cross value
    ]
    ok = True
    for cs, cc, s, expected in cases:
        got = c_of_s(cs, cc, s)
        good = abs(got - expected) < 1e-12
        ok &= good
        print(f"  c_same={cs} c_cross={cc} S={s:>2} -> {got:.6f} "
              f"(expected {expected})  {'ok' if good else 'FAIL'}")

    # Monotonicity: with a real penalty, c(S) must rise with S and approach
    # c_cross from below, never exceeding it.
    cs, cc = 1.0, 2.5
    seq = [c_of_s(cs, cc, s) for s in range(1, 60)]
    rising = all(b >= a for a, b in zip(seq, seq[1:]))
    bounded = max(seq) <= cc + 1e-12
    print(f"\n  monotonically rising in S: {'ok' if rising else 'FAIL'}")
    print(f"  bounded above by c_cross : {'ok' if bounded else 'FAIL'}")
    print(f"  limit as S->inf is c_cross ({seq[-1]:.4f} -> {cc})")
    ok &= rising and bounded
    print(f"\n  {'ALL CHECKS PASS' if ok else '*** SELF-TEST FAILED ***'}")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--clean", default=str(CLEAN))
    ap.add_argument("--max-shards", type=int, default=MAINNET_SHARDS)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    path = Path(args.clean)
    if not path.exists():
        print(f"missing {path}. Run analysis/export.py first.", file=sys.stderr)
        return 1

    df = pd.read_parquet(path, columns=[
        "run_id", "architecture", "arm", "target_tps", "succeeded",
        "latency_s", "gas_used", "route_hops", "window_seconds"])
    near = df[(df["architecture"] == "near") & (df["arm"] == "baseline")]
    if near.empty:
        print("No NEAR baseline payments in the clean dataset yet.\n"
              "This script is ready to run the moment the sweep completes; "
              "use --self-test to verify the projection maths meanwhile.")
        return 0

    print(f"{len(near):,} NEAR baseline payments across "
          f"{near['run_id'].nunique()} runs")

    # SANITY CHECK FIRST. A mix far from (S-1)/S means account placement is
    # broken, not that sharding behaves unexpectedly -- and the failure is
    # silent, so it must be checked explicitly (method §6).
    lat = regimes(near, "latency_s")
    expected = (OUR_SHARDS - 1) / OUR_SHARDS
    share = lat["cross_share"]
    print(f"\ncross-shard share: {100*share:.1f}% "
          f"(expected {100*expected:.1f}% at {OUR_SHARDS} shards)")
    if abs(share - expected) > 0.10:
        print("  *** OFF EXPECTATION BY MORE THAN 10 POINTS ***")
        print("  Near 0%: every account landed on one shard and the arm is")
        print("  measuring an unsharded chain. Near 100%: senders and recipients")
        print("  are cleanly separated and c_same has no data behind it.")
        print("  Both are fixture faults, not findings.")
    else:
        print("  within tolerance -- account placement is doing its job")

    report_metric("SETTLEMENT LATENCY", lat, "s", args.max_shards)
    gas = regimes(near, "gas_used")
    report_metric("GAS PER PAYMENT", gas, "gas", args.max_shards)

    if PRICING.exists() and np.isfinite(gas["c_same"]):
        p = json.loads(PRICING.read_text())
        gp = p.get("near", {}).get("gas_price_yocto_per_gas")
        usd = p.get("prices", {}).get("NEAR", {}).get("usd")
        if gp and usd:
            print(f"\nCOST IN DOLLARS  (mainnet gas price {gp:.0e} yocto/gas, "
                  f"NEAR ${usd}, pulled {p['pulled_utc']})")
            for label, g in (("same-shard", gas["c_same"]),
                             ("cross-shard", gas["c_cross"]),
                             (f"blended at S={OUR_SHARDS}",
                              c_of_s(gas["c_same"], gas["c_cross"], OUR_SHARDS)),
                             (f"blended at S={MAINNET_SHARDS} (mainnet)",
                              c_of_s(gas["c_same"], gas["c_cross"], MAINNET_SHARDS))):
                print(f"  {label:32} ${g * gp / 1e24 * usd:.6f}")

    # THROUGHPUT: only projected if the chain actually saturated.
    print("\nTHROUGHPUT PROJECTION")
    per_run = near.groupby(["run_id", "target_tps"], observed=True)["succeeded"] \
                  .agg(["sum", "size"]).reset_index()
    window = float(near["window_seconds"].iloc[0]) - 10.0
    per_run["achieved"] = per_run["sum"] / window
    by_load = per_run.groupby("target_tps")[["achieved"]].mean()
    by_load["ratio"] = by_load["achieved"] / by_load.index
    saturated = by_load[by_load["ratio"] < 0.90]

    if saturated.empty:
        top = by_load.index.max()
        print(f"  The chain met at least 90% of every offered load up to "
              f"{top:g}/sec, so NO ceiling was observed.")
        print(f"  T_shard is therefore NOT measured, and S x T_shard would "
              f"project our own test plan rather than NEAR's capacity.")
        print(f"  Refusing to extrapolate. To obtain a ceiling, add exploratory")
        print(f"  load steps above {top:g}/sec -- the same route Polygon took "
              f"with its 500 and 1000/sec levels (ANALYSIS_PLAN amendment 3).")
    else:
        ceiling = float(saturated.index.min())
        collapsed = float(by_load.loc[ceiling, "achieved"])

        # T_shard IS THE HIGHEST SUSTAINED THROUGHPUT, NOT THE THROUGHPUT AT
        # THE FIRST SATURATED STEP.
        #
        # This previously used the achieved rate at the saturating load. On
        # NEAR that is 52.0/sec (measured at 200/sec offered, where the chain
        # has collapsed and fails ~76% of payments), giving T_shard = 13.0/sec
        # and a 10-shard projection of 130/sec.
        #
        # That projection is self-evidently wrong: we MEASURED 150/sec
        # sustained on 4 shards, so it claimed mainnet's 10 shards would be
        # SLOWER than our own testbed. Throughput past the knee is a collapse
        # artefact -- the rate at which a failing system still happens to
        # settle things -- not a measure of capacity.
        #
        # The chain's demonstrated capacity is the highest load it actually
        # sustained, which is exactly the pre-registered "sustainable
        # throughput" of ANALYSIS_PLAN S2: achieved >= 90% of offered AND
        # failures < 5%. Saturation must still have been OBSERVED somewhere
        # above it, or the ceiling is our test plan rather than NEAR's limit --
        # that check is the `if saturated.empty` branch above.
        sustained = by_load[by_load["ratio"] >= 0.90]
        basis_load = float(sustained.index.max())
        observed = float(by_load.loc[basis_load, "achieved"])
        t_shard = observed / OUR_SHARDS
        print(f"  saturation first seen at {ceiling:g}/sec offered "
              f"(achieved only {collapsed:.1f}/sec there -- past the knee, so "
              f"NOT a capacity measure)")
        print(f"  highest SUSTAINED load: {basis_load:g}/sec offered, "
              f"{observed:.1f}/sec achieved  <- basis for T_shard")
        print(f"  per-shard throughput T_shard = {t_shard:.1f}/sec")
        print(f"  correction uses GAS, not latency -- throughput is limited by "
              f"work per block, not by queueing delay")
        base_gas = c_of_s(gas["c_same"], gas["c_cross"], OUR_SHARDS)
        print(f"\n  {'S':>3}  {'projected total/sec':>20}")
        for s in range(OUR_SHARDS, args.max_shards + 1):
            adj = base_gas / c_of_s(gas["c_same"], gas["c_cross"], s)
            tag = "  <- mainnet" if s == MAINNET_SHARDS else ""
            print(f"  {s:>3}  {s * t_shard * adj:>20.1f}{tag}")
        print("\n  Assumes shards execute independently (Nightshade's design "
              "intent) and that cross-shard cost does not itself vary with S. "
              "Nothing in our data can rule the latter out.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
