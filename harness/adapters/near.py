"""NEAR adapter -- NEP-141 fungible token transfers on a private Nightshade network.

WHAT MAKES THIS DIFFERENT FROM THE OTHER TWO
--------------------------------------------
NEAR is the sharding arm. A transaction is routed to the shard that owns the
receiver's account, executed there, and the result folded into a single chain
of blocks. So unlike Polygon -- where every validator processes everything --
work is genuinely divided, and unlike Lightning there is no routing or
liquidity to fail.

Two consequences the adapter has to respect:

**Settlement means FINAL, not EXECUTED_OPTIMISTIC** (claude.md S7). NEAR will
tell you a transaction executed as soon as its shard has run it, before the
result is final across the network. Accepting that would measure shard-local
execution and understate real settlement latency -- flattering NEAR against
Polygon, whose IBFT finality is genuine at one block. py-near's `get_tx` uses
the legacy positional RPC form with no finality control, so this adapter calls
the RPC itself with an explicit `wait_until`.

**Cross-shard transfers cost more than same-shard ones.** A transfer whose
sender and receiver live on different shards needs a second block to resolve.
That is the central property of sharding and the thing this arm exists to
measure, so sender and recipient accounts are deliberately spread across shards
rather than clustered.

WHY NEP-141 AND NOT NATIVE NEAR
-------------------------------
Real remittances move stablecoins, not the native token (claude.md S6). A
NEP-141 transfer is also the closer analogue of the ERC-20 transfer measured on
Polygon, which keeps the cross-architecture comparison honest: two token
transfers, not a token transfer against a native one.
"""

from __future__ import annotations

import asyncio
from typing import Any

from py_near.account import Account

from .base import Adapter, ConfirmResult, SubmitResult

#: Gas attached to an ft_transfer. NEAR gas is deterministic -- the same call
#: burns the same amount on our network and on mainnet -- so what we attach is
#: only a ceiling. 30 TGas is the community standard for NEP-141 transfers and
#: comfortably exceeds the ~3-5 TGas actually burned.
_FT_TRANSFER_GAS = 30_000_000_000_000

#: NEP-141 requires exactly 1 yoctoNEAR attached to any transfer. It is a
#: security requirement of the standard, forcing the caller to have signed with
#: a full-access key rather than a function-call key.
_ONE_YOCTO = 1

#: Token decimals. Matches the ERC-20 used on Polygon so that $200 is 200 tokens
#: on both chains and no conversion enters the comparison.
_TOKEN_DECIMALS = 6

#: Finality to wait for. The alternative, EXECUTED_OPTIMISTIC, returns as soon
#: as the receiving shard has executed -- before the result is final network
#: wide. See the module docstring.
_FINALITY = "FINAL"


