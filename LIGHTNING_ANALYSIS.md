# Lightning Network — Complete Analysis

**Architecture:** Off-chain (payment channels)
**Software:** LND v0.18.3-beta on `regtest`, against Bitcoin Core 27.1
**Status:** Data collection closed 10 Aug 2026. Reliability and throughput sourced from published measurement; two figures retained from our own runs as illustrative.
**Written:** 10 August 2026

> Read this alongside `POLYGON_ANALYSIS.md`. The two are deliberately *not* symmetrical, and §1 explains why that is a finding rather than a gap.

---

## 1. The headline: why this arm is different

**Lightning's reliability and throughput data in this paper comes from Waugh & Holz (2020), not from our simulation.** That is a considered methodological decision, logged as amendment 5 in `ANALYSIS_PLAN.md` §13, and the reasoning is itself a result worth reporting.

### The structural problem

Lightning's success behaviour depends on how many routing paths exist between a sender and a receiver. Capacity and reliability are **additive across channels**: the network's ability to move payments is the sum of what its channels can carry, and a payment succeeds only if some path has liquidity pointing the right way at every hop.

| | Real network (1ML, 9 Aug 2026) | Our testbed |
|---|---|---|
| Nodes | 6,010 | 20 |
| Channels | **19,644** | **51** |

**Roughly 385× fewer channels.** A network with 385× fewer paths does not behave like the real one, and no amount of debugging, hardware or budget within this project closes that gap.

### Why Polygon did not have this problem

This is the part worth stating carefully, because the asymmetry looks like inconsistency and is not.

**Polygon is a replicated state machine.** Every validator processes every transaction, so throughput is set by the block gas limit and consensus timing — not by how many validators exist. Four validators and a hundred have the same ceiling; more nodes add latency, not capacity. A 4-validator measurement therefore transfers to mainnet directly.

**Lightning is not.** Its capacity is the sum over channels, so a 51-channel measurement is a 51-channel measurement. It does not scale up by argument.

**The consequence for the paper:** Polygon's throughput number is a property of the protocol. Lightning's is a property of *deployed capital*. Those are not the same kind of quantity, and putting them side by side as though they were would be the same error this paper criticises in the widely-repeated 3,800 TPS vendor claim for Polygon.

---

## 2. What the published measurement says

**Waugh, F. & Holz, R. (2020).** *An empirical study of availability and reliability properties of the Bitcoin Lightning Network.* arXiv:2006.14358. Measured against the real production network.

| Payment size | Payment success rate | Nodes reachable |
|---|---|---|
| $0.01 | 71.9% | 35.2% |
| $1 | 57.8% | 35.2% |
| $5 | 44.1% | 25.7% |
| $10 | 44.2% | 33.7% |
| $50 | 30.9% | 9.2% |
| $100 | **17.3%** | 4.8% |

**Success rate falls sharply as payment size rises** — 71.9% at a cent, 17.3% at $100. That inverse relationship is the central Lightning finding and the one that matters for remittances, where the World Bank benchmark is $200.

### A citation error corrected

An earlier draft of this project's documents described "~35% success for the smallest payments." That conflated two different statistics in the source. **Node reachability** — the fraction of the network reachable at all — is a separate figure, roughly flat at 25–35% across small and medium sizes, and that is where the stray ~35% came from. It is not a size-specific success rate, and describing it as one reverses the direction of the paper's central finding.

Verified directly against the source PDF on 10 Aug 2026. Logged in `ANALYSIS_PLAN.md` §13.

### The scope limit this creates

**Waugh & Holz tested only up to $100.** This project's benchmark sizes are $200 and $500 — above anything they measured. Extending their declining trend to those amounts is a reasonable extrapolation and **must be labelled as an extrapolation**, never as measured data.

---

## 3. Cost per transaction — measured route length, mainnet fee rates

This is the one Lightning metric generated from our own network, and it follows the same discipline as Polygon's gas methodology: **measure the real quantity, price it with real external rates.**

### The trap, and how it was avoided

Our LND nodes ran the stock fee policy — 1,000 msat base per hop plus 1 ppm. At the route lengths we observed, that alone predicts ~2,530 msat, and the measured mean was **2,016 msat**. In other words the "measured" fee was essentially **our own configuration**, exactly the circularity `ANALYSIS_PLAN.md` §6.3 warns about for Polygon's gas price.

What is genuinely architecture-determined is **route length**.

> **Corrected 12 Aug 2026 — recomputed from `all_runs_raw.parquet`.** The earlier
> version of this section printed a route-length distribution **pooled across all
> amounts** (2 hops: 72,910; 3 hops: 118,807; 4 hops: 2,679; n = 194,396) and then
> stated "Mean 2.53 hops" beside it. Those two do not describe the same
> population: the pooled table's own mean is **2.639**, and 2.53 was the
> **$200-only** figure. The pooled table also omitted the 10-second warm-up cut
> that `ANALYSIS_PLAN.md` §7 applies uniformly to all three architectures.
>
> The consequence was not the mismatch itself but what was done with it: **a
> single hop count was applied to every row of the cost table**, when route length
> in fact varies materially with amount.

