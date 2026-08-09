# Polygon Edge — Complete Analysis

**Architecture:** Sidechain
**Software:** Polygon Edge v1.3.2 (final release, 24 Jan 2024), IBFT proof-of-authority
**Status:** Measurement complete. 140/140 clean configurations + 15/15 adversarial runs.
**Data:** 7,921,652 payments across 211 runs, 123 node-outage events
**Written:** 9 August 2026

> Every figure here comes from `data/clean/all_runs_clean.parquet`. Methodology and parameters are in `METHODOLOGY_LOG.md`; the locked analysis rules are in `ANALYSIS_PLAN.md`.

---

## 1. Test conditions

Four validators, one per real remittance corridor:

| Validator | Region | Corridor role |
|---|---|---|
| 0 | `us-east4` (Virginia) | US — largest sending country |
| 1 | `asia-south1` (Mumbai) | India — largest receiving country |
| 2 | `asia-southeast1` (Singapore) | SE Asia / Philippines |
| 3 | `europe-west2` (London) | UK — major sender to South Asia |

All at `n2-standard-8` (8 vCPU / 32 GB), matching Polygon's published validator specification. Storage deliberately not matched — published figures quote ~1.2 TB purely to hold years of mainnet history a fresh chain does not have.

**Realism applied:** genuine intercontinental distance; injected per-corridor latency, jitter and packet loss on consensus traffic only; competing background traffic at ~88 tx/sec calibrated to real Polygon mainnet activity; production-spec hardware.

**Protocol:** 300-second windows, 5 repeats per configuration, Poisson arrival, concurrent submission, first 10 seconds discarded, 60-second failure threshold, settlement = inclusion in a committed block (N=1, since IBFT gives deterministic finality).

---

## 2. Headline result — clean conditions, $200

| Offered/sec | Achieved | Range | Failures | p50 | p95 | p99 |
|---|---|---|---|---|---|---|
| 10 | 9.9 | 9.7–10.2 | 0.00% | 3.19s | 4.16s | 4.40s |
| 25 | 25.0 | 24.9–25.1 | 0.00% | 3.19s | 4.17s | 4.39s |
| 50 | 50.0 | 49.5–50.4 | 0.00% | 3.20s | 4.22s | 4.46s |
| 100 | 100.1 | 99.2–101.4 | 0.00% | 3.23s | 4.25s | 4.52s |
| 150 | 150.3 | 149.5–151.0 | 0.00% | 3.31s | 4.38s | 4.70s |
| **200** | **200.8** | 198.7–202.5 | **0.00%** | 3.43s | 4.76s | 6.48s |
| 300 | 270.5 | 260.6–277.0 | 9.97% | 10.61s | 24.26s | 30.49s |

### **Sustainable throughput at $200 = 200 payments/second**

The pre-registered primary metric: the highest load step where achieved throughput reaches ≥90% of offered load **and** failures stay under 5%. At 300/sec both conditions fail — 90.2% delivered, 9.97% failures.

### The knee sits between 200 and 300/sec

Settlement is essentially flat from 10 through 200 — 3.19s to 3.43s at the median, a 7% rise across a twentyfold increase in load. Then at 300 it **triples**, and failures appear for the first time.

This is not gradual degradation. The system is comfortable until it isn't, and the transition happens within one step of the ramp.

### Against the architecture-selection thresholds

At 200/sec Polygon clears both pre-registered bars: p95 of **4.76s** against a 10-second ceiling, and cost far under $0.10 (§4). At 300/sec it fails both — p95 of 24.26s, and 9.97% failures against a 5% bar.

---

## 3. Transaction size does not affect performance

Pre-registered prediction (§12 of the analysis plan): amount cannot affect Polygon, because the network charges for computational work performed and moving a larger number is not more work.

**Confirmed.** At 200/sec, all four amounts are indistinguishable:

| Amount | Achieved | Failures | Gas consumed |
|---|---|---|---|
| $10 | 199.9 | 0.00% | 28,204 |
| $50 | 200.0 | 0.00% | 28,228 |
| $200 | 200.8 | 0.00% | 28,204 |
| $500 | 200.2 | 0.00% | 28,205 |

