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
import ssl
from typing import Any

import aiohttp

from .base import Adapter, ConfirmResult, SubmitResult

#: Matches the Polygon adapter. The library default of 100 sat below our
#: concurrency demand, and the overflow queues silently -- which reads as
#: network latency rather than as our own connection limit. That exact mistake
#: cost a day on Polygon (RESUME_HERE.md).
_HTTP_CONNECTION_LIMIT = 256

#: LND rejects a payment whose fee would exceed this. Set generously: we are
#: measuring what routing *costs*, so capping it low would convert a expensive
#: successful route into a failure and corrupt both metrics at once.
_FEE_LIMIT_FRACTION = 0.05

#: Invoices are minted this many deep per recipient before a run. Sized from
#: the run's scheduled payment count in `setup()`; this is only the floor.
_MIN_INVOICE_POOL = 256

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
        per_recipient = max(_MIN_INVOICE_POOL,
                            (scheduled // max(len(self._recipients), 1)) + 64)
        amount_usd = float(context.get("tx_size_usd", 200.0))
        await self._mint_invoices(per_recipient, amount_usd)

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
            if info is None or not info.get("synced_to_chain"):
                return False
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

    async def _mint_invoices(self, per_recipient: int, amount_usd: float) -> None:
        """Pre-generate the invoice pool, in parallel across recipients."""
        sats = self.usd_to_sat(amount_usd)
        self._invoices = [[] for _ in self._recipients]

        async def mint(idx: int, ep: dict[str, str]) -> None:
            batch: list[tuple[str, str]] = []
            for _ in range(per_recipient):
                resp = await self._post(ep, "/v1/invoices",
                                        {"value": str(sats), "expiry": "7200"})
                if resp is None:
                    continue
                # LND returns r_hash base64; the payment hash we key on is its
                # hex form, which is what appears in logs and lncli output.
                r_hash = base64.b64decode(resp["r_hash"]).hex()
                batch.append((resp["payment_request"], r_hash))
            self._invoices[idx] = batch

        await asyncio.gather(*(mint(i, ep) for i, ep in enumerate(self._recipients)))

    async def _take_invoice(self) -> tuple[str, str] | None:
        """Pop one invoice, round robin across recipients.

        Round robin rather than random so payment destinations are spread
        evenly: concentrating on one recipient would exhaust its inbound
        liquidity and produce failures that reflect our sampling rather than
        the network's structure.
        """
        async with self._invoice_lock:
            for _ in range(len(self._invoices)):
                idx = self._next_sender % len(self._invoices)
                if self._invoices[idx]:
                    return self._invoices[idx].pop()
                self._next_sender += 1
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
