#!/usr/bin/env python3
"""Continuously record whether the NEAR validator set was whole.

WHY THIS EXISTS
---------------
claude.md S8 requires that any run touched by a spot preemption be invalidated
and re-queued, because a validator vanishing mid-run is indistinguishable from
the adversarial arm's deliberate fault injection (technique #6). If the two are
mixed, neither arm means anything: a degraded baseline number cannot be told
apart from a node-failure number.

`analysis/export.py` already drops runs that have a `node_events` row with
`source='preemption'`. Nothing ever wrote one. On 12 Aug 2026 the phase-4
cluster had lost node0 to preemption, the protocol had expelled it for missing
blocks, shard 3 was down to a single validator -- and the database recorded
none of it. The gap was found by hand, not by any check.

This closes that gap, and closes it more completely than a preemption hook
would: it records what the CHAIN believes, so it catches a validator lost for
any reason -- reclaimed instance, crash, network partition, or expulsion by the
protocol's own kickout rule. A preemption hook on the instance would have
missed the expulsion entirely, because by then the machine was running fine.

WHAT IS RECORDED
----------------
One JSON object per sample, appended to a log that survives restarts:

    t          epoch seconds (wall clock -- this is correlated against
               runs.t0_wall + offset later, so it must be wall, not monotonic)
    height     latest block height
    epoch_id   so an epoch boundary is visible in the record
    validators number of validators in the current epoch
    shards     {shard_id: number of validators serving it}
    peers      active peer count seen by the RPC node
    ok         True only if validators == expected AND every shard has >= 2

`ok` is the field the invalidation step keys on. Sampling every 10s against
300s runs means roughly 30 observations per run, so a degradation lasting even
a few seconds is very likely to be seen.

FAILURE IS RECORDED, NOT SWALLOWED
----------------------------------
If the RPC cannot be reached the sample is still written, with ok=False and an
`error` field. A silent gap in this log would be indistinguishable from a
period of health, and the whole point is to be able to prove health rather than
assume it. `analysis/apply_validator_liveness.py` treats gaps as unproven too.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_RPC = "http://10.40.0.10:3030"
DEFAULT_LOG = "/opt/benchmark/data/working/validator_liveness.jsonl"


def rpc(url: str, method: str, params, timeout: float = 8.0):
    req = urllib.request.Request(
        url,
        data=json.dumps({"jsonrpc": "2.0", "id": 1,
                         "method": method, "params": params}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.load(resp)
    if "error" in body and body["error"]:
        raise RuntimeError(str(body["error"])[:200])
    return body["result"]


def sample(rpc_url: str, expected_validators: int, min_per_shard: int) -> dict:
    out: dict = {"t": time.time()}
    try:
        status = rpc(rpc_url, "status", [])
        out["height"] = status["sync_info"]["latest_block_height"]
        out["syncing"] = status["sync_info"]["syncing"]

        vals = rpc(rpc_url, "validators", [None])
        current = vals["current_validators"]
        out["epoch_id"] = vals.get("epoch_start_height")
        out["validators"] = len(current)

        shards: dict[str, int] = {}
        for v in current:
            for s in v.get("shards", []):
                shards[str(s)] = shards.get(str(s), 0) + 1
        out["shards"] = shards

        try:
            out["peers"] = rpc(rpc_url, "network_info", [])["num_active_peers"]
        except Exception:                          # noqa: BLE001 - secondary
            out["peers"] = None

        # Both conditions matter and they are not the same. The count catches a
        # missing validator; the per-shard check catches the case that actually
        # invalidates a sharding measurement -- a shard left with one producer,
        # which is the adversarial arm's condition sitting in the baseline.
        enough_total = out["validators"] >= expected_validators
        enough_each = (len(shards) > 0
                       and all(n >= min_per_shard for n in shards.values()))
        out["ok"] = bool(enough_total and enough_each and not out["syncing"])
    except Exception as exc:                       # noqa: BLE001 - recorded
        out["ok"] = False
        out["error"] = f"{type(exc).__name__}: {exc}"[:300]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rpc", default=DEFAULT_RPC)
    ap.add_argument("--log", default=DEFAULT_LOG)
    ap.add_argument("--interval", type=float, default=10.0)
    ap.add_argument("--expected-validators", type=int, default=8)
    ap.add_argument("--min-per-shard", type=int, default=2)
    args = ap.parse_args()

    log = Path(args.log)
    log.parent.mkdir(parents=True, exist_ok=True)

    print(f"watching {args.rpc} every {args.interval:g}s -> {log}", flush=True)
    print(f"healthy means >= {args.expected_validators} validators and "
          f">= {args.min_per_shard} per shard", flush=True)

    last_ok: bool | None = None
    while True:
        s = sample(args.rpc, args.expected_validators, args.min_per_shard)
        # Append and flush per sample. A buffered write loses precisely the
        # records around a crash, which are the ones that matter.
        with log.open("a") as fh:
            fh.write(json.dumps(s) + "\n")
            fh.flush()

        # Only transitions are printed, so the service log stays readable over
        # a 13-hour sweep while still showing every change of state.
        if s["ok"] != last_ok:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(s["t"]))
            if s["ok"]:
                print(f"{ts}Z HEALTHY  validators={s.get('validators')} "
                      f"shards={s.get('shards')}", flush=True)
            else:
                print(f"{ts}Z DEGRADED validators={s.get('validators')} "
                      f"shards={s.get('shards')} "
                      f"{s.get('error', '')}", flush=True)
            last_ok = s["ok"]

        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
