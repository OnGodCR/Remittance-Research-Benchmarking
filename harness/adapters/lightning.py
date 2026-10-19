"""Lightning adapter -- LND over its REST API, against bitcoind on regtest.

WHAT IS DIFFERENT FROM POLYGON, AND WHY IT MATTERS
--------------------------------------------------
Polygon settles a transaction by putting it in a block: the chain either has
capacity or it does not, and the amount is irrelevant (POLYGON_ANALYSIS.md S3
measured the effect of amount at 0.044%). Lightning settles by finding a *path*
where every hop holds enough liquidity pointing the right way. So:

  - Failure is the headline result here, not a footnote. Waugh & Holz (2020)
    measured success falling from ~72% to ~15% as payment size rises, and
    reproducing that gradient is the point of this arm.
  - `route_hops` and the failure *reason* must be recorded per payment. "It
    failed" is not a finding; "it failed because no route had liquidity for
    this amount" is.
  - Cost is partly proportional to amount (base fee + rate x amount), unlike
    Polygon's flat fee. That predicts a crossover point where Lightning stops
    being cheapest as amounts rise -- a pre-registered objective
    (ANALYSIS_PLAN.md S12).

WHY INVOICES ARE PRE-GENERATED
------------------------------
A Lightning payment needs an invoice from the recipient, and invoices are
single-use. Creating one inside `submit()` would put a network round trip to
the recipient inside the measured latency -- and Polygon's timer starts when
the payment is sent, not when the recipient is contacted. To keep the two
architectures' definitions identical, invoices are generated during `setup()`
and handed out from a pool. This is the direct analogue of Polygon's
pre-funded sender pool: preparation belongs in setup, not in the measurement.

WHY SEND AND TRACK ARE ONE STREAM
---------------------------------
LND's SendPaymentV2 is server-streaming: it emits IN_FLIGHT then a final
SUCCEEDED/FAILED. `submit()` starts that stream in a background task and
returns the payment hash immediately, so the send loop never blocks (claude.md
S6). `await_confirmation()` waits on that task's future. Using the separate
TrackPaymentV2 endpoint would mean a second connection per payment, and at 300
payments/second that is 300 extra connections a second competing with the
sends -- the same class of self-inflicted bottleneck that produced Polygon's
phantom throughput knee.
"""

from __future__ import annotations

import asyncio
import base64
import json
import random
import ssl
from typing import Any

import aiohttp

from .base import Adapter, ConfirmResult, SubmitResult

#: Every in-flight payment holds an OPEN streaming connection.
#:
#: SendPaymentV2 is server-streaming: the connection stays open from submission
#: until the payment resolves. At a mean settlement of ~4.7s, 300 payments a
#: second means ~1,400 connections open at once. The Polygon adapter's 256 was
#: sized for request/response calls that return immediately and is far too low
#: here -- above ~50/sec the excess queues silently, which reads as the network
#: being slow rather than as our own client throttling itself. That is exactly
#: the mistake that cost a day on Polygon, in a form that bites ~6x sooner.
_HTTP_CONNECTION_LIMIT = 4096

#: LND rejects a payment whose fee would exceed this. Set generously: we are
#: measuring what routing *costs*, so capping it low would convert a expensive
#: successful route into a failure and corrupt both metrics at once.
_FEE_LIMIT_FRACTION = 0.05

#: Invoices are minted this many deep per recipient before a run. Sized from
#: the run's scheduled payment count in `setup()`; this is only the floor.
_MIN_INVOICE_POOL = 256

#: How many invoice requests are in flight at once while filling the pool.
#: High enough to hide a 315 ms intercontinental round trip, bounded so that
#: minting cannot starve the connection pool the measured run needs.
_MINT_CONCURRENCY = 100

SATS_PER_BTC = 100_000_000


