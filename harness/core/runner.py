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
    #: (real_on_chain_ref, run_id, seq) for adapters that only learn the true
    #: identifier during confirmation. See ConfirmResult.settled_ref.
    settled_refs: list[tuple] = field(default_factory=list)


async def run_benchmark(
    adapter: Adapter,
    cfg: RunConfig,
    store: Store,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    verbose: bool = True,
    worker_index: int = 0,
    worker_count: int = 1,
    run_id: str | None = None,
) -> dict:
    """Execute one test run and persist every transaction.

    Returns the run summary dict. Check `generator_saturated` on it before
    trusting the throughput number for anything.

    **Splitting across processes.** Python executes on a single processor
    core, which became the binding limit at ~150 payments/second in the
    Phase 2 pilot -- above that the harness, not the chain, was the
    bottleneck. Passing `worker_count > 1` runs several processes, each
    firing the transactions where `seq % worker_count == worker_index`.

    That specific split matters: the full Poisson schedule is generated
    identically in every worker from the same seed, and each takes a stride
    through it. The union of all workers therefore reproduces the original
    arrival pattern EXACTLY, so offered load stays a true Poisson process
    rather than several independent ones layered on top of each other, which
    would have different burst behaviour.

    Every worker must be given the same `run_id`, or one test appears in the
    data as several unrelated partial runs. Workers must also be given
    DISJOINT sender accounts -- two processes sharing an account would
    collide on transaction ordering, which looks exactly like chain
    congestion.
    """
    all_offsets = poisson_schedule(cfg.target_tps, cfg.window_seconds, cfg.arrival_seed)
    # Stride through the shared schedule. Sequence numbers stay GLOBAL so the
    # merged data reconstructs the original ordering exactly.
    schedule = [(i, off) for i, off in enumerate(all_offsets)
                if i % worker_count == worker_index]

    loop = asyncio.get_running_loop()
    counters = _Counters()
    buffers = _Buffers()
    submitted_at: dict[int, float] = {}

    await adapter.setup(cfg.extra)
    if not await adapter.health_check():
        await adapter.teardown()
        raise RuntimeError(f"adapter {adapter.name} failed its health check; aborting run")

    run_id = store.start_run(cfg, scheduled_count=len(all_offsets),
                             t0_wall=time.time(), run_id=run_id)
    store.record_schedule_pairs(run_id, schedule)

    if verbose:
        share = "" if worker_count == 1 else f" (worker {worker_index+1}/{worker_count})"
        print(f"[{run_id}] {len(schedule)} tx scheduled @ {cfg.target_tps:g} TPS "
              f"over {cfg.window_seconds:g}s (seed {cfg.arrival_seed}){share}")

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

            # Prefer the adapter's real on-chain identifier when it only
            # becomes known during confirmation; otherwise the submission-time
            # reference stands. Without this, an asynchronously broadcast
            # payment is recorded under a local counter and can never be found
            # on chain again.
            if res.settled_ref:
                buffers.settled_refs.append((res.settled_ref, run_id, seq))
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
        # Batched deliberately. The row-at-a-time version issued one statement
        # per payment -- roughly 3,000 per flush at 300/sec -- and every one
        # of them blocked the event loop that is timing the run. Batching
        # prepares each statement once and commits the lot in one go.
        if buffers.submitted:
            store.record_submitted_batch(buffers.submitted)
            buffers.submitted.clear()
        if buffers.outcomes:
            store.record_outcome_batch(buffers.outcomes)
            buffers.outcomes.clear()
        if buffers.settled_refs:
            store.update_tx_refs(buffers.settled_refs)
            buffers.settled_refs.clear()

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
        for seq, offset in schedule:
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

    lag = summarize_lag([off for _, off in schedule],
                        [submitted_at.get(seq) for seq, _ in schedule])
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
