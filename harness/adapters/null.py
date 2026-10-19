"""Null adapter -- measures the harness's own throughput ceiling.

claude.md S8 and S13 step 8: before any measured run, we have to know the
maximum rate the generator itself can sustain. Without that number, an
observed plateau at (say) 180 TPS is ambiguous -- it could be the chain
degrading, or it could be our own Python event loop topping out. One of those
is a finding; the other is a bug we would have published.

This adapter answers nothing about blockchains. It accepts every payment,
optionally sleeps for a fixed delay to imitate settlement, and returns.
Whatever ceiling shows up running against it is pure harness overhead, so a
real architecture's numbers are only trustworthy well below that ceiling.

Usage: ramp the null adapter across the same 10 -> 300 TPS steps as a real
sweep and find where `summarize_lag` starts reporting saturation. Every
architecture result must sit below that point, or it needs more workers.
"""

from __future__ import annotations

import asyncio
import itertools
from typing import Any

from .base import Adapter, ConfirmResult, SubmitResult


class NullAdapter(Adapter):
    architecture = "null"
    name = "null"

    def __init__(self, settle_delay_seconds: float = 0.0, fail_rate: float = 0.0):
        """
        Args:
            settle_delay_seconds: artificial confirmation delay. Set this near
                a real chain's finality (~2-5s) when sizing worker counts --
                a harness that keeps up with instant confirmations may still
                fall over when thousands of confirmation watchers are in
                flight at once, which is the realistic condition.
            fail_rate: fraction of payments to fail deterministically, for
                exercising the failure-accounting path without a real network.
        """
        self.settle_delay = settle_delay_seconds
        self.fail_rate = fail_rate
        self._counter = itertools.count()
        self._submitted = 0

    async def setup(self, context: dict[str, Any]) -> None:
        self._counter = itertools.count()
        self._submitted = 0

    async def submit(self, seq: int, amount_usd: float) -> SubmitResult:
        self._submitted += 1
        return SubmitResult(
            ok=True,
            tx_ref=f"null-{seq}-{next(self._counter)}",
            # Mirror the string-not-float discipline the real adapters use.
            amount_native=f"{amount_usd:.6f}",
        )

    async def await_confirmation(self, tx_ref: str, timeout_seconds: float) -> ConfirmResult:
        if self.settle_delay > 0:
            await asyncio.sleep(min(self.settle_delay, timeout_seconds))
            if self.settle_delay > timeout_seconds:
                return ConfirmResult(status="timeout", error="null adapter forced timeout")

        if self.fail_rate > 0:
            seq = int(tx_ref.split("-")[1])
            if (seq % 100) < int(self.fail_rate * 100):
                return ConfirmResult(status="failed", error="null adapter synthetic failure")

        return ConfirmResult(status="confirmed", gas_used=0, fee_native="0")

    async def teardown(self) -> None:
        return None
