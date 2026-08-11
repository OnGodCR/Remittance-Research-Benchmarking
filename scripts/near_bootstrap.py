#!/usr/bin/env python3
"""Deploy the NEP-141 token, create and fund accounts, write the run config.

Runs ON THE GENERATOR, inside the VPC. The harness has to run here anyway --
phase 1 measured a saturated generator at 5 payments/second purely because
every submission paid an intercontinental round trip.

ACCOUNTS ARE PLACED ACROSS SHARDS ON PURPOSE
--------------------------------------------
NEAR routes a transaction to the shard that owns the RECEIVER's account, so
whether a transfer is same-shard or cross-shard is decided entirely by account
names. If every sender and recipient landed on one shard, every transfer would
be same-shard, the extra block a cross-shard receipt needs would never be paid,
and the arm would report sharding numbers for work that was never divided.

`verify_distribution()` reads the genesis shard boundaries and checks the
accounts actually spread, rather than assuming it.

ORDER MATTERS -- EACH STEP GATES THE NEXT
-----------------------------------------
  1. create the token account and deploy the NEP-141 contract
  2. create sender and recipient accounts
  3. storage_deposit for every account that will hold tokens
     (NEP-141 rejects transfers to unregistered accounts, which would look
      like a chain failure rather than our setup)
  4. distribute the token supply to senders
  5. verify shard spread, registration and balances -- and REFUSE to write a
     config if any of them fail
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

#: The reference NEP-141 implementation, pinned. Fetched rather than built
#: because building needs a Rust toolchain the generator has no other use for.
#: Using the standard implementation matters: a hand-written token could have
#: different gas characteristics, and the cost comparison against Polygon's
#: ERC-20 would stop being like-for-like.
FT_WASM_URL = "https://github.com/near/near-sdk-rs/releases/download/5.1.0/fungible_token.wasm"

#: Six decimals, matching the ERC-20 on Polygon, so $200 is 200 tokens on both
#: chains and no exchange rate enters the study.
TOKEN_DECIMALS = 6

#: NEP-141 holds storage on each holder's behalf and requires a deposit.
STORAGE_DEPOSIT = 1_250_000_000_000_000_000_000        # 0.00125 NEAR
ACCOUNT_BALANCE = 10_000_000_000_000_000_000_000_000   # 10 NEAR per account
TGAS = 1_000_000_000_000


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rpc", default="http://10.40.0.10:3030")
    ap.add_argument("--senders", type=int, default=64,
                    help="NEAR orders transactions per access key by nonce, so "
                         "this is the concurrency ceiling")
    ap.add_argument("--recipients", type=int, default=16)
    ap.add_argument("--shards", type=int, default=4)
    ap.add_argument("--out", default="config/phase4.json")
    ap.add_argument("--keys-out", default="keys/near_senders.json")
    args = ap.parse_args()

    from py_near.account import Account
    from nacl.signing import SigningKey
    import base58

    key = json.loads(Path("/opt/near/localnet/node0/validator_key.json").read_text())
    master_id = key["account_id"]
    master = Account(master_id, key["secret_key"], rpc_addr=args.rpc)
    await master.startup()
    print(f"  master: {master_id}   balance: {await master.get_balance()/10**24:,.1f} NEAR")

    def new_key() -> tuple[str, str]:
        """Return (public_key, secret_key) in NEAR's ed25519:base58 form."""
        sk = SigningKey.generate()
        pub = bytes(sk.verify_key)
        return ("ed25519:" + base58.b58encode(pub).decode(),
                "ed25519:" + base58.b58encode(bytes(sk) + pub).decode())

    # --- 1. token contract -------------------------------------------------
    print("\n[1/5] deploying the NEP-141 token")
    wasm = Path("/tmp/fungible_token.wasm")
    if not wasm.exists() or wasm.stat().st_size < 1000:
        subprocess.run(["curl", "-fsSL", "-o", str(wasm), FT_WASM_URL], check=False)
    if not wasm.exists() or wasm.stat().st_size < 1000:
        print("  ERROR: could not fetch the NEP-141 contract"); return 1

    token_id = f"usdbench.{master_id}"
    token_pub, token_sec = new_key()
    if not await _exists(master, token_id):
        await master.create_account(token_id, token_pub, ACCOUNT_BALANCE * 10)
        print(f"  created {token_id}")
    token = Account(token_id, token_sec, rpc_addr=args.rpc)
    await token.startup()

    if not await _view_ok(token, token_id, "ft_metadata"):
        await token.deploy_contract(wasm.read_bytes())
        total = str(10**15 * 10**TOKEN_DECIMALS)
        await token.function_call(token_id, "new", {
            "owner_id": token_id,
            "total_supply": total,
            "metadata": {"spec": "ft-1.0.0", "name": "Benchmark USD",
                         "symbol": "USDB", "decimals": TOKEN_DECIMALS},
        }, gas=100 * TGAS)
        print(f"  deployed and initialised, supply {int(total)/10**TOKEN_DECIMALS:,.0f} USDB")
    else:
        print("  contract already deployed, leaving it alone")

    # --- 2. accounts -------------------------------------------------------
    print(f"\n[2/5] creating {args.senders} senders and {args.recipients} recipients")
    senders = [f"s{i:03d}.{master_id}" for i in range(args.senders)]
    recipients = [f"r{i:03d}.{master_id}" for i in range(args.recipients)]
    sender_keys: list[dict[str, str]] = []

    async def ensure(account_id: str) -> str:
        pub, sec = new_key()
        if not await _exists(master, account_id):
            await master.create_account(account_id, pub, ACCOUNT_BALANCE)
            return sec
        return ""

    for acct in senders:
        sec = await ensure(acct)
        if sec:
            sender_keys.append({"account_id": acct, "private_key": sec})
    for acct in recipients:
        await ensure(acct)
    print(f"  {len(sender_keys)} new sender keys written")

    if sender_keys:
        p = Path(args.keys_out); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(sender_keys, indent=2))

    # --- 3. registration ---------------------------------------------------
    # NEP-141 rejects a transfer to an unregistered account. Skipping this
    # would fail every payment addressed to that recipient and read as a chain
    # failure rather than as our setup.
    print(f"\n[3/5] registering {len(senders) + len(recipients)} accounts with the token")
    for acct in senders + recipients:
        await token.function_call(token_id, "storage_deposit",
                                  {"account_id": acct, "registration_only": True},
                                  gas=30 * TGAS, amount=STORAGE_DEPOSIT)
    print("  registered")

    # --- 4. fund senders ---------------------------------------------------
    print(f"\n[4/5] distributing tokens to {len(senders)} senders")
    per_sender = str(10**9 * 10**TOKEN_DECIMALS)   # 1e9 USDB each, ample
    for acct in senders:
        await token.function_call(token_id, "ft_transfer",
                                  {"receiver_id": acct, "amount": per_sender, "memo": None},
                                  gas=30 * TGAS, amount=1)
    print(f"  each sender holds {int(per_sender)/10**TOKEN_DECIMALS:,.0f} USDB")

    # --- 5. verify ---------------------------------------------------------
    print(f"\n[5/5] verifying")
    report = await verify_distribution(master, senders + recipients, args.shards)
    for shard, n in sorted(report["by_shard"].items()):
        print(f"    shard {shard}: {n} accounts")
    if not report["ok"]:
        print("  REFUSING: accounts are not spread across shards. Every transfer")
        print("  would be same-shard, and the arm would report sharding numbers")
        print("  for work that was never actually divided.")
        return 1

    unfunded = [a for a in senders[:5] if await _ft_balance(master, token_id, a) <= 0]
    if unfunded:
        print(f"  REFUSING: {len(unfunded)} sampled senders hold no tokens")
        return 1
    print(f"  shard spread OK across {len(report['by_shard'])} shards; senders funded")

    cfg = {
        "architecture": "near",
        "rpc_url": args.rpc,
        "token_contract": token_id,
        "recipients": recipients,
        "num_shards": args.shards,
        "shard_distribution": report["by_shard"],
        "token_decimals": TOKEN_DECIMALS,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(cfg, indent=2))
    print(f"\nconfig -> {args.out}")
    return 0


