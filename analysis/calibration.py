#!/usr/bin/env python3
"""The two calibration figures of ANALYSIS_PLAN §11, computed from the data.

WHY TWO FIGURES AND NOT ONE
---------------------------
§11 is emphatic about this and it is the easiest thing in the study to get
wrong. Real Polygon runs at tens of transactions per second because that is
current **demand**, not because it cannot go faster — measured 12 Aug 2026 at
79.6 tx/sec with blocks only **28.5% full**. Dividing our capacity by that and
calling the result a capability gap would say "our four-validator testbed is
2.5× more capable than Polygon mainnet", which is nonsense a reviewer spots
immediately.

So:

  **Demand ratio** = our sustainable throughput / mainnet OBSERVED throughput.
      A statement about workload realism: are the loads we test comparable to
      real activity? Not about capability at all.

  **Capability gap** = our sustainable throughput / mainnet CAPACITY.
      The closer analogue of a capacity comparison, and the figure behind the
      "treat our results as an upper bound roughly Z% high" claim.

**Mainnet observed throughput is a floor on capacity, never a measurement of
it.** The paper must say so.

HOW MAINNET CAPACITY IS ESTIMATED, AND THE ASSUMPTION IT CARRIES
---------------------------------------------------------------
§11 asks for "the highest sustained throughput visible in explorer history".
That is a manual lookup and cannot be pulled from an RPC, so this script
derives capacity instead, from a figure it CAN measure:

    implied capacity = observed throughput / block utilisation

If Polygon carries 79.6 tx/sec with blocks 28.5% full, then full blocks of the
same transaction mix carry ~279 tx/sec. **The assumption is that the mix stays
constant** — that the marginal transaction costs what the average one costs. On
a chain whose traffic is mostly simple transfers that is reasonable; on one
dominated by heavy contract calls it would overstate capacity.

Both the derived figure and its inputs are printed, so a reader can substitute
an explorer-sourced peak instead. Where a manual peak is supplied via
--mainnet-peak it is used in preference and the derivation is reported beside it.

USAGE
    ./.venv/bin/python analysis/calibration.py
    ./.venv/bin/python analysis/calibration.py --architecture polygon
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

#: Measured from each chain's own RPC on 12 Aug 2026, not scraped.
#: `utilisation` is the share of the block gas limit actually used, which is what
#: turns an observed rate into an implied capacity.
MAINNET_OBSERVED = {
    "polygon": {
        "tps": 79.6, "utilisation": 0.285,
        "source": "polygon-bor-rpc.publicnode.com, 25 contiguous blocks, "
                  "head 91,888,830, pulled 2026-08-12T12:37:57Z",
        "note": "the project notes quote ~87 tx/sec (7.5M/day) from a secondary "
                "source; this figure is measured from the chain and corroborates it",
    },
    "near": {
        "tps": 4.8, "utilisation": 0.0004,
        "source": "rpc.mainnet.near.org, 8 contiguous blocks across 10 shards, "
                  "pulled 2026-08-12T01:35Z",
        "note": "small sample, taken before the public endpoint rate-limited "
                "further sampling. Treat as indicative of order of magnitude, "
                "not precise. NEAR mainnet is very lightly loaded.",
    },
}

#: Pre-registered sustainability bar (ANALYSIS_PLAN §4): achieved >= 90% of
#: offered AND failures < 5%.
MIN_ACHIEVED_FRACTION = 0.90
MAX_FAILURE_PCT = 5.0

#: Below this block utilisation, `capacity = observed / utilisation` stops being
#: a measurement and becomes an extrapolation dominated by its own error. At 5%
#: the multiplier is 20x; at NEAR mainnet's 0.04% it is 2,500x. Polygon's 28.5%
#: sits comfortably above it.
MIN_UTILISATION_FOR_CAPACITY = 0.05


def sustainable_throughput(df: pd.DataFrame, arch: str, amount: float = 200.0):
    """Highest offered load meeting the pre-registered bar, and what it achieved."""
    sel = df[(df["architecture"] == arch) & (df["arm"] == "baseline")
             & (df["tx_size_usd"] == amount)]
    if sel.empty:
        return None, None
    best = None
    for tps, g in sel.groupby("target_tps"):
        per_run = g.groupby("run_id").agg(
            ok=("succeeded", "sum"), n=("succeeded", "size"),
            window=("window_seconds", "first"))
        achieved = (per_run["ok"] / (per_run["window"] - 10.0)).mean()
        fail = 100.0 * (1 - per_run["ok"].sum() / per_run["n"].sum())
        if achieved >= MIN_ACHIEVED_FRACTION * tps and fail < MAX_FAILURE_PCT:
            if best is None or tps > best[0]:
                best = (float(tps), float(achieved))
    return best if best else (None, None)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--clean", default=str(CLEAN))
    ap.add_argument("--architecture", default=None)
    ap.add_argument("--amount", type=float, default=200.0)
    ap.add_argument("--mainnet-peak", type=float, default=None,
                    help="an explorer-sourced sustained peak, if you have one. "
                         "Used in preference to the derived capacity.")
    args = ap.parse_args()

    path = Path(args.clean)
    if not path.exists():
        print(f"missing {path}. Run analysis/export.py first.", file=sys.stderr)
        return 1
    df = pd.read_parquet(path, columns=[
        "run_id", "architecture", "arm", "tx_size_usd", "target_tps",
        "succeeded", "window_seconds"])

    arches = [args.architecture] if args.architecture else \
        [a for a in ("polygon", "near") if a in set(df["architecture"])]
    if not arches:
        print("no measured architectures in the dataset yet")
        return 0

    print(f"Calibration at ${args.amount:g}, the World Bank benchmark size\n")
    for arch in arches:
        m = MAINNET_OBSERVED.get(arch)
        tps, achieved = sustainable_throughput(df, arch, args.amount)
        print(f"{'='*66}\n{arch.upper()}")
        if tps is None:
            print("  no load step met the sustainability bar "
                  f"(achieved >= {MIN_ACHIEVED_FRACTION:.0%} of offered, "
                  f"failures < {MAX_FAILURE_PCT:g}%)")
            continue
        print(f"  our sustainable throughput : {tps:g}/sec offered, "
              f"{achieved:.1f}/sec achieved")
        if not m:
            print("  no mainnet reference recorded for this architecture")
            continue
        print(f"  mainnet observed           : {m['tps']:.1f} tx/sec")
        print(f"    source: {m['source']}")
        if m.get("note"):
            print(f"    note  : {m['note']}")

        demand = achieved / m["tps"]
        print(f"\n  DEMAND RATIO = {demand:.2f}x")
        print(f"    We sustain {demand:.1f}x what the real network currently "
              f"carries. This is about WORKLOAD REALISM, not capability:")
        print(f"    mainnet's rate is demand, and its blocks are "
              f"{100*m['utilisation']:.1f}% full.")

        if args.mainnet_peak:
            capacity, how = args.mainnet_peak, "explorer-sourced sustained peak"
        else:
            capacity = m["tps"] / m["utilisation"] if m["utilisation"] else float("nan")
            how = (f"derived: {m['tps']:.1f} tx/sec at "
                   f"{100*m['utilisation']:.4g}% block utilisation")

        # DIVIDING BY A NEARLY-EMPTY CHAIN'S UTILISATION IS NOT A MEASUREMENT.
        #
        # `capacity = observed / utilisation` is only meaningful while the
        # denominator is large enough that the ratio is not dominated by its
        # own error. NEAR mainnet was measured at 0.04% utilisation, so the
        # derivation multiplies an 8-block sample by ~2,500 to reach "12,000
        # tx/sec", and the resulting capability gap of 0.013x says far more
        # about how idle NEAR is than about what our testbed can do.
        #
        # Polygon at 28.5% is fine: the multiplier is ~3.5.
        #
        # Refusing to print the number is the point. A figure this unstable
        # would be quoted, and it is exactly the kind of derived quantity a
        # reviewer takes apart first.
        if not args.mainnet_peak and m["utilisation"] < MIN_UTILISATION_FOR_CAPACITY:
            print(f"\n  mainnet capacity           : NOT DERIVABLE")
            print(f"    Blocks were {100*m['utilisation']:.4g}% full, so "
                  f"capacity = observed / utilisation multiplies the sample by "
                  f"~{1/m['utilisation']:,.0f}x.")
            print(f"    That amplifies any sampling error by the same factor, "
                  f"and the result ({capacity:,.0f} tx/sec) would describe how "
                  f"idle the chain is,")
            print(f"    not what it can do. **Report the demand ratio only for "
                  f"this architecture**, or supply an explorer-sourced")
            print(f"    sustained peak with --mainnet-peak and re-run.")
            continue
        gap = achieved / capacity if capacity else float("nan")
        print(f"\n  mainnet capacity           : {capacity:,.0f} tx/sec ({how})")
        print(f"  CAPABILITY GAP = {gap:.3f}x")
        if gap < 1:
            print(f"    Our testbed sustains {100*gap:.1f}% of what the real "
                  f"network could carry, so our figures are NOT an overstatement")
            print(f"    of mainnet capability on this axis.")
        else:
            print(f"    Our testbed sustains MORE than the real network's "
                  f"estimated capacity -- treat results as an upper bound "
                  f"roughly {100*(gap-1):.0f}% high.")

    print(f"\n{'='*66}")
    print("Both figures are reported even when uncomfortable (§11), and the")
    print("capability gap rests on a stated assumption: that the marginal")
    print("transaction costs what the average one costs. Substitute an")
    print("explorer-sourced sustained peak with --mainnet-peak if you have one.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
