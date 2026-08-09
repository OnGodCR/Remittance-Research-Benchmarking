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

**Protocol:** 300-second windows, 5 repeats per configuration, Poisson arrival, concurrent submission, first 10 seconds discarded, 60-second failure threshold, settlement = inclusion in a committed block (N=1, since IBFT gives deterministic finality). 140 measured runs: 4 amounts × 7 load levels × 5 repeats, with no cell over- or under-filled.

---

## 2. Headline result — clean conditions, $200

| Offered/sec | Achieved | Range | Failures | p50 | p95 | p99 |
|---|---|---|---|---|---|---|
| 10 | 9.9 | 9.7–10.2 | 0.00% | 3.19s | 4.16s | 4.40s |
| 25 | 25.0 | 24.9–25.1 | 0.00% | 3.19s | 4.17s | 4.39s |
| 50 | 50.0 | 49.5–50.4 | 0.00% | 3.20s | 4.22s | 4.46s |
| 100 | 100.1 | 99.2–101.4 | 0.00% | 3.23s | 4.25s | 4.52s |
| 150 | 150.3 | 149.5–151.0 | 0.00% | 3.31s | 4.38s | 4.70s |
| **200** | **200.9** | 198.7–202.5 | **0.00%** | 3.43s | 4.77s | 6.35s |
| 300 | 270.5 | 260.6–277.0 | 9.97% | 10.61s | 24.26s | 30.49s |

### **Sustainable throughput at $200 = 200 payments/second**

The pre-registered primary metric: the highest load step where achieved throughput reaches ≥90% of offered load **and** failures stay under 5%. At 300/sec both conditions fail — 90.2% delivered, 9.97% failures.

### The knee sits between 200 and 300/sec

Settlement is essentially flat from 10 through 200 — 3.19s to 3.43s at the median, a 7% rise across a twentyfold increase in load. Then at 300 it **triples**, and failures appear for the first time.

This is not gradual degradation. The system is comfortable until it isn't, and the transition happens within one step of the ramp.

### What a "failure" actually is here — read before quoting the failure rate

Every failure in this dataset is the **same** failure, and it is not the one the word usually implies.

All 457,197 of them were **rejected at submission** with `txpool is full` (98.2%) or `rejected future tx due to low slots` (1.8%). The transaction never entered the chain. Not one of them has a transaction hash, and not one consumed gas.

Two things follow, and both matter:

- **No transaction the chain accepted ever failed to settle.** Settlement reliability was 100% at every load level, including the overloaded one. The 60-second timeout threshold never fired once, in any run, in the entire study — the slowest settled payment took 57.0s at the 99.9th percentile, and that only at 300/sec.
- **The "9.97% failure rate" at 300/sec is an overflow rate**, not a settlement failure rate. The chain committed roughly 270/sec and refused the surplus at the door rather than accepting work it could not do.

**For remittances this distinction is the whole point.** A rejected submission returns an error to the sender immediately and can be retried. A payment accepted and then lost is a reconciliation problem — money that has left one side and not arrived at the other. Polygon under overload does the first and never the second. That is a genuine architectural strength, and reporting it as "10% of payments failed" would conceal it.

⚠️ **Limitation this creates.** The queue is Polygon Edge's default size; we did not tune it. A larger queue would absorb more backlog and push the rejections later, converting them into longer waits and eventually real timeouts. **The 270/sec committed-throughput ceiling is a property of the architecture; the precise 9.97% is a property of the architecture at its default queue setting.** The ceiling is the finding. The rejection percentage should always be reported with the queue caveat attached.

### Against the architecture-selection thresholds

At 200/sec Polygon clears both pre-registered bars: p95 of **4.77s** against a 10-second ceiling, and cost far under $0.10 (§4). At 300/sec it fails both — p95 of 24.26s, and 9.97% failures against a 5% bar.

---

## 3. Transaction size does not affect performance

Pre-registered prediction (§12 of the analysis plan): amount cannot affect Polygon, because the network charges for computational work performed and moving a larger number is not more work.

