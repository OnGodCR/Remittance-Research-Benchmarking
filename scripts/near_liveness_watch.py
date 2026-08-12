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
    produced   {validator: [blocks_produced, expected, chunks_produced, expected]}
    ok         True only if the set is full, every shard has >= 2 producers,
               enough peers are visible, and the node is not syncing

Sampling every 10s against 300s runs means roughly 30 observations per run, so
a degradation lasting even a few seconds is very likely to be seen.

`ok` is a convenience summary. `analysis/apply_validator_liveness.py` recomputes
its own verdict from the recorded fields rather than trusting it, because the
criteria differ by arm: the adversarial arm takes a validator offline on
purpose, so a peer-count dip there is the experiment working, not a fault.
This file's job is to record facts; deciding what they mean belongs in analysis.

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


def sample(rpc_url: str, expected_validators: int, min_per_shard: int,
           min_peers: int) -> dict:
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

        # Per-validator production counters, so a validator that is LISTED but
        # not actually producing is visible in the record. See below.
        out["produced"] = {
            v["account_id"]: [v["num_produced_blocks"], v["num_expected_blocks"],
                              v["num_produced_chunks"], v["num_expected_chunks"]]
            for v in current
        }

        try:
            out["peers"] = rpc(rpc_url, "network_info", [])["num_active_peers"]
        except Exception:                          # noqa: BLE001 - secondary
            out["peers"] = None

        # THREE CONDITIONS, and the third is the one that is easy to miss.
        #
        # The count catches a validator the protocol has already removed. The
        # per-shard check catches a shard left with one producer -- the
        # adversarial arm's condition sitting inside the baseline.
        #
        # But a validator that has crashed or been reclaimed is STILL LISTED in
        # current_validators for up to two epochs, because expulsion is decided
        # at the end of the epoch it underperformed in and applied two epochs
        # later. Counting validators alone would therefore report a healthy set
        # for up to four hours after a machine went dark. node0 sat in that
        # state for most of 11 Aug. The peer count drops within seconds, so it
        # is the signal that actually catches a live failure.
        enough_total = out["validators"] >= expected_validators
        enough_each = (len(shards) > 0
                       and all(n >= min_per_shard for n in shards.values()))
        enough_peers = out["peers"] is not None and out["peers"] >= min_peers
        out["ok"] = bool(enough_total and enough_each and enough_peers
                         and not out["syncing"])
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
    ap.add_argument("--min-peers", type=int, default=7,
                    help="peers the RPC node should see. On an 8-validator "
                         "cluster the RPC node is one of them, so it sees the "
                         "other 7. This is the signal that catches a validator "
                         "that has gone dark but is still listed in the set.")
    args = ap.parse_args()

    log = Path(args.log)
    log.parent.mkdir(parents=True, exist_ok=True)

    print(f"watching {args.rpc} every {args.interval:g}s -> {log}", flush=True)
    print(f"healthy means >= {args.expected_validators} validators, "
          f">= {args.min_per_shard} per shard, >= {args.min_peers} peers",
          flush=True)

    last_ok: bool | None = None
    while True:
        s = sample(args.rpc, args.expected_validators, args.min_per_shard,
                   args.min_peers)
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
                      f"shards={s.get('shards')} peers={s.get('peers')}",
                      flush=True)
            else:
                print(f"{ts}Z DEGRADED validators={s.get('validators')} "
                      f"shards={s.get('shards')} peers={s.get('peers')} "
                      f"{s.get('error', '')}", flush=True)
            last_ok = s["ok"]

        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
