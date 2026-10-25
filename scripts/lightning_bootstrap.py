#!/usr/bin/env python3
"""Bring a deployed Lightning cluster from bare daemons to a funded topology.

Runs ON THE GENERATOR, against the LND REST endpoints.

WHY THIS IS A SCRIPT AND NOT PART OF THE STARTUP SCRIPT
-------------------------------------------------------
GCP re-runs startup scripts on every boot (README.md cloud trap 2). On
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


async def bitcoin_rpc(session, host: str, method: str, params: list, wallet: str = ""):
    auth = aiohttp.BasicAuth("bench", "bench")
    path = f"/wallet/{wallet}" if wallet else "/"
    async with session.post(f"http://{host}:18443{path}", auth=auth,
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
    # Agreement on block height is the substantive condition, not the
    # `synced_to_chain` flag. That flag flaps: a node momentarily reports false
    # right after a block even while sitting at the tip, and one node in Mumbai
    # doing so was enough to fail the whole run. What actually matters for
    # opening channels is that every node sees the same chain.
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        info = await asyncio.gather(*(rest(session, n, "GET", "/v1/getinfo") for n in nodes))
        heights = {r.get("block_height") for r, _ in info if r}
        got_all = len([1 for r, _ in info if r]) == len(nodes)
        if got_all and len(heights) == 1 and None not in heights:
            return True
        await asyncio.sleep(5)
    return False


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--endpoints", required=True,
                    help="JSON: {node_id: {url, macaroon}} written by deploy_lightning.sh")
    ap.add_argument("--bitcoind-host", default="10.30.0.10")
    ap.add_argument("--out", default="config/phase3.json")
    ap.add_argument("--scale", type=int, default=1,
                    help="capacity multiplier; topo_mod.WELL_CAPITALISED_SCALE for the main arm")
    args = ap.parse_args()

    plan = topo_mod.build(scale=args.scale)
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
        # Openers are funded by TRANSFER from the mining wallet, not by mining
        # to each of them.
        #
        # The first version mined blocks directly to every opener until its
        # balance was sufficient. That works only while the block subsidy is
        # large. regtest halves the subsidy every 150 blocks, so by the time the
        # chain had grown past 25,000 blocks each block was worth nothing and
        # the loop mined tens of thousands of blocks while funding nobody.
        #
        # The mining wallet already holds the early, large subsidies. Sending
        # from it is one transaction per opener and is independent of height.
        # Which channels already exist must be known BEFORE funding, not after.
        # Funding was sized from the whole plan, but a re-run's openers have
        # already spent their coins into the channels they opened -- so the
        # script saw them as broke and demanded 1,900 BTC that was not missing
        # at all, it was simply already inside channels. Need is therefore
        # computed only over channels still to open.
        existing: set[tuple[str, str]] = set()
        for node in nodes.values():
            for path in ("/v1/channels", "/v1/channels/pending"):
                data, _ = await rest(session, node, "GET", path)
                if not data:
                    continue
                blobs = (data.get("channels") or []) + \
                        [q.get("channel", {}) for q in data.get("pending_open_channels") or []]
                for c in blobs:
                    peer = c.get("remote_pubkey") or c.get("remote_node_pub")
                    if peer:
                        existing.add(tuple(sorted((node.pubkey or "", peer))))

        remaining = [ch for ch in plan.channels
                     if tuple(sorted((nodes[ch.source].pubkey or "",
                                      nodes[ch.target].pubkey or ""))) not in existing]
        print(f"  {len(existing)} channels already open, {len(remaining)} to go")

        need: dict[str, int] = {}
        for ch in remaining:
            need[ch.source] = need.get(ch.source, 0) + ch.capacity_sat

        openers = sorted(need)
        total_btc = sum(need.values()) / 1e8
        print(f"\n[2/6] funding {len(openers)} openers for {len(remaining)} channels "
              f"({total_btc:,.1f} BTC)")

        # Send only the SHORTFALL. A re-run must not re-send what an opener
        # already holds: the first attempt moved most of the mining wallet's
        # balance out, and topping every node up from zero again would demand
        # far more than exists -- the run would refuse to start even though the
        # coins were already sitting exactly where they belonged.
        shortfall: dict[str, float] = {}
        for node_id in openers:
            b, _ = await rest(session, nodes[node_id], "GET", "/v1/balance/blockchain")
            have = int((b or {}).get("confirmed_balance", 0) or 0)
            want = int(need[node_id] * 1.5)     # headroom for fees and reserve
            if have < want:
                shortfall[node_id] = round((want - have) / 1e8, 8)

        if not shortfall:
            print("  every opener already funded")
        else:
            required = sum(shortfall.values())
            bal = await bitcoin_rpc(session, args.bitcoind_host, "getbalance", [], wallet="bench")
            print(f"  {len(shortfall)} openers short by {required:,.1f} BTC; wallet holds {bal:,.1f}")
            if bal < required * 1.02:
                print("  INSUFFICIENT: mine more early-subsidy blocks or lower --scale")
                return 1
            for node_id, amount in shortfall.items():
                addr, err = await rest(session, nodes[node_id], "GET",
                                       "/v1/newaddress?type=WITNESS_PUBKEY_HASH")
                if err:
                    print(f"  {node_id}: address failed ({err})")
                    return 1
                await bitcoin_rpc(session, args.bitcoind_host, "sendtoaddress",
                                  [addr["address"], amount], wallet="bench")
                print(f"  {node_id}: topped up {amount:,.2f} BTC")

        burn, _ = await rest(session, nodes[openers[0]], "GET",
                             "/v1/newaddress?type=WITNESS_PUBKEY_HASH")
        # Mine until the mempool is empty, not a fixed number of blocks. A
        # fixed count confirmed only the transfers that had propagated by then;
        # the rest sat unconfirmed, and every channel open failed with "not
        # enough witness outputs ... only have 0 BTC available" -- an error that
        # points at the opener rather than at the funding that never confirmed.
        for _ in range(20):
            info = await bitcoin_rpc(session, args.bitcoind_host, "getmempoolinfo", [])
            if int(info.get("size", 0)) == 0:
                break
            await bitcoin_rpc(session, args.bitcoind_host, "generatetoaddress",
                              [3, burn["address"]])
            await asyncio.sleep(2)
        await bitcoin_rpc(session, args.bitcoind_host, "generatetoaddress",
                          [3, burn["address"]])
        # Wait for the coins to actually appear in each opener's wallet.
        #
        # Mining until the mempool empties confirms the transfers on the chain,
        # but LND still has to scan those blocks and credit its own wallet.
        # Opening a channel in that gap fails with "not enough witness outputs
        # ... only have 0 BTC available" -- which reads as a funding failure
        # when the funding is already on chain and simply not yet noticed.
        print("  waiting for openers to see their funds")
        deadline_funds = asyncio.get_event_loop().time() + 300
        while asyncio.get_event_loop().time() < deadline_funds:
            short = []
            for node_id in openers:
                b, _ = await rest(session, nodes[node_id], "GET", "/v1/balance/blockchain")
                have = int((b or {}).get("confirmed_balance", 0) or 0)
                if have < need[node_id]:
                    short.append(node_id)
            if not short:
                break
            await bitcoin_rpc(session, args.bitcoind_host, "generatetoaddress",
                              [2, burn["address"]])
            await asyncio.sleep(10)
        else:
            print(f"  WARNING: {len(short)} openers still short after 300s")

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

        # Reuses the `existing` set computed before funding -- opens are
        # on-chain and irreversible, so repeating one would burn coins and
        # build a topology that no longer matches the verified plan.
        if existing:
            print(f"  {len(existing)} channels already present, skipping those")

        # Opens are retried in rounds, mining between them.
        #
        # An opener funds several channels. The first open spends its UTXO and
        # returns the remainder as CHANGE, which is unconfirmed -- so the second
        # open from the same node fails with "only have 0 BTC available" even
        # though the node holds plenty. Mining between rounds confirms the
        # change and lets the next open proceed. Repeating until no further
        # progress converges without guessing how many rounds are needed.
        pending = list(remaining)
        for round_no in range(1, 13):
            failures = []
            for ch in pending:
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
                    failures.append(ch)
            opened = len(pending) - len(failures)
            print(f"  round {round_no}: opened {opened}, {len(failures)} remaining")
            if not failures:
                break
            if opened == 0 and round_no > 2:
                print("  no progress -- these cannot be funded:")
                for ch in failures[:5]:
                    print(f"    {ch.source}->{ch.target} ({ch.capacity_sat/1e8:.2f} BTC)")
                return 1
            pending = failures
            await bitcoin_rpc(session, args.bitcoind_host, "generatetoaddress",
                              [3, burn["address"]])
            await asyncio.sleep(12)
        else:
            print(f"  {len(pending)} channels never opened")
            return 1

        print("  all opens accepted")

        # 5. Confirm.
        print(f"\n[5/6] mining {CHANNEL_CONFIRMS} blocks to confirm")
        await bitcoin_rpc(session, args.bitcoind_host, "generatetoaddress",
                          [CHANNEL_CONFIRMS, burn["address"]])
        await asyncio.sleep(10)
        await wait_synced(session, list(nodes.values()))

        # 6. Verify -- the step that decides whether the arm is measurable.
        # A channel becomes active only once both ends are connected and the
        # funding is confirmed, and peers three continents apart take longer to
        # get there than local ones. Judging once, immediately, mistakes "not
        # yet" for "never" -- so poll.
        print("\n[6/6] verifying")
        deadline = asyncio.get_event_loop().time() + 900
        active = 0
        while True:
            active = 0
            for node in nodes.values():
                chans, err = await rest(session, node, "GET", "/v1/channels")
                if err:
                    continue
                active += sum(1 for c in chans.get("channels", []) if c.get("active"))
            active //= 2   # each channel is reported by both ends
            if active >= len(plan.channels) or asyncio.get_event_loop().time() > deadline:
                break
            print(f"  {active}/{len(plan.channels)} active, waiting...")
            await bitcoin_rpc(session, args.bitcoind_host, "generatetoaddress",
                              [1, burn["address"]])
            await asyncio.sleep(20)
        print(f"  active channels {active} / {len(plan.channels)}")
        if active < len(plan.channels):
            print("  REFUSING: topology incomplete. A partially funded network still")
            print("  produces numbers -- wrong ones, biased against Lightning.")
            return 1

        cfg = {
            "architecture": "lightning",
            "btc_usd_rate": topo_mod.BTC_USD_PINNED,
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