Per amount, after the warm-up cut, over confirmed payments:

| Amount | Confirmed payments | Runs | Mean route length | Fee-charging hops (N−1) |
|---|---|---|---|---|
| $10 | 173,449 | 46 | 2.651 | **1.651** |
| $50 | *none — never tested* | 0 | — | — |
| $200 | 2,162 | 3 | 2.571 | **1.571** |
| $500 | 3,305 | 2 | 2.772 | **1.772** |

Fees on Lightning are charged by *forwarding* nodes, so a route of N hops has
N−1 chargers.

**Two things this table makes visible that the pooled one hid:**

1. **$50 was never run on Lightning at all.** Only $10, $200 and $500 were. The
   $50 row in the cost table below is therefore a **formula extrapolation**, not a
   measurement, and is labelled as one.
2. **The evidence is very unevenly distributed.** 96% of confirmed Lightning
   payments are $10. The $200 figure rests on **3 runs** and $500 on **2** —
   against the 5-repeat minimum in `ANALYSIS_PLAN.md` §5. These do not meet the
   pre-registered protocol and must not be presented as though they do.

### Pricing

**Source:** 1ML network statistics, pulled 10 Aug 2026 (`data/reference/calibration_2026-08-09.md` §5).

```
median base fee   = 0.449584 sat per hop
median fee rate   = 0.000165 sat/sat  (165 ppm)

per hop = 0.449584 + 0.000165 x amount_sat
fee     = per_hop x (that amount's own fee-charging hops)
```

| Amount | Satoshis | Charging hops | Fee (sat) | **Fee (USD)** | % of value | Superseded |
|---|---|---|---|---|---|---|
| $10 | 15,431 | 1.651 | 4.9 | **$0.0032** | 0.032% | $0.0030 |
| $50 | 77,157 | *1.571 assumed* | 20.7 | **$0.0134** ⚠️ | 0.027% | $0.0131 |
| **$200** | 308,628 | 1.571 | 80.7 | **$0.0523** | 0.026% | $0.0509 |
| $500 | 771,569 | 1.772 | 226.4 | **$0.1467** | 0.029% | $0.1267 |

⚠️ **$50 was never measured on Lightning.** Its row borrows the $200 hop count
because that is the nearest measured amount, and it is an **extrapolation, not a
result**. Label it as such wherever it appears, or drop the row.

**Direction of the correction:** every figure moved **up**, because the pooled
mean that was previously applied everywhere sat below the true hop count at $10
and well below it at $500. The old numbers therefore **understated Lightning's
cost**, which is the same direction as the topology caveat below — the two biases
compound rather than cancel.

### The two findings this produces

**1. Lightning costs ~87× more than Polygon to settle a $200 remittance** — $0.0523 against $0.0006 measured. And this is routing fees *only*, before amortised channel-open cost or the cost of capital locked in channels. *(Was stated as 85× on the superseded $0.0509; the correction does not change the finding, and the order of magnitude is what carries it.)*

**2. The cost crossover exists, and it sits below $500.** This resolves the secondary objective pre-registered in `ANALYSIS_PLAN.md` §12.

Polygon charges for computational work, so its cost is **flat** — $500 costs exactly what $10 costs (measured variation: 0.044%). Lightning charges 165 ppm of the amount, so its cost is **proportional**. At **$500 the Lightning routing fee alone is $0.1467, which exceeds the $0.10 architecture-selection threshold** in §10 — by 47%, where the superseded figure cleared it by only 27%. **The correction strengthens this finding rather than threatening it.**

> ⚠️ **Route length is topology-dependent.** These hop counts were measured on a 20-node network; a 6,010-node network generally needs longer paths. They therefore likely **understate** mainnet Lightning cost. The bias flatters Lightning rather than its competitors, which is the safer direction, but it must be stated.

> ⚠️ **The $200 and $500 rows do not meet the pre-registered repeat protocol.** They rest on 3 and 2 runs against a 5-repeat minimum (`ANALYSIS_PLAN.md` §5), and $50 was never run at all. The crossover finding above should be stated as **supported by, not established by**, this evidence: the mechanism (flat versus proportional fees) is architectural and certain, while the exact crossing point is not tightly pinned by two runs. Collecting more is not possible — Lightning data collection closed 10 Aug (§1) and the cluster is gone.

---

## 4. Illustrative figures from our own network