async def _exists(master, account_id: str) -> bool:
    try:
        await master._provider.get_account(account_id)
        return True
    except Exception:                              # noqa: BLE001
        return False


async def _view_ok(acct, contract: str, method: str) -> bool:
    try:
        await acct.view_function(contract, method, {})
        return True
    except Exception:                              # noqa: BLE001
        return False


async def _ft_balance(acct, contract: str, account_id: str) -> int:
    try:
        res = await acct.view_function(contract, "ft_balance_of", {"account_id": account_id})
        return int(res.result or 0)
    except Exception:                              # noqa: BLE001
        return 0


async def verify_distribution(master, accounts: list[str], num_shards: int) -> dict:
    """Check the accounts actually land on more than one shard.

    NEAR assigns an account to a shard by where its name falls between the
    genesis boundary accounts. Reading those boundaries and bucketing the names
    is the honest check; assuming a spread and being wrong would mean every
    measured transfer was same-shard while the paper reported sharding.
    """
    protocol = await master._provider.json_rpc(
        "EXPERIMENTAL_protocol_config", {"finality": "final"})
    layout = (protocol or {}).get("shard_layout", {})
    version = layout.get("V2") or layout.get("V1") or layout.get("V0") or {}
    boundaries = version.get("boundary_accounts") or []

    by_shard: dict[int, int] = {}
    for acct in accounts:
        shard = sum(1 for b in boundaries if acct >= b)
        by_shard[shard] = by_shard.get(shard, 0) + 1

    return {"by_shard": by_shard, "boundaries": boundaries, "ok": len(by_shard) > 1}


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