**Confirmed, and more precisely than the prediction required.** At 200/sec all four amounts are indistinguishable:

| Amount | Achieved | Failures | Mean gas |
|---|---|---|---|
| $10 | 199.9 | 0.00% | 28,213 |
| $50 | 200.0 | 0.00% | 28,228 |
| $200 | 200.9 | 0.00% | 28,205 |
| $500 | 200.2 | 0.00% | 28,205 |

The mean gas figures differ slightly, but **not because of the amount**. Gas falls into three tiers set by how many storage slots are already warm (§4), and the tier mix varies with which accounts a run happens to touch. Comparing like with like — within the warm tier only — isolates the amount:

| Amount | Mean gas, warm tier |
|---|---|
| $10 | 27,464.6 |
| $50 | 27,476.6 |
| $200 | 27,464.6 |
| $500 | 27,464.6 |

**A spread of 12 gas, or 0.044%.** That residue is not the value either: it is the cost of the zero bytes in the encoded amount, since the EVM charges 4 gas for a zero byte and 16 for a non-zero one. A fiftyfold increase in transferred value changes the cost of settling it by four thousandths of one percent.

At 300/sec, where the system is stressed, failure rates show no monotonic relationship with amount either: $10 9.79%, $50 8.51%, $200 9.97%, $500 12.85%.

**This flat result is the baseline for the Lightning comparison.** Lightning is expected to show the opposite — an inverse relationship between payment size and success, because larger payments need every hop along a route to hold sufficient liquidity. Polygon's flatness is what makes that contrast meaningful.

---

## 4. Cost per transaction

**Method** (`ANALYSIS_PLAN.md` §6.3): fees on a private chain are an artifact of our own configuration and would be circular to report. Instead we measure **gas consumed** — deterministic, architecture-determined, identical on mainnet — and price it using real mainnet rates pulled on one stated date.

**Measured gas per stablecoin transfer: 28,538 (mean), 27,465 (median).**

The distribution has clear tiers reflecting EVM storage-access costs:

| Gas tier | Share | Cause |
|---|---|---|
| ~27,465 | 80.1% | Sender and recipient balance slots both already warm |
| ~31,665 | 14.4% | One cold storage access (EIP-2929) |
| ~35,865 | 5.6% | Both accesses cold |

Within each tier values vary by ±12 gas with the number of zero bytes in the encoded amount. Tiers account for 100% of settled transactions.

**Pricing** — PolygonScan, 9 Aug 2026 19:42 UTC (`data/reference/calibration_2026-08-09.md`):
- Gas price (Standard): 270.927 Gwei
- POL: $0.0774

```
28,538 gas × 270.927 × 10⁻⁹ POL × $0.0774  =  $0.000598
```

### **Cost per remittance: $0.0006**

Clears the pre-registered $0.10 threshold by **167×**. Against the UN SDG 10.c target of total remittance cost under 3% of value — $6.00 on a $200 transfer — the settlement layer consumes **0.01%** of that budget.

**The implication for the paper:** the blockchain is effectively free. The entire cost of a remittance sits in the fiat conversion at each end, which this study explicitly does not measure. Any Design Science proposal that optimises settlement cost is optimising a rounding error.

> ⚠️ **Correction made 9 Aug 2026.** An earlier figure of $0.00075 was computed from **Phase 1 data**, which is excluded from results by the pre-registered rules. Phase 1 was a small run in which every storage slot was cold, so it showed a uniform 35,865 gas — a value that occurs in only 3.6% of the actual results data. Using it overstated cost by 26%. The figures above come from the results dataset.

> ⚠️ **Pricing caveat.** 270 Gwei is high against Polygon's historical 30-50 Gwei range. A single-day snapshot makes this figure **conservative** — a long-run average would be cheaper. Erring high is the safer direction, but the limitation should be stated.

---

## 5. Adversarial arm — behaviour under node failure

Identical conditions plus validators dropping offline throughout. 3 load levels × $200 × 5 repeats. 119 outage events recorded and joined to the payment data.