**Label these "small-scale, illustrative" wherever they appear.** They describe how a 20-node testbed behaves, not how the real network performs, and they must not be presented alongside Polygon's or NEAR's numbers as the same class of evidence.

### Settlement time, clean no-load conditions

$200 payments at 10/sec, 1,111 payments across two runs, 1.0% failure:

| p50 | p95 | p99 | mean |
|---|---|---|---|
| **1.501s** | 3.501s | 3.975s | 1.816s |

Worth noting this is *slower* than typical Lightning benchmarks, and deliberately so: our nodes are placed on real remittance corridors (US → India, UK → SE Asia), so every payment crosses an ocean. A single-region benchmark would report sub-second times that no real remittance would achieve.

**Caveat:** two runs, not the five-repeat protocol. Illustrative only.

### Channel-open cost

**Cited from literature rather than measured.** The cluster was destroyed before this measurement was taken, and re-provisioning for a single figure was not judged worth the budget. A channel funding transaction's size is a protocol-determined property, so a cited figure is not materially weaker than a measured one — but the provenance is stated rather than blurred.

---

## 5. What our simulation actually established

The Lightning testbed did not produce a reliability finding, but the attempt was not wasted. It produced two things the literature does not contain:

**The scale limitation itself, quantified.** "Lightning's throughput cannot be measured below mainnet scale because capacity is additive across channels" is a methodological result. It explains why published Lightning throughput figures vary so widely, and it is the reason this paper treats Lightning's capacity as a question about capital rather than about protocol.

**A demonstration that Lightning is not throughput-limited for remittances.** Per-channel throughput measured on our network, scaled by mainnet's channel count, implies capacity in the thousands of payments per second against global remittance demand of roughly 150/sec. **Neither architecture is throughput-constrained for this use case** — which is why the comparison turns on cost and reliability, and why the throughput ramp mattered less than it first appeared.

---

## 6. Faults found and corrected during Phase 3

Recorded for methodological transparency. Each produced a plausible, publishable-looking number that was wrong, and each was caught by checking the data rather than by reading the code.

| Symptom | Actual cause |
|---|---|
| 100% failure, every payment | Our client rejected valid proof-of-authority blocks (Polygon, Phase 1) |
| Throughput knee at 100–150/sec | Our own load generator, not the chain |
| Lightning ceiling of 25/sec | Uniform destination selection concentrating 1/7 of flow on a node holding 0.01 BTC |
| 71% failure rate | A rebalancer that checked for success one second after firing asynchronous payments, so it always quit after 40 attempts and restored 0.006 BTC instead of 5 |
| A hard 28.6% failure floor | Three starved recipients — 3/7 = 42.9%, and the observed rate was 43.3% |
| Failures climbing across identical repeats | Tried resetting LND's mission control; **measured it making things worse** (3–17% → 71%). Its learned routing state is what makes a topology navigable. Reverted. |

**The generalisable lesson, already recorded for Polygon and reaffirmed here: a plausible-sounding failure deserves the same scrutiny as a surprising success.** Every entry above would have been publishable and wrong.

---

## 7. What the paper must not claim

1. **Do not present our Lightning throughput or reliability numbers as findings.** They are excluded from `data/clean/all_runs_clean.parquet` for this reason. Reliability comes from Waugh & Holz.
2. **Do not describe node reachability (~35%) as a payment success rate.** They are different statistics and the confusion reverses the paper's central Lightning finding.
3. **Do not present $200/$500 Lightning success rates as measured.** Waugh & Holz stop at $100; anything above is extrapolation and must say so.
4. **Do not describe Lightning's Bitcoin usage as an exchange-rate risk problem.** Money is converted, routed and converted back within about a second. The real issue is that converting BTC to local currency is a market trade with spread and slippage, where redeeming a dollar-token is near par — a costlier conversion, not a volatility exposure, and outside what this study measured.
5. **Do not compare Lightning's throughput ceiling to Polygon's as like-for-like.** Polygon's is protocol-determined; Lightning's is capital-determined.
6. **State that channel-open cost is cited, not measured.**

---

## 8. Data provenance

- **All Lightning runs remain in `data/raw/all_runs_raw.parquet`** — 51 runs, 317,911 payments — flagged and inspectable. Nothing was deleted.
- **None appear in `data/clean/all_runs_clean.parquet`**, which contains only data that contributes to a reported result.
- Exclusions and their rules are logged in `data/clean/exclusions.log`.

---

## 9. Remaining Lightning work

**None scheduled.** Scope was closed on 10 Aug 2026 after assessing four candidate follow-ups (`ANALYSIS_PLAN.md` §13, amendment 7). One — comparing even versus hub-and-spoke liquidity funding — has a genuine remittance tie, since real providers concentrate liquidity along the corridors they serve. It is **parked, not rejected**, and should be revisited only if NEAR and Phases 5–6 finish with real time and budget to spare.
