"""Run one benchmark across several processes, then merge the results.

WHY THIS EXISTS
---------------
Python executes on a single processor core. In the Phase 2 pilot that became
the binding limit at roughly 150 payments/second: at 200 the harness fell
2 seconds behind its own schedule, and at 300 it fell 20 seconds behind. Both
runs auto-invalidated, correctly -- the ceiling being measured was ours, not
the blockchain's.

Splitting the load across processes removes that limit, because each process
gets its own core and its own event loop.

TWO THINGS THAT MUST BE RIGHT
-----------------------------
**The arrival pattern must stay a single Poisson process.** Every worker
generates the identical schedule from the same seed and takes a stride
through it (`seq % worker_count == worker_index`). The union is exactly the
original schedule -- same transactions, same times. Running N independent
Poisson generators instead would produce different burst behaviour, and
bursts are precisely where queues form and systems break.

**Workers must never share a sender account.** Each account numbers its own
transactions strictly in order; two processes drawing on one account would
collide, stall, and produce a slowdown indistinguishable from chain
congestion. Accounts are partitioned with no overlap.

Each worker writes to its own database file and the parent merges them.
That avoids multi-process write contention entirely, at the cost of a merge
step measured in milliseconds.
"""

from __future__ import annotations

import asyncio
import multiprocessing as mp
import sqlite3
import tempfile
from dataclasses import replace
from pathlib import Path

from .arrival import SATURATION_GROWTH_SECONDS
from .runner import DEFAULT_TIMEOUT_SECONDS, run_benchmark
from .storage import RunConfig, Store


def _worker(worker_index: int, worker_count: int, cfg: RunConfig, run_id: str,
            db_path: str, adapter_spec: dict, timeout_seconds: float, out_q) -> None:
    """One worker process: build its own adapter, run its slice, report back."""
    try:
        from ..adapters.polygon import PolygonAdapter

        keys = adapter_spec["sender_keys"]
        # Disjoint account slice. Stride-partitioned so every worker gets an
        # even share even when the count does not divide cleanly.
        my_keys = [k for i, k in enumerate(keys) if i % worker_count == worker_index]
        if not my_keys:
            out_q.put({"worker": worker_index, "error": "no sender accounts allocated"})
            return

        adapter = PolygonAdapter(
            rpc_url=adapter_spec["rpc_url"],
            token_address=adapter_spec["token_address"],
            sender_keys=my_keys,
            recipients=adapter_spec["recipients"],
            chain_id=adapter_spec["chain_id"],
            gas_price_wei=adapter_spec["gas_price_wei"],
        )

        store = Store(db_path)
        summary = asyncio.run(run_benchmark(
            adapter, cfg, store,
            timeout_seconds=timeout_seconds,
            verbose=False,
            worker_index=worker_index,
            worker_count=worker_count,
            run_id=run_id,
        ))
        store.close()

        lag = summary.pop("lag")
        summary["lag_p95"] = lag.p95_lag
        summary["lag_mean"] = lag.mean_lag
        summary["lag_max"] = lag.max_lag
        summary["lag_growth"] = lag.growth
        summary["worker"] = worker_index
        out_q.put(summary)
    except Exception as exc:
        out_q.put({"worker": worker_index, "error": f"{type(exc).__name__}: {exc}"})


