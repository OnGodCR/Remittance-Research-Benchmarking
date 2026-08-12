"""Realism technique #3: competing background traffic.

WHY THIS MATTERS
----------------
Every measurement so far has run against an empty chain. At 300 payments per
second we were using roughly 4% of block capacity, so remittances never
competed with anything for space in a block.

Real blockchains are never empty. A remittance on Polygon mainnet queues
behind trading, gaming, NFT mints and everything else, and it wins space by
outbidding them. Measuring on an idle chain measures the best case that never
occurs in production.

WHAT THIS GENERATES
-------------------
Non-remittance transactions, running concurrently with the remittance
workload, at a rate that VARIES OVER TIME rather than staying constant
(claude.md S5 #3). Constant noise is unrealistic in the same way constant
arrival is: real congestion comes in waves, and it is the waves that cause
queues to build.

The noise is deliberately a DIFFERENT SHAPE of work from the payments being
measured -- native value transfers rather than token transfers. That keeps
the two separable in the data: anything consuming 21,000 gas is noise,
anything near 35,865 is a measured remittance. Using identical transactions
would make them impossible to tell apart after the fact.

WHAT IT DOES NOT DO
-------------------
Noise transactions are never recorded as results. They exist to occupy block
space, and they are sent from a separate account pool so they cannot collide
with the measured workload's transaction ordering.

USAGE
    python -m harness.noise --config config/phase1.json \\
        --duration 300 --base-tps 20 --peak-tps 80
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import sys
import time
from pathlib import Path

from .noise_shape import noise_rate
from eth_account import Account
from web3 import AsyncHTTPProvider, AsyncWeb3

REPO = Path(__file__).resolve().parent.parent

#: Native transfers cost 21,000 gas -- a distinct signature from the 35,865 a
#: token transfer uses, so noise and measured traffic stay separable in the
#: block data.
_NOISE_GAS = 21_000


async def generate_noise(rpc_url: str, chain_id: int, keys: list[str],
                         recipients: list[str], duration: float,
                         base_tps: float, peak_tps: float,
                         gas_price_wei: int, seed: int = 1234) -> dict:
    w3 = AsyncWeb3(AsyncHTTPProvider(rpc_url))

    # Polygon Edge is proof-of-authority; without this, web3 rejects every
    # block header as malformed. Same trap that produced a 100% failure rate
    # in Phase 1.
    from web3.middleware import ExtraDataToPOAMiddleware
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

    accounts = [Account.from_key(k) for k in keys]
    nonces = {}
    for a in accounts:
        nonces[a.address] = await w3.eth.get_transaction_count(a.address, "pending")
    locks = {a.address: asyncio.Lock() for a in accounts}

    rng = random.Random(seed)
    sent = failed = 0
    t0 = time.monotonic()

    async def one(i: int) -> None:
        nonlocal sent, failed
        acct = accounts[i % len(accounts)]
        to = recipients[i % len(recipients)]
        async with locks[acct.address]:
            nonce = nonces[acct.address]
            try:
                signed = Account.sign_transaction({
                    "to": to, "value": 1, "gas": _NOISE_GAS,
                    "gasPrice": gas_price_wei, "nonce": nonce, "chainId": chain_id,
                }, acct.key)
                await w3.eth.send_raw_transaction(signed.raw_transaction)
                nonces[acct.address] = nonce + 1
                sent += 1
            except Exception:
                # Noise failures are unimportant -- the point is occupying
                # block space, not measuring anything. The nonce is left
                # unadvanced so this account recovers on its next attempt.
                failed += 1

    tasks: set[asyncio.Task] = set()
    i = 0
    print(f"background traffic: {base_tps:g}-{peak_tps:g}/sec, varying, "
          f"for {duration:g}s")

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

    if tasks:
        await asyncio.wait(tasks, timeout=30)

    provider = w3.provider
    if hasattr(provider, "disconnect"):
        await provider.disconnect()

    return {"sent": sent, "failed": failed,
            "mean_rate": sent / duration if duration else 0.0}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", required=True)
    p.add_argument("--duration", type=float, default=300.0)
    # CALIBRATED TO REAL POLYGON MAINNET ACTIVITY, 8 Aug 2026.
    #
    # Polygon PoS carries roughly 7.5 million transactions per day, about 87
    # per second, and is reported at 68-109/sec during normal operation. The
    # original 20-80 default (mean ~45) understated real background load by
    # roughly half, which would have made our chain look emptier -- and
    # therefore better-performing -- than the network it stands in for.
    #
    # 60-115 gives a mean near 87, matching observed mainnet activity.
    p.add_argument("--base-tps", type=float, default=60.0,
                   help="quiet-period background rate (calibrated to mainnet)")
    p.add_argument("--peak-tps", type=float, default=115.0,
                   help="busy-period background rate (calibrated to mainnet)")
    p.add_argument("--keys", default="keys/noise_senders.json",
                   help="separate account pool -- MUST NOT overlap the measured "
                        "workload's accounts, or the two collide on transaction "
                        "ordering and the interference is our own doing")
    args = p.parse_args()

    config = json.loads(Path(args.config).read_text())
    keys_path = REPO / args.keys
    if not keys_path.exists():
        print(f"ERROR: no noise accounts at {keys_path}.\n"
              f"Create them with: python -m scripts.deploy_and_fund "
              f"--senders N --keys-out {args.keys}")
        return 1

    result = asyncio.run(generate_noise(
        rpc_url=config["rpc_url"], chain_id=config["chain_id"],
        keys=json.loads(keys_path.read_text()),
        recipients=config["recipients"], duration=args.duration,
        base_tps=args.base_tps, peak_tps=args.peak_tps,
        gas_price_wei=config.get("gas_price_wei", 1_000_000_000),
    ))
    print(f"background traffic finished: {result['sent']:,} sent, "
          f"{result['failed']:,} rejected, mean {result['mean_rate']:.1f}/sec")
    return 0


if __name__ == "__main__":
    sys.exit(main())
