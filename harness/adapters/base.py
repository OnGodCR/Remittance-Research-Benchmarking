"""Adapter interface -- the one seam between the shared harness and each chain.

claude.md S8: one measurement instrument across all three architectures.
Everything that determines a *number* -- Poisson arrival, concurrency, timing,
storage schema -- lives in the shared core and is byte-identical for Polygon,
Lightning and NEAR. Adapters only know how to build, send and confirm a
payment on their own network. If timing logic ever leaks into an adapter, the
cross-architecture comparison in Phase 6 stops being apples-to-apples, which
is the entire reason Hyperledger Caliper was dropped.

Submission and confirmation are deliberately separate calls. Concurrent
submission (claude.md S6) means we must never block the send loop waiting for
a confirmation; the runner fires `submit()` on schedule and watches for
settlement independently.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class SubmitResult:
    """Outcome of getting a payment onto the network."""

    ok: bool
    tx_ref: str | None = None       # tx hash / payment hash
    amount_native: str | None = None  # exact decimal string; never a float
    error: str | None = None


@dataclass
class ConfirmResult:
    """Outcome of waiting for settlement.

    `status` is one of: confirmed | failed | timeout.

    What counts as settled differs per architecture and is defined in
    claude.md S7 -- Polygon: inclusion in a committed block (PolyBFT gives
    instant finality, so no N-confirmations wait); Lightning: preimage
    returned to sender; NEAR: outcome at FINAL, not EXECUTED_OPTIMISTIC.
    Each adapter is responsible for honouring its own definition.
    """

    status: str
    gas_used: int | None = None
    fee_native: str | None = None
    route_hops: int | None = None   # Lightning only
    error: str | None = None

    #: The REAL on-chain identifier, when it is not known at submission time.
    #:
    #: NEAR's adapter broadcasts asynchronously and returns a local reference
    #: (`seq-N`) from submit(), because the hash does not exist until the
    #: transaction has been signed inside the send task. Without this field the
    #: database kept `seq-268` forever and NOT ONE NEAR payment in the dataset
    #: could be checked against the chain -- no post-hoc verification, and no
    #: way to investigate an individual failure. Polygon and Lightning know
    #: their identifier at submission and leave this None.
    settled_ref: str | None = None


class Adapter(ABC):
    """One network under test."""

    #: 'polygon' | 'lightning' | 'near' | 'null'
    architecture: str = "unknown"

    #: Human-readable adapter identity, recorded per run for provenance.
    name: str = "unknown"

    @abstractmethod
    async def setup(self, context: dict[str, Any]) -> None:
        """Connect, load keys, prepare the sender account pool.

        The account *pool* is not optional for EVM chains: concurrent
        submission from a single account serialises on nonce assignment and
        will look like chain-side backpressure when it is really a client-side
        artifact. Each concurrent worker needs its own funded sender.
        """

    @abstractmethod
    async def submit(self, seq: int, amount_usd: float) -> SubmitResult:
        """Send one payment. Must not block on confirmation."""

    @abstractmethod
    async def await_confirmation(self, tx_ref: str, timeout_seconds: float) -> ConfirmResult:
        """Wait for settlement, or give up at `timeout_seconds`.

        Timeout is 60s per claude.md S7 -- roughly 10x the expected p99 for
        both chains, and past that point a remittance has functionally failed
        regardless of what the network eventually does.
        """

    @abstractmethod
    async def teardown(self) -> None:
        """Release connections. Must be safe to call after a failed setup."""

    async def health_check(self) -> bool:
        """Optional pre-run sanity check. Override where cheap to implement."""
        return True
