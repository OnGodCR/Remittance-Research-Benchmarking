# Cross-Architecture Comparison — the measured evidence

**Built 13 August 2026 from `data/clean/all_runs_clean.parquet`.**

> ## What this document is, and what it is not
>
> **This is the evidence table, not the argument.** Phase 6 — interpreting these
> numbers and selecting a recommended architecture — is the paper's central
> contribution and is Angad's work. This file assembles what was measured, states
> what each number rests on, and flags where the three columns are **not the same
> kind of evidence**. It deliberately stops short of a recommendation.
>
> Every figure is reproducible: `analysis/results.py`, `analysis/calibration.py`,
> `analysis/shard_scaling.py`.

---

## ⚠️ Read this before using any table below

**The three architectures are not measured to the same standard, and no table can
hide that.**

| | Polygon Edge | NEAR | Lightning |
|---|---|---|---|
| Throughput & reliability | **measured by us** | **measured by us** | **published literature** (Waugh & Holz 2020) |
| Full 7-step ladder × 4 amounts × 5 repeats | ✅ 140/140 | ⚠️ 118 measured, 22 unmeasurable | ❌ never run |
| Cost per transaction | measured gas | measured gas | measured route length |
| Asset moved | ERC-20 stablecoin | NEP-141 stablecoin | **native BTC** |
| Adversarial arm | ✅ 15 runs | ✅ 15 runs | ❌ none |

**Why Lightning differs:** our testbed had 51 channels against the real network's
19,644 — ~385× fewer. Lightning's capacity is *additive across channels*, so a
385×-smaller network does not behave like the real one at any scale of effort.
Reliability and throughput were therefore sourced from published measurement of
the real network. See `LIGHTNING_ANALYSIS.md`.

**A Lightning remittance also carries exchange-rate exposure the other two do
not** — there is no stablecoin in the base Lightning protocol. That is an
architectural difference, not a testing artefact.

---

## 1. Throughput ladder at $200 — achieved/sec (failure %)

| Offered | Polygon Edge | NEAR |
|---|---|---|
| 10/sec | 9.9 (0.0%) | 9.8 (1.4%) |
| 25/sec | 25.0 (0.0%) | 24.8 (0.9%) |
| 50/sec | 50.0 (0.0%) | 49.8 (0.4%) |
| 100/sec | 100.1 (0.0%) | 100.0 (0.2%) |
| 150/sec | 150.3 (0.0%) | **150.1 (0.1%)** ← NEAR's ceiling |
| 200/sec | **200.9 (0.0%)** ← Polygon's ceiling | 47.5 (76.3%) |
| 300/sec | 270.5 (10.0%) | not measurable |

**Sustainable throughput at $200** (achieved ≥90% of offered AND failures <5%):

- **Polygon Edge: 200/sec**
- **NEAR: 150/sec**
- **Lightning: not measured by us** — Waugh & Holz report payment success falling
  from 71.9% at $0.01 to 17.3% at $100, with reliability rather than throughput as
  the binding constraint.

---

## 2. The failure mode differs, and it may matter more than the ceiling

| | Past the knee | Behaviour |
|---|---|---|
| **Polygon** | 300 offered → 270.5 achieved, 10.0% fail | **degrades gracefully** |
| **NEAR** | 200 offered → 47.5 achieved, 76.3% fail | **collapses** |

NEAR at 200/sec achieves *less than it does at 50/sec*. Offering more produces
less.

**Context for why this is a remittance question, not a benchmark curiosity:**
global remittance volume averages ~140–150/sec (≈$905B/year ÷ $200). Peak
conditions — payday and holiday clustering — push above that. Both architectures
clear the average. **Polygon clears it with headroom; NEAR sits at the boundary,
and past that boundary it does not slow down, it stops.**

---

## 3. Settlement latency at $200 (baseline, up to each architecture's ceiling)

| | p50 | p95 | p99 | fastest observed |
|---|---|---|---|---|
| Polygon Edge | 3.26s | 4.29s | 4.60s | 1.41s |
| NEAR | 11.81s | 16.09s | 21.59s | **8.49s** ($200) / 7.90s (any amount) |
| Lightning | ~1.5s (small-scale, illustrative) | — | — | — |

**NEAR's 8.49s floor is structural**, not a defect: transaction inclusion, then a
cross-shard receipt to the token contract's shard, then finality — each costing
blocks. 74.3% of our payments crossed shards.

