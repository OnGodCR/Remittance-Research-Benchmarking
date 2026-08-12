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

#: The reference NEP-141 implementation, BUILT FROM SOURCE on the generator by
#: scripts/build_ft.sh.
#:
#: No prebuilt artifact is published anywhere reliable: near-examples/FT has no
#: releases, and every res/*.wasm path older guides cite now returns a 404 HTML
#: page (which downloads as ~300 KB and looks like a file until you check the
#: magic bytes). Building from near-sdk-rs is better anyway -- it is the
#: implementation the ecosystem actually uses, so gas figures stay comparable
#: with Polygon's ERC-20 rather than reflecting a contract we invented.
FT_WASM_PATH = "/opt/benchmark/fungible_token.wasm"

#: Six decimals, matching the ERC-20 on Polygon, so $200 is 200 tokens on both
#: chains and no exchange rate enters the study.
TOKEN_DECIMALS = 6

#: NEP-141 holds storage on each holder's behalf and requires a deposit.
STORAGE_DEPOSIT = 1_250_000_000_000_000_000_000        # 0.00125 NEAR
ACCOUNT_BALANCE = 2_000_000_000_000_000_000_000_000    # 2 NEAR per account
#: 2 NEAR, not 10. With ~900 senders the larger figure would need 9,000 NEAR of
#: the master's balance; 2 comfortably covers storage plus gas for a sender
#: that only ever calls ft_transfer.
TGAS = 1_000_000_000_000


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rpc", default="http://10.40.0.10:3030")
    ap.add_argument("--senders", type=int, default=900,
                    help="NEAR orders transactions per access key by nonce, so "
                         "the sender count IS the concurrency ceiling. At ~2s "
                         "to inclusion, sustaining N/sec needs roughly 3N "
                         "senders; 300/sec therefore needs ~900. Measured with "
                         "64, the ceiling was 14-32/sec and the top of the "
                         "load ramp could not be reached at all.")
    ap.add_argument("--recipients", type=int, default=16)
    ap.add_argument("--shards", type=int, default=4)
    ap.add_argument("--out", default="config/phase4.json")
    ap.add_argument("--keys-out", default="keys/near_senders.json")
    ap.add_argument("--tag", default="a",
                    help="short prefix for account names. Change it to get a "
                         "clean identity set: accounts left over from an "
                         "earlier attempt hold keys we no longer have, and "
                         "NEAR has no way to reclaim them without the key.")
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
    wasm = Path(FT_WASM_PATH)
    if not wasm.exists() or wasm.stat().st_size < 1000:
        print(f"  ERROR: {FT_WASM_PATH} missing. Run scripts/build_ft.sh first.")
        return 1
    if wasm.read_bytes()[:4] != b"\x00asm":
        print(f"  ERROR: {FT_WASM_PATH} is not a wasm module")
        return 1

    token_id = f"usdb{args.tag}.{master_id}"
    # Persisted, so a re-run signs with the key the account was created with.
    # Generating a fresh key each time guarantees "access key does not exist".
    token_key_path = Path(f"/opt/benchmark/keys/near_token_{args.tag}.json")
    token_key_path.parent.mkdir(parents=True, exist_ok=True)
    if token_key_path.exists() and await _exists(master, token_id):
        saved = json.loads(token_key_path.read_text())
        token_pub, token_sec = saved["public_key"], saved["private_key"]
        print(f"  reusing existing {token_id}")
    else:
        token_pub, token_sec = new_key()
        token_key_path.write_text(json.dumps(
            {"account_id": token_id, "public_key": token_pub, "private_key": token_sec}))
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
    # Account names are chosen to STRADDLE the shard boundaries.
    #
    # NEAR assigns an account to a shard by where its name sorts between the
    # genesis boundary accounts, which on this chain are ['test1','test2',
    # 'test3']. Names beginning with 's' or 'r' all sort BEFORE 'test1', so
    # every account landed on shard 0 -- 80 accounts, one shard, and every
    # transfer would have been same-shard while the arm reported sharding.
    #
    # These prefixes place accounts deliberately in each shard:
    #     <anything before 'test1'>  -> shard 0
    #     test1...                   -> shard 1
    #     test2...                   -> shard 2
    #     test3... (or later)        -> shard 3
    shard_prefix = ["aa", "test1a", "test2a", "test3a"]

    def spread(kind: str, n: int) -> list[str]:
        out = []
        for i in range(n):
            pre = shard_prefix[i % len(shard_prefix)]
            out.append(f"{pre}{kind}{args.tag}{i:03d}.{master_id}")
        return out

    senders = spread("s", args.senders)
    recipients = spread("r", args.recipients)
    sender_keys: list[dict[str, str]] = []

    existing_keys = {}
    kp = Path(args.keys_out)
    if kp.exists():
        existing_keys = {k["account_id"]: k["private_key"]
                         for k in json.loads(kp.read_text())}

    async def ensure(account_id: str, nowait: bool = False) -> str:
        if account_id in existing_keys and await _exists(master, account_id):
            return existing_keys[account_id]
        pub, sec = new_key()
        if not await _exists(master, account_id):
            for attempt in range(3):
                try:
                    await master.create_account(account_id, pub, ACCOUNT_BALANCE,
                                                nowait=nowait)
                    break
                except Exception:                  # noqa: BLE001
                    await asyncio.sleep(1.0)
        return sec

    # Submitted one at a time (the master account has a single access key, so
    # nonces serialise regardless) but WITHOUT waiting for finality, then
    # verified in bulk. Waiting per account would cost ~2s each -- half an hour
    # for 900 accounts.
    created = 0
    for acct in senders:
        sec = await ensure(acct, nowait=True)
        if sec:
            sender_keys.append({"account_id": acct, "private_key": sec})
            created += 1
        if created and created % 100 == 0:
            print(f"    {created} sender accounts submitted")
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
    # Fired without waiting, then verified. Waiting for finality on each of 80
    # transactions serially takes longer than the RPC's own timeout allows once
    # block time is 2s -- the run died on a TIMEOUT_ERROR partway through.
    # Submitting concurrently and checking the RESULT afterwards is both faster
    # and more honest: what matters is that every account ends up registered,
    # not that we watched each one land.
    all_accounts = senders + recipients
    print(f"\n[3/5] registering {len(all_accounts)} accounts with the token")

    # SUBMITTED ONE AT A TIME, but without waiting for finality.
    #
    # Every one of these is signed by the token account, which has a single
    # access key -- and NEAR orders transactions per access key by NONCE.
    # Firing them concurrently makes them collide: 64 of 80 landed and the
    # rest were silently dropped, which looked like a contract problem and was
    # actually our own nonce contention. The same hazard as Polygon's single
    # sender, in a place that is easy to miss because setup feels incidental.
    #
    # nowait=True keeps this fast: each call returns once broadcast, so
    # sequential submission does not mean waiting 2s per block.
    async def register(acct: str) -> None:
        for attempt in range(3):
            try:
                await token.function_call(
                    token_id, "storage_deposit",
                    {"account_id": acct, "registration_only": True},
                    gas=30 * TGAS, amount=STORAGE_DEPOSIT, nowait=True)
                return
            except Exception:                      # noqa: BLE001
                await asyncio.sleep(1.5)

    for acct in all_accounts:
        await register(acct)
    print("  submitted; waiting for registrations to land")

    for attempt in range(40):
        await asyncio.sleep(6)
        missing = []
        for acct in all_accounts:
            res = await _view(token, token_id, "storage_balance_of", {"account_id": acct})
            if not res:
                missing.append(acct)
        if not missing:
            print(f"  all {len(all_accounts)} registered")
            break
        if attempt % 5 == 0:
            print(f"    {len(all_accounts) - len(missing)}/{len(all_accounts)} registered")
    else:
        print(f"  REFUSING: {len(missing)} accounts never registered. NEP-141 "
              f"rejects transfers to unregistered accounts, so every payment to "
              f"them would fail and read as a chain failure rather than setup.")
        return 1

    # --- 4. fund senders ---------------------------------------------------
    print(f"\n[4/5] distributing tokens to {len(senders)} senders")
    per_sender = str(10**9 * 10**TOKEN_DECIMALS)   # 1e9 USDB each, ample

    # Sequential for the same reason as registration: one signing key, one
    # nonce sequence.
    async def fund(acct: str) -> None:
        for attempt in range(3):
            try:
                await token.function_call(
                    token_id, "ft_transfer",
                    {"receiver_id": acct, "amount": per_sender, "memo": None},
                    gas=30 * TGAS, amount=1, nowait=True)
                return
            except Exception:                      # noqa: BLE001
                await asyncio.sleep(1.5)

    for acct in senders:
        await fund(acct)
    for attempt in range(40):
        await asyncio.sleep(6)
        unfunded = [a for a in senders
                    if await _ft_balance(master, token_id, a) <= 0]
        if not unfunded:
            print(f"  all {len(senders)} senders hold "
                  f"{int(per_sender)/10**TOKEN_DECIMALS:,.0f} USDB")
            break
        if attempt % 5 == 0:
            print(f"    {len(senders) - len(unfunded)}/{len(senders)} funded")
    else:
        print(f"  REFUSING: {len(unfunded)} senders hold no tokens")
        return 1

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
    """Does this account exist on chain?

    Checks the RESPONSE, not merely the absence of an exception. py-near can
    return an error object rather than raising, so a bare try/except reported
    every account as existing -- including on a freshly wiped chain, which then
    skipped account creation and tried to sign with a key the chain had never
    seen ("access key does not exist while viewing").
    """
    try:
        res = await master._provider.get_account(account_id)
    except Exception:                              # noqa: BLE001
        return False
    return bool(res) and ("amount" in res or "code_hash" in res)


async def _view(acct, contract: str, method: str, args: dict):
    try:
        res = await acct.view_function(contract, method, args)
        return res.result
    except Exception:                              # noqa: BLE001
        return None


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
