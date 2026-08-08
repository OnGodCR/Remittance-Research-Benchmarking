"""Poisson arrival process for the offered-load generator.

Why Poisson and not fixed-interval (claude.md S6): real remittance traffic
arrives at randomly-spaced times, not on a metronome. A fixed-interval
generator at 100 TPS presents a perfectly smooth load that no real system
ever sees, and it systematically *understates* queueing effects -- bursts are
where mempools back up and channels run dry, and a fixed-rate generator never
produces one.

For a Poisson process at rate lambda, inter-arrival times are Exponential with
mean 1/lambda. The schedule is generated up front from a seeded RNG rather
than sampled live, for three reasons:

  1. Reproducibility. A run can be replayed with the identical arrival pattern,
     so a difference between two runs is a difference in the *system*, not in
     the load we happened to draw.
  2. The 5 repeats per configuration get 5 *different* seeds. Repeats that
     shared an arrival pattern would understate variance and make the
     confidence intervals (technique #8) too narrow.
  3. Schedule lag becomes measurable. If the harness fires a transaction later
     than its scheduled offset, that gap is generator saturation, not chain
     latency -- see `summarize_lag`.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


def poisson_schedule(rate_tps: float, window_seconds: float, seed: int) -> list[float]:
    """Arrival offsets (seconds from run start) for a Poisson process.

    Returns offsets strictly within [0, window_seconds).
    """
    if rate_tps <= 0:
        raise ValueError(f"rate_tps must be positive, got {rate_tps}")
    if window_seconds <= 0:
        raise ValueError(f"window_seconds must be positive, got {window_seconds}")

    rng = random.Random(seed)
    offsets: list[float] = []
    t = 0.0
    while True:
        # expovariate(lambd) draws from Exponential with mean 1/lambd.
        t += rng.expovariate(rate_tps)
        if t >= window_seconds:
            break
        offsets.append(t)
    return offsets


def seed_for(base_seed: int, target_tps: float, tx_size_usd: float,
             repeat_index: int) -> int:
    """Derive a distinct, deterministic seed per (config, repeat).

    Distinct so repeats explore different arrival patterns; deterministic so
    the whole sweep is reproducible from one base seed.
    """
    key = (base_seed, round(target_tps * 1000), round(tx_size_usd * 100), repeat_index)
    return abs(hash(key)) % (2**31 - 1)


@dataclass
class LagSummary:
    """How far behind its own schedule the generator ran."""

    mean_lag: float
    p95_lag: float
    max_lag: float
    saturated: bool

    def describe(self) -> str:
        verdict = (
            "GENERATOR SATURATED -- this run's throughput ceiling is the harness, "
            "not the chain. Discard or re-run with more workers."
            if self.saturated
            else "generator kept up with schedule"
        )
        return (f"lag mean={self.mean_lag*1000:.1f}ms p95={self.p95_lag*1000:.1f}ms "
                f"max={self.max_lag*1000:.1f}ms -- {verdict}")


def summarize_lag(scheduled: list[float], submitted: list[float | None],
                  threshold_seconds: float = 0.25) -> LagSummary:
    """Compare intended vs actual submission times.

    This is the guard against the failure mode claude.md S8 warns about: at
    300 TPS the load generator can become the bottleneck, and an observed
    throughput ceiling would then be a property of our tooling rather than of
    the architecture under test. Sustained lag is the signature of that.

    `threshold_seconds` defaults to 250ms -- an order of magnitude below the
    ~5s finality both chains target, so it trips well before generator delay
    could be mistaken for settlement latency.
    """
    lags = [s - sch for sch, s in zip(scheduled, submitted) if s is not None]
    if not lags:
        return LagSummary(0.0, 0.0, 0.0, False)

    lags.sort()
    p95 = lags[min(int(len(lags) * 0.95), len(lags) - 1)]
    return LagSummary(
        mean_lag=sum(lags) / len(lags),
        p95_lag=p95,
        max_lag=lags[-1],
        saturated=p95 > threshold_seconds,
    )