**Polygon is far inside the pre-registered p95 < 10s threshold at every load it
sustains. NEAR is outside it at EVERY load, including the lightest** — 12.76s at
10/sec, never below 12.3s anywhere. See §7b: this is what the pre-registered
decision rule turns on.

---

## 4. Cost per $200 remittance

| | Cost | Scales with amount? | Basis |
|---|---|---|---|
| **NEAR** | **$0.000365** | no | 2.214×10¹² gas, mainnet price, 2.4M payments |
| Polygon Edge | $0.0006 | no | measured gas, mainnet price |
| Lightning | $0.0523 | **yes — 165 ppm** | measured route length, 1ML fee rates |

**All three are far below the $0.10 selection threshold.** Cost does not
discriminate between the two on-chain architectures — they differ by a factor of
1.6 on a quantity that is a rounding error against any remittance fee.

**The crossover finding stands:** Polygon and NEAR charge for computational work,
so cost is flat with amount. Lightning charges a percentage, so at **$500 its
routing fee alone ($0.1467) breaches the $0.10 threshold**. Caveat: $200 and $500
Lightning figures rest on 3 and 2 runs respectively, and $50 was never run.

---

## 5. Behaviour under node failure

| | Baseline at knee | With node failures | Capacity lost |
|---|---|---|---|
| Polygon (200/sec) | 200.9/sec, 0.0% | 148.4/sec [122, 173], 26.1% | **26%** |
| NEAR (150/sec) | 150.1/sec, 0.15% | 35.4/sec [3.8, 69.3], 76.4% | **76%** |

**Do not read this as "sharding is fragile."** The two arms are not equally
severe, and they differ in opposite directions:

| | Polygon | NEAR | Harsher for |
|---|---|---|---|
| Share of network removed | 1 of 4 = 25% | 1 of 8 = 12.5% | **Polygon** |
| Redundancy left in affected shard | 3 of 4 remain | 2 → **1** producer (protocol minimum) | **NEAR** |
| Recovery cost | rejoins on restart | **expelled ~4 hours** | **NEAR** |

Rows 1 and 2 pull opposite ways, both consequences of the same 96-vCPU quota that
forced 8 validators over 4 shards. **Row 3 is the one genuinely about the
architecture** — Polygon's arm structurally cannot produce it.

**Both injections are far more hostile than their real networks** (~130× for
Polygon, ~53×/5×/430× for NEAR on three separate axes). These measure *sensitivity
to validator loss*, not mainnet behaviour.

---

## 6. Calibration against real networks

| | Demand ratio | Capability gap |
|---|---|---|
| Polygon | 2.52× | 0.719× |
| NEAR | 31.3× | **not derivable** |

**Demand ratio** = our sustainable throughput ÷ what mainnet currently carries. A
statement about workload realism, not capability.

**Capability gap** = ours ÷ mainnet capacity. Polygon's 0.719× means our testbed
sustains 72% of what real Polygon could carry — so our figures are **not** an
overstatement on that axis. **NEAR's is deliberately not reported:** its mainnet
blocks were 0.04% full, so deriving capacity multiplies an 8-block sample by
~2,500×, describing how idle NEAR is rather than what it can do.

---

## 7. Scaling NEAR's 4 shards toward mainnet's 10

| Shards | Projected total/sec |
|---|---|
| 4 (measured) | 148.8 |
| 10 (mainnet) | **372.0** |

**A projection with stated assumptions, not a measurement.** It assumes shards
execute independently and that cross-shard cost does not grow with shard count.
If it holds, NEAR at mainnet shard count would exceed Polygon's measured 200/sec —
**but Polygon has no equivalent projection**, because its throughput is set by
block gas limit and consensus timing rather than validator count, so its 4-validator
measurement already transfers to mainnet.

**Do not put 372 and 200 in the same column as though they were the same kind of
number.**

---

## 7b. What the pre-registered decision rule actually selects

`ANALYSIS_PLAN.md` §10, fixed on **7 August 2026 before any Phase 2+ data existed**,
defines the recommended architecture as the one with the **highest sustainable
throughput at $200**, among those that at that same load also keep **p95 settlement
below 10 seconds** and **cost below $0.10**.

Applying it mechanically:

