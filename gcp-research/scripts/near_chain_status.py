#!/usr/bin/env python3
"""One-screen view of the NEAR chain: who is validating, who is coming back, when.

Runs ON THE GENERATOR (it needs the in-VPC RPC).

WHY A FILE RATHER THAN AN INLINE SSH COMMAND
Nesting quotes through `gcloud compute ssh --command` mangles escapes silently
across three shell layers (RESUME_HERE.md §5 trap 5), and a Python f-string
containing a quoted dict lookup is exactly the shape that breaks. Write a
script, copy it, run it.

WHAT TO LOOK FOR
- `current` must be 8 with 2+ validators per shard before any measured run.
- A validator missing from `next` is NOT coming back next epoch and needs a
  stake proposal; the supervisor submits one automatically.
- A validator below the kickout threshold will be expelled at the end of this
  epoch and stays expelled for two more, so it needs a proposal even while it
  is still nominally a member.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request

DEFAULT_RPC = "http://10.40.0.10:3030"


def rpc(url: str, method: str, params):
    req = urllib.request.Request(
        url,
        data=json.dumps({"jsonrpc": "2.0", "id": 1,
                         "method": method, "params": params}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        body = json.load(r)
    if body.get("error"):
        raise RuntimeError(str(body["error"])[:200])
    return body["result"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rpc", default=DEFAULT_RPC)
    ap.add_argument("--expect", type=int, default=8)
    ap.add_argument("--kickout-threshold", type=float, default=90.0)
    ap.add_argument("--watch", type=int, nargs="*", default=[],
                    help="block heights to report a countdown to")
    args = ap.parse_args()

    st = rpc(args.rpc, "status", [])
    h = st["sync_info"]["latest_block_height"]
    v = rpc(args.rpc, "validators", [None])
    try:
        peers = rpc(args.rpc, "network_info", [])["num_active_peers"]
    except Exception:                              # noqa: BLE001
        peers = None

    cur = v["current_validators"]
    nxt = [x["account_id"] for x in v.get("next_validators", [])]
    props = [p["account_id"] for p in v.get("current_proposals", [])]
    epoch_start = v.get("epoch_start_height")

    shards: dict[int, int] = {}
    for x in cur:
        for s in x.get("shards", []):
            shards[s] = shards.get(s, 0) + 1

    print(f"height {h}   epoch started {epoch_start}   peers {peers}")
    print(f"validators {len(cur)}/{args.expect}   "
          f"per shard {dict(sorted(shards.items()))}")

    healthy = len(cur) >= args.expect and shards and min(shards.values()) >= 2
    print(f"STATE: {'HEALTHY -- safe to measure' if healthy else 'DEGRADED -- must not measure'}")

    print(f"\n{'node':8} {'shard':>5} {'blocks':>14} {'%':>7} {'chunks':>14} {'%':>7}  verdict")
    for x in sorted(cur, key=lambda y: y["account_id"]):
        pb, eb = x["num_produced_blocks"], max(1, x["num_expected_blocks"])
        pc, ec = x["num_produced_chunks"], max(1, x["num_expected_chunks"])
        bp, cp = 100 * pb / eb, 100 * pc / ec
        doomed = bp < args.kickout_threshold or cp < args.kickout_threshold
        sh = ",".join(str(s) for s in x.get("shards", []))
        print(f"{x['account_id']:8} {sh:>5} {pb:6d}/{eb:6d} {bp:6.1f}% "
              f"{pc:6d}/{ec:6d} {cp:6.1f}%  "
              f"{'WILL BE EXPELLED' if doomed else 'safe'}")

    print(f"\nnext epoch ({len(nxt)}): {sorted(nxt)}")
    print(f"proposals        : {sorted(props)}")
    absent = sorted({x['account_id'] for x in cur} | set(nxt) | set(props))
    missing_next = [a for a in absent if a not in nxt and a not in props]
    if missing_next:
        print(f"NOT returning and NOT proposing: {missing_next}  "
              f"<- the supervisor should re-stake these")

    for target in args.watch:
        d = target - h
        if d > 0:
            print(f"block {target}: {d} blocks away = {d * 2 / 60:.0f} min")
        else:
            print(f"block {target}: reached")
    return 0


if __name__ == "__main__":
    sys.exit(main())
