# NEAR (Sharding) — Results

**Status:** Data collection closed 13 August 2026. All figures below are computed
from `data/clean/all_runs_clean.parquet` by `analysis/results.py`,
`analysis/calibration.py` and `analysis/shard_scaling.py`, under the rules locked
in `ANALYSIS_PLAN.md`.

**Deployment:** nearcore 2.13.3, protocol 86, **4 shards, 8 validators** across
us-east4 / asia-south1 / asia-southeast1 / europe-west2, `n2-standard-8`
(8 vCPU / 32 GB), full realism stack — real intercontinental latency plus injected
per-region impairment, competing background traffic averaging ~88 tx/sec, NEP-141
fungible-token transfers, settlement at `FINAL`.

---

## 1. Headline: 150 payments per second

**Sustainable throughput at $200 = 150/sec** (pre-registered metric: achieved ≥90%
of offered AND failures <5%).

| Offered/sec | Achieved | 95% CI | Failures | p50 | p95 | p99 |
|---|---|---|---|---|---|---|
| 10 | 9.8 | [9.6, 9.9] | 1.37% | 11.33s | 12.76s | 15.38s |
| 25 | 24.8 | [24.6, 24.9] | 0.88% | 11.20s | 12.33s | 14.27s |
| 50 | 49.8 | [49.5, 50.1] | 0.41% | 11.29s | 12.43s | 14.08s |
| 100 | 100.0 | [99.3, 100.7] | 0.16% | 11.68s | 13.18s | 15.37s |
| **150** | **150.1** | **[149.6, 150.6]** | **0.15%** | 12.43s | 19.20s | 23.25s |
| 200 | 47.5 | [26.3, 68.7] | 76.30% | 35.48s | 57.85s | 59.56s |
| 300 | — | — | — | — | — | — |

Five repeats per cell, bootstrap intervals resampled over **runs**, not payments.

---

## 2. The finding that matters more than the ceiling: NEAR collapses, Polygon bends

At 200/sec NEAR does not plateau. **It achieves 47.5/sec — less than it manages
when offered 50/sec.** Ask for more, get less.

| | Polygon Edge | NEAR |
|---|---|---|
| Sustainable at $200 | 200/sec | 150/sec |
| One step past the knee | 300 offered → **270.5 achieved**, 9.97% fail | 200 offered → **47.5 achieved**, 76.3% fail |
| Behaviour past the knee | **graceful degradation** | **congestion collapse** |

**Why this belongs in the paper's argument, not a footnote.** The scope document
identifies peak demand as *payday and holiday clustering* — predictable spikes
above the ~140–150/sec global average. A system that degrades gracefully delivers
most payments late. A system that collapses delivers almost none, precisely when
volume peaks. **For remittances the failure mode is as consequential as the
ceiling.**

### What the failures actually are

Not lost money. The errors read `reached EXECUTED, not FINAL` — payments were
accepted and executed on chain but did not reach final settlement inside the
60-second budget. NEAR degrades by becoming slow, not by dropping transactions.

Per `claude.md` §7, past 60s a remittance has functionally failed regardless of
what the chain eventually does, so these count as failures (`ANALYSIS_PLAN.md`
§13 amendment 11).

### Settlement floor: 7.90 seconds

The fastest settlement recorded anywhere in NEAR's baseline data is **7.90s**
(8.49s restricted to $200), median 11.83s up to 150/sec, against Polygon's 1.22s
minimum and 3.82s median. This is protocol structure, not a defect: inclusion, then a
cross-shard receipt to the token contract's shard, then finality — each costing
blocks. **74.3% of payments crossed shards**, against a theoretical 75% for 836
senders spread over 4 shards with the token on one of them.

---

## 3. Transaction size does not matter, and that is the expected result

| Amount | Sustainable | Achieved at 150/sec | Failures |
|---|---|---|---|
| $10 | 150/sec | 150.0 | 0.17% |
| $50 | 150/sec | 150.0 | 0.19% |
| $200 | 150/sec | 150.1 | 0.15% |
| $500 | 150/sec | 145.2 | 2.99% |