| | Sustainable at $200 | p95 there | Cost | Verdict |
|---|---|---|---|---|
| **Polygon Edge** | **200/sec** | **4.77s** | $0.000600 | **QUALIFIES** |
| NEAR | 150/sec | **19.20s** | $0.000365 | **disqualified — latency** |
| Lightning | not measured by us | — | $0.0523 | cannot be ranked |

**The rule selects Polygon Edge**, and it does not select it on throughput. It
selects it because **NEAR fails the latency bar** — and not marginally, and not
only at its ceiling:

| Offered | Polygon p95 | NEAR p95 |
|---|---|---|
| 10/sec | 4.16s ✅ | 12.76s ❌ |
| 25/sec | 4.17s ✅ | 12.33s ❌ |
| 50/sec | 4.22s ✅ | 12.43s ❌ |
| 100/sec | 4.25s ✅ | 13.18s ❌ |
| 150/sec | 4.38s ✅ | 19.20s ❌ |
| 200/sec | 4.77s ✅ | 57.85s ❌ |

**NEAR breaches the 10-second bar at every load level tested, including the
lightest.** Its fastest settlement ever recorded is 7.90s; its p95 never drops
below 12.3s. This is structural — inclusion, then a cross-shard receipt, then
finality, each costing blocks — not a symptom of load.

### Why this matters more than a throughput table

Three things make this the strongest single result in the study:

1. **The threshold was fixed before the data existed**, with its reasoning
   recorded (10s is generous against the 2–5s finality both chains target; it
   exists so the paper can claim these rails settle in seconds where SWIFT settles
   in days). It was not chosen to produce this outcome.
2. **It is a disqualification on a dimension NEAR was not expected to lose on.**
   The pre-registered expectation was that sharding would win on throughput. It
   does not lose on throughput — it loses on latency, which the sharded design
   causes directly through cross-shard receipts.
3. **It cannot be rescued by the shard projection.** Even if NEAR at 10 shards
   reaches ~372/sec (§7), shard count does not shorten the finality path. More
   shards would raise throughput while leaving the p95 latency that disqualifies
   it unchanged — arguably making it worse, since a larger share of traffic
   crosses shards.

### The honest caveats on that conclusion

- **§10 explicitly permits a tradeoff answer** rather than a forced winner. NEAR is
  cheaper ($0.000365 vs $0.0006) and would project higher throughput at mainnet
  shard count. A defensible write-up reports Polygon as the rule's selection *and*
  states what NEAR wins on.
- **Polygon Edge is archived software** (read-only since Dec 2024). The rule
  selects it on measured behaviour; the Design Science section has to address
  whether an unmaintained codebase is a defensible recommendation.
- **Lightning cannot be ranked at all**, because its throughput was never measured
  by us. Its exclusion from the ranking is a limitation of the evidence, not a
  finding about Lightning.
- **NEAR ran at 4 of mainnet's 10 shards with the minimum 2 validators per shard.**
  The latency result is the one least sensitive to that (finality path length does
  not shrink with more shards), which is part of why it is the safer conclusion to
  lean on.

---

## 8. What this evidence base cannot answer

- **The fiat on/off-ramp.** Nothing here models currency conversion at either
  end — which prior work suggests may dominate real remittance friction.
- **Interoperability with SWIFT/RTGS.** Design Science only; nothing was built.
- **Adoption.** El Salvador's ~0.7% crypto-remittance share after years of
  government push is a trust and adoption problem, not a throughput one.
- **Sharding in general.** One implementation, at 4 of its 10 mainnet shards, with
  the minimum validators per shard.
- **Polygon Edge's future.** Archived read-only since Dec 2024. Pinned commit,
  stated in Limitations.

---

## 9. Where each number comes from

| Claim | Source |
|---|---|
| Polygon ladder, latency, adversarial | `POLYGON_ANALYSIS.md`, `analysis/results.py --verify-polygon` |
| NEAR ladder, latency, cost, adversarial | `NEAR_ANALYSIS.md`, `analysis/results.py --architecture near` |
| Lightning reliability | Waugh & Holz (2020), arXiv:2006.14358 |
| Lightning cost | `LIGHTNING_ANALYSIS.md` §3 |
| Calibration ratios | `analysis/calibration.py` |
| Shard projection | `analysis/shard_scaling.py` |
| Every exclusion | `data/clean/exclusions.log` |