| Offered/sec | Clean | With node failures | Range | Throughput lost |
|---|---|---|---|---|
| 100 | 100.1/s, 0.00% fail | 99.4/s, 0.76% fail | 98.8–100.0 | **0.8%** |
| 200 | 200.9/s, 0.00% fail | 148.4/s, 26.13% fail | 122.3–173.0 | **26.1%** |
| 300 | 270.5/s, 9.97% fail | 156.2/s, 48.03% fail | 93.2–203.0 | **42.2%** |

Settlement latency degrades in step: p95 rises from 4.25s to **17.51s** at 100/sec, and from 4.77s to **43.62s** at 200/sec.

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

**22 duplicate runs counted as repeats.** Found 9 Aug during a full audit. Spot preemption interrupted the sweep twice, and on resume it restarted from the beginning of the load ladder rather than from the point of interruption — so 22 configurations were measured a second time, 3.9 to 8.1 hours later. Four cells held 10 runs instead of 5.

These were never independent repeats: each re-execution reused the **same arrival seed**, replaying an identical schedule. At load levels with no failures the pairs are transaction-for-transaction identical. Left in place they would have doubled those cells' weight and, more seriously, inflated the sample size for the confidence intervals still to be computed — narrower intervals resting on no additional evidence.

Now excluded by a rule applied uniformly (`ANALYSIS_PLAN.md` §13): the first completed execution of a configuration stands. The matrix is exactly 140 runs, every cell holding exactly 5. **Effect on results: negligible.** The $200 curve moved 200.8 → 200.9/sec at one load step; the knee, the ceiling, the cost and the adversarial findings are unchanged. The failure spread across amounts at 300/sec widened from 2.9 to 4.3 percentage points and remains non-monotonic, so the size-independence conclusion holds.

**100% failure rate from a client defect.** Every payment timed out in one early run because our client rejected the chain's block headers as malformed. It was our software, not the architecture — a plausible-sounding result that would have been entirely wrong. Run excluded and flagged.

---

## 8. What is excluded, and why

**211 runs collected, 155 form the results** — 140 in the main matrix plus 15 in the adversarial arm. 56 runs were excluded, each logged in `data/clean/exclusions.log` with its triggering rule.

| Excluded | Runs | Rule |
|---|---|---|
| Non-result phases | 34 | Pipeline validation, capacity checks, exploratory pilots — excluded wholesale by the pre-registered rules, and never contributing to any figure here |
| Re-executions | 22 | Duplicate measurements of configurations already completed (§7) |
| **Total** | **56** | |

Also excluded, per transaction rather than per run: **250,204 payments** falling in the first 10 seconds of a run, the pre-registered warm-up discard.

**A point worth making in the Methodology.** Nine runs were independently flagged — eight for generator saturation (scheduling lag growing from 285ms to 45,664ms mid-run, meaning the load actually offered had drifted from the load intended) and one for the proof-of-authority client defect. **All nine fall inside the 34 non-result phases and were already excluded on that ground.** Applying the study's saturation criterion to the results phases removed nothing: no measured run in the 140-run matrix or the 15-run adversarial arm ever drifted from its intended load. The criterion was tested against the results and the results passed.

**Nothing was deleted.** Every excluded run remains in `data/raw/all_runs_raw.parquet`, flagged, so raw and clean can be compared.

---

## 9. Outstanding for this architecture

- **Confidence intervals.** Results above are means with observed ranges. The pre-registered protocol calls for bootstrap 95% intervals — needed most for the adversarial arm, given the 2× spread at 300/sec.
- **Calibration ratios** (`ANALYSIS_PLAN.md` §11). Requires Polygon's observed mainnet *peak* throughput, still to pull. The ~87/sec average is already recorded.
- **Queue-depth sensitivity.** Every failure recorded was a submission rejection at Polygon Edge's default queue size (§2). A short sweep at a larger queue would establish how much of the 9.97% is architectural and how much is that default — currently stated as a limitation rather than measured.
- **Block utilisation curve.** Cost as a function of load, mapping our measured utilisation onto mainnet's historical price-vs-congestion relationship — the "stronger version" of the cost methodology.
