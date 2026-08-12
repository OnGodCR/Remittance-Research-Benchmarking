"""Realism technique #3 for NEAR: competing background traffic.

WHY THIS EXISTS
---------------
`harness/noise.py` is EVM-only -- web3, eth_account, 21,000-gas native
transfers, a `chain_id`. It cannot speak to NEAR at all. Without a NEAR
equivalent the phase-4 sweep would run against an idle chain while every one of
Polygon's 140 runs carried ~88 transactions per second of competing load. NEAR
would then win the comparison partly because nothing else was using its blocks,
which is not a fact about sharding.

Verified 12 Aug 2026: neither NEAR sweep script started any background traffic.
Polygon's sweep script refuses to start without it, with the comment "the sweep
would run against an idle chain, which is not the full realism stack."

WHAT IT GENERATES
-----------------
Native NEAR transfers -- deliberately a DIFFERENT SHAPE of work from the
NEP-141 `ft_transfer` calls being measured. That mirrors the Polygon design,
where noise is a 21,000-gas native transfer against a 35,865-gas token transfer,
and it keeps the two separable in the block data after the fact: a payment that
invoked no contract is noise, a payment that called `ft_transfer` is a measured
remittance. Using identical transactions would make them impossible to tell
apart.

The rate varies over time using `harness/noise_shape.py`, the SAME wave Polygon
used, so the two architectures meet identical congestion patterns rather than
merely similar ones.

WHY THE RATE MATCHES POLYGON RATHER THAN NEAR MAINNET
-----------------------------------------------------
NEAR mainnet carries far less traffic than Polygon mainnet -- measured 12 Aug
2026 at roughly 5 transactions per second across 10 shards, against Polygon's
~87. Calibrating each chain's noise to its own mainnet would have given NEAR a
near-idle chain and Polygon a busy one, so a large part of any measured
difference would be the difference in how popular the two networks currently
are, not how the architectures perform.

The comparison this study exists to make is architectural, so both are offered
the SAME competing load. The consequence must be stated in the paper: our NEAR
runs face roughly 18x more background traffic than NEAR mainnet currently
carries, which makes the NEAR result **conservative** -- the safe direction, and
the same principle applied to the impairment values.

WHAT IT DOES NOT DO
-------------------
Noise is never recorded as a result. It exists to occupy block space, and it
comes from a SEPARATE account pool so it cannot collide with the measured
workload's nonce ordering -- NEAR sequences transactions per access key, so
sharing accounts between noise and payments would make each stall the other.

USAGE
    python -m harness.noise_near --config config/phase4.json \\
        --keys keys/near_noise_senders.json --duration 300
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import time
from pathlib import Path

import base58 as _b58
from py_near import transactions as _near_tx
from py_near.account import Account

from .noise_shape import noise_rate

#: 1 yoctoNEAR. The transfer must be non-zero to be a real transfer, but the
#: value is irrelevant -- the point is occupying block space, not moving money.
_NOISE_AMOUNT = 1


async def _balance(acct, account_id: str) -> int:
    """Native NEAR balance of an account, used only by the landing probe."""
    r = await acct._provider.get_account(account_id)
    return int(r["amount"]) if isinstance(r, dict) and "amount" in r else 0


async def generate_noise(rpc_url: str, keys: list[dict], recipients: list[str],
                         duration: float, base_tps: float, peak_tps: float,
                         seed: int = 1234) -> dict:
    accounts = []
    for k in keys:
        a = Account(k["account_id"], k["private_key"], rpc_addr=rpc_url)
        await a.startup()
        accounts.append(a)

    # PRIME EACH NONCE FROM THE CHAIN. This line is the whole ballgame.
    #
    # py-near's Account._access_key_nonce starts at 0 and is NOT populated by
    # startup(). NEAR sets an account's initial nonce from the block height at
    # creation, so it is a large number -- and a transaction signed with nonce 1
    # is stale, and the chain drops it. broadcast_tx_async does not validate, so
    # every send returns happily and nothing lands.
    #
    # Without this, the generator reported "3,646 sent, 0 failed, 81/sec" while
    # the chain carried 0.4 transactions/sec. The sweep then ran with NO
    # background traffic while its runs recorded background_traffic.enabled =
    # True -- the exact condition this module exists to prevent, wearing the
    # appearance of success. NearAdapter.setup does the same priming; the
    # omission here is why its payments landed and these did not.
    signers = {}
    for a in accounts:
        pk = await a._free_signers.get()
        await a._free_signers.put(pk)
        access_key = await a.get_access_key(pk)
        a._access_key_nonce[pk] = max(a._access_key_nonce[pk], access_key.nonce)
        signers[a.account_id] = pk
    locks = {a.account_id: asyncio.Lock() for a in accounts}

    rng = random.Random(seed)
    sent = failed = 0
    t0 = time.monotonic()

    async def one(i: int) -> None:
        nonlocal sent, failed
        acct = accounts[i % len(accounts)]
        to = recipients[i % len(recipients)]
        # ONE IN FLIGHT PER ACCOUNT. NEAR orders per access key by nonce, so
        # concurrent sends from one account collide and neither lands.
        async with locks[acct.account_id]:
            try:
                await acct._update_last_block_hash()
                pk = signers[acct.account_id]
                acct._access_key_nonce[pk] += 1
                nonce = acct._access_key_nonce[pk]
                block_hash = _b58.b58decode(acct._latest_block_hash.encode("utf8"))
                actions = [_near_tx.create_transfer_action(_NOISE_AMOUNT)]
                signed = _near_tx.sign_and_serialize_transaction(
                    acct.account_id, pk, to, nonce, actions, block_hash)
                # broadcast_tx_async: returns as soon as the node accepts it and
                # never waits for execution. py-near's nowait= flag does NOT do
                # this -- it blocks server-side until block inclusion, which
                # would cap noise at roughly one transaction per account per
                # two seconds and quietly deliver a fraction of the intended
                # load while reporting success.
                await acct._provider.send_tx(signed)
                sent += 1
            except Exception:                      # noqa: BLE001
                # Noise failures do not matter -- nothing is being measured
                # here. The nonce is left advanced; the account recovers on its
                # next turn once the chain catches up.
                failed += 1

    print(f"NEAR background traffic: {base_tps:g}-{peak_tps:g}/sec, varying, "
          f"for {duration:g}s across {len(accounts)} accounts", flush=True)

    # PROVE IT LANDS BEFORE CLAIMING TO GENERATE LOAD.
    #
    # "sent" only means the node accepted the broadcast. Twice on 12 Aug a
    # component reported thousands of successful sends while the chain saw
    # none, because the transactions were signed with stale nonces and dropped
    # without complaint. A generator that silently produces no load is worse
    # than one that crashes: the sweep runs to completion and records
    # conditions that never existed.
    #
    # So: send one, wait, and confirm the recipient's balance actually moved.
    # 20s, not 4s. Measured settlement to FINAL on this chain is ~9s at p50,
    # so a 4-second probe reports "not landing" for a transfer that is merely
    # still in flight -- a false alarm that would block every run.
    probe_to = recipients[0]
    before = await _balance(accounts[0], probe_to)
    await one(0)
    landed = False
    for _ in range(10):
        await asyncio.sleep(2)
        after = await _balance(accounts[0], probe_to)
        if after > before:
            landed = True
            break
    if not landed:
        raise RuntimeError(
            f"background traffic is NOT landing: {probe_to} balance unchanged "
            f"({before} -> {after}) after a probe transfer. Refusing to run: a "
            f"silent no-op here means the whole sweep is measured on an idle "
            f"chain while recording that it was not.")
    print(f"  probe landed ({probe_to} {before} -> {after}); traffic is real",
          flush=True)
    # Reset the counters so the probe is not reported as delivered load.
    sent = 0
    t0 = time.monotonic()

    tasks: set[asyncio.Task] = set()
    i = 0
    while True:
        elapsed = time.monotonic() - t0
        if elapsed >= duration:
            break
        rate = noise_rate(elapsed, duration, base_tps, peak_tps)
        await asyncio.sleep(rng.expovariate(max(rate, 0.1)))
        t = asyncio.create_task(one(i))
        tasks.add(t)
        t.add_done_callback(tasks.discard)
        i += 1
        if i % 2000 == 0:
            print(f"  t={elapsed:5.0f}s  sent={sent:6d} failed={failed:5d} "
                  f"target={rate:5.1f}/sec", flush=True)

    if tasks:
        await asyncio.wait(tasks, timeout=30)

    return {"sent": sent, "failed": failed,
            "mean_rate": sent / duration if duration else 0.0}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", required=True)
    p.add_argument("--keys", default="keys/near_noise_senders.json")
    p.add_argument("--duration", type=float, default=300.0)
    # 60-115 gives a mean near 87.5, matching the Polygon runs exactly
    # (recorded there as mean_tps 88, calibrated to Polygon mainnet ~87/sec).
    p.add_argument("--base-tps", type=float, default=60.0)
    p.add_argument("--peak-tps", type=float, default=115.0)
    p.add_argument("--seed", type=int, default=1234)
    args = p.parse_args()

    config = json.loads(Path(args.config).read_text())
    keys_path = Path(args.keys)
    if not keys_path.exists():
        print(f"missing {keys_path}. Run scripts/near_noise_bootstrap.py first "
              f"-- noise needs its OWN accounts, separate from the measured "
              f"senders, or the two will stall each other on nonce ordering.",
              file=sys.stderr)
        return 1
    keys = json.loads(keys_path.read_text())

    result = asyncio.run(generate_noise(
        rpc_url=config["rpc_url"], keys=keys,
        recipients=config["recipients"], duration=args.duration,
        base_tps=args.base_tps, peak_tps=args.peak_tps, seed=args.seed))

    print(f"\nbackground traffic finished: sent {result['sent']:,}, "
          f"failed {result['failed']:,}, mean {result['mean_rate']:.1f}/sec")
    return 0


if __name__ == "__main__":
    sys.exit(main())
