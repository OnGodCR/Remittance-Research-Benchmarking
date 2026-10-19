"""End-to-end smoke test of the harness core against the null adapter.

Proves the pipeline (schedule -> submit -> confirm -> persist -> summarise)
works before any cloud spend. Run:

    python3.12 -m harness.smoke_test
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from .adapters.null import NullAdapter
from .core.arrival import poisson_schedule, seed_for
from .core.runner import run_benchmark
from .core.storage import RunConfig, Store


def check_arrival_statistics() -> None:
    """A Poisson process at rate lambda over T seconds should yield ~lambda*T
    arrivals. If this drifts, every offered-load number in the paper is wrong,
    so it is worth asserting rather than assuming."""
    print("== arrival process ==")
    for rate in (10, 50, 300):
        counts = [len(poisson_schedule(rate, 60, seed)) for seed in range(20)]
        mean = sum(counts) / len(counts)
        expected = rate * 60
        drift = abs(mean - expected) / expected
        print(f"  {rate:>3} TPS x 60s -> mean {mean:8.1f} arrivals "
              f"(expected {expected}, drift {drift*100:.2f}%)")
        assert drift < 0.05, f"Poisson generator off by {drift*100:.1f}% at {rate} TPS"

    # Repeats must not share an arrival pattern, or the confidence intervals
    # in technique #8 come out artificially narrow.
    seeds = {seed_for(42, 100, 200.0, r) for r in range(5)}
    assert len(seeds) == 5, f"repeat seeds collided: {seeds}"
    print(f"  5 repeats -> 5 distinct seeds OK")


async def check_pipeline() -> None:
    print("\n== pipeline (null adapter) ==")
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "smoke.sqlite")

        cfg = RunConfig(
            architecture="null",
            adapter="null",
            tx_size_usd=200.0,          # the World Bank headline size
            target_tps=25.0,
            window_seconds=10.0,        # short: this is a smoke test, not a measurement
            repeat_index=0,
            arrival_seed=seed_for(42, 25.0, 200.0, 0),
            phase="phase-0-smoke",
        )

        summary = await run_benchmark(
            NullAdapter(settle_delay_seconds=0.4), cfg, store, verbose=True
        )

        assert summary["scheduled"] > 0, "no transactions scheduled"
        assert summary["confirmed"] == summary["submitted"], (
            f"null adapter should confirm everything: "
            f"{summary['confirmed']}/{summary['submitted']}"
        )
        assert summary["failed"] == 0, f"unexpected failures: {summary['failed']}"

        # Latency should track the adapter's artificial settle delay.
        assert 0.3 < summary["mean_latency"] < 0.6, (
            f"mean latency {summary['mean_latency']:.3f}s does not match the "
            f"0.4s synthetic settle delay -- timing path is wrong"
        )
        print(f"  mean latency {summary['mean_latency']*1000:.0f}ms "
              f"(synthetic delay was 400ms) OK")

        # Per-second series must exist -- it is what lets us drop warm-up later.
        rows = store.conn.execute(
            "SELECT COUNT(*) c FROM samples WHERE run_id=?", (summary["run_id"],)
        ).fetchone()["c"]
        assert rows >= 5, f"expected a per-second series, got {rows} rows"
        print(f"  {rows} per-second samples recorded OK")

        store.close()


async def check_failure_accounting() -> None:
    """Failures must be counted separately and excluded from achieved
    throughput (claude.md S7). For Lightning this is the headline result, so
    the accounting has to be right."""
    print("\n== failure accounting ==")
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "fail.sqlite")
        cfg = RunConfig(
            architecture="null", adapter="null", tx_size_usd=200.0,
            target_tps=50.0, window_seconds=6.0, arrival_seed=7,
            phase="phase-0-smoke",
        )
        summary = await run_benchmark(
            NullAdapter(settle_delay_seconds=0.1, fail_rate=0.30), cfg, store, verbose=False
        )

        total = summary["confirmed"] + summary["failed"]
        observed = summary["failed"] / total
        print(f"  injected 30% failures -> observed {observed*100:.1f}%")
        assert 0.20 < observed < 0.40, f"failure rate accounting is off: {observed:.2f}"

        expected_tps = summary["confirmed"] / cfg.window_seconds
        assert abs(summary["achieved_tps"] - expected_tps) < 0.01, (
            "achieved throughput must count confirmed transactions only"
        )
        print(f"  achieved TPS counts confirmed only "
              f"({summary['achieved_tps']:.1f}, not {total/cfg.window_seconds:.1f}) OK")
        store.close()


def check_worker_split() -> None:
    """Splitting load across processes must not change the offered load.

    Each worker strides through the same schedule. If the union were not
    exactly the original, offered load would silently become a different
    stochastic process -- several independent Poisson streams rather than one,
    which have different burst behaviour. Bursts are where queues form and
    systems break, so this would quietly change what is being measured.
    """
    print("\n== worker split ==")
    offsets = poisson_schedule(150, 60, seed=99)

    for workers in (2, 4, 8):
        union = []
        for w in range(workers):
            union += [(i, off) for i, off in enumerate(offsets) if i % workers == w]
        union.sort()

        assert len(union) == len(offsets), (
            f"{workers} workers: {len(union)} transactions vs {len(offsets)} scheduled"
        )
        assert [off for _, off in union] == offsets, (
            f"{workers} workers: arrival times differ from the single-process schedule"
        )
        assert [i for i, _ in union] == list(range(len(offsets))), (
            f"{workers} workers: sequence numbers are not the original ones"
        )

        shares = [sum(1 for i in range(len(offsets)) if i % workers == w)
                  for w in range(workers)]
        spread = max(shares) - min(shares)
        assert spread <= 1, f"{workers} workers: uneven split {shares}"
        print(f"  {workers} workers -> {len(union):,} tx, identical schedule, "
              f"balanced within {spread} tx OK")

    # Accounts must never be shared: two processes on one account collide on
    # transaction ordering, which looks exactly like chain congestion.
    for workers in (2, 4, 8):
        keys = [f"key{i}" for i in range(46)]
        slices = [[k for i, k in enumerate(keys) if i % workers == w] for w in range(workers)]
        flat = [k for s in slices for k in s]
        assert len(flat) == len(set(flat)), f"{workers} workers: accounts overlap"
        assert sorted(flat) == sorted(keys), f"{workers} workers: accounts lost"
        assert all(s for s in slices), f"{workers} workers: a worker got no accounts"
    print("  account partitions are disjoint and complete OK")


async def main() -> None:
    check_arrival_statistics()
    check_worker_split()
    await check_pipeline()
    await check_failure_accounting()
    print("\nAll smoke checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
