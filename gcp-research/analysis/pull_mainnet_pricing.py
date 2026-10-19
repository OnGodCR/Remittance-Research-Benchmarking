#!/usr/bin/env python3
"""Pull every mainnet pricing and calibration input, on one date, from sources.

WHY ONE SCRIPT AND ONE DATE
---------------------------
ANALYSIS_PLAN §6.3 and §11 both require mainnet figures pulled "on the same date
as the cost data", cited once. Gathered piecemeal, the inputs drift: Polygon's
cost was priced with POL on 9 Aug, NEAR's would otherwise be priced days later,
and the paper would be comparing two architectures at two exchange rates without
saying so. This pulls all of them together and writes a dated snapshot, so a
reader can reproduce every cost figure from one recorded set of numbers.

WHY THE CHAIN AND NOT AN EXPLORER
---------------------------------
Gas price is read from each network's own RPC rather than scraped from a block
explorer's front page. It is the same number, it needs no API key, and it cannot
be a stale cached widget. Token prices necessarily come from a market source
(CoinGecko), which is recorded with its own `last_updated_at` so a stale feed is
visible rather than silently trusted -- the `matic-network` feed, for instance,
has not updated since February 2026 because MATIC migrated to POL, and a script
that took it at face value would price Polygon with a six-month-old rate.

WHAT THE COST FIGURES MEAN
--------------------------
Per claude.md §7, what is real is GAS CONSUMED -- a deterministic property of the
opcodes executed, identical on our private chain and on mainnet. The gas PRICE on
our chain is a number we chose, so pricing with it would be circular. These are
the mainnet prices that gas consumption gets multiplied by.

USAGE
    ./.venv/bin/python analysis/pull_mainnet_pricing.py
    ./.venv/bin/python analysis/pull_mainnet_pricing.py --out docs/mainnet_pricing.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

NEAR_RPC = "https://rpc.mainnet.near.org"
#: publicnode, because polygon-rpc.com now returns "API key disabled" and
#: rpc.ankr.com requires an account. Checked 12 Aug 2026.
POLYGON_RPC = "https://polygon-bor-rpc.publicnode.com"
COINGECKO = ("https://api.coingecko.com/api/v3/simple/price"
             "?ids=near,polygon-ecosystem-token&vs_currencies=usd"
             "&include_last_updated_at=true")

#: A CoinGecko feed older than this is reported as stale rather than used
#: silently. matic-network is the cautionary case: dead since the POL migration.
STALE_AFTER_SECONDS = 24 * 3600


#: publicnode returns 403 to urllib's default User-Agent while serving curl
#: happily. A snapshot that silently lost one chain's gas price would leave the
#: cross-architecture cost comparison priced on two different dates.
_UA = "remittance-benchmark/1.0 (research; +https://github.com/OnGodCR/Remittance-Research-Benchmarking)"


def post(url: str, payload: dict, timeout: float = 25.0) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def get(url: str, timeout: float = 25.0) -> dict:
    req = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def rpc(url: str, method: str, params) -> dict:
    body = post(url, {"jsonrpc": "2.0", "id": 1, "method": method,
                      "params": params})
    if body.get("error"):
        raise RuntimeError(f"{url} {method}: {str(body['error'])[:200]}")
    return body["result"]


def near_snapshot() -> dict:
    gas_price = int(rpc(NEAR_RPC, "gas_price", [None])["gas_price"])
    cfg = rpc(NEAR_RPC, "EXPERIMENTAL_protocol_config", {"finality": "final"})
    vals = rpc(NEAR_RPC, "validators", [None])

    layout = cfg["shard_layout"]
    version = next(iter(layout))
    inner = layout[version]
    ids = inner.get("shard_ids")
    if ids is None:
        ids = list(range(len(inner.get("boundary_accounts", [])) + 1))

    per_shard: dict[str, int] = {}
    for v in vals["current_validators"]:
        for s in v.get("shards", []):
            per_shard[str(s)] = per_shard.get(str(s), 0) + 1

    return {
        "gas_price_yocto_per_gas": gas_price,
        "protocol_version": cfg["protocol_version"],
        "epoch_length_blocks": cfg["epoch_length"],
        "shard_count": len(ids),
        "shard_layout_version": version,
        "validators": len(vals["current_validators"]),
        "validators_per_shard": dict(sorted(per_shard.items(), key=lambda kv: int(kv[0]))),
    }


def polygon_snapshot() -> dict:
    wei = int(rpc(POLYGON_RPC, "eth_gasPrice", []), 16)
    block = int(rpc(POLYGON_RPC, "eth_blockNumber", []), 16)
    return {
        "gas_price_wei": wei,
        "gas_price_gwei": wei / 1e9,
        "block_number": block,
    }


def prices() -> dict:
    raw = get(COINGECKO)
    now = time.time()
    out = {}
    for key, label in (("near", "NEAR"), ("polygon-ecosystem-token", "POL")):
        d = raw.get(key, {})
        age = now - d.get("last_updated_at", 0)
        out[label] = {
            "usd": d.get("usd"),
            "last_updated_at": d.get("last_updated_at"),
            "age_seconds": round(age),
            "stale": age > STALE_AFTER_SECONDS,
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(REPO / "docs" / "mainnet_pricing.json"))
    args = ap.parse_args()

    pulled = time.time()
    snap = {
        "pulled_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(pulled)),
        "pulled_epoch": int(pulled),
        "sources": {
            "near_gas_and_config": NEAR_RPC,
            "polygon_gas": POLYGON_RPC,
            "token_prices": "https://api.coingecko.com/api/v3/simple/price",
        },
    }

    failures = []
    for name, fn in (("near", near_snapshot), ("polygon", polygon_snapshot),
                     ("prices", prices)):
        try:
            snap[name] = fn()
        except Exception as exc:                   # noqa: BLE001
            snap[name] = {"error": f"{type(exc).__name__}: {exc}"}
            failures.append(name)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snap, indent=2) + "\n")

    print(f"snapshot pulled {snap['pulled_utc']} -> {out}\n")

    n, p, pr = snap.get("near", {}), snap.get("polygon", {}), snap.get("prices", {})
    if "error" not in n:
        print("NEAR mainnet")
        print(f"  gas price        {n['gas_price_yocto_per_gas']:,} yoctoNEAR/gas")
        print(f"  protocol version {n['protocol_version']}")
        print(f"  shards           {n['shard_count']}  (layout {n['shard_layout_version']})")
        print(f"  validators       {n['validators']}, "
              f"{min(n['validators_per_shard'].values())}-"
              f"{max(n['validators_per_shard'].values())} per shard")
    if "error" not in p:
        print("\nPolygon mainnet")
        print(f"  gas price        {p['gas_price_gwei']:.3f} Gwei  (block {p['block_number']:,})")
    if pr:
        print("\nToken prices")
        for label, d in pr.items():
            flag = "  *** STALE FEED, do not price with this ***" if d.get("stale") else ""
            print(f"  {label:5} ${d.get('usd')}   "
                  f"updated {d.get('age_seconds')}s ago{flag}")

    # Cost per payment, at the gas each architecture actually consumes. Gas
    # consumption is measured on our own chain (claude.md §7); only the price
    # comes from mainnet.
    if "error" not in n and "error" not in p and pr:
        near_usd = pr.get("NEAR", {}).get("usd")
        pol_usd = pr.get("POL", {}).get("usd")
        print("\nCost per payment at these prices")
        if pol_usd:
            gas = 28_538          # measured, warm recipient (POLYGON_ANALYSIS.md)
            usd = gas * p["gas_price_wei"] / 1e18 * pol_usd
            print(f"  Polygon  {gas:,} gas x {p['gas_price_gwei']:.1f} Gwei "
                  f"x ${pol_usd}  =  ${usd:.6f}")
        if near_usd:
            print(f"  NEAR     gas per NEP-141 transfer is measured by the sweep; "
                  f"at {n['gas_price_yocto_per_gas']:.0e} yocto/gas and ${near_usd},")
            for tgas in (3, 5, 10):
                usd = tgas * 1e12 * n["gas_price_yocto_per_gas"] / 1e24 * near_usd
                print(f"             {tgas:>2} TGas would be ${usd:.6f}")
            print("             (illustrative only until the sweep measures it)")

    if failures:
        print(f"\nFAILED to pull: {', '.join(failures)} -- snapshot is incomplete")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