class LightningAdapter(Adapter):
    """One LND node acting as sender, paying invoices from recipient nodes."""

    architecture = "lightning"
    name = "lnd-regtest"

    def __init__(
        self,
        sender_endpoints: list[dict[str, str]],
        recipient_endpoints: list[dict[str, str]],
        btc_usd_rate: float,
        fee_limit_fraction: float = _FEE_LIMIT_FRACTION,
    ) -> None:
        """
        `sender_endpoints` / `recipient_endpoints`: one dict per node, with
        `url` (https://host:8080) and `macaroon` (hex). Senders are used round
        robin so no single node's channel liquidity becomes the ceiling --
        the Lightning equivalent of Polygon's nonce contention, and just as
        capable of looking like a network limit when it is ours.
        """
        self._senders = sender_endpoints
        self._recipients = recipient_endpoints
        self._rate = btc_usd_rate
        self._fee_limit_fraction = fee_limit_fraction

        self._session: aiohttp.ClientSession | None = None
        #: payment_hash -> future resolved by the send stream
        self._pending: dict[str, asyncio.Future] = {}
        #: recipient index -> list of unused (payment_request, payment_hash)
        self._invoices: list[list[tuple[str, str]]] = []
        self._invoice_lock = asyncio.Lock()
        self._tasks: set[asyncio.Task] = set()
        self._next_sender = 0
        self._weights: list[float] = []
        self._rng = random.Random(20260810)

    # -- lifecycle ----------------------------------------------------------

    async def setup(self, context: dict[str, Any]) -> None:
        # regtest nodes use self-signed certificates. Verification is disabled
        # deliberately and ONLY here: this is a private network we deployed
        # ourselves, on hosts we control, carrying no real value. It is a
        # test-fixture decision, not a security position, and must not be
        # copied into anything handling real funds.
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

        self._session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(
                limit=_HTTP_CONNECTION_LIMIT,
                limit_per_host=_HTTP_CONNECTION_LIMIT,
                ssl=ssl_ctx,
            ),
            timeout=aiohttp.ClientTimeout(total=None, sock_connect=10),
        )

        scheduled = int(context.get("scheduled_count", 0))
        amount_usd = float(context.get("tx_size_usd", 200.0))

        # Destinations are chosen in proportion to how much each can RECEIVE,
        # not uniformly.
        #
        # Uniform round robin is our artifact, not Lightning's behaviour. It
        # sent one seventh of all flow at a node holding 0.01 BTC of inbound --
        # 65 payments at $10 before it was full -- so three thin recipients
        # saturated within seconds and rejected everything addressed to them
        # for the rest of the run. Three of seven is 42.9%; the measured
        # failure rate was 43.3%.
        #
        # On the real network a payment goes to whoever is being paid, and
        # traffic concentrates on well-connected, well-funded nodes for the
        # same reason liquidity does. Weighting by inbound capacity reproduces
        # that, and it stops a thin leaf from being handed a share of flow it
        # could never see in reality. Thin nodes still fail when they are
        # chosen and cannot route -- which is the real effect this arm
        # measures, and is left intact.
        self._weights = await self._recipient_weights()
        await self._mint_invoices(scheduled, amount_usd)

    async def teardown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def health_check(self) -> bool:
        """Every node must be synced and have at least one active channel.

        A node with no active channel cannot pay or be paid, and would report
        100% failure that belongs to our deployment rather than to Lightning.
        Cheap to check, and it fails loudly instead of producing a plausible
        wrong number -- the lesson Polygon's proof-of-authority bug taught.
        """
        for ep in self._senders + self._recipients:
            info = await self._get(ep, "/v1/getinfo")
            if info is None:
                return False
            # `synced_to_chain` is deliberately NOT required.
            #
            # LND reports false whenever the chain tip looks stale, and a
            # regtest chain only produces blocks when we mine them -- so a few
            # hours into a sweep every node declares itself out of sync while
            # routing payments perfectly well. Requiring it aborted a run on a
            # network whose channels were all active and all routable.
            #
            # What actually determines whether a payment can be made is having
            # a live channel, so that is what is checked. A separate block
            # ticker keeps the chain moving for the sake of realism.
            if int(info.get("num_active_channels", 0)) < 1:
                return False
        return True

    # -- measurement --------------------------------------------------------

    def usd_to_sat(self, amount_usd: float) -> int:
        """Convert at the rate pinned for the whole study.

        One rate, fixed at project start and held across every run
        (claude.md S6). Lightning is the only architecture needing this at all:
        the stablecoin chains make $200 exactly 200 tokens, which is a second
        independent reason the ERC-20/NEP-141 choice was right.
        """
        return int(round(amount_usd / self._rate * SATS_PER_BTC))

    async def submit(self, seq: int, amount_usd: float) -> SubmitResult:
        sender = self._senders[self._next_sender % len(self._senders)]
        self._next_sender += 1

        invoice = await self._take_invoice()
        if invoice is None:
            return SubmitResult(ok=False, error="invoice pool exhausted")
        payment_request, payment_hash = invoice

        sats = self.usd_to_sat(amount_usd)
        loop = asyncio.get_running_loop()
        self._pending[payment_hash] = loop.create_future()

        task = asyncio.create_task(self._send_and_stream(sender, payment_request,
                                                         payment_hash, sats))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

        return SubmitResult(ok=True, tx_ref=payment_hash, amount_native=str(sats))

    async def await_confirmation(self, tx_ref: str, timeout_seconds: float) -> ConfirmResult:
        future = self._pending.get(tx_ref)
        if future is None:
            return ConfirmResult(status="failed", error="no pending payment for hash")
        try:
            return await asyncio.wait_for(future, timeout=timeout_seconds)
        except asyncio.TimeoutError:
            # Settlement is the preimage returning to the sender (claude.md S7).
            # Past 60s a remittance has functionally failed regardless of what
            # the network eventually decides.
            return ConfirmResult(status="timeout", error=f"no preimage within {timeout_seconds:g}s")
        finally:
            self._pending.pop(tx_ref, None)

    # -- internals ----------------------------------------------------------

    async def _send_and_stream(self, sender: dict[str, str], payment_request: str,
                               payment_hash: str, sats: int) -> None:
        """Drive one SendPaymentV2 stream to its final update."""
        body = {
            "payment_request": payment_request,
            "timeout_seconds": 60,
            "fee_limit_msat": str(int(sats * 1000 * self._fee_limit_fraction)),
            "no_inflight_updates": True,   # we only need the final state
        }
        result = ConfirmResult(status="failed", error="stream ended with no final update")
        try:
            assert self._session is not None
            async with self._session.post(
                f"{sender['url']}/v2/router/send",
                headers=self._headers(sender),
                json=body,
            ) as resp:
                async for raw in resp.content:
                    line = raw.strip()
                    if not line:
                        continue
                    payload = json.loads(line)
                    update = payload.get("result", payload)
                    status = update.get("status")
                    if status in ("SUCCEEDED", "FAILED"):
                        result = self._interpret(update)
                        break
        except asyncio.CancelledError:
            raise
        except Exception as exc:                      # noqa: BLE001 - recorded, not raised
            result = ConfirmResult(status="failed", error=f"{type(exc).__name__}: {exc}")

        future = self._pending.get(payment_hash)
        if future is not None and not future.done():
            future.set_result(result)

    @staticmethod
    def _interpret(update: dict) -> ConfirmResult:
        """Turn LND's final payment update into a recorded outcome.

        The failure *reason* is the substance of this arm. LND distinguishes
        no-route from insufficient-balance from timeout, and those are
        different findings about Lightning: the first says the topology has no
        path, the second says a path exists but cannot carry this amount. The
        second is the Waugh & Holz effect; collapsing them would erase it.
        """
        if update.get("status") == "SUCCEEDED":
            htlcs = update.get("htlcs") or []
            hops = None
            for htlc in htlcs:
                route = (htlc.get("route") or {})
                if route.get("hops"):
                    hops = len(route["hops"])
                    break
            fee_msat = update.get("fee_msat")
            return ConfirmResult(
                status="confirmed",
                fee_native=str(fee_msat) if fee_msat is not None else None,
                route_hops=hops,
            )
        reason = update.get("failure_reason", "FAILURE_REASON_UNKNOWN")
        return ConfirmResult(status="failed", error=str(reason))

    async def _recipient_weights(self) -> list[float]:
        """Share of payments each recipient should receive.

        Proportional to inbound capacity -- what the node can actually take in
        -- with a floor so every destination still receives some traffic and
        the thin ones remain part of the measurement.
        """
        inbound = []
        for ep in self._recipients:
            data = await self._get(ep, "/v1/channels")
            chans = (data or {}).get("channels", [])
            inbound.append(sum(int(c.get("remote_balance", 0)) for c in chans))

        total = sum(inbound)
        if total <= 0:
            return [1.0 / len(self._recipients)] * len(self._recipients)

        # 2% floor each: thin nodes stay in the sample, so their failures are
        # still measured, but they are not handed 1/n of the entire workload.
        floor = 0.02
        raw = [max(v / total, floor) for v in inbound]
        scale = sum(raw)
        return [v / scale for v in raw]

    async def _mint_invoices(self, scheduled: int, amount_usd: float) -> None:
        """Pre-generate the invoice pool, concurrently.

        Minting is one HTTP round trip per invoice, and the recipients sit in
        Mumbai and Singapore -- 315 ms each from the generator in Virginia.
        Issued one at a time that is 81 MINUTES of setup before a single
        300/sec run, and roughly 27 hours across the high-load steps: setup
        would have cost more than the measurements.

        Issued concurrently the same work takes about 12 ms each, a 27x
        difference that is entirely latency hiding, not extra load on the
        nodes. The semaphore keeps a lid on it so minting cannot itself
        saturate the connection pool the measured run depends on.
        """
        sats = self.usd_to_sat(amount_usd)
        self._invoices = [[] for _ in self._recipients]
        sem = asyncio.Semaphore(_MINT_CONCURRENCY)

        # Pool depth follows the weights, so a destination that will receive
        # 30% of payments gets 30% of the invoices.
        counts = [max(_MIN_INVOICE_POOL, int(scheduled * w) + 64) for w in self._weights]

        async def one(idx: int, ep: dict[str, str]) -> None:
            async with sem:
                resp = await self._post(ep, "/v1/invoices",
                                        {"value": str(sats), "expiry": "7200"})
            if resp is None:
                return
            # LND returns r_hash base64; the payment hash we key on is its hex
            # form, which is what appears in logs and lncli output.
            r_hash = base64.b64decode(resp["r_hash"]).hex()
            self._invoices[idx].append((resp["payment_request"], r_hash))

        await asyncio.gather(*(
            one(i, ep)
            for i, ep in enumerate(self._recipients)
            for _ in range(counts[i])
        ))

        minted = sum(len(p) for p in self._invoices)
        if minted < sum(counts) * 0.9:
            # Short pools mean payments later fail with "invoice pool
            # exhausted" -- our artifact, recorded as if Lightning refused the
            # payment. Better to say so now than to find it in the data.
            print(f"  WARNING: minted {minted} invoices, wanted "
                  f"{sum(counts)}")

    async def _take_invoice(self) -> tuple[str, str] | None:
        """Pop one invoice, choosing the destination by capacity weight.

        Seeded from the run's own arrival seed so the destination sequence is
        reproducible: two repeats of a configuration must not differ because
        they happened to pick different recipients.
        """
        async with self._invoice_lock:
            idx = self._rng.choices(range(len(self._invoices)), weights=self._weights)[0]
            if self._invoices[idx]:
                return self._invoices[idx].pop()
            # Chosen pool is empty -- fall back to any pool that is not, so a
            # single exhausted destination cannot stall the whole run.
            for j in range(len(self._invoices)):
                if self._invoices[j]:
                    return self._invoices[j].pop()
        return None

    @staticmethod
    def _headers(ep: dict[str, str]) -> dict[str, str]:
        return {"Grpc-Metadata-macaroon": ep["macaroon"]}

    async def _get(self, ep: dict[str, str], path: str) -> dict | None:
        assert self._session is not None
        try:
            async with self._session.get(f"{ep['url']}{path}",
                                         headers=self._headers(ep)) as resp:
                if resp.status != 200:
                    return None
                return await resp.json()
        except Exception:                             # noqa: BLE001
            return None

    async def _post(self, ep: dict[str, str], path: str, body: dict) -> dict | None:
        assert self._session is not None
        try:
            async with self._session.post(f"{ep['url']}{path}",
                                          headers=self._headers(ep),
                                          json=body) as resp:
                if resp.status != 200:
                    return None
                return await resp.json()
        except Exception:                             # noqa: BLE001
            return None
