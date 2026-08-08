"""Polygon Edge adapter -- sends stablecoin transfers and times their settlement.

Three problems this file exists to solve. Each one, done naively, produces
numbers that look plausible and are wrong.

**1. Nonce collisions look exactly like chain congestion.**
Every account numbers its transactions strictly in order. Fire fifty at once
from one account and the network holds all of them until the gaps fill in --
which looks precisely like the blockchain struggling under load. It is not; it
is a client-side artifact, and it would have been reported as an architecture
limit. Fixed with a pool of funded senders, each with its own lock and its own
locally-tracked counter, so sends are serialised per account and parallel
across accounts.

**2. Polling each payment for its receipt does not survive the load.**
At 300 payments/second with a 60-second timeout, up to 18,000 payments are in
flight at once. Asking the node about each one a few times a second is ~90,000
requests per second -- the harness would collapse long before the chain did,
and we would have published our own bottleneck as a finding. Fixed by watching
*blocks* instead of payments: one request per block resolves every payment
inside it, so cost scales with block production, not with load.

**3. Settlement must mean what we said it means.**
`ANALYSIS_PLAN.md` S6.1 fixes Polygon at one confirmation, because PolyBFT
gives deterministic instant finality -- a committed block is final, with no
reorg window to wait out. Waiting extra blocks would add delay that does not
exist. A payment is settled the moment it appears in a committed block.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from eth_account import Account
from web3 import AsyncHTTPProvider, AsyncWeb3

from .base import Adapter, ConfirmResult, SubmitResult

#: ERC-20 transfer(address,uint256) selector.
_TRANSFER_SELECTOR = bytes.fromhex("a9059cbb")

#: Fixed gas limit for a token transfer. Estimating per payment would add an
#: extra round trip to the node on the hot path, throttling the generator.
#: Real consumption (~51-65k) is read back from receipts -- that measured value
#: is the one that feeds the cost analysis, not this ceiling.
_GAS_LIMIT = 120_000

#: How often to ask for a new block. Well under the expected block time so we
#: never miss one, but not so often that polling itself becomes load.
_BLOCK_POLL_INTERVAL = 0.2

#: Simultaneous HTTP connections allowed to the node. The library's default
#: is 100; we routinely want more, and exceeding it makes requests silently
#: queue rather than fail -- appearing in the data as chain latency.
_HTTP_CONNECTION_LIMIT = 256

#: How many receipt requests may be in flight at once when falling back to
#: per-transaction fetching. High enough to clear a block's worth quickly,
#: low enough not to flood a single node -- which would create client-side
#: congestion indistinguishable from the chain slowing down.
_RECEIPT_CONCURRENCY = 64

#: Token has 6 decimals, matching USDC/USDT. $1 == 1_000_000 base units.
_TOKEN_UNITS = 10 ** 6


@dataclass
class _Sender:
    """One funded account. The lock is what keeps its nonces sequential."""

    address: str
    key: str
    nonce: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class PolygonAdapter(Adapter):
    architecture = "polygon"
    name = "polygon-edge"

    def __init__(
        self,
        rpc_url: str,
        token_address: str,
        sender_keys: list[str],
        recipients: list[str],
        chain_id: int,
        gas_price_wei: int = 1_000_000_000,
    ):
        """
        Args:
            sender_keys: private keys of pre-funded accounts. Pool size sets the
                ceiling on concurrent sends -- see `required_pool_size`.
            recipients: destination addresses. Reused deliberately: paying a
                brand-new address costs extra because it creates a balance
                record, and that one-off cost would contaminate early payments.
            gas_price_wei: what we charge ourselves. Arbitrary on a private
                network and NOT the measured cost -- cost comes from gas
                *consumed*, priced against real mainnet rates later
                (ANALYSIS_PLAN.md S6.3).
        """
        self.rpc_url = rpc_url
        self.token_address = AsyncWeb3.to_checksum_address(token_address)
        self.chain_id = chain_id
        self.gas_price_wei = gas_price_wei
        self._sender_keys = sender_keys
        self._recipients = [AsyncWeb3.to_checksum_address(r) for r in recipients]

        self.w3: AsyncWeb3 | None = None
        self._senders: list[_Sender] = []
        self._pending: dict[str, asyncio.Future] = {}
        self._watcher: asyncio.Task | None = None
        self._last_block = 0
        self._supports_block_receipts = True

    @staticmethod
    def required_pool_size(target_tps: float, safety_factor: float = 3.0) -> int:
        """How many sender accounts are needed for a given rate.

        Each account serialises its own sends, so one account's ceiling is
        1/(round-trip time). Assuming a conservative 50ms round trip, that is
        ~20 payments/second per account. The safety factor covers latency spikes
        -- running a sender near its limit turns a slow node response into
        apparent chain backpressure, which is the confound this whole design
        exists to avoid.
        """
        per_account_tps = 20.0
        return max(8, int((target_tps / per_account_tps) * safety_factor) + 1)

    # -- lifecycle --------------------------------------------------------

    async def setup(self, context: dict[str, Any]) -> None:
        provider = AsyncHTTPProvider(self.rpc_url)

        # RAISE THE HTTP CONNECTION LIMIT.
        #
        # The underlying HTTP library defaults to 100 simultaneous connections
        # per session. At 300 payments/second we ask for more than that: up to
        # 64 concurrent receipt fetches plus in-flight submissions from ~64
        # sender accounts, all to a single node.
        #
        # Exceeding the pool does not error -- requests simply WAIT for a free
        # connection. That wait is indistinguishable from the chain responding
        # slowly, so it would have been recorded as settlement latency. It is
        # the same class of mistake as the serial receipt fetching: our own
        # client queueing, reported as the architecture's behaviour.
        import aiohttp
        session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(
                limit=_HTTP_CONNECTION_LIMIT,
                limit_per_host=_HTTP_CONNECTION_LIMIT,
                ttl_dns_cache=300,
            ),
            timeout=aiohttp.ClientTimeout(total=30),
        )
        await provider.cache_async_session(session)

        self.w3 = AsyncWeb3(provider)

        # REQUIRED for proof-of-authority chains, which Polygon Edge is.
        #
        # PoA consensus stores validator signatures in each block header's
        # extraData field, making it far longer than the 32 bytes Ethereum's
        # spec allows. Without this middleware, web3 rejects every block as
        # malformed -- so no settlement is ever detected, every payment times
        # out at 60 seconds, and the run reports 100% failure.
        #
        # That failure mode is dangerous precisely because it looks like a
        # finding: "the architecture failed every transaction" is a plausible
        # sentence. It was our client refusing to read the blocks.
        from web3.middleware import ExtraDataToPOAMiddleware
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

        actual_chain_id = await self.w3.eth.chain_id
        if actual_chain_id != self.chain_id:
            raise RuntimeError(
                f"connected to chain {actual_chain_id}, expected {self.chain_id} -- "
                f"wrong network, refusing to run"
            )

        # Each account's on-chain nonce is fetched once. After this we track it
        # locally: asking the node before every send would double our request
        # rate and reintroduce the bottleneck we're avoiding.
        #
        # Fetched concurrently rather than one after another. Setup happens
        # before every run in a 140-run sweep, and with 160 accounts the
        # serial version spent a round trip per account each time.
        accounts = [Account.from_key(k) for k in self._sender_keys]
        nonces = await asyncio.gather(
            *(self.w3.eth.get_transaction_count(a.address, "pending") for a in accounts)
        )
        self._senders = [
            _Sender(address=a.address, key=k, nonce=n)
            for a, k, n in zip(accounts, self._sender_keys, nonces)
        ]

        self._last_block = await self.w3.eth.block_number
        self._pending = {}
        self._watcher = asyncio.create_task(self._watch_blocks())

    async def health_check(self) -> bool:
        """Refuse to start a run that would produce meaningless data."""
        if self.w3 is None:
            return False
        if not self._senders:
            print("health check failed: no funded sender accounts")
            return False
        if not self._recipients:
            print("health check failed: no recipient addresses")
            return False

        # A sender with no gas cannot pay for anything; every payment would fail
        # and be recorded as an architecture failure rather than our mistake.
        for sender in self._senders[:5]:
            balance = await self.w3.eth.get_balance(sender.address)
            if balance < _GAS_LIMIT * self.gas_price_wei * 100:
                print(f"health check failed: {sender.address} has insufficient "
                      f"native balance for gas ({balance} wei)")
                return False
        return True

    async def teardown(self) -> None:
        if self._watcher is not None:
            self._watcher.cancel()
            try:
                await self._watcher
            except asyncio.CancelledError:
                pass
            self._watcher = None

        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()

        if self.w3 is not None:
            provider = self.w3.provider
            if hasattr(provider, "disconnect"):
                await provider.disconnect()
            self.w3 = None

    # -- the measured path ------------------------------------------------

    async def submit(self, seq: int, amount_usd: float) -> SubmitResult:
        assert self.w3 is not None, "setup() not called"

        sender = self._senders[seq % len(self._senders)]
        recipient = self._recipients[seq % len(self._recipients)]
        amount_units = int(round(amount_usd * _TOKEN_UNITS))

        # transfer(address,uint256), ABI-encoded by hand. web3's contract layer
        # rebuilds and re-validates this on every call, which is measurable
        # overhead at 300/second when the shape never changes.
        payload = (
            _TRANSFER_SELECTOR
            + bytes.fromhex(recipient[2:].rjust(64, "0"))
            + amount_units.to_bytes(32, "big")
        )

        async with sender.lock:
            nonce = sender.nonce
            tx = {
                "to": self.token_address,
                "value": 0,
                "gas": _GAS_LIMIT,
                "gasPrice": self.gas_price_wei,
                "nonce": nonce,
                "chainId": self.chain_id,
                "data": payload,
            }
            try:
                signed = Account.sign_transaction(tx, sender.key)
                tx_hash = await self.w3.eth.send_raw_transaction(signed.raw_transaction)
            except Exception as exc:
                # Roll the counter back. Leaving a gap would stall every
                # subsequent payment from this account behind a nonce that
                # never arrives -- one failed send would cascade into a fake
                # collapse of the whole run.
                return SubmitResult(ok=False, error=f"{type(exc).__name__}: {exc}")
            sender.nonce = nonce + 1

        tx_ref = tx_hash.hex()
        if not tx_ref.startswith("0x"):
            tx_ref = "0x" + tx_ref

        self._pending[tx_ref.lower()] = asyncio.get_running_loop().create_future()
        return SubmitResult(ok=True, tx_ref=tx_ref, amount_native=str(amount_units))

    async def await_confirmation(self, tx_ref: str, timeout_seconds: float) -> ConfirmResult:
        future = self._pending.get(tx_ref.lower())
        if future is None:
            return ConfirmResult(status="failed", error="payment was never registered as pending")

        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout_seconds)
        except asyncio.TimeoutError:
            return ConfirmResult(
                status="timeout",
                error=f"not settled within {timeout_seconds:g}s",
            )
        finally:
            self._pending.pop(tx_ref.lower(), None)

    # -- block watcher ----------------------------------------------------

    async def _watch_blocks(self) -> None:
        """Resolve settlements by scanning new blocks.

        One request per block, regardless of how many payments are in flight.
        This is the difference between a harness that holds up at 300/second
        and one that becomes the bottleneck it was built to detect.
        """
        assert self.w3 is not None
        while True:
            try:
                await asyncio.sleep(_BLOCK_POLL_INTERVAL)
                head = await self.w3.eth.block_number
                while self._last_block < head:
                    self._last_block += 1
                    await self._process_block(self._last_block)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # A transient node error must not kill the watcher -- every
                # in-flight payment would then time out and be recorded as an
                # architecture failure.
                print(f"[polygon] block watcher error (continuing): "
                      f"{type(exc).__name__}: {exc}")

    async def _process_block(self, number: int) -> None:
        assert self.w3 is not None
        if not self._pending:
            return

        receipts = await self._fetch_block_receipts(number)
        if receipts is None:
            return

        for receipt in receipts:
            tx_hash = receipt.get("transactionHash")
            if tx_hash is None:
                continue
            key = (tx_hash.hex() if hasattr(tx_hash, "hex") else str(tx_hash)).lower()
            if not key.startswith("0x"):
                key = "0x" + key

            future = self._pending.get(key)
            if future is None or future.done():
                continue

            status = receipt.get("status", 1)
            gas_used = receipt.get("gasUsed")
            if isinstance(gas_used, str):
                gas_used = int(gas_used, 16)

            if status == 1 or status == "0x1":
                future.set_result(ConfirmResult(
                    status="confirmed",
                    gas_used=gas_used,
                    # Fee in native units. NOT the reported cost -- see class docstring.
                    fee_native=str(gas_used * self.gas_price_wei) if gas_used else None,
                ))
            else:
                # Included but reverted. A real failure, not a timeout, and it
                # must not be silently counted as a success.
                future.set_result(ConfirmResult(
                    status="failed",
                    gas_used=gas_used,
                    error="transaction reverted on chain",
                ))

    async def _fetch_block_receipts(self, number: int) -> list[dict] | None:
        """Get every receipt in a block, preferring the single-call method.

        `eth_getBlockReceipts` is one request per block. Not every client
        implements it, so we detect that once and fall back to per-transaction
        receipts -- correct either way, just more requests.
        """
        assert self.w3 is not None

        if self._supports_block_receipts:
            try:
                result = await self.w3.provider.make_request(
                    "eth_getBlockReceipts", [hex(number)]
                )
                if "result" in result and result["result"] is not None:
                    return result["result"]
                self._supports_block_receipts = False
                print("[polygon] eth_getBlockReceipts unavailable, "
                      "falling back to per-transaction receipts")
            except Exception:
                self._supports_block_receipts = False

        block = await self.w3.eth.get_block(number, full_transactions=False)

        # Collect only the transactions that are ours; background traffic
        # shares these blocks and fetching its receipts would be wasted work.
        wanted = []
        for tx_hash in block.transactions:
            key = tx_hash.hex().lower()
            if not key.startswith("0x"):
                key = "0x" + key
            if key in self._pending:
                wanted.append(tx_hash)
        if not wanted:
            return []

        # CONCURRENT, not sequential.
        #
        # This previously awaited each receipt one at a time inside a loop. At
        # 300 payments/sec roughly 600 of our transactions land in each
        # 2-second block, so the watcher spent ~600 serial round trips per
        # block -- and every one of those blocks arrives whether or not the
        # previous batch finished. That backlog, not processor count, is the
        # likeliest reason the generator saturated at 500 and 1000/sec even
        # with eight worker processes.
        #
        # Bounded concurrency rather than unbounded: firing 600 simultaneous
        # requests at a single node would create exactly the client-side
        # congestion this is trying to avoid, and could be mistaken for the
        # chain slowing down.
        sem = asyncio.Semaphore(_RECEIPT_CONCURRENCY)

        async def fetch(tx_hash):
            async with sem:
                try:
                    return dict(await self.w3.eth.get_transaction_receipt(tx_hash))
                except Exception:
                    return None

        results = await asyncio.gather(*(fetch(h) for h in wanted))
        return [r for r in results if r is not None]