async def run_parallel_benchmark(
    cfg: RunConfig,
    store: Store,
    adapter_spec: dict,
    *,
    workers: int = 4,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    verbose: bool = True,
) -> dict:
    """Run one test across `workers` processes and merge into `store`."""
    if workers < 1:
        raise ValueError("workers must be at least 1")

    keys = adapter_spec["sender_keys"]
    if len(keys) < workers:
        raise ValueError(
            f"{workers} workers but only {len(keys)} sender accounts. Each worker "
            f"needs its own accounts -- sharing one causes transaction-ordering "
            f"collisions that look exactly like chain congestion. "
            f"Re-run deploy_and_fund with more senders."
        )

    run_id = cfg.run_id()
    if verbose:
        print(f"[{run_id}] {cfg.target_tps:g} TPS over {cfg.window_seconds:g}s "
              f"across {workers} workers ({len(keys)} accounts, "
              f"~{len(keys)//workers} each)")

    tmpdir = Path(tempfile.mkdtemp(prefix="harness-workers-"))
    ctx = mp.get_context("spawn")
    out_q = ctx.Queue()
    procs = []

    for w in range(workers):
        db_path = str(tmpdir / f"worker{w}.sqlite")
        p = ctx.Process(
            target=_worker,
            args=(w, workers, cfg, run_id, db_path, adapter_spec, timeout_seconds, out_q),
        )
        p.start()
        procs.append((p, db_path))

    results = [out_q.get() for _ in procs]
    for p, _ in procs:
        p.join()

    errors = [r for r in results if "error" in r]
    if errors:
        for e in errors:
            print(f"  worker {e['worker']} FAILED: {e['error']}")
        raise RuntimeError(f"{len(errors)}/{workers} workers failed")

    # --- merge worker databases ------------------------------------------
    for _, db_path in procs:
        src = sqlite3.connect(db_path)
        src.close()
        store.conn.execute("ATTACH DATABASE ? AS w", (db_path,))
        store.conn.execute("INSERT OR IGNORE INTO runs SELECT * FROM w.runs")
        store.conn.execute("INSERT OR REPLACE INTO transactions SELECT * FROM w.transactions")
        # Per-second counts are per worker, so they must be summed rather than
        # replaced -- otherwise the time series would show one worker's share
        # and understate the run by a factor of `workers`.
        store.conn.execute("""
            INSERT INTO samples (run_id, second, submitted, confirmed, failed, inflight)
            SELECT run_id, second, submitted, confirmed, failed, inflight FROM w.samples
            WHERE true
            ON CONFLICT(run_id, second) DO UPDATE SET
                submitted = samples.submitted + excluded.submitted,
                confirmed = samples.confirmed + excluded.confirmed,
                failed    = samples.failed    + excluded.failed,
                inflight  = samples.inflight  + excluded.inflight
        """)
        store.conn.execute("DETACH DATABASE w")

    store.end_run(run_id)

    # --- aggregate -------------------------------------------------------
    summary = store.run_summary(run_id)
    # Judged on the WORST worker's lag GROWTH, not its magnitude. One process
    # falling progressively behind is enough to distort the arrival pattern,
    # whereas a constant offset in all of them is harmless fixed overhead.
    worst_growth = max(r["lag_growth"] for r in results)
    summary["generator_saturated"] = worst_growth > SATURATION_GROWTH_SECONDS
    summary["worker_count"] = workers
    summary["lag_p95"] = max(r["lag_p95"] for r in results)
    summary["lag_mean"] = sum(r["lag_mean"] for r in results) / len(results)
    summary["lag_max"] = max(r["lag_max"] for r in results)
    summary["lag_growth"] = worst_growth

    if summary["generator_saturated"]:
        store.invalidate_run(
            run_id,
            f"generator saturated across {workers} workers: worst-worker lag grew "
            f"{worst_growth*1000:.1f}ms during the run "
            f"(threshold {SATURATION_GROWTH_SECONDS*1000:.0f}ms)",
        )

    if verbose:
        print(f"[{run_id}] offered={cfg.target_tps:g} "
              f"achieved={summary['achieved_tps']:.1f} TPS | "
              f"ok={summary['confirmed']} fail={summary['failed']}")
        state = ("GENERATOR SATURATED -- ceiling is the harness, not the chain"
                 if summary["generator_saturated"] else "workers kept pace")
        print(f"[{run_id}] worst-worker lag growth={worst_growth*1000:+.1f}ms -- {state}")

    return summary