At 300/sec, where the system is stressed, failure rates show no monotonic relationship with amount either: $10 10.86%, $50 10.83%, $200 9.97%, $500 12.85%.

**This flat result is the baseline for the Lightning comparison.** Lightning is expected to show the opposite — an inverse relationship between payment size and success, because larger payments need every hop along a route to hold sufficient liquidity. Polygon's flatness is what makes that contrast meaningful.

---

## 4. Cost per transaction

**Method** (`ANALYSIS_PLAN.md` §6.3): fees on a private chain are an artifact of our own configuration and would be circular to report. Instead we measure **gas consumed** — deterministic, architecture-determined, identical on mainnet — and price it using real mainnet rates pulled on one stated date.

**Measured gas per stablecoin transfer: 28,467 (mean), 27,465 (median).**

The distribution has clear tiers reflecting EVM storage-access costs:

| Gas | Share | Cause |
|---|---|---|
| 27,465 | 55.3% | Sender and recipient balance slots both warm |
| 27,477 | 24.0% | As above, trivial variation |
| 31,665 | 9.8% | One cold slot access |
| 35,865 | 3.6% | Fully cold access |

**Pricing** — PolygonScan, 9 Aug 2026 19:42 UTC (`data/reference/calibration_2026-08-09.md`):
- Gas price (Standard): 270.927 Gwei
- POL: $0.0774

```
28,467 gas × 270.927 × 10⁻⁹ POL × $0.0774  =  $0.000597
```

### **Cost per remittance: $0.0006**

Clears the pre-registered $0.10 threshold by **168×**. Against the UN SDG 10.c target of total remittance cost under 3% of value — $6.00 on a $200 transfer — the settlement layer consumes **0.01%** of that budget.

**The implication for the paper:** the blockchain is effectively free. The entire cost of a remittance sits in the fiat conversion at each end, which this study explicitly does not measure. Any Design Science proposal that optimises settlement cost is optimising a rounding error.

> ⚠️ **Correction made 9 Aug 2026.** An earlier figure of $0.00075 was computed from **Phase 1 data**, which is excluded from results by the pre-registered rules. Phase 1 was a small run in which every storage slot was cold, so it showed a uniform 35,865 gas — a value that occurs in only 3.6% of the actual results data. Using it overstated cost by 26%. The figures above come from the results dataset.

> ⚠️ **Pricing caveat.** 270 Gwei is high against Polygon's historical 30-50 Gwei range. A single-day snapshot makes this figure **conservative** — a long-run average would be cheaper. Erring high is the safer direction, but the limitation should be stated.

---

## 5. Adversarial arm — behaviour under node failure

Identical conditions plus validators dropping offline throughout. 3 load levels × $200 × 5 repeats. 123 outage events recorded and joined to the payment data.

| Offered/sec | Clean | With node failures | Range | Throughput lost |
|---|---|---|---|---|
| 100 | 100.1/s, 0.00% fail | 99.4/s, 0.76% fail | 98.8–100.0 | **0.8%** |
| 200 | 200.8/s, 0.00% fail | 148.4/s, 26.11% fail | 122.3–173.0 | **26.1%** |
| 300 | 270.5/s, 9.97% fail | 156.2/s, 48.03% fail | 93.2–203.0 | **42.2%** |

Settlement latency degrades in step: p95 rises from 4.25s to **17.51s** at 100/sec, and from 4.76s to **43.62s** at 200/sec.

### The finding: damage scales with existing load

- **Under 1%** loss with ample headroom
- **26%** at the sustainable ceiling
- **42%** past it, with nearly half of all payments failing

**Polygon does not degrade gracefully under node loss.** It absorbs a missing validator almost for free while slack exists, then collapses once it does not. Three of four validators are enough to keep reaching agreement, so with headroom the network simply carries on — but with none, the reduced consensus capacity meets an already-saturated queue.

### Why this matters for remittances

Peak demand and infrastructure strain arrive **together**. Payday clustering and holiday surges are exactly when systems are most loaded and most likely to have something fail. This curve says that combination is the worst case.

**Design rule for the architecture proposal: size for node failure, not clean-condition throughput.** A system provisioned on the clean 200/sec figure would lose a quarter of its payments the first time a validator rebooted during a busy period.

### The variance is itself a finding

