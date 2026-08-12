"""How many NEAR payments can this generator BUILD AND SIGN per second?

WHY THE BUILT-IN CAPACITY CHECK DOES NOT ANSWER THIS
`harness.cli capacity` ramps against the null adapter, which accepts a payment
and returns. It measures the scheduler, the task machinery and the storage
writer -- everything except the per-payment CPU work an adapter actually does.
For NEAR that omission is the whole question.

WHY IT IS THE WHOLE QUESTION
`_run_near` is deliberately single-process, on the reasoning recorded in
harness/cli.py that "a NEAR submission is one RPC call and the work happens on
the validators." That reasoning predates the Bug 2 fix. The adapter now signs
every transaction LOCALLY -- borsh-serialising it twice (once in calc_trx_hash,
once in sign_and_serialize_transaction), ed25519-signing it, and base58-decoding
a block hash -- which is exactly the CPU-bound work that capped the Polygon
harness near 150/sec and forced it onto eight worker processes.

If this generator cannot build and sign 300 payments a second in one process,
then a NEAR ceiling observed at 300/sec is OUR ceiling wearing NEAR's name. That
is the specific error that produced Polygon's phantom knee, and the reason
claude.md S8 says to validate generator capacity BEFORE collecting.

WHAT THIS MEASURES
The exact construct-and-sign sequence from NearAdapter._send_one, with the
network call removed. Nothing is broadcast and no chain state is touched.
"""
import asyncio
import json
import sys
import time

sys.path.insert(0, "/opt/benchmark")

from pathlib import Path                                    # noqa: E402
from harness.cli import load_near_adapter                   # noqa: E402
import base58 as _b58                                       # noqa: E402
from py_near import transactions as _near_tx                # noqa: E402

N = 3000
TARGET = 300.0     # the top of the pre-registered load ramp


async def main() -> int:
    adapter = load_near_adapter(Path("/opt/benchmark/config/phase4.json"))
    await adapter.setup({})
    print(f"{len(adapter._sender_keys)} senders primed\n")

    acct = adapter._accounts[0]
    # _send_one refreshes this first; the attribute does not exist until it has
    # been called at least once.
    await acct._update_last_block_hash()
    pk = await acct._free_signers.get()
    await acct._free_signers.put(pk)
    block_hash = _b58.b58decode(acct._latest_block_hash.encode("utf8"))
    amount = adapter.to_token_units(200.0)
    recipient = adapter._recipients[0]

    # Import the module-level constants the adapter uses, so gas and deposit
    # match a real payment byte for byte.
    from harness.adapters import near as near_mod
    gas, one_yocto = near_mod._FT_TRANSFER_GAS, near_mod._ONE_YOCTO

    def build_and_sign(nonce: int):
        actions = [_near_tx.create_function_call_action(
            "ft_transfer",
            json.dumps({"receiver_id": recipient,
                        "amount": amount, "memo": None}).encode("utf8"),
            gas, one_yocto)]
        h = _near_tx.calc_trx_hash(
            acct.account_id, pk, adapter._token, nonce, actions, block_hash)
        s = _near_tx.sign_and_serialize_transaction(
            acct.account_id, pk, adapter._token, nonce, actions, block_hash)
        return h, s

    build_and_sign(1)                      # warm any lazy imports

    print(f"building and signing {N} payments...")
    t0 = time.perf_counter()
    for i in range(N):
        build_and_sign(i + 1000)
    elapsed = time.perf_counter() - t0
    rate = N / elapsed
    per = elapsed / N * 1000

    print(f"\n  {N} payments in {elapsed:.2f}s")
    print(f"  {rate:,.0f} payments/sec  ({per:.3f} ms each)")
    print(f"  CPU cost of signing at {TARGET:g}/sec = "
          f"{100 * TARGET / rate:.1f}% of one core")

    # Split the two halves. calc_trx_hash and sign_and_serialize_transaction
    # each serialise the transaction, so the adapter pays for that work twice
    # per payment. Worth knowing whether that is where the time goes before
    # anyone optimises the wrong thing.
    t0 = time.perf_counter()
    for i in range(N):
        actions = [_near_tx.create_function_call_action(
            "ft_transfer",
            json.dumps({"receiver_id": recipient,
                        "amount": amount, "memo": None}).encode("utf8"),
            gas, one_yocto)]
        _near_tx.calc_trx_hash(acct.account_id, pk, adapter._token,
                               i + 1000, actions, block_hash)
    hash_only = time.perf_counter() - t0
    print(f"\n  of which calc_trx_hash alone: {hash_only / elapsed * 100:.0f}% "
          f"({N / hash_only:,.0f}/sec on its own)")

    await adapter.teardown()

    headroom = rate / TARGET
    print(f"\n  VERDICT: {headroom:.1f}x headroom at the {TARGET:g}/sec top step.")
    if headroom < 3:
        print("  *** TOO CLOSE. Under 3x, a ceiling seen at 300/sec cannot be")
        print("  *** attributed to the chain. Use worker processes.")
    else:
        print("  Signing is not the constraint; the scheduler ceiling from")
        print("  `harness.cli capacity` is the number that governs.")
    return 0


sys.exit(asyncio.run(main()))
