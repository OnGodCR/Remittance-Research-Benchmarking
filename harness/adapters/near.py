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
import json as _json
from typing import Any

from py_near.account import Account
from py_near import transactions as _near_tx

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
        rpc_url: str | list[str],
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
        # ONE ENDPOINT, OR SEVERAL FOR SETTLEMENT CHECKS ONLY.
        #
        # A plain string is the published behaviour, unchanged: everything goes
        # to one node. A list spreads the SETTLEMENT POLLING across nodes while
        # payments still go out through the nearest one.
        #
        # WHY (19 Aug 2026). On Polygon, measuring where the work landed during
        # a 300/sec run found the node answering RPC at 84% busy while the three
        # validators doing only consensus sat at 8-14%. Spreading the settlement
        # checks took that cluster from 274.9/sec (invalid, the sender fell
        # 228ms behind schedule) to 290.5/sec clean -- beating the published
        # figure on half the validator hardware. See POLYGON_RPC_BOTTLENECK.md.
        #
        # NEAR has the same shape and worse. `await_confirmation` polls EVERY
        # payment repeatedly until it reads FINAL, and it did so through
        # `self._accounts[0]._provider` -- one node. At 150/sec with ~10s
        # settlement that is roughly 1,500 payments being asked about over and
        # over, all at the same node, on top of submissions and block
        # production. NEAR's measured 150/sec ceiling and its collapse past that
        # may be the same artefact, and this is what tests it.
        #
        # SUBMISSIONS DELIBERATELY DO NOT SPREAD. NEAR orders transactions per
        # access key by nonce, so a sender holds its ordering lock across the
        # submit round trip. Sending that to another continent caps one sender
        # at roughly four payments a second; on Polygon this produced ten
        # SECONDS of scheduling lag at a load that was otherwise clean. The
        # constraint is identical here.
        self._rpc_urls: list[str] = [rpc_url] if isinstance(rpc_url, str) else list(rpc_url)
        if not self._rpc_urls:
            raise ValueError("at least one RPC endpoint is required")
        self._rpc_url = self._rpc_urls[0]
        self._poll_providers: list[Any] = []
        self._poll_seq = 0
        self._probe_accounts: list[Any] = []
        self._token = token_contract
        self._sender_keys = sender_keys
        self._recipients = recipients

        #: Shards the chain must have for this arm to mean anything.
        #: claude.md S4 sizes the cluster at >=4 shards with >=2 validators
        #: each; with the 8 validators the quota allows, 4 shards gives exactly
        #: 2 per shard and no margin.
        self.expected_shards = 4

        #: Validators that must be in the CURRENT epoch. Chunk count alone does
        #: not prove work is divided -- see health_check step 1b.
        self.expected_validators = 8

        self._accounts: list[Account] = []
        self._next_sender = 0
        self._next_recipient = 0
        #: local ref -> future resolving to (tx hash, signer, shards crossed)
        self._hashes: dict[str, asyncio.Future] = {}
        self._tasks: set[asyncio.Task] = set()

        #: One lock per sender account -- see the comment in submit().
        import collections as _collections
        self._locks: dict[str, asyncio.Lock] = _collections.defaultdict(asyncio.Lock)

        #: Seeded so the shard mix is reproducible across repeats of a
        #: configuration -- two repeats must not differ because one happened to
        #: draw more cross-shard transfers than the other.
        import random as _random
        self._rng = _random.Random(20260811)

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
        self._probe_accounts = []
        for key in self._sender_keys:
            acct = Account(key["account_id"], key["private_key"], rpc_addr=self._rpc_url)
            await acct.startup()

            # Prime the local nonce from chain ONCE, here, rather than per
            # submission. _send_one increments this counter and never re-reads
            # it: see the long note there for why re-reading per payment both
            # costs an RPC round trip and returns a stale value while earlier
            # sends from the same key are still in flight.
            pk = await acct._free_signers.get()
            await acct._free_signers.put(pk)
            access_key = await acct.get_access_key(pk)
            acct._access_key_nonce[pk] = max(
                acct._access_key_nonce[pk], access_key.nonce)

            self._accounts.append(acct)

        # ONE POLLING CONNECTION PER ENDPOINT.
        #
        # Built from throwaway Account objects purely to obtain their providers:
        # py-near does not expose a bare provider constructor, and reusing a
        # SENDER's connection for polling would put settlement checks back on
        # the same sockets as submissions, which is what this separates.
        #
        # Endpoint 0's provider is the sender path's own, so it is reused rather
        # than duplicated -- with one endpoint configured this list is exactly
        # [the existing provider] and behaviour is byte-identical to before.
        self._poll_providers = [self._accounts[0]._provider]
        probe_key = self._sender_keys[0]
        for url in self._rpc_urls[1:]:
            probe = Account(probe_key["account_id"], probe_key["private_key"], rpc_addr=url)
            await probe.startup()
            self._poll_providers.append(probe._provider)
            self._probe_accounts.append(probe)
        if len(self._poll_providers) > 1:
            print(f"[near] settlement checks spread across "
                  f"{len(self._poll_providers)} endpoints "
                  f"(submissions stay on the nearest node)")

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
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        for acct in self._accounts + self._probe_accounts:
            try:
                await acct._provider.shutdown()
            except Exception:                      # noqa: BLE001 - teardown must not raise
                pass
        self._accounts.clear()
        # Leaked polling connections would accumulate across a sweep and the
        # next run would start with fewer usable sockets than it thinks.
        self._probe_accounts.clear()
        self._poll_providers.clear()

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
            # Called through json_rpc rather than py-near's get_block(), whose
            # signature in this version takes no finality argument -- passing
            # one raises TypeError, which this check swallowed, so the run
            # aborted with no indication of which condition had failed.
            block = await provider.json_rpc("block", {"finality": "final"})
            shards = len((block or {}).get("chunks") or [])
        except Exception as exc:                   # noqa: BLE001
            print(f"  HEALTH CHECK FAILED: could not read a block ({exc})")
            return False
        if shards < self.expected_shards:
            print(f"  HEALTH CHECK FAILED: chain has {shards} shard(s), "
                  f"expected {self.expected_shards}. A single-shard chain would "
                  f"measure sharding that is not happening.")
            return False

        # 1b. Are the shards actually being served by DIFFERENT validators?
        #
        # Counting chunks is not enough, and this nearly cost the whole arm.
        # After a restart the chain kept advancing with ONE validator producing
        # chunks for all four shards -- 4 chunks per block, health check
        # satisfied, and completely meaningless: one machine doing all the work
        # split four ways is not sharding. Validators are chosen per epoch and
        # nodes that miss blocks get dropped, so this can happen at any time,
        # not just at startup.
        try:
            vs = await provider.json_rpc("validators", [None])
            current = (vs or {}).get("current_validators") or []
        except Exception:                          # noqa: BLE001
            return False
        if len(current) < self.expected_validators:
            print(f"  HEALTH CHECK FAILED: {len(current)} validator(s) in the "
                  f"current epoch, expected {self.expected_validators}. Work is "
                  f"not divided across the cluster, so any 'sharding' result "
                  f"would describe one machine chunking its own output.")
            for v in current:
                print(f"    {v.get('account_id')} serving shards {v.get('shards')}")
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

        # Destination selection targets the SHARD MIX, not just a round robin.
        #
        # Senders and recipients are both laid out across shards in the same
        # rotation, so pairing sender i with recipient i put both on the SAME
        # shard every time: 100% same-shard traffic, and the cross-shard
        # finding -- the whole reason this arm exists -- would have been zero
        # in the data while everything looked healthy.
        #
        # Payments are drawn to match the mix a real S-shard network sees: a
        # randomly addressed transfer is cross-shard with probability
        # (S-1)/S, so with 4 shards 75% should cross. Choosing the recipient
        # by shard rather than by index reproduces that, and every payment
        # still records which case it was (see await_confirmation).
        sender_shard = self._shard_of(acct.account_id)
        want_cross = self._rng.random() < (self.expected_shards - 1) / self.expected_shards
        pool = [r for r in self._recipients
                if (self._shard_of(r) != sender_shard) == want_cross]
        if not pool:
            pool = self._recipients
        recipient = pool[self._next_recipient % len(pool)]
        self._next_recipient += 1

        amount = self.to_token_units(amount_usd)
        crossed = 0 if self._shard_of(acct.account_id) == self._shard_of(recipient) else 1

        # The send is fired as a BACKGROUND TASK and this returns immediately.
        #
        # py-near's `nowait=True` is misleadingly named: its own docstring says
        # it waits until the transaction is INCLUDED IN A BLOCK before
        # returning the hash. With 2-second blocks that is ~2s per submission,
        # and sign_and_submit_tx additionally makes two RPC round trips
        # (refresh block hash, fetch access key) before broadcasting. Awaiting
        # that inline serialised the send loop: scheduling lag climbed and 3 of
        # the first 7 runs were invalidated as generator-saturated -- our own
        # client, measured as if it were the chain. Exactly the fault that
        # produced Polygon's phantom throughput knee.
        #
        # A local reference is returned instead and resolved to the real
        # transaction hash in await_confirmation, the same pattern the
        # Lightning adapter uses for its streaming sends.
        ref = f"seq-{seq}"
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._hashes[ref] = fut
        # `fut` is held as a LOCAL and handed to the send task directly. It must
        # not be re-read from self._hashes inside the task: await_confirmation
        # pops the ref, and asyncio.create_task does not run the coroutine until
        # the caller next awaits, so the pop routinely happens FIRST. The task
        # then looked up a ref that was already gone, broadcast the payment, and
        # discarded the hash -- every transaction settled on chain while the
        # harness recorded "never broadcast within 60s" for all of them.

        async def send() -> None:
            # ONE SUBMISSION IN FLIGHT PER SENDER.
            #
            # NEAR orders transactions per ACCESS KEY by nonce, and py-near
            # fetches and increments that nonce per call. Firing concurrently
            # from the same account makes them collide. Without this lock the
            # first attempt queued 2,241 simultaneous sends against 64
            # accounts, none completed inside 60s, and every payment recorded
            # as "never broadcast" -- our own client, not the chain.
            #
            # This makes the sender pool the concurrency limit: with N senders
            # and ~2s to inclusion, the ceiling is about N/2 per second. That
            # is why required_pool_size() exists and why the CLI warns when the
            # pool is too small for the target rate.
            async with self._locks[acct.account_id]:
                await self._send_one(acct, recipient, amount, fut, crossed)

        task = asyncio.create_task(send())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

        return SubmitResult(ok=True, tx_ref=ref, amount_native=amount)

    async def _send_one(self, acct, recipient: str, amount: str,
                        fut: asyncio.Future, crossed: int) -> None:
        """Sign and broadcast one transfer, resolving the caller's future.

        WHY THIS DOES NOT CALL `account.function_call(nowait=True)`
        ----------------------------------------------------------
        Because in py-near 1.2.22 that flag does not mean what it says. Its own
        docstring reads "nowait: LEGACY, now same as included", and
        `sign_and_submit_tx` then does `included = included or nowait` and calls
        `send_tx_included`, which blocks SERVER-SIDE until the transaction is
        included in a block.

        That is fatal for a throughput benchmark. Inclusion takes about 2s, the
        node's own RPC ceiling is 10s, and concurrent submissions queue behind
        one another until they exceed it: 20 simultaneous sends produced one
        success and nineteen TIMEOUT_ERRORs, and a 100/sec run recorded all
        5,956 payments as "never broadcast within 60s". The chain was healthy
        throughout -- the ceiling was our client library.

        So the transaction is signed here and handed to `send_tx`, which is
        `broadcast_tx_async`: it returns the hash as soon as the node accepts
        the transaction and never waits for execution. Settlement is then
        measured where it should be, by polling for FINAL in await_confirmation.

        The nonce is tracked locally (fetched once per account in setup) rather
        than re-read per submission. NEAR orders transactions per access key by
        nonce, and re-reading it would both add an RPC round trip per payment
        and read a stale value while earlier sends are still in flight -- the
        per-sender lock in submit() is what keeps the local counter correct.
        """
        try:
            await acct._update_last_block_hash()

            pk = await acct._free_signers.get()
            await acct._free_signers.put(pk)

            acct._access_key_nonce[pk] += 1
            nonce = acct._access_key_nonce[pk]

            import base58 as _b58
            block_hash = _b58.b58decode(acct._latest_block_hash.encode("utf8"))
            actions = [_near_tx.create_function_call_action(
                "ft_transfer",
                _json.dumps({"receiver_id": recipient,
                             "amount": amount, "memo": None}).encode("utf8"),
                _FT_TRANSFER_GAS,
                _ONE_YOCTO,
            )]

            tx_hash = _near_tx.calc_trx_hash(
                acct.account_id, pk, self._token, nonce, actions, block_hash)
            signed = _near_tx.sign_and_serialize_transaction(
                acct.account_id, pk, self._token, nonce, actions, block_hash)

            await acct._provider.send_tx(signed)

            if fut and not fut.done():
                fut.set_result((str(tx_hash), acct.account_id, crossed))
        except Exception as exc:                   # noqa: BLE001 - recorded, not raised
            if fut and not fut.done():
                fut.set_exception(exc)

    async def await_confirmation(self, tx_ref: str, timeout_seconds: float) -> ConfirmResult:
        # ONE DEADLINE FOR THE WHOLE PATH, started here and shared by both
        # stages below.
        #
        # This must match Polygon exactly. There, await_confirmation is a single
        # `wait_for(future, timeout_seconds)` covering submission through
        # settlement, so a payment has 60s total (claude.md S7) and is a failure
        # after that whatever the chain later decides.
        #
        # NEAR settles in two observable stages -- the node accepts the
        # transaction, then it reaches FINAL -- and giving each stage its own
        # fresh `timeout_seconds` allowed up to 120s. A NEAR payment could then
        # be counted as settled where the identical Polygon payment was already
        # recorded as failed, which puts a real advantage for one architecture
        # inside the three-way comparison this project exists to make. The
        # stages are an implementation detail of how we observe NEAR; they must
        # not buy NEAR extra time.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds

        fut = self._hashes.pop(tx_ref, None)
        if fut is None:
            return ConfirmResult(status="failed", error="no pending submission for ref")
        try:
            tx_ref, signer, crossed = await asyncio.wait_for(
                fut, timeout=max(0.0, deadline - loop.time()))
        except asyncio.TimeoutError:
            return ConfirmResult(status="timeout",
                                 error=f"never broadcast within {timeout_seconds:g}s")
        except Exception as exc:                   # noqa: BLE001
            return ConfirmResult(status="failed", error=f"{type(exc).__name__}: {exc}")

        # Rotate which node answers this payment's settlement checks. With one
        # endpoint this is always the same provider, unchanged. The choice is
        # per PAYMENT rather than per attempt, so a payment's repeated polls all
        # go to one node and cannot be answered inconsistently mid-flight by
        # nodes at different heights.
        #
        # Finality is a property of the chain, not of a node, so any node can
        # answer -- only who does the work changes.
        self._poll_seq += 1
        provider = self._poll_providers[self._poll_seq % len(self._poll_providers)]

        # WHY THE LAST RPC ERROR IS KEPT.
        #
        # A timeout that says only "not FINAL within 60s" cannot distinguish the
        # two outcomes that matter most, and they are not remotely equivalent:
        #
        #   UNKNOWN_TRANSACTION -- the chain has never heard of it. It was
        #       broadcast, accepted by the node, and then dropped from the pool.
        #       Nothing was charged and nothing moved; the sender can retry. This
        #       is the same class as Polygon's "txpool is full" rejections.
        #
        #   still executing -- the chain HAS it and has not finalised it. This is
        #       the "money left one side and never arrived" case, which
        #       RESUME_HERE S3 singles out as the serious one, and which on
        #       Polygon appeared ONLY under deliberate node failure.
        #
        # Reporting a NEAR loss rate without separating these would either
        # slander NEAR or flatter it, depending which dominates. Observed on the
        # first runs: 1.1-1.5% of payments at the LOWEST load step never reached
        # FINAL, while the slowest payment that did arrive took 29.6s against a
        # 60s budget -- so they were not slow, they were gone. Which kind they
        # were is exactly what this records.
        last_error = "no response recorded"

        while loop.time() < deadline:
            try:
                # Called directly rather than through py-near's get_tx, which
                # uses the legacy positional form and cannot request a finality
                # level. Settlement here means FINAL (claude.md S7).
                # wait_until=NONE, NOT FINAL -- and this still measures
                # FINAL, because finality is READ from the response rather than
                # waited for.
                #
                # `wait_until=FINAL` blocks SERVER-SIDE until the transaction is
                # final or the node gives up. Measured on this cluster: 10.002s
                # per call for a transaction that is not yet final, against
                # 0.001s for wait_until=NONE. With ~11s settlement, a run at
                # 300/sec would hold roughly three thousand simultaneous
                # ten-second requests against a single RPC node, and the ceiling
                # we measured would be that node's request capacity rather than
                # NEAR's throughput -- our own tooling reported as a finding,
                # the exact error claude.md S8 exists to prevent. It was already
                # visible at the LOWEST load step as 1.6% of payments timing out
                # with HANDLER_ERROR/TIMEOUT_ERROR.
                #
                # The response carries `final_execution_status`, so NONE returns
                # immediately and finality is checked below. The settlement
                # definition is unchanged: nothing counts until FINAL.
                result = await provider.json_rpc("tx", {
                    "tx_hash": tx_ref,
                    "sender_account_id": signer,
                    "wait_until": "NONE",
                })
            except Exception as exc:               # noqa: BLE001 - not final yet, or transient
                last_error = f"{type(exc).__name__}: {exc}"[:160]
                await asyncio.sleep(0.2)
                continue

            outcome = (result or {}).get("final_execution_outcome") or result or {}
            status = (outcome.get("status") or {})
            reached = (result or {}).get("final_execution_status")
            # Both conditions, and the finality one is not optional: an outcome
            # can be successful at EXECUTED_OPTIMISTIC and still be reorged.
            # claude.md S7 requires FINAL for NEAR precisely so the comparison
            # against Polygon's deterministic instant finality is honest.
            if reached != _FINALITY:
                last_error = f"reached {reached}, not {_FINALITY}"
                await asyncio.sleep(0.2)
                continue
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
                    # The real on-chain hash. submit() could only return a local
                    # `seq-N` reference, because the hash does not exist until
                    # the send task has signed. Reporting it here is what lets
                    # any NEAR payment in the dataset be checked against the
                    # chain afterwards.
                    settled_ref=tx_ref,
                )
            if "Failure" in status:
                return ConfirmResult(status="failed", error=str(status["Failure"])[:200])
            # Present but not final yet -- record that, so a timeout here is
            # distinguishable from one where the chain never had it.
            last_error = f"present but not FINAL (status keys: {list(status)[:3]})"
            await asyncio.sleep(0.2)

        # 60s per claude.md S7. Past that a remittance has functionally failed
        # regardless of what the chain eventually decides. The last thing the
        # chain said is carried through so the failure can be classified rather
        # than guessed at -- see the note above the poll loop.
        return ConfirmResult(
            status="timeout",
            error=f"not FINAL within {timeout_seconds:g}s | last: {last_error}")

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