At 300/sec, identical configurations produced **93.2 to 203.0** payments/sec — better than a 2× range. Outage timing is random: a run where a validator drops during a lull survives far better than one where it drops mid-surge.

A single run could have reported either extreme. **This is the clearest justification in the study for the five-repeat protocol**, and the reason this arm in particular must be reported as ranges rather than means.

### ⚠️ Realism limitation — state this before a reviewer does

**The failure injection is roughly 130× more hostile than real Polygon mainnet.**

| | This study | Real Polygon PoS |
|---|---|---|
| Validators | 4 | ~100 |
| One validator down removes | **25%** of the network | ~1% |
| Availability | offline **51%** of the time | 99.9%+ uptime target |
| Average capacity missing | ~13% | ~0.1% |
| Penalty for downtime | none | jailing, stake slashing |

Two structural causes, neither avoidable at this cluster size. With four validators the smallest possible failure unit is 25% of the network — already above the 10-20% the technique specifies. And real validators are professionally operated on redundant infrastructure with financial penalties for downtime; ours fail every few seconds with no consequence.

**What the arm therefore measures:** *sensitivity to validator loss*, not expected mainnet behaviour. No result here should be phrased as a prediction of how Polygon behaves in production.

Defensible phrasing: *"Under sustained validator unavailability far exceeding realistic mainnet conditions, Polygon Edge degrades negligibly where load headroom exists and severely where it does not."*

---

## 6. Putting the numbers in context

**Global remittance demand** is roughly 140-150 payments/second ($905B/year ÷ $200 average). Peak conditions — holiday season, payday clustering — are estimated at 200-300/sec.

So Polygon Edge:
- **Comfortably clears steady-state global demand** at under 5 seconds settlement and effectively zero cost
- **Sits exactly at the bottom of the peak range**, breaking in the middle of it
- **Loses a quarter of that capacity** once validators become unreliable

*Sufficient for steady state, marginal at peak, fragile under infrastructure failure* is a more useful characterisation than any single throughput number, and it points directly at what the architecture proposal must address.

---

## 7. Corrections and superseded findings

Recorded so the progression is visible rather than hidden.

**A throughput knee that did not exist.** An early report placed a knee at 100-150/sec. It was our own measurement tool falling behind, inflating settlement times 5.5×. Retracted 8 Aug. Led to replacing the saturation criterion.

**"Polygon sustains 300/sec with zero failures."** From a pilot using 60-second windows on a chain without background traffic. The full protocol contradicts it — 270.5/sec with 9.97% failures. Short windows measured the burst, not the steady state. This is a concrete argument for the 300-second window.

**Cost overstated by 26%.** Computed from Phase 1, an excluded phase where all storage slots were cold. Corrected in §4.

**100% failure rate from a client defect.** Every payment timed out in one early run because our client rejected the chain's block headers as malformed. It was our software, not the architecture — a plausible-sounding result that would have been entirely wrong. Run excluded and flagged.

---

## 8. What is excluded, and why

9 of 211 runs excluded — every exclusion logged in `data/clean/exclusions.log` with its triggering rule.

- **8 runs — generator saturation.** Scheduling lag grew 285ms to 45,664ms during the run, meaning the load actually offered had drifted from the load intended. Judged by the study's single criterion (lag *growth* > 50ms), applied uniformly to all 211 runs.
- **1 run — client defect.** The proof-of-authority header bug above.

Non-result phases (pipeline validation, capacity checks, exploratory pilots) are excluded wholesale by the pre-registered rules and never contributed to any figure here.

**Nothing was deleted.** Every excluded run remains in `data/raw/all_runs_raw.parquet`, flagged, so raw and clean can be compared.

---

## 9. Outstanding for this architecture

- **Confidence intervals.** Results above are means with observed ranges. The pre-registered protocol calls for bootstrap 95% intervals — needed most for the adversarial arm, given the 2× spread at 300/sec.
- **Calibration ratios** (`ANALYSIS_PLAN.md` §11). Requires Polygon's observed mainnet *peak* throughput, still to pull. The ~87/sec average is already recorded.
- **Block utilisation curve.** Cost as a function of load, mapping our measured utilisation onto mainnet's historical price-vs-congestion relationship — the "stronger version" of the cost methodology.
