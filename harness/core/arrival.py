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
    """How far behind its own schedule the generator ran.

    `growth` is what decides validity -- see SATURATION_GROWTH_SECONDS. The
    magnitude figures are retained because they are useful for describing a
    run, but a large constant lag is not by itself disqualifying.
    """

    mean_lag: float
    p95_lag: float
    max_lag: float
    growth: float
    saturated: bool

    def describe(self) -> str:
        verdict = (
            "GENERATOR SATURATED -- lag grew during the run, so the load actually "
            "offered drifted from the load intended. Discard or add workers."
            if self.saturated
            else "generator kept pace (lag stable)"
        )
        return (f"lag mean={self.mean_lag*1000:.1f}ms p95={self.p95_lag*1000:.1f}ms "
                f"growth={self.growth*1000:+.1f}ms -- {verdict}")


#: How much the generator's scheduling lag may GROW across a run before the
#: run's numbers cannot be trusted.
#:
#: This is the project's single saturation criterion, applied uniformly to
#: every run in the study. It replaced an absolute-magnitude threshold on
#: 9 Aug 2026 (ANALYSIS_PLAN.md S13).
#:
#: WHY GROWTH RATHER THAN MAGNITUDE
#:
#: The earlier rule asked whether lag was large. That turned out to be the
#: wrong question. A generator can sit a constant few milliseconds behind
#: schedule forever without distorting anything -- that is fixed overhead, and
#: the load actually offered still matches the load intended.
#:
#: What corrupts a measurement is lag that GROWS: the generator falling
#: progressively further behind, so the arrival pattern being delivered drifts
#: away from the Poisson process that was scheduled. Offered load stops being
#: what we said it was.
#:
#: Measured evidence for the distinction. At 200 payments/sec the median lag
#: was 7.2ms in the first quarter of a run and 7.2ms in the last -- flat --
#: and settlement (3.69s) continued smoothly from 150/sec (3.33s). Nothing was
#: distorted, yet a 40ms magnitude threshold excluded every such run. By
#: contrast the genuinely broken runs show lag climbing from 870ms to 3,638ms,
#: or 4,622ms to 37,489ms, with settlement inflated three- to elevenfold.
#:
#: VALIDATION: applied to seven runs independently known to be broken -- the
#: pre-fix single-process runs and the 500 and 1000/sec ceiling tests -- this
#: criterion detects all seven, including a subtle case growing 9.7ms to
#: 294.9ms. It is not a permissive rule that catches nothing.
SATURATION_GROWTH_SECONDS = 0.050

#: Minimum submitted transactions before growth can be assessed. Below this a
#: quartile median is too noisy to mean anything.
SATURATION_MIN_SAMPLES = 100


def summarize_lag(scheduled: list[float], submitted: list[float | None],
                  growth_threshold: float = SATURATION_GROWTH_SECONDS) -> LagSummary:
    """Compare intended vs actual submission times.

    This is the guard against the failure mode claude.md S8 warns about: at
    300 TPS the load generator can become the bottleneck, and an observed
    throughput ceiling would then be a property of our tooling rather than of
    the architecture under test.

    The signature of that failure is lag that GROWS across a run, not lag that
    is merely large -- see SATURATION_GROWTH_SECONDS.
    """
    # Kept in SCHEDULE ORDER -- growth is only meaningful over time.
    ordered = [(sch, s - sch) for sch, s in zip(scheduled, submitted) if s is not None]
    ordered.sort(key=lambda x: x[0])
    lags_in_order = [lag for _, lag in ordered]

    if not lags_in_order:
        return LagSummary(0.0, 0.0, 0.0, 0.0, False)

    def median(xs: list[float]) -> float:
        ys = sorted(xs)
        n = len(ys)
        return ys[n // 2] if n % 2 else (ys[n // 2 - 1] + ys[n // 2]) / 2.0

    # Median of the first and last quarter. Medians rather than means so a
    # handful of outliers cannot manufacture apparent growth.
    if len(lags_in_order) >= SATURATION_MIN_SAMPLES:
        q = len(lags_in_order) // 4
        growth = median(lags_in_order[-q:]) - median(lags_in_order[:q])
        saturated = growth > growth_threshold
    else:
        growth = 0.0
        saturated = False

    sorted_lags = sorted(lags_in_order)
    p95 = sorted_lags[min(int(len(sorted_lags) * 0.95), len(sorted_lags) - 1)]
    return LagSummary(
        mean_lag=sum(lags_in_order) / len(lags_in_order),
        p95_lag=p95,
        max_lag=sorted_lags[-1],
        growth=growth,
        saturated=saturated,
    )