NEAR charges for computational work, not for value moved, so a $500 transfer costs
what a $10 transfer costs. **$10 collapses at 200/sec exactly as $200 does.** The
ceiling is architectural.

$500 is slightly worse at 150/sec (145.2, p95 49.23s) but still clears the bar.
With five runs and this spread it is not distinguishable from the others.

---

## 4. Cost per transaction: the cheapest of the three

**Mean gas per NEP-141 transfer: 2.214 × 10¹²**, measured over **2,423,969**
confirmed payments. Gas is architecture-determined — the same opcodes cost the
same on our chain and on mainnet — so this is the real quantity, priced with real
external rates.

At mainnet gas price 1×10⁸ yocto/gas and NEAR at $1.65 (both dated, see
`docs/mainnet_pricing.json`):

**$0.000365 per payment.**

| Architecture | Cost per $200 remittance | Basis |
|---|---|---|
| **NEAR** | **$0.000365** | measured gas, mainnet price |
| Polygon Edge | $0.0006 | measured gas, mainnet price |
| Lightning | $0.0523 | measured route length, 1ML fee rates |

NEAR is the cheapest measured, ~1.6× below Polygon and ~143× below Lightning.
**All three are far under the $0.10 selection threshold of `ANALYSIS_PLAN.md`
§10** — settlement cost does not discriminate between the two on-chain
architectures. That is itself a finding: **cost is not the deciding axis;
throughput and failure behaviour are.**

---

## 5. Node failures: NEAR is far more fragile than Polygon

Three load levels × $200 × 5 repeats, one validator offline at a time, 15–45s
down, 20–60s between — **the identical fault schedule Polygon received**.

| Offered | Baseline | With node failures | Capacity lost |
|---|---|---|---|
| 100/sec | 100.0/sec, 0.16% fail | 68.4/sec [39.1, 95.3], 31.7% fail | **32%** |
| 150/sec | 150.1/sec, 0.15% fail | 35.4/sec [3.8, 69.3], 76.4% fail | **76%** |
| 200/sec | 47.5/sec, 76.3% fail | 0.1/sec [0.0, 0.3], 99.9% fail | **100%** |

At its own knee, **NEAR loses three quarters of its capacity** to intermittent
loss of a single validator. Polygon at its knee lost 26%.

**The intervals are very wide** — [3.8, 69.3] at 150/sec — because outage timing
is random and a single run could land anywhere in that range. Report the range,
never the mean alone.

### The structural reason, which must travel with the number

8 validators over 4 shards is **exactly 2 per shard, the protocol minimum**. One
validator offline does not remove an eighth of the network; it **halves the
affected shard's producers**, and NEAR needs chunks from every shard to finalise
anything. Polygon kept 3 of 4 validators.

This is a **quota artefact of our cluster, not a property of sharding**. It must
be stated wherever the comparison appears. Full asymmetry analysis:
`docs/near_methodology/adversarial_arm.md`.

### Calibration against real NEAR

| | Our arm | NEAR mainnet | Ratio |
|---|---|---|---|
| Validators removed | 1 of 8 = 12.5% | 1 of 422 = 0.24% | ~53× more hostile |
| Affected shard's producers removed | 1 of 2 = 50% | 1 of 10 = 10% | ~5× more hostile |
| Time offline | ~43% | ~0.1% target | ~430× more downtime |

**This measures sensitivity to validator loss, not mainnet behaviour.**

---

## 6. Exploratory: damage does *not* scale with how often validators drop

Designed **after** seeing §5, therefore exploratory (`ANALYSIS_PLAN.md` §4) and
recorded under a separate arm label so it can never pool with the pre-registered
15. Same 150/sec, same amount, same everything — only outage *frequency* changed.

| | Downtime | n | Achieved | 95% CI | Failures |
|---|---|---|---|---|---|
| No outages | 0% | 5 | 150.1/sec | [149.6, 150.6] | 0.1% |
| Pre-registered arm | 43% | 5 | 35.4/sec | [3.8, 69.3] | 76.4% |
| Exploratory | **4%** | 5 | **47.9/sec** | [0.6, 107.0] | 68.0% |

**Cutting downtime more than tenfold did not produce a distinguishable
improvement.** The intervals overlap almost completely. Two readings, and the
honest one is the weaker:

1. **What can be said:** this experiment could not detect a benefit from reducing
   outage frequency by 10×. With n=5 and intervals this wide it had little power
   to detect one.
2. **What cannot be said:** that damage is provably independent of downtime. The
   data is consistent with that, and also with a real but modest effect.

**The consequence for calibration is the useful part.** The intended argument —
measure two downtime levels, establish a scaling relationship, extrapolate toward
mainnet's 0.1% — **does not survive**. There is no measured relationship to
extrapolate along. Any claim about NEAR's real-world behaviour under validator
failure must rest on the §5 hostility ratios as *bounds*, stated as bounds.

**A plausible mechanism, offered as hypothesis only:** the chain did not recover
between runs. Minutes after all outages ceased, validators were still ~120 blocks
behind the tip. If damage is cumulative rather than rate-dependent, brief rare
interruptions would reach the same degraded state as frequent long ones. **Not
established** — it would need a designed experiment with recovery intervals.

**Limitation:** this block ran ~2 minutes after the pre-registered arm, on a chain
recovering from it. Its first run was clean (149.3/sec), so recovery had occurred,
but it is not a fully independent test.

---

## 7. Calibration against mainnet

**Demand ratio = 31.3×.** We sustain 31× what NEAR mainnet currently carries
(4.8 tx/sec, measured 12 Aug 2026). This is about **workload realism** — our test
loads far exceed real NEAR activity — not capability.

**Capability gap: NOT REPORTED, deliberately.** It would be our throughput divided
by mainnet capacity, and capacity has to be derived from block utilisation. NEAR
mainnet's blocks were **0.04% full**, so the derivation multiplies an 8-block
sample by ~2,500× to reach "12,000 tx/sec". That amplifies sampling error by the
same factor and describes how idle NEAR is rather than what it can do.
`analysis/calibration.py` refuses to print it below 5% utilisation.

**Polygon is unaffected** (28.5% full, multiplier ~3.5): demand ratio 2.52×,
capability gap 0.719×.

---

## 8. Scaling 4 shards to mainnet's 10

Per-shard throughput from the **highest sustained** load — 150/sec ÷ 4 shards =
**37.2/sec per shard** — corrected for the changing cross-shard mix via
`c(S) = (1/S)·c_same + ((S−1)/S)·c_cross`.

| Shards | Projected total/sec |
|---|---|
| 4 (ours) | 148.8 ← reproduces the measurement |
| 6 | 223.2 |
| 8 | 297.6 |
| **10 (mainnet)** | **372.0** |

The gas correction from 4 to 10 shards is **1.0001×** — cross-shard transfers cost
essentially the same as same-shard ones on NEAR, so the projection is very close to
linear in shard count.

**Assumptions, both stated because neither can be verified from our data:** that
shards execute independently (Nightshade's design intent), and that cross-shard
cost does not itself grow with shard count.

**This projection was wrong in an earlier version** and is worth knowing about: it
based per-shard throughput on the *collapsed* rate at 200/sec, projecting 130/sec
for 10 shards — slower than our own 4-shard measurement. Throughput past the knee
measures a failing system, not capacity.

---

## 9. What this arm supports, and what it does not

**Supported:**
- NEAR sustains 150 payments/sec at $200 on 4 shards under the full realism stack.
- The ceiling is NEAR's, not the instrument's — the harness was independently
  validated to 300/sec against a null backend at equivalent in-flight load, p95
  scheduling lag 1.2 ms (`docs/near_methodology/generator_is_not_the_ceiling.md`).
- Past its knee NEAR collapses rather than degrades, unlike Polygon.
- Cost per payment $0.000365, the lowest of the three architectures.
- Sensitivity to validator loss at 2 producers per shard: 76% of capacity lost at
  the knee.

**Not supported:**
- Any prediction of NEAR mainnet throughput. §8 is a projection with stated
  assumptions, not a measurement.
- Any prediction of mainnet behaviour under validator failure. See §5 and §6.
- A capability gap against mainnet capacity. See §7.
- Sharding as a general architecture — this is **one implementation, at 4 of its
  10 mainnet shards, with the minimum validators per shard.**
