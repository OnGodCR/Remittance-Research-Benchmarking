"""Concurrent submission engine -- the shared measurement instrument.

This file is where offered load becomes real traffic, and it is identical for
every architecture. Adapters plug in underneath it (see adapters/base.py).

Two design points that materially affect the numbers:

**Submission never waits for confirmation.** claude.md S6 is explicit: submit
concurrently at the target rate, do not send-and-wait. A sequential harness
measures the round-trip latency of one transaction and calls it throughput,
which is a different (and much easier) question than sustained load. Here a
pacer fires each transaction at its scheduled offset and hands settlement
tracking to an independent task, so offered load is genuinely offered even
while thousands of payments are still in flight.

**Database writes are buffered, not inline.** Writing to SQLite inside the hot
path would block the event loop a few hundred times a second and inject
jitter into the very timestamps we are trying to measure. Outcomes accumulate
in memory and flush on the sampler's tick, which is already a natural pause.
The full schedule is written *before* the run starts, so a crash shows up as
missing submissions rather than as a silently shorter run.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from ..adapters.base import Adapter
from .arrival import poisson_schedule, summarize_lag
from .storage import RunConfig, Store

#: Per claude.md S7. Roughly 10x expected p99 for both chains; past this a
#: remittance has functionally failed whatever the network later does.
DEFAULT_TIMEOUT_SECONDS = 60.0

#: How long after the send window closes we keep waiting for stragglers.
#: Must be >= the timeout, or in-flight payments would be counted as failures
#: purely because the window ended.
_DRAIN_GRACE = DEFAULT_TIMEOUT_SECONDS + 5.0


@dataclass
class _Counters:
    submitted: int = 0
    confirmed: int = 0
    failed: int = 0
    inflight: int = 0


@dataclass
class _Buffers:
    """Pending DB writes, flushed on the sampler tick."""

    submitted: list[tuple] = field(default_factory=list)
    outcomes: list[tuple] = field(default_factory=list)


async def run_benchmark(
    adapter: Adapter,
    cfg: RunConfig,
    store: Store,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    verbose: bool = True,
) -> dict:
    """Execute one test run and persist every transaction.

    Returns the run summary dict. Check `generator_saturated` on it before
    trusting the throughput number for anything.
    """
    offsets = poisson_schedule(cfg.target_tps, cfg.window_seconds, cfg.arrival_seed)

    loop = asyncio.get_running_loop()
    counters = _Counters()
    buffers = _Buffers()
    submitted_at: list[float | None] = [None] * len(offsets)

    await adapter.setup(cfg.extra)
    if not await adapter.health_check():
        await adapter.teardown()
        raise RuntimeError(f"adapter {adapter.name} failed its health check; aborting run")

    run_id = store.start_run(cfg, scheduled_count=len(offsets), t0_wall=time.time())
    store.record_schedule(run_id, offsets)

    if verbose:
        print(f"[{run_id}] {len(offsets)} tx scheduled @ {cfg.target_tps:g} TPS "
              f"over {cfg.window_seconds:g}s (seed {cfg.arrival_seed})")

    t0 = loop.time()

    def now() -> float:
        return loop.time() - t0

    async def one_transaction(seq: int, scheduled_offset: float) -> None:
        counters.inflight += 1
        try:
            sub = await adapter.submit(seq, cfg.tx_size_usd)
            offset = now()
            submitted_at[seq] = offset

            if not sub.ok:
                counters.failed += 1
                buffers.outcomes.append(
                    (run_id, seq, "failed", None, None, None, None, sub.error)
                )
                return

            counters.submitted += 1
            buffers.submitted.append((run_id, seq, offset, sub.tx_ref, sub.amount_native))

            res = await adapter.await_confirmation(sub.tx_ref, timeout_seconds)
            confirmed_offset = now() if res.status == "confirmed" else None

            if res.status == "confirmed":
                counters.confirmed += 1
            else:
                counters.failed += 1

            buffers.outcomes.append(
                (run_id, seq, res.status, confirmed_offset, res.gas_used,
                 res.fee_native, res.route_hops, res.error)
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # adapter bug or transport failure
            counters.failed += 1
            buffers.outcomes.append(
                (run_id, seq, "failed", None, None, None, None, f"{type(exc).__name__}: {exc}")
            )
        finally:
            counters.inflight -= 1

    def flush() -> None:
        for rec in buffers.submitted:
            store.record_submitted(*rec)
        buffers.submitted.clear()
        for run, seq, status, conf, gas, fee, hops, err in buffers.outcomes:
            store.record_outcome(run, seq, status, confirmed_offset=conf, gas_used=gas,
                                 fee_native=fee, route_hops=hops, error=err)
        buffers.outcomes.clear()

    async def sampler() -> None:
        """Per-second time series. Enables excluding warm-up analytically
        later without re-running anything (claude.md S6)."""
        last = _Counters()
        second = 0
        try:
            while True:
                await asyncio.sleep(1.0)
                store.record_sample(
                    run_id, second,
                    submitted=counters.submitted - last.submitted,
                    confirmed=counters.confirmed - last.confirmed,
                    failed=counters.failed - last.failed,
                    inflight=counters.inflight,
                )
                last = _Counters(counters.submitted, counters.confirmed,
                                 counters.failed, counters.inflight)
                second += 1
                if second % 10 == 0:
                    flush()
                if verbose and second % 15 == 0:
                    print(f"[{run_id}] t={second}s "
                          f"sub={counters.submitted} ok={counters.confirmed} "
                          f"fail={counters.failed} inflight={counters.inflight}")
        except asyncio.CancelledError:
            raise

    sampler_task = asyncio.create_task(sampler())
    tasks: set[asyncio.Task] = set()

    try:
        # Pacer: create each task just in time rather than all up front --
        # at 300 TPS over 300s that would be 90k coroutines allocated before
        # the first one runs.
        for seq, offset in enumerate(offsets):
            delay = offset - now()
            if delay > 0:
                await asyncio.sleep(delay)
            task = asyncio.create_task(one_transaction(seq, offset))
            tasks.add(task)
            task.add_done_callback(tasks.discard)

        if verbose:
            print(f"[{run_id}] send window closed, draining {len(tasks)} in flight...")

        if tasks:
            await asyncio.wait(tasks, timeout=_DRAIN_GRACE)

        # Anything still running has exceeded the drain grace; it is a timeout
        # by definition, not a slow success.
        for task in list(tasks):
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        sampler_task.cancel()
        try:
            await sampler_task
        except asyncio.CancelledError:
            pass
        flush()
        store.end_run(run_id)
        await adapter.teardown()

    lag = summarize_lag(offsets, submitted_at)
    summary = store.run_summary(run_id)
    summary["generator_saturated"] = lag.saturated
    summary["lag"] = lag

    if verbose:
        print(f"[{run_id}] offered={cfg.target_tps:g} achieved={summary['achieved_tps']:.1f} TPS "
              f"| ok={summary['confirmed']} fail={summary['failed']}")
        print(f"[{run_id}] {lag.describe()}")

    if lag.saturated:
        store.invalidate_run(run_id, f"generator saturated: p95 lag {lag.p95_lag:.3f}s")

    return summary
