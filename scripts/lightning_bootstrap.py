#!/usr/bin/env python3
"""Bring a deployed Lightning cluster from bare daemons to a funded topology.

Runs ON THE GENERATOR, against the LND REST endpoints.

WHY THIS IS A SCRIPT AND NOT PART OF THE STARTUP SCRIPT
-------------------------------------------------------
GCP re-runs startup scripts on every boot (RESUME_HERE.md S5 trap 2). On
Polygon that cost a morning. Here it would be far worse: re-creating an LND
wallet destroys its channel state, and with it the entire funded topology this
script spends real minutes building. Wallet creation therefore lives here,
runs once, is explicitly resumable, and refuses to touch a node that already
has a wallet.

ORDER MATTERS, AND EACH STEP GATES THE NEXT
-------------------------------------------
  1. create/unlock every wallet
  2. mine coins to each node that must OPEN a channel
  3. connect peers   -- a channel cannot be opened to an unknown peer
  4. open channels   -- per harness/topology.py
  5. mine to confirm -- channels are unusable until their funding tx confirms
  6. verify          -- every planned channel active, or the arm is invalid

Step 6 is not decoration. A partially-funded topology still produces payments
and numbers; they would simply be wrong, and wrong in the direction that makes
Lightning look worse than it is. Polygon's proof-of-authority bug taught that
a plausible failure result deserves the same scrutiny as a surprising success.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import ssl
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import aiohttp  # noqa: E402

from harness import topology as topo_mod  # noqa: E402

#: regtest needs 100 blocks before coinbase output is spendable.
COINBASE_MATURITY = 101

#: Confirmations before a channel is usable. 3 is LND's regtest default for
#: non-wumbo; we mine well past it because mining is free here and a channel
#: that is merely pending would look exactly like a liquidity failure.
CHANNEL_CONFIRMS = 6


class Node:
    def __init__(self, spec: dict, url: str, macaroon: str) -> None:
        self.id = spec["node_id"]
        self.tier = spec["tier"]
        self.role = spec["role"]
        self.host_index = spec["host_index"]
        self.url = url
        self.macaroon = macaroon
        self.pubkey: str | None = None
        self.p2p: str | None = None


async def rest(session, node: Node, method: str, path: str, body: dict | None = None):
    headers = {"Grpc-Metadata-macaroon": node.macaroon} if node.macaroon else {}
    async with session.request(method, f"{node.url}{path}", headers=headers,
                               json=body) as resp:
        text = await resp.text()
        if resp.status != 200:
            return None, f"{resp.status}: {text[:200]}"
        return json.loads(text) if text else {}, None


async def bitcoin_rpc(session, host: str, method: str, params: list):
    auth = aiohttp.BasicAuth("bench", "bench")
    async with session.post(f"http://{host}:18443/", auth=auth,
                            json={"jsonrpc": "1.0", "id": "bootstrap",
                                  "method": method, "params": params}) as resp:
        payload = await resp.json()
        if payload.get("error"):
            raise RuntimeError(f"{method}: {payload['error']}")
        return payload["result"]


async def wait_synced(session, nodes: list[Node], timeout: float = 300.0) -> bool:
    """Every node must see the chain tip before channels are opened.

    A node behind the tip will reject a channel open with a confusing error,
    and the retry loop that would follow is far harder to debug than waiting
    here.
    """
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        info = await asyncio.gather(*(rest(session, n, "GET", "/v1/getinfo") for n in nodes))
        if all(r is not None and r.get("synced_to_chain") for r, _ in info):
            return True
        await asyncio.sleep(5)
    return False


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--endpoints", required=True,
                    help="JSON: {node_id: {url, macaroon}} written by deploy_lightning.sh")
    ap.add_argument("--bitcoind-host", default="10.30.0.10")
    ap.add_argument("--out", default="config/phase3.json")
    args = ap.parse_args()

    plan = topo_mod.build()
    report = topo_mod.verify(plan)
    print(f"topology: {report['nodes']} nodes, {report['channels']} channels, "
          f"skew {report['capacity_skew']}x, {report['channels_per_node']} channels/node")
    if not report["skew_ok"]:
        print("REFUSING: topology is too flat to reproduce real routing failure")
        return 1

    endpoints = json.loads(Path(args.endpoints).read_text())
    nodes = {n.node_id: Node(n.__dict__, endpoints[n.node_id]["url"],
                             endpoints[n.node_id].get("macaroon", ""))
             for n in plan.nodes}

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE   # private regtest hosts, self-signed

    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(ssl=ssl_ctx, limit=64),
        timeout=aiohttp.ClientTimeout(total=120),
    ) as session:

        # 1. Identify every node. Wallets are expected to exist already --
        #    creating them needs the seed handling that deploy_lightning.sh
        #    does once, on the host, where the macaroon is readable.
        print("\n[1/6] identifying nodes")
        for node in nodes.values():
            info, err = await rest(session, node, "GET", "/v1/getinfo")
            if err:
                print(f"  {node.id}: NOT READY ({err})")
                return 1
            node.pubkey = info["identity_pubkey"]
            node.p2p = info["uris"][0] if info.get("uris") else None
        print(f"  {len(nodes)} nodes responding")

        # 2. Fund every node that opens a channel. Openers need on-chain coins;
        #    a node that only receives channels needs none.
        openers = sorted({c.source for c in plan.channels})
        print(f"\n[2/6] funding {len(openers)} channel openers")
        for node_id in openers:
            node = nodes[node_id]
            addr, err = await rest(session, node, "POST", "/v1/newaddress",
                                   {"type": "WITNESS_PUBKEY_HASH"})
            if err:
                print(f"  {node_id}: address failed ({err})")
                return 1
            await bitcoin_rpc(session, args.bitcoind_host, "generatetoaddress",
                              [10, addr["address"]])
        # Coinbase maturity: without these blocks the funds exist but cannot
        # be spent, and every channel open fails with an opaque error.
        burn, _ = await rest(session, nodes[openers[0]], "POST", "/v1/newaddress",
                             {"type": "WITNESS_PUBKEY_HASH"})
        await bitcoin_rpc(session, args.bitcoind_host, "generatetoaddress",
                          [COINBASE_MATURITY, burn["address"]])
        if not await wait_synced(session, list(nodes.values())):
            print("  nodes did not reach chain tip")
            return 1
        print("  funded and mature")

        # 3. Peer connections. Opening a channel to an unknown peer fails.
        print("\n[3/6] connecting peers")
        pairs = {(c.source, c.target) for c in plan.channels}
        for src, dst in sorted(pairs):
            target = nodes[dst]
            if not target.p2p:
                print(f"  {dst}: no reachable address")
                return 1
            host = target.p2p.split("@", 1)[1]
            await rest(session, nodes[src], "POST", "/v1/peers",
                       {"addr": {"pubkey": target.pubkey, "host": host}, "perm": True})
        print(f"  {len(pairs)} peer connections requested")

        # 4. Open channels exactly as planned.
        print(f"\n[4/6] opening {len(plan.channels)} channels")
        failures = []
        for ch in plan.channels:
            src, dst = nodes[ch.source], nodes[ch.target]
            body = {
                "node_pubkey_string": dst.pubkey,
                "local_funding_amount": str(ch.capacity_sat),
                "push_sat": str(ch.push_sat),
                "private": False,
                "sat_per_vbyte": "1",
            }
            res, err = await rest(session, src, "POST", "/v1/channels", body)
            if err:
                failures.append(f"{ch.source}->{ch.target} ({ch.capacity_sat} sat): {err}")
        if failures:
            print(f"  {len(failures)} channel opens failed:")
            for f in failures[:10]:
                print(f"    {f}")
            return 1
        print("  all opens accepted")

        # 5. Confirm.
        print(f"\n[5/6] mining {CHANNEL_CONFIRMS} blocks to confirm")
        await bitcoin_rpc(session, args.bitcoind_host, "generatetoaddress",
                          [CHANNEL_CONFIRMS, burn["address"]])
        await asyncio.sleep(10)
        await wait_synced(session, list(nodes.values()))

        # 6. Verify -- the step that decides whether the arm is measurable.
        print("\n[6/6] verifying")
        active = 0
        for node in nodes.values():
            chans, err = await rest(session, node, "GET", "/v1/channels")
            if err:
                continue
            active += sum(1 for c in chans.get("channels", []) if c.get("active"))
        active //= 2   # each channel is reported by both ends
        print(f"  active channels {active} / {len(plan.channels)}")
        if active < len(plan.channels):
            print("  REFUSING: topology incomplete. A partially funded network still")
            print("  produces numbers -- wrong ones, biased against Lightning.")
            return 1

        cfg = {
            "architecture": "lightning",
            "btc_usd_rate": 65163.0,
            "senders": [{"url": nodes[n.node_id].url, "macaroon": nodes[n.node_id].macaroon}
                        for n in plan.senders()],
            "recipients": [{"url": nodes[n.node_id].url, "macaroon": nodes[n.node_id].macaroon}
                           for n in plan.recipients()],
            "topology_report": report,
        }
        Path(args.out).write_text(json.dumps(cfg, indent=2))
        print(f"\ntopology live. config -> {args.out}")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
