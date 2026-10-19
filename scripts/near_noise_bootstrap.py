#!/usr/bin/env python3
"""Create and fund the account pool that generates NEAR background traffic.

Runs ON THE GENERATOR.

WHY A SEPARATE POOL FROM THE MEASURED SENDERS
---------------------------------------------
NEAR orders transactions per access key by nonce, so one account cannot hold two
transactions in flight. If noise and measured payments shared accounts they
would serialise behind each other: the noise would throttle the measurement and
the measurement would throttle the noise, and the run would report a throughput
ceiling that was really a nonce queue. That is the same fault that capped the
first phase-4 attempt at 14-32/sec.

HOW MANY ACCOUNTS
-----------------
Background traffic peaks at 115/sec. At roughly 2s to inclusion and one
transaction in flight per account, sustaining R/sec needs about 2R accounts to
never queue; 3R gives headroom for a slow block. 115 x 3 / 10 is the same
arithmetic `NearAdapter.required_pool_size` uses. The default below is
deliberately generous because these accounts are cheap and running short would
silently deliver less background load than intended -- which would look like a
successful run against a busier chain than actually existed.

WHY NATIVE NEAR AND NO TOKEN REGISTRATION
-----------------------------------------
Noise transactions are native transfers, not NEP-141 calls, so these accounts
never touch the token contract and need no `storage_deposit`. That is also what
keeps noise separable from measured payments in the block data.

WHY THE ACCOUNTS ARE SPREAD ACROSS SHARDS
-----------------------------------------
Background traffic that all landed on one shard would congest that shard and
leave the other three idle, which is not what a busy chain looks like and would
distort the same-shard versus cross-shard comparison the arm depends on. The
same boundary-straddling prefixes the measured accounts use are applied here.

USAGE
    ./.venv/bin/python scripts/near_noise_bootstrap.py --count 360
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

#: 1 NEAR each. Noise transfers move 1 yoctoNEAR, so this covers gas for far
#: more transactions than the whole matrix will send.
ACCOUNT_BALANCE = 1_000_000_000_000_000_000_000_000


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rpc", default="http://10.40.0.10:3030")
    ap.add_argument("--count", type=int, default=360,
                    help="peak noise is 115/sec; ~3x that at 2s inclusion")
    ap.add_argument("--out", default="/opt/benchmark/keys/near_noise_senders.json")
    ap.add_argument("--tag", default="n")
    args = ap.parse_args()

    from py_near.account import Account
    from nacl.signing import SigningKey
    import base58

    key = json.loads(
        Path("/opt/near/localnet/node0/validator_key.json").read_text())
    master_id = key["account_id"]
    master = Account(master_id, key["secret_key"], rpc_addr=args.rpc)
    await master.startup()
    bal = await master.get_balance() / 10**24
    print(f"master {master_id}, balance {bal:,.0f} NEAR")
    need = args.count * ACCOUNT_BALANCE / 10**24
    if bal < need * 1.1:
        print(f"REFUSING: need ~{need:,.0f} NEAR for {args.count} accounts, "
              f"master holds {bal:,.0f}")
        return 1

    def new_key() -> tuple[str, str]:
        sk = SigningKey.generate()
        pub = bytes(sk.verify_key)
        return ("ed25519:" + base58.b58encode(pub).decode(),
                "ed25519:" + base58.b58encode(bytes(sk) + pub).decode())

    # Same shard-straddling prefixes as the measured accounts: names sort
    # against the genesis boundary accounts ['test1','test2','test3'], so
    # anything before 'test1' lands on shard 0 and the rest follow.
    prefixes = ["aa", "test1a", "test2a", "test3a"]
    names = [f"{prefixes[i % 4]}noise{args.tag}{i:04d}.{master_id}"
             for i in range(args.count)]

    out_path = Path(args.out)
    existing = {}
    if out_path.exists():
        for k in json.loads(out_path.read_text()):
            existing[k["account_id"]] = k

    print(f"\ncreating {len(names)} noise accounts")
    created = []
    for i, name in enumerate(names):
        if name in existing:
            created.append(existing[name])
            continue
        pub, sec = new_key()
        try:
            # nowait: submitted without waiting for finality, then verified in
            # bulk below. Waiting per account costs ~2s each.
            await master.create_account(name, pub, ACCOUNT_BALANCE, nowait=True)
            created.append({"account_id": name, "private_key": sec,
                            "public_key": pub})
        except Exception as exc:                   # noqa: BLE001
            print(f"  {name}: {type(exc).__name__}")
        if (i + 1) % 60 == 0:
            print(f"  {i + 1}/{len(names)} submitted")

    # VERIFY BEFORE WRITING, for the reason near_bootstrap.py now does: a key
    # written for an account that does not carry it produces a sender that
    # cannot sign, and the failure surfaces later as a chain error rather than
    # a setup error.
    print(f"\nverifying {len(created)} accounts carry their keys")
    verified = []
    for attempt in range(25):
        await asyncio.sleep(4)
        verified, pending = [], []
        for k in created:
            try:
                res = await master._provider.json_rpc("query", {
                    "request_type": "view_access_key_list",
                    "finality": "final", "account_id": k["account_id"]})
                if any(x.get("public_key") == k["public_key"]
                       for x in (res or {}).get("keys", [])):
                    verified.append(k)
                else:
                    pending.append(k["account_id"])
            except Exception:                      # noqa: BLE001
                pending.append(k["account_id"])
        if not pending:
            break
        if attempt % 5 == 0:
            print(f"  {len(verified)}/{len(created)} confirmed")

    if len(verified) < args.count * 0.9:
        print(f"REFUSING: only {len(verified)} of {args.count} accounts "
              f"verified. Background traffic would run at a fraction of the "
              f"intended rate, and the runs would look like a busy chain "
              f"while facing a quiet one.")
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(verified, indent=2))
    print(f"\n{len(verified)} noise accounts ready -> {out_path}")

    by_shard: dict[str, int] = {}
    for k in verified:
        n = k["account_id"]
        s = "0" if n < "test1" else "1" if n < "test2" else "2" if n < "test3" else "3"
        by_shard[s] = by_shard.get(s, 0) + 1
    print(f"shard spread: {dict(sorted(by_shard.items()))}")
    return 0


sys.exit(asyncio.run(main()))