class NearAdapter(Adapter):
    """One NEAR account per worker, transferring a NEP-141 token."""

    architecture = "near"
    name = "nearcore-localnet"

    def __init__(
        self,
        rpc_url: str,
        token_contract: str,
        sender_keys: list[dict[str, str]],
        recipients: list[str],
    ) -> None:
        """
        `sender_keys`: one dict per sender with `account_id` and `private_key`.

        A POOL of senders, not one. NEAR serialises transactions per access key
        by nonce, exactly as Ethereum does per account -- so a single sender
        would queue its own sends and the measured ceiling would be our client,
        not the chain. That mistake produced Polygon's phantom throughput knee.
        """
        self._rpc_url = rpc_url
        self._token = token_contract
        self._sender_keys = sender_keys
        self._recipients = recipients

        #: Shards the chain must have for this arm to mean anything.
        #: claude.md S4 sizes the cluster at >=4 shards with >=2 validators
        #: each; with the 8 validators the quota allows, 4 shards gives exactly
        #: 2 per shard and no margin.
        self.expected_shards = 4

        self._accounts: list[Account] = []
        self._next_sender = 0
        self._next_recipient = 0
        #: tx hash -> (signing account, shard boundaries crossed)
        self._signers: dict[str, tuple[str, int]] = {}

        #: Genesis shard boundary accounts, read once in setup(). NEAR assigns
        #: an account to a shard by where its name falls between these.
        self._boundaries: list[str] = []

    @staticmethod
    def required_pool_size(target_tps: float, safety_factor: float = 3.0) -> int:
        """Senders needed so nonce ordering never becomes the bottleneck.

        NEAR finality is roughly 2s. A sender cannot have more than one
        transaction in flight per access key without risking nonce conflicts,
        so the pool must cover the in-flight window with headroom.
        """
        return max(8, int(target_tps * 2.0 * safety_factor / 10))

    # -- lifecycle ----------------------------------------------------------

    async def setup(self, context: dict[str, Any]) -> None:
        self._accounts = []
        for key in self._sender_keys:
            acct = Account(key["account_id"], key["private_key"], rpc_addr=self._rpc_url)
            await acct.startup()
            self._accounts.append(acct)

        # Read the shard boundaries so every transfer can be classified as
        # same-shard or cross-shard. See `_shard_of` for why this matters more
        # than it first appears.
        try:
            cfg = await self._accounts[0]._provider.json_rpc(
                "EXPERIMENTAL_protocol_config", {"finality": "final"})
            layout = (cfg or {}).get("shard_layout", {})
            version = layout.get("V2") or layout.get("V1") or layout.get("V0") or {}
            self._boundaries = version.get("boundary_accounts") or []
        except Exception:                          # noqa: BLE001
            self._boundaries = []

    async def teardown(self) -> None:
        for acct in self._accounts:
            try:
                await acct._provider.shutdown()
            except Exception:                      # noqa: BLE001 - teardown must not raise
                pass
        self._accounts.clear()

    async def health_check(self) -> bool:
        """Three things must hold before a run is worth starting.

        The shard count is the one that matters. If the chain came up with a
        single shard, every transfer is same-shard, nothing is actually
        divided, and the arm would measure a non-sharded chain while reporting
        it as a sharding result. That is a plausible number that is entirely
        wrong -- the failure mode this project has hit repeatedly -- so it
        fails loudly here instead.
        """
        if not self._accounts:
            return False
        provider = self._accounts[0]._provider

        # 1. Sharded? One chunk per shard in every block.
        try:
            block = await provider.get_block(finality="final")
            shards = len(block.get("chunks") or [])
        except Exception:                          # noqa: BLE001
            return False
        if shards < self.expected_shards:
            print(f"  HEALTH CHECK FAILED: chain has {shards} shard(s), "
                  f"expected {self.expected_shards}. A single-shard chain would "
                  f"measure sharding that is not happening.")
            return False

        # 2. Shard boundaries were read. Without them every transfer would be
        #    classified same-shard and the cross-shard finding would vanish.
        if not self._boundaries:
            print("  HEALTH CHECK FAILED: no shard boundaries read from genesis; "
                  "every transfer would be misclassified as same-shard")
            return False

        # 3. Every sender holds tokens to send.
        for acct in self._accounts:
            if await self._ft_balance(acct, acct.account_id) <= 0:
                print(f"  HEALTH CHECK FAILED: {acct.account_id} holds no tokens")
                return False

        # 4. Recipients are registered with the token contract. NEP-141
        #    requires storage_deposit before an account can receive, and an
        #    unregistered recipient fails every transfer addressed to it --
        #    which would look like a chain failure rather than our setup.
        for recipient in self._recipients:
            res = await self._accounts[0].view_function(
                self._token, "storage_balance_of", {"account_id": recipient})
            if not res.result:
                print(f"  HEALTH CHECK FAILED: {recipient} not registered with "
                      f"the token contract (needs storage_deposit)")
                return False
        return True

    # -- measurement --------------------------------------------------------

    def to_token_units(self, amount_usd: float) -> str:
        """$200 becomes exactly 200 tokens. No exchange rate enters the study.

        NEP-141 amounts are strings because they are u128 -- larger than JSON
        can carry as a number.
        """
        return str(int(round(amount_usd * (10 ** _TOKEN_DECIMALS))))

    async def submit(self, seq: int, amount_usd: float) -> SubmitResult:
        acct = self._accounts[self._next_sender % len(self._accounts)]
        self._next_sender += 1
        recipient = self._recipients[self._next_recipient % len(self._recipients)]
        self._next_recipient += 1

        amount = self.to_token_units(amount_usd)
        try:
            # nowait=True returns as soon as the transaction is broadcast.
            # Blocking here would serialise the send loop and turn a
            # concurrency test into a round-trip-latency test (claude.md S6).
            tx_hash = await acct.function_call(
                contract_id=self._token,
                method_name="ft_transfer",
                args={"receiver_id": recipient, "amount": amount, "memo": None},
                gas=_FT_TRANSFER_GAS,
                amount=_ONE_YOCTO,
                nowait=True,
            )
        except Exception as exc:                   # noqa: BLE001 - recorded, not raised
            return SubmitResult(ok=False, error=f"{type(exc).__name__}: {exc}")

        tx_hash = str(tx_hash)
        crossed = 0 if self._shard_of(acct.account_id) == self._shard_of(recipient) else 1
        self._signers[tx_hash] = (acct.account_id, crossed)
        return SubmitResult(ok=True, tx_ref=tx_hash, amount_native=amount)

    async def await_confirmation(self, tx_ref: str, timeout_seconds: float) -> ConfirmResult:
        entry = self._signers.pop(tx_ref, None)
        if entry is None:
            return ConfirmResult(status="failed", error="no signer recorded for tx")
        signer, crossed = entry

        provider = self._accounts[0]._provider
        deadline = asyncio.get_event_loop().time() + timeout_seconds

        while asyncio.get_event_loop().time() < deadline:
            try:
                # Called directly rather than through py-near's get_tx, which
                # uses the legacy positional form and cannot request a finality
                # level. Settlement here means FINAL (claude.md S7).
                result = await provider.json_rpc("tx", {
                    "tx_hash": tx_ref,
                    "sender_account_id": signer,
                    "wait_until": _FINALITY,
                })
            except Exception:                      # noqa: BLE001 - not final yet, or transient
                await asyncio.sleep(0.2)
                continue

            outcome = (result or {}).get("final_execution_outcome") or result or {}
            status = (outcome.get("status") or {})
            if "SuccessValue" in status or "SuccessReceiptId" in status:
                return ConfirmResult(
                    status="confirmed",
                    gas_used=self._total_gas(outcome),
                    fee_native=str(self._total_tokens_burnt(outcome)),
                    # route_hops carries SHARD BOUNDARIES CROSSED here: 0 for a
                    # same-shard transfer, 1 for cross-shard. The field is
                    # otherwise unused on NEAR and the meaning is a fair
                    # analogue -- how many boundaries the value had to cross.
                    #
                    # Recording it per transaction is what makes a 4-shard
                    # measurement transferable to mainnet's 8-9. A random
                    # transfer is cross-shard with probability (S-1)/S, so the
                    # BLEND changes with shard count: 75% cross-shard at 4
                    # shards, 87.5% at 8. Reporting only the 4-shard average
                    # would understate mainnet cross-shard overhead. Measuring
                    # the two regimes separately lets the average be recomputed
                    # for any shard count.
                    route_hops=crossed,
                )
            if "Failure" in status:
                return ConfirmResult(status="failed", error=str(status["Failure"])[:200])
            await asyncio.sleep(0.2)

        # 60s per claude.md S7. Past that a remittance has functionally failed
        # regardless of what the chain eventually decides.
        return ConfirmResult(status="timeout", error=f"not FINAL within {timeout_seconds:g}s")

    # -- internals ----------------------------------------------------------

    def _shard_of(self, account_id: str) -> int:
        """Which shard owns this account.

        NEAR assigns an account to a shard by where its name sorts relative to
        the genesis boundary accounts. With no boundaries read, everything
        reports shard 0 and every transfer would be classified same-shard --
        so `health_check` verifies the boundaries exist before a run starts.
        """
        return sum(1 for b in self._boundaries if account_id >= b)

    @staticmethod
    def _total_gas(outcome: dict) -> int | None:
        """Gas burned across the transaction AND all its receipts.

        A NEAR transfer is not one execution. The transaction converts into
        receipts that execute on the receiver's shard, and a cross-shard
        transfer produces more of them. Counting only the transaction outcome
        would report a fraction of the real cost and would hide the very
        difference between same-shard and cross-shard work that this arm exists
        to measure.
        """
        total = 0
        tx_outcome = outcome.get("transaction_outcome") or {}
        total += int((tx_outcome.get("outcome") or {}).get("gas_burnt", 0) or 0)
        for receipt in outcome.get("receipts_outcome") or []:
            total += int((receipt.get("outcome") or {}).get("gas_burnt", 0) or 0)
        return total or None

    @staticmethod
    def _total_tokens_burnt(outcome: dict) -> int:
        """Yocto-NEAR burnt, summed the same way and for the same reason."""
        total = 0
        tx_outcome = outcome.get("transaction_outcome") or {}
        total += int((tx_outcome.get("outcome") or {}).get("tokens_burnt", 0) or 0)
        for receipt in outcome.get("receipts_outcome") or []:
            total += int((receipt.get("outcome") or {}).get("tokens_burnt", 0) or 0)
        return total

    async def _ft_balance(self, acct: Account, account_id: str) -> int:
        try:
            res = await acct.view_function(self._token, "ft_balance_of",
                                           {"account_id": account_id})
            return int(res.result or 0)
        except Exception:                          # noqa: BLE001
            return 0
