# Pre-Registered Analysis Plan
### Blockchain Remittance Scaling Architecture Benchmarking

**Status: LOCKED — 7 August 2026.** All open items resolved (see the resolution record below). Every further change goes in the Amendment Log (Section 13) with a date and a reason. Nothing above that log gets silently edited.

**Locked before any Phase 2+ data collection begins.** Phase 1 pipeline-validation data does not count as real results and is excluded from everything below.

**Purpose of locking this**: every decision in this document is being made while the actual numbers are still unknown. That's the entire point. Once real results start coming in, this document does not get silently edited to match what looks good — if something here turns out to be wrong or needs to change, it gets logged in the Amendment Log at the bottom with a date and a stated reason, not quietly rewritten. This is what turns "here's what we found" into something a reader can actually trust.

---

## Resolution Record (settled before lock)

Six items were raised against the draft. Two were factual errors, corrected in place. Four were decisions, all made by Angad on 7 Aug 2026 with the costs and tradeoffs stated in advance and with no data in hand.

| # | Section | Issue | Resolution |
|---|---|---|---|
| 1 | §12 | Waugh & Holz figures stated backwards — success rate claimed lowest at the *smallest* payments, which contradicts the same sentence's "inverse relationship" | Corrected against the source. ~72% at smallest, ~15% at largest; the stray "~35%" was their separate node-*reachability* result. Locking the original wording would have pre-registered the expectation backwards, so agreement with the literature would have read as contradiction. |
| 2 | §1, §6.1 | Sharding network still written as "Zilliqa/NEAR" | NEAR. Zilliqa 2.0 removed the sharded architecture we set out to measure. |
| 3 | §6.1 | Draft asked for a "confirmation count" for Polygon — premise was wrong | **N = 1.** PolyBFT gives deterministic instant finality; there is no reorg window to wait out. Extra confirmations would have added delay that doesn't exist and masked a genuine Polygon advantage. |
| 4 | §10 | Two blanks left unfilled in the rule that selects the recommended architecture | **p95 latency < 10s; cost < $0.10/tx.** Both anchored to external standards rather than our expectations — see §10. |
| 5 | §5, §9 | Size-sweep structure conflicted with the trimmed 240-run matrix | **Full matrix adopted — every amount tested at every load level on every architecture.** Angad's call, taken over a cheaper trimmed alternative, for an unqualified symmetry claim. See §5. |
| 6 | §11 | Calibration ratio compared our *capacity* against mainnet *demand* — different quantities | **Two figures reported separately**, demand ratio and capability gap. See §11. |

**On §7's warm-up rule:** this reverses the earlier "no warm-up discard" decision in `CLAUDE.md` §6. The reversal is an improvement and is adopted. It costs nothing retroactively, because the harness records a full per-second time series precisely so warm-up can be excluded in analysis rather than at collection time. `CLAUDE.md` §6 has been updated to match.

---

## 1. Primary Research Questions (stated in advance, not derived from results)

**RQ1 (throughput/cost)**: Of the three tested architectures (Polygon Edge sidechain, Lightning off-chain, NEAR sharding), which sustains the highest offered load at the $200 benchmark transaction size while keeping failure rate under 5%?

**RQ2 (reliability-by-size)**: Does failure rate increase with transaction size for each architecture, and does the pattern match the direction reported in Waugh & Holz (2020) for Lightning specifically?

**RQ3 (cost)**: At the $200 benchmark size and a shared moderate load level (see Section 5), which architecture has the lowest cost per transaction when priced using real mainnet rates (not our own private-network gas/fee configuration)?

**RQ4 (gap to production)**: How large is the gap between our private-network results and real published mainnet activity for each architecture, expressed as a ratio or percentage?

Everything else the data might reveal is secondary/exploratory (Section 4) — interesting, worth reporting, but not what the paper's headline claims rest on.

---

## 2. Primary Outcome Metric (the one the paper's main claim rests on)

**Sustainable throughput at $200**: the highest offered-load step (from the 10/25/50/100/150/200/300 TPS ramp) at which an architecture achieves BOTH:
- achieved throughput ≥ 90% of offered load, AND
- failure/timeout rate < 5%

This exact threshold (90% / 5%) is being fixed now, before we know which architectures will clear it easily and which will struggle. If every architecture blows past 300 TPS at this threshold, that's a real, reportable finding, not a reason to retroactively tighten the bar. If every architecture fails at 25 TPS, that's also real, and it becomes a finding about private-network ceiling rather than something to loosen the bar to hide.

---

## 3. Secondary Outcome Metrics (reported, but not the headline claim)

- p50, p95, and p99 settlement latency at each load step (not just mean latency — mean alone hides tail behavior that matters for a "would a family actually get their money on time" claim)
- Cost per transaction, computed per Section 6.3
- Failure rate broken out by transaction size ($10/$50/$200/$500), at a fixed moderate load level (Section 5)
- Node-offline correlation: performance delta between adversarial-node runs and clean-baseline runs, same configuration otherwise

---

## 4. Exploratory / Non-Primary Findings

Anything else the data surfaces (e.g., an unexpected latency spike at a specific load step, an interesting liquidity-topology effect on Lightning specifically) gets reported as exploratory and labeled as such. Exploratory findings are allowed to shape the Discussion/Limitations section and future-work suggestions. They are not allowed to become a headline claim or replace a primary metric that didn't turn out the way we hoped.

---

## 5. Comparison Structure (fixed in advance)

**Primary comparison**: all three architectures, at the $200 transaction size, across the full load ramp (10→300 TPS), under the full realism stack (post-Phase-3/4), 5 repeats each, reported as mean ± 95% CI.

**Fixed "moderate load level" for cross-metric comparisons** (used wherever a single load level is needed instead of the full ramp, e.g. Section 1's RQ3): **100 TPS**. Chosen now, in advance, as roughly the midpoint of the ramp and below the expected average global demand ceiling (~140-150 TPS) discussed in the project scope. Not chosen after seeing which load level makes any particular architecture look best.

**Secondary comparisons**: $10/$50/$500 sizes, **full 7-step load ramp on every architecture**, 5 repeats each — the same structure as the primary. Reported but not used to override the $200 primary comparison's conclusion.

> **Resolved (item 5).** The alternative considered was a trimmed 240-run matrix, which would have run full size sweeps only on Lightning and spot-checked the other two at 100 TPS. The reasoning for trimming: transaction amount **cannot** affect Polygon or NEAR, because those networks charge for computational work done, and moving a larger number is not more work — an ERC-20 transfer of 10 tokens consumes identical gas to one of 500. The three extra size curves would have landed exactly on top of the $200 curve.
>
> **Angad chose the full matrix anyway**, at roughly $35 and one extra day of cluster time, to be able to state without qualification that every amount was tested at every load level on every architecture. Decision made 7 Aug 2026 with the cost stated in advance.
>
> **Consequence to hold ourselves to:** if the Polygon and NEAR size curves come out flat, as predicted, that is a *confirmed prediction*, not a null finding to bury. It is the baseline the Lightning cost curve is measured against — see §12.

**Full matrix**: 3 architectures × 4 sizes × 7 load steps × 5 repeats = **420 runs**, plus the adversarial arm (§5 below) = **465 runs**, ≈ 38.75 hours of measured run time.

**Adversarial-node comparison**: run as a separate arm (clean baseline vs. 10-20% adversarial) at the fixed moderate load level (100 TPS) and the $200 size only, not across the full matrix, to keep this measurable without doubling total run time.

---

## 6. Definitions Locked in Advance

### 6.1 "Settled" / finality, per architecture

- **Lightning**: settled when the sender receives the payment preimage (the standard definition of Lightning payment success).
- **NEAR**: settled at the finality stage NEAR itself defines as final — transaction outcome at `FINAL`, **not** `EXECUTED_OPTIMISTIC`. Optimistic execution would understate real settlement latency.
- **Polygon**: settled at **inclusion in a committed block (N = 1 confirmation)**.

> **Resolved (item 3).** The draft asked to "set a fixed number of confirmations now," which rested on a wrong premise. Polygon Edge runs PolyBFT/IBFT, giving **deterministic instant finality** — a committed block is final, with no probabilistic reorg window to wait out and no "default finality assumption" to match. Waiting extra blocks would have added delay that does not exist and understated a genuine architectural advantage Polygon holds over probabilistic-finality chains.
>
> This must be stated explicitly in the Methodology so no reader mistakes N = 1 for a shortcut. The asymmetry with the other networks is real and in Polygon's favour; it is reported as a finding, not neutralised.

### 6.2 "Failed" vs. "slow"

A transaction is counted as **failed**, not merely slow, if it has not settled within **60 seconds** of submission. This threshold is fixed now. If real results show architectures regularly settling at 45-55 seconds under load, that is a legitimate, reportable finding (borderline performance) — the threshold does not get quietly extended to 90 seconds to reclassify those as successes.

### 6.3 Cost per transaction

Cost is **not** measured as the raw fee/gas price we ourselves configured on the private network, since that number is an artifact of our own settings, not a finding. Instead: measure **gas/resource actually consumed** per transaction on our network, then convert to a dollar cost using real, current mainnet pricing data (Polygonscan gas price, 1ML.com fee-rate data for Lightning, NEAR Explorer) pulled on a specific stated date. That date gets recorded and cited exactly once as the pricing source for the whole paper — not re-pulled quietly later if the number becomes inconvenient.

**Lightning additionally amortizes on-chain channel open/close cost** across the number of payments a channel carries. Most Lightning benchmarks omit this and thereby report Lightning as near-free; including it is the honest number.

### 6.4 Failed transactions and throughput

Failed transactions (per 6.2) **do not count toward achieved throughput**. Achieved throughput = successful, settled transactions per second only. This is being decided now because it materially changes every headline number, and deciding it after seeing the data would let a bad failure rate get hidden inside an inflated throughput figure.

---

## 7. Exclusion Rules (decided before data exists)

- **Warm-up period**: the first 10 seconds of every sustained test run are discarded from measurement, to avoid cold-start effects (connection establishment, initial channel routing, etc.) skewing the numbers. Applied uniformly across all three architectures.
  - *Precise rule*: exclude transactions whose **submission** offset is < 10.0s. Confirmation may land after the 10s mark; what's excluded is the transaction, not the time window, so no settlement is counted with a truncated latency.
- **Generator saturation**: if the harness's own p95 schedule lag exceeds 250 ms, the run's throughput ceiling reflects our tooling rather than the architecture. Such runs are auto-flagged invalid by the harness and excluded. *(Added — this rule is enforced in code and must appear here to be pre-registered.)*
- **Spot/preemptible instance reclamation**: if a run is interrupted by a cloud provider reclaiming a spot instance mid-run, that run is discarded entirely and re-run, not partially salvaged. A partial run under an unplanned infrastructure failure is not the same experiment as a completed one.
- **Infrastructure crash vs. architecture failure**: if an entire node crashes due to our own misconfiguration (not the adversarial-node test condition), the run is discarded and re-run, logged as an infrastructure issue, not counted as a data point reflecting the architecture's real reliability.
- **Runs are never discarded for producing an inconvenient result.** The only valid reasons to discard are those above — never "this number looks bad for the architecture we expected to win."
- **Nothing is ever deleted.** Excluded runs remain in `data/raw/all_runs_raw.parquet`, flagged. Every exclusion is logged to `data/clean/exclusions.log` with run ID, triggering rule, and reason.

---

## 8. Handling an Incomplete Architecture

If time or budget runs out before an architecture (most likely sharding, per the phased rollout's own risk ordering) completes the full realism stack: that architecture's results are reported at whatever phase they reached, explicitly labeled with which realism techniques were and weren't applied, and directly compared against published literature benchmarks for the same architecture as a stated fallback. It does not get quietly dropped from the comparison, and it does not get presented as equivalent-quality data to the architectures that completed the full stack.

---

## 9. Guardrail Against Cherry-Picking Across the Matrix

Across three architectures, four sizes, seven load steps and two arms there are a lot of individual numbers — more than enough that some comparison, somewhere, will look favorable to some architecture. The primary comparison (Section 5) is what the paper's headline conclusion is based on. Any claim of the form "architecture X is best" must be traceable to the primary comparison at $200/full ramp, not to a favorable-looking secondary or exploratory result. If a secondary result contradicts the primary comparison's conclusion, that contradiction gets reported and discussed, not suppressed.

---

## 10. Decision Rule for "Best Architecture" (feeds Design Science section)

Fixed in advance, since this is the single most consequential judgment call in the whole project: the architecture recommended in the Design Science / Architecture Proposal section is the one with the **highest sustainable throughput at $200** (Section 2's primary metric), **among architectures that at that same load level also keep:**

- **p95 settlement latency below 10 seconds**, and
- **cost per transaction below $0.10.**

> **Resolved (item 4).** These were left blank in the draft. They are the most consequential numbers in the document, and pre-registration achieves nothing if they are filled in after seeing results. Both are anchored to external standards rather than to our expectations:
>
> **10 seconds** is generous against the ~2-5s finality both chains target, so it will not arbitrarily disqualify a working architecture, but it is tight enough to mean something. It is grounded in the claim the paper actually wants to make — that these rails settle in seconds where SWIFT settles in days.
>
> **$0.10** is 0.05% of the $200 benchmark, anchored to **UN SDG 10.c**, which targets total remittance cost below 3% of transfer value — $6.00 on a $200 transfer. Reserving no more than 0.05% for the settlement layer leaves essentially the entire 3% budget for the fiat on/off-ramp, which prior research suggests dominates real-world remittance friction and which this simulation explicitly does not measure. A settlement layer that cannot clear this bar could not plausibly support a compliant remittance product.

If no single architecture wins on all three dimensions simultaneously, the paper reports this honestly as a genuine tradeoff (e.g., "Architecture A has the highest throughput ceiling but Architecture B has meaningfully better reliability at the $10-$50 size range") rather than forcing a single artificial winner. A tradeoff-based conclusion, accepted as a legitimate outcome now, is more credible than picking a winner after the fact by whichever metric happens to favor one architecture.

---

## 11. Calibration Gap Computation

**Two figures are reported per architecture, clearly distinguished.** Both use mainnet data pulled from the block explorer on the same date as the cost data (Section 6.3). Both are reported even when uncomfortable.

1. **Demand ratio** = `our_sustainable_throughput / mainnet_observed_throughput`.
   Establishes that the loads we test are realistic relative to real-world activity. This is a statement about **workload realism, not capability.**

2. **Capability gap** = `our_sustainable_throughput / mainnet_observed_peak`, where the peak is the highest sustained throughput visible in explorer history.
   This is the closer analogue of a capacity comparison, and it is the figure supporting the "treat our results as an upper bound roughly Z% high" claim the project scope calls for.

> **Resolved (item 6).** The draft used a single ratio dividing our *capacity* by mainnet's *observed throughput*. Those are different quantities. Real Polygon PoS runs at tens of transactions per second because that is current **demand**, not because it cannot go faster — so a ratio of 3× would not mean "our network is 3× more capable," it would mean "mainnet is lightly loaded." Presented as a capability gap, that would be straightforwardly wrong, and it is the kind of error a reviewer spots immediately.
>
> **Mainnet observed throughput is a floor on capacity, never a measurement of it.** The paper must say so explicitly.

---

## 12. Pre-Registered Expectations (literature priors, for comparison against actual results)

Stated now so it's later possible to distinguish "matched expectations" from "genuine surprise":

- **Sharding (live network)** expected to land meaningfully below its own academic lab benchmarks (OmniLedger ~6,000 TPS, RapidChain ~7,384 TPS), since those are idealized lab conditions.
- **Polygon sidechain** expected to land below its ~3,800 TPS theoretical max — noting that figure is a **vendor claim, not a peer-reviewed measurement**, and is unsuitable as an empirical benchmark. Expected to show more predictable/flat latency degradation than Lightning as load increases.
- **Lightning** expected to show a **clear inverse relationship between transaction size and success rate** (RQ2).

  > ✅ **Corrected.** The draft cited "success rates as low as ~15-35% for the smallest payments," which is backwards and contradicts the same sentence's claim of an inverse relationship. Verified against the source (Finnegan Waugh & Ralph Holz, *An empirical study of availability and reliability properties of the Bitcoin Lightning Network*, arXiv:2006.14358), the paper reports **two distinct findings**:
  >
  > 1. Payment success rate ranged **15.32% – 72.09%**, **inversely** related to payment volume — so ~72% at the *smallest* payments and ~15% at the *largest*.
  > 2. **Separately**, only about **one third of destination nodes** were reachable at all, roughly *independent* of payment volume. The stray "~35%" in the draft appears to be this reachability figure, not a payment-size result.
  >
  > Locking the original wording would have meant concluding our Lightning data contradicted the literature when it in fact agreed with it.

  So the pre-registered expectation is: **success rate highest at $10 and lowest at $500.** If our results do NOT show this, that is a genuinely notable, reportable divergence — not an error to be quietly corrected.

- **Cost behaves differently with transaction size across architectures.** Registered as a prediction now, before any data:
  - **Polygon and NEAR: cost is flat with respect to amount.** These networks charge for computational work performed, and moving a larger number is not more work. Sending $10 and sending $500 should cost the same. (Cost still varies with *load*, via congestion pricing — that is a separate axis.)
  - **Lightning: cost rises with amount.** Routing fees are partly proportional to the sum being moved, so each hop takes a cut that scales with the payment.
  - **Therefore we predict a crossover**: Lightning cheapest at $10, progressively less competitive as amount rises, with the flat-fee architectures undercutting it somewhere in the tested range. **Locating that crossover point, if it exists within $10-$500, is a pre-registered secondary objective** — it bears directly on the cost half of the research question, and it is corridor-relevant, since a worker remitting $30 weekly and one remitting $500 monthly may be best served by different rails.
  - If the Polygon and NEAR size curves come out flat as predicted, that is a **confirmed prediction and the baseline the Lightning curve is measured against** — not a null result to be buried.

- **El Salvador's ~0.7% crypto-remittance adoption** is a separate, non-technical prior: no simulation result is expected to explain or predict it, since it's a trust/adoption phenomenon already flagged as outside the simulation's scope.

---

## 13. Amendment Log

*(This section exists so that any change to Sections 1-12 after the lock date gets recorded here with a date and stated reason, rather than the original document being silently edited.)*

| Date | Section changed | What changed | Why |
|---|---|---|---|
| 9 Aug 2026 | §7 (exclusions) | **Generator-saturation criterion changed from absolute lag magnitude to lag GROWTH across a run.** A run is excluded when its median scheduling lag rises by more than 50 ms between the first and last quarter. Applied uniformly to all 131 runs recorded to date; no run in this study is judged by any other saturation rule. | The original magnitude threshold asked the wrong question. A generator sitting a constant few milliseconds behind schedule distorts nothing — the load offered still matches the load intended. What corrupts a measurement is lag that *grows*, because the arrival pattern delivered then drifts from the Poisson process scheduled. Evidence: at 200/sec the median lag was 7.2 ms in both the first and last quarter of a run, with settlement (3.69 s) continuing smoothly from 150/sec (3.33 s) — yet a magnitude threshold excluded every such run, removing the peak-demand levels the study exists to measure. **Validation:** applied to seven runs independently known to be broken (pre-fix single-process runs; 500 and 1000/sec ceiling tests, settlement inflated 3–11×), the criterion detects all seven, including a subtle case growing 9.7→294.9 ms. **Effect and stated limitation:** re-judging moved 24 runs from excluded to included and none in the other direction. That asymmetry is the signature of a criterion devised after seeing data, and is stated here rather than left for a reader to discover. It is mitigated by uniform application and by the validation above, not dismissed. Superseded an interim 250 ms → 40 ms tightening made 8 Aug that never produced a reported result. |
| 8 Aug 2026 | §2 (load ramp) | **Exploratory** load levels added above the pre-registered ceiling: 500 and 1000/sec | Polygon Edge sustained the entire pre-registered range (10–300/sec) with zero failures and p95 settlement of 6.71 s, passing every threshold at every level. The ramp's ceiling is therefore too low to locate the architecture's limit. **The primary metric is unchanged and still evaluated on the original 10–300 ramp.** Levels above 300 are exploratory per §4 and cannot support a headline claim. |
| 8 Aug 2026 | §6.3 (cost) | Warm-recipient gas figure (35,865) confirmed as the reported value | At scale, remittances move between a small fixed set of institutional treasury addresses rather than between millions of self-custodied wallets, so first-time-recipient cost is paid once per corridor partner and amortises to nothing. Reporting it per-transaction would overstate the cost of every transfer after the first. Self-custodial designs are a separate architectural case for the Design Science section. |

### Amendment 4 — 9 Aug 2026: re-executions of a completed configuration are excluded

**Rule.** Where a configuration was measured more than once, the first completed execution stands; later executions of the same configuration are excluded.

**Why it was needed.** Spot preemption interrupted the main sweep twice. On resume the sweep restarted from the beginning of the load ladder rather than from the point of interruption, so 22 configurations were measured a second time, 3.9-8.1 hours later. Four cells of the matrix held 10 runs where the protocol specifies 5.

**Why these are not repeats.** Each re-execution reused the *same arrival seed*, so it replays an identical Poisson schedule rather than drawing a new one. At load levels with no failures the pairs are transaction-for-transaction identical. A repeat exists to sample arrival-pattern variability; a replay of the same pattern samples nothing. Counting both would double those cells' weight and inflate n for the §8 confidence intervals, producing intervals narrower than the evidence supports.

**Why first rather than last.** The rule is mechanical and fixes the choice without reference to the numbers. It is also the less flattering direction: the second pass ran on a chain carrying several more hours of accumulated state and performed slightly worse, so keeping the first *widens* the reported failure spread at 300/sec (2.9 to 4.3 percentage points) rather than narrowing it.

**Applied uniformly** to all runs by `analysis/export.py`. Effect on published results: the $200 curve moved 200.8 to 200.9/sec at one load step. The ceiling, knee, cost and adversarial findings are unchanged, and size-independence remains non-monotonic under either choice of rule.

### Amendment 5 — 10 Aug 2026: Lightning reliability and throughput come from published measurement, not our simulation

**Sections affected:** 2, 5, 6, 12 (all Lightning-related metrics).

**Change.** Lightning's reliability and throughput data is sourced from **Waugh & Holz (2020)**, an empirical measurement of the real production Lightning Network, rather than from our own private testbed.

**Why.** A structural scale limitation, not a bug. The real network has 6,010 nodes and 19,644 channels; ours has 20 and 51 — roughly **385× fewer channels**. Lightning's success rate depends on how many routing paths exist between sender and receiver, so a network with 385× fewer paths does not behave like the real one no matter how well the rig is built. More hardware, more debugging or a larger cluster within budget does not close this; it is a property of deployed capital, not of the protocol.

> **⚠️ Citation corrected 18 Aug 2026:** the "6,010 nodes / 19,644 channels" figure does NOT appear in Waugh & Holz — zero occurrences in the full text. The paper states **4,826–4,950 nodes and ~31.4–31.8k channels** (Nov 2019). Against our 51 channels the true ratio is **~620x fewer, not 385x** — a stronger argument. 19,644 most likely came from 1ML, which publishes no collection timestamp and disagreed with mempool.space by 40% on 18 Aug 2026 (20,004 vs 33,313 channels). See `LIGHTNING_EVIDENCE.md` §2.

This differs in kind from the Polygon faults. Those were genuine mistakes that, once fixed, produced trustworthy numbers, because Polygon is a replicated state machine: throughput is set by the block gas limit and consensus timing, not by validator count, so a 4-validator measurement transfers to a 100-validator mainnet. Lightning capacity is *additive across channels*, so ours does not transfer.

**What is retained from our Lightning runs.** Two figures, labelled "small-scale, illustrative" wherever they appear, and never presented as the same class of evidence as the Polygon or NEAR measurements:
- settlement time under clean, no-load conditions
- observed route length (which feeds the cost metric below)

All Lightning runs remain in `data/raw/all_runs_raw.parquet`; none contribute to a reliability or throughput claim.

**Numerical correction to how this plan cited Waugh & Holz.** An earlier draft stated "~35% success for the smallest payments", conflating two distinct statistics. Verified against the source (arXiv:2006.14358):

| Payment size | Payment success rate | Nodes reachable |
|---|---|---|
| $0.01 | 71.9% | 35.2% |
| $1 | 57.8% | 35.2% |
| $5 | 44.1% | 25.7% |
| $10 | 44.2% | 33.7% |
| $50 | 30.9% | 9.2% |
| $100 | 17.3% | 4.8% |

**Success rate** falls sharply with payment size — the inverse relationship the paper's abstract describes, and the figure relevant to remittance-sized transfers. **Node reachability** is a separate, roughly flat statistic (~25-35%) and is where the stray "~35%" came from. It must not be described as a size-specific success rate.

**Scope limit to state in the paper.** Waugh & Holz tested only up to $100. Our $200 and $500 benchmark sizes are above anything they measured. Extending their declining trend to those amounts is a reasonable extrapolation and must be labelled as one, not presented as measured data.

---

### Amendment 6 — 10 Aug 2026: Lightning cost per transaction is priced from mainnet fee policy, not our own

**Section affected:** 6.3 (cost per transaction).

**Change.** Lightning's cost per transaction is computed as **measured route length × real mainnet per-hop fee rates** from 1ML, pulled 10 Aug 2026. Our own nodes' routing fees are not reported.

**Why.** Identical in principle to the trap §6.3 already identifies for Polygon's gas price. Our LND nodes ran the stock fee policy (1,000 msat base, 1 ppm). At the 2.53-hop routes measured, that yields ~2,530 msat — and the observed mean was 2,016 msat, confirming the "measured" fee was essentially our own configuration. Pricing a number we chose ourselves would be circular.

What *is* architecture-determined is **route length**. That is measured; the price comes from the real network:

```
per hop = median_base_fee + (median_fee_rate x amount)
        = 0.449584 sat + 0.000165 x amount_sat
fee     = per_hop x (hops - 1)          # forwarding nodes charge, the destination does not
```

**Result at $200: $0.0523**, against Polygon's measured $0.0006 — a factor of 87. *(Corrected 12 Aug 2026; was $0.0509 and 85×. See amendment 10.)*

**This resolves the §12 crossover objective.** Polygon charges for computational work, so cost is flat with amount. Lightning charges 165 ppm, so cost is proportional. At **$500 the Lightning routing fee alone is $0.1467, exceeding the $0.10 architecture-selection threshold in §10** — before amortised channel-open cost or the cost of locked capital. The crossover lies below $500. *(Corrected 12 Aug 2026; was $0.1267. See amendment 10.)*

**Limitation.** Route lengths of 2.571 hops at $200 and 2.772 at $500 were measured on a 20-node network; a 6,010-node network generally requires longer paths, so this likely *understates* mainnet Lightning cost. The bias flatters Lightning rather than its competitors, and is stated rather than corrected.

**Second limitation, added 12 Aug 2026.** The $200 and $500 route lengths rest on **3 and 2 runs** against the 5-repeat minimum in §5, and **$50 was never run on Lightning at all**. The crossover *mechanism* — flat versus proportional fees — is architectural and certain; the exact crossing point is not tightly pinned by two runs. State the finding as supported by, not established by, this evidence.

**Channel-open cost** is cited from literature rather than measured — the cluster was destroyed before that measurement was taken, and re-provisioning for one figure was not judged worth the budget.

---

### Amendment 7 — 10 Aug 2026: Lightning testing scope closed

No further Lightning testing is scheduled. Four candidates were assessed against two bars — effort-to-insight ratio, and whether the question is specifically about remittances rather than generic protocol mechanics:

- **Reproducing insufficient-funds failures on our network — rejected.** Waugh & Holz already measured this at real scale (31.58% of observed errors). A weaker version of a solid finding adds nothing, and it is not remittance-specific.
- **Hop-count versus latency — rejected.** A real protocol property, but it feeds no comparison the paper makes.
- **Fee structure / channel-open cost — not new work.** Already required by §6.3; handled in amendment 6.
- **Liquidity topology comparison (even versus hub-and-spoke funding) — parked, not rejected.** The one candidate with a genuine remittance tie: real providers concentrate liquidity along the corridors they serve. It roughly doubles the Lightning matrix and competes with NEAR and Phases 5-6, which are under real constraint from the GCP quota and the 6 November credit expiry. Revisit only if those finish with time and budget to spare.

---

### Amendment 8 — 12 Aug 2026: the warm-up cut is applied on SCHEDULED offset, not submitted offset

**Section affected:** 7 (exclusions, warm-up period).

**What §7 says.** "Exclude transactions whose **submission** offset is < 10.0s."

**What the code does.** `analysis/export.py` filters on `scheduled_offset >= 10.0`.

**Why this was not caught earlier.** Submission offset is scheduled offset plus scheduling lag, and lag cannot be negative, so `scheduled >= 10` always implies `submitted >= 10`. The code's rule is therefore a strict superset of the pre-registered one: everything §7 excludes, the code also excludes. The two differ only for transactions *scheduled* just before the 10s mark that were *submitted* just after it, and those are dropped rather than kept.

**Magnitude, measured across all 236 runs in the raw dataset (7,377,810 valid submitted payments):**

| | |
|---|---|
| Payments kept by §7 but dropped by the code | **1,140 (0.0155%)** |
| The reverse | 0 (impossible while lag ≥ 0) |
| Runs touched | 108 of 236; median 2 payments per run |
| Worst single run | 189 payments, **0.22%** of that run |
| Concentration | 950 of 1,140 sit at the 300/sec step, where lag is largest |

**Resolution: the code's behaviour stands, and §7 is amended to match it** — for a reason that makes it the better rule rather than merely the implemented one.

Filtering on *submission* time conditions the sample on an outcome. A transaction scheduled at 9.8s is retained only if it was **delayed** past 10.0s, so the rule preferentially keeps exactly those transactions that experienced lag while discarding their punctual neighbours. That is a selection effect, it grows with load, and it acts hardest at 300/sec — the step where the knee is and where the study's headline claim lives. Filtering on the *schedule* is independent of what later happened to the transaction.

**No reported figure changes.** At 0.0155% overall and 0.22% in the worst single run, this cannot move an achieved throughput of 270.5/sec or a failure rate of 9.97%. It is recorded because a discrepancy between the locked text and the implementation is the kind of thing a reviewer is entitled to find already disclosed, not because the numbers are in doubt.

**Applies uniformly** to all architectures and all runs, past and future, since it describes the export path every result passes through.

---

### Amendment 9 — 12 Aug 2026: runs that never recorded an end are excluded

**Rule.** A run whose `ended_wall` timestamp is NULL is excluded from the clean dataset. Its payments remain in the raw dataset, flagged, like every other exclusion.

**What `ended_wall` means.** The harness writes it when a run finishes its window normally. NULL means the run was cut off part-way — the process was killed, the machine went away, or the sweep was restarted underneath it.

**Why it is needed.** The payments such a run recorded are real, but they are a **truncated** sample of a window that was specified as 300s, and the truncation is not random: a run gets interrupted precisely when something is going wrong. Including one silently mixes a partial measurement taken during a fault with complete measurements taken under control.

**The concrete case that exposed it.** On 12 Aug the `$10 at 100/sec repeat 0` run was cut off at 12:02 UTC when two validators dropped out of the set mid-window. It retained 30,403 payments, was never flagged invalid, and passed every existing exclusion rule. Two consequences:

1. a truncated run measured on a degrading network would have entered the clean dataset as an ordinary measurement; and
2. **Amendment 4 keeps the *first* execution of a configuration.** The orphan is earlier than its eventual clean re-run, so the truncated run would have been kept and the good complete one discarded.

The second is the serious one, and it is the reverse of what Amendment 4 was written to achieve.

**Why this is not outcome-selection.** The rule keys on whether a run *finished*, which is known without inspecting its throughput, latency or failure rate. It cannot be used to drop a run for being inconvenient. This matters because the rule was written after data existed, unlike Rules 1 and 3–6.

**Scope.** Applies uniformly to all architectures and all runs, past and future. **No published figure changes:** the only run it excludes at the time of writing is the NEAR orphan above, which was never part of any reported result, and re-running `analysis/results.py --verify-polygon` reproduces all seven published Polygon load steps exactly.

**Why the harness did not already prevent this.** It half did. The sweep's own completeness check requires `ended_wall IS NOT NULL`, so an interrupted configuration is correctly re-run rather than skipped. Only the export path was missing the matching rule, which is why the orphan was queued for re-measurement *and* would have been exported.

---

### Amendment 10 — 12 Aug 2026: Lightning route length is per-amount, not pooled

**Sections affected:** §6.3 (cost), §12 (crossover objective).

**What was wrong.** `LIGHTNING_ANALYSIS.md` §3 printed a route-length distribution **pooled across all amounts** (2 hops: 72,910; 3 hops: 118,807; 4 hops: 2,679; n = 194,396) and stated "Mean 2.53 hops" beside it. Two defects:

1. The pooled table's own mean is **2.639**, not 2.53. The 2.53 figure was the **$200-only** mean, printed against a pooled table.
2. That single hop count was then applied to **every row** of the cost table — but route length varies materially with amount.

The pooled table also omitted the 10-second warm-up cut that §7 applies uniformly to all three architectures.

**Measured per-amount route lengths** (confirmed payments, warm-up cut applied):

| Amount | Confirmed | Runs | Mean hops | Fee-charging hops |
|---|---|---|---|---|
| $10 | 173,449 | 46 | 2.651 | 1.651 |
| $50 | *never run* | 0 | — | — |
| $200 | 2,162 | 3 | 2.571 | 1.571 |
| $500 | 3,305 | 2 | 2.772 | 1.772 |

**Corrected costs**, priced identically (1ML medians, 0.449584 sat base + 165 ppm):

| Amount | Was | Now |
|---|---|---|
| $10 | $0.0030 | **$0.0032** |
| $50 | $0.0131 | **$0.0134** ⚠️ extrapolated |
| $200 | $0.0509 | **$0.0523** |
| $500 | $0.1267 | **$0.1467** |

**Independent confirmation.** Each amount's measured mean fee reproduces its own hop count against our nodes' stock LND policy (1,000 msat base + 1 ppm) to within 1%: $10 → 1.638 implied vs 1.638 measured; $200 → 1.541 vs 1.534; $500 → 1.738 vs 1.729. The per-amount hop counts are therefore not an artefact of how the data was sliced.

**Effect on findings.**
- The $200 comparison moves from **85× to 87×** Polygon. The finding is unchanged; it was always carried by the order of magnitude.
- The $500 crossover **strengthens**: the routing fee clears the $0.10 threshold by 47% rather than 27%.
- Every figure moved **up**, so the superseded numbers understated Lightning's cost — the same direction as the topology caveat, which the two now compound rather than cancel.

**Two evidence limits recorded at the same time, previously undisclosed:**
- **$50 was never run on Lightning.** Only $10, $200 and $500 were. The $50 cost row is a formula extrapolation and must be labelled or dropped.
- **$200 and $500 rest on 3 and 2 runs**, against the 5-repeat minimum in §5, and 96% of all confirmed Lightning payments are $10. The crossover mechanism (flat versus proportional fees) is architectural and certain; the exact crossing point is not tightly pinned. More data cannot be collected — Lightning collection closed 10 Aug and the cluster is gone.

**How it was found.** Recomputing the published figures from `all_runs_raw.parquet` during a Phase 4 check, per the standing rule to re-derive every number from the data at each architecture boundary rather than carrying figures forward.

---

### Amendment 11 — 12 Aug 2026: the 60-second budget decides success, applied in analysis

**Sections affected:** §2 (primary outcome), §3 (secondary metrics), §7 (exclusions).

**This is a bug fix, not a rule change.** The 60-second timeout is pre-registered in `claude.md` §7, with its reason stated: *"past 60s a remittance has functionally failed regardless of what the chain eventually does."* The rule was not being applied consistently by the harness. This amendment records the correction, not a new criterion.

**What was wrong.** `analysis/export.py` defined `succeeded = (status == 'confirmed')`, ignoring latency. Polygon's adapter stops at the deadline, so its slowest recorded settlement is **60.0101s** and the omission was invisible. NEAR's adapter drains still-in-flight payments after the send window closes, so a payment finalising at 91 seconds was recorded `confirmed` with its true latency — and counted as a success.

**Scale of it, at the load where it matters most:**

| Run | Confirmed | Of those, over 60s | Share |
|---|---|---|---|
| $200 @ 200/sec r0 | 34,813 | 11,839 | **34.0%** |
| $200 @ 200/sec r1 | 22,496 | 15,560 | **69.2%** |

200/sec is where NEAR's knee sits, so the error understated the failure rate at exactly the point the headline claim rests on. At and below 150/sec no payment exceeded 60s (slowest 30.4s), so lower load steps are unaffected.

**The correction.** `succeeded = (status == 'confirmed') AND (latency_s <= 60)`.

**Why in analysis rather than in the adapter.**
1. It lands identically on all three architectures, which is the comparability argument that justified dropping Caliper in the first place.
2. It is recoverable for data already collected, because per-transaction latency was recorded — the reason `claude.md` §8 insists on per-transaction records rather than pre-aggregated summaries.
3. It does not require changing a measurement instrument in the middle of a matrix.

**`status` is deliberately left untouched.** It remains the raw observation — what the chain actually did — so a reviewer can see both *"it did confirm, at 91s"* and *"it counts as a failure"*. The fact stays separate from the verdict.

**Effect on published results: none.** Across the whole clean dataset only **10** payments were affected outside NEAR — 1 at Polygon 200/sec and 9 at 300/sec, the slowest being 60.0101s. All seven published Polygon load steps reproduce exactly, to two decimals, on throughput, failure rate, p50, p95 and p99.

---

### Amendment 12 — 14 Aug 2026: disclosure pass after an adversarial audit of the finished dataset

**No rule changes. No clean-dataset changes. Presentation and disclosure only.** A 7-lens adversarial audit produced 76 raw findings; the items below were each re-verified by hand against the raw data and the deployment scripts before being acted on.

**1. Consensus timing disclosed.** NEAR ran `min_block_production_delay = 2s`; nearcore's default is 600ms. The default could not hold consensus across four continents (`ShardStuck`), and 2s was the fastest stable interval. Finality costs a fixed number of blocks, so measured settlement scales roughly linearly with block interval — meaning **every NEAR latency figure, including the §10 latency disqualification, is conditional on the 2s cadence**. Polygon ran its own ~2s default. First-order sensitivity: at ~1.2s cadence NEAR's p95 at ≤150/sec (12.3–19.2s) scales to ~7.4–11.5s, straddling the 10s bar; at 600ms, ~3.7–5.8s, passing it. Throughput may also rise with cadence, so no direction is assumed; a block-time supplementary test is queued. This setting existed only in a deploy-script comment before this amendment.

**2. Single-shard execution disclosed; the 10-shard projection withdrawn.** Every `ft_transfer`'s transaction receiver is the single token contract, so all 2.4M measured payments executed on the one shard hosting it. The recorded `route_hops` field compared sender and recipient home shards — a boundary not on the execution path (the recipient's shard holds no state for a token transfer). True statement: ~3/4 of payments paid one cross-shard receipt hop (sender→token). The 372/sec projection assumed distributable execution and is **withdrawn**; the replacement finding is that sharding as deployed provides no execution-throughput scaling for a single-contract stablecoin workload — the dominant real-world remittance pattern.

**3. The 300/sec step is reported, from raw, as marked sensitivity data.** All 20 runs were excluded by the (pre-registered, amendment-1) lag-growth rule at 57–83ms against the 50ms threshold, yet are internally consistent: failures 94.2–99.7% across every run and amount; at $200, 9.9/sec [8.0, 11.7], 96.69% failures, p50 44.85s. Presenting the cell as "not measurable" hid the strongest evidence of the collapse and made the Polygon comparison at 300/sec one-sided. Reported with a † and never merged into the clean set.

**4. Threshold fragility at the knee disclosed, with a both-versions sensitivity.** Kept 200/sec runs span 22.8–46.8ms of lag growth; the two excluded sit at 51.9/54.3ms; the distribution has no gap. At a 40ms threshold, 14 of 24 raw 200/sec runs would drop. Sensitivity at $200/200: clean n=4 gives 47.5/sec, 76.3% failures; all-runs n=5 gives 44.9/sec, 77.6%. Both fail the sustainability bar by an enormous margin, so no conclusion at the knee depends on the rule.

**5. Audit claim corrected rather than adopted.** The audit asserted the saturation rule "never fires on Polygon". False: it excluded 3 Polygon runs inside the 10–300 ramp (growth 0.3–45 s), caused by the pre-fix single-process client and re-measured cleanly after the worker fix, plus 5 exploratory runs at 500/1000. The real, remaining asymmetry is that NEAR's 300/sec cells failed on every attempt (the drift originates in NEAR's congested RPC, per the null-backend validation), and that settlement detection differs by architecture (per-payment polling on NEAR vs per-block receipts on Polygon) — an open instrument limitation.

**6. A CI-fragile ordering claim reworded.** "47.5/sec at 200 offered is less than at 50 offered" rested on a 2.3/sec difference inside a 42.4/sec-wide interval. The collapse claim now rests on the failure curve (0.15% → 76.3% → 96.7%) and no longer on cross-load throughput ordering.

---

### Amendment 13 — 18 Aug 2026: Lightning evidence base rebuilt; a citation in our own documents corrected

**Sections affected:** §1 (RQ1), §10 (decision rule), §12 (Lightning expectations). **No data changes.**

A six-angle literature and network-data sweep was run to establish whether Lightning can be ranked alongside the two measured architectures. 25 citations confirmed, 9 corrected, 1 refuted, **57 absences recorded**. Full write-up: `LIGHTNING_EVIDENCE.md`.

**1. A citation error in this project's own documents.** The "6,010 nodes / 19,644 channels" figure attributed to Waugh & Holz **does not appear anywhere in that paper** — zero occurrences of any of those numbers in the full text. The paper states **4,826–4,950 nodes and ~31.4–31.8k non-stale channels** (3–25 Nov 2019). Against our 51 channels the correct ratio is **~620× fewer, not 385×** — the argument is *stronger* than we claimed. The 19,644 figure most likely came from 1ML, which **publishes no collection timestamp** and which disagreed with mempool.space by 40% on the same day (20,004 vs 33,313 channels, 18 Aug 2026). Every affected document is tagged in place.

**2. Lightning cannot be evaluated against the §10 decision rule, and this is now stated as a finding rather than a gap.** The rule requires sustainable throughput at $200, p95 latency, and cost. **No measured throughput ceiling for Lightning exists in any source** — only demand (~2.5 tx/sec network-wide, River, Aug 2023) and a protocol concurrency constant (483 HTLCs/channel). **No p95 or p99 latency exists from any source** — not one publishes a percentile beyond a median and a single decile. Two of three inputs are absent, so §10 is applied to Polygon and NEAR only, with Lightning reported separately on the axes where evidence exists. The reason is architectural: Lightning has no global state, no blocks, and most channels are private, so there is no observer position from which network throughput is defined.

**3. Waugh & Holz remains usable, with a sharper caveat.** Their intermediate points are now recorded ($5 = 44.06%, $10 = 44.15%, filling gaps the brief lacked). Channel count today (33,313) is only ~6% above their window (~31,600), so routing topology is comparable — but capital per channel is ~4.7× deeper, which should have *improved* large-payment success. **Their absolute values are therefore likely pessimistic for 2026; the direction should still hold.** Two further limits: only two attempts were allowed per payment (so these are lower bounds against real retrying wallets), and **no confidence intervals exist for any Lightning success figure from any source**. $100 remains the largest amount ever tested by anyone — $200 and $500 are extrapolation.

**4. A structural fact that supports the size effect, sourced and current.** Median public channel capacity is 2,042,100 sat; at BTC = $64,186 (18 Aug 2026) **a $200 remittance is ~15% of the median channel**, and must clear that at every hop in the right direction.

**5. The cost omission this project already flags is standard, and its magnitude is now sourced.** Béres, Seres & Benczúr (arXiv 1911.09432) state explicitly that they give no estimate of channel-opening cost. They also show routing fees would need to rise **1,240–1,680×** for routers to earn 5% annually on locked capital. **Lightning's near-zero fees exist because routing capital is currently uncompensated** — the strongest cost finding available, and it reframes the crossover result. Network-wide on-chain compression is ~53 payments per on-chain transaction (not River's own 252, which is unrepresentative).

**6. Four widely-circulated figures identified as uncitable**, and recorded so they are not picked up later: the "~80% success for $500+" series (no primary source), "Stadelmann (2023), 50% success" (**attributed to a real paper that contains no such claim — apparently fabricated**), the "8.6 second median" (untraceable), and a Voltage iGaming pilot claim (unverified). That such figures circulate is itself reportable: the Lightning performance literature is thin enough that secondary sources have filled the gap with numbers that do not exist.

**7. Remittance deployment evidence is weaker than the narrative.** El Salvador's 0.70% crypto-remittance share (Jan–Apr 2026) is an undifferentiated **"crypto wallet" central-bank category with no Lightning breakout**. Alvarez, Argente & Van Patten (*Science*, 2023, n=1,800) find the barrier is demand-side: of Chivo downloaders, 3% received remittances in bitcoin and 89% received none. Chipper Cash claims 50% of its Bitcoin traffic runs on Lightning but publishes no performance data of any kind. River states remittances were **not** a driver of Lightning growth.

---

### Amendment 14 — 19 Aug 2026: Polygon's measured ceiling is a single-endpoint limit; the "graceful degradation" contrast is withdrawn

**What prompted it.** A supplementary test was run to answer an auditor's
objection that the ~270 payments/sec Polygon ceiling might be an artefact of a
transaction-queue size we never tuned. It found something else. Measuring
where the work actually landed during a 300/sec run showed the node serving
JSON-RPC at 84% busy while the three validators doing only consensus sat at
8–14% and the sending machine idled at 12%. Full evidence in
`POLYGON_RPC_BOTTLENECK.md`.

**Four changes follow, and all four affect published claims.**

**1. The ceiling is re-described, not re-measured.** On one cluster, changing
only where settlement checks are sent: 274.9/sec through one node (invalid,
the sender fell 228.6 ms behind) against **290.5/sec across four** (clean,
0.3 ms). That is on 4-processor validators, beating the published 270.5/sec
measured on 8-processor ones. Halving the validators changed nothing;
spreading the settlement checks changed everything.

Wherever the paper says Polygon Edge sustains ~270 payments/sec, it must say
**the measured throughput of this deployment**, with the single-endpoint
design stated. It is not established as a property of the sidechain
architecture, and the architecture's real ceiling is higher and unmeasured.

**2. The "Polygon degrades gracefully, NEAR collapses" contrast is
withdrawn.** With the bottleneck relieved the ramp was pushed past 300 for the
first time: 290.5 → 202.5 → 108.3 → 96.5 at 300/400/500/600 offered, every run
holding its schedule. Polygon collapses to a third of peak. The published
contrast was drawn from a ramp that stopped at 300/sec — Polygon's knee, not
past it — so "graceful degradation past the knee" described a region never
measured. Both architectures collapse. NEAR's is steeper (≈7% of peak at twice
peak offered against Polygon's 33%), so a difference in degree survives and
should be reported as such.

**3. The failure-mode claim is conditioned on the measurement method.** The
published finding that *every* Polygon failure was a submission rejection
holds for the single-endpoint configuration. With settlement checks spread,
the same cluster at 300/sec produced **zero** rejections and 2,758 payments
accepted-then-unsettled; by 600/sec rejections dominate again. Relieving the
bottleneck admits more payments and converts refusals into stuck payments.
Either failure mode may now only be reported alongside the configuration that
produced it.

**4. A blind spot in the saturation rule is disclosed, and the rule is NOT
changed.** The criterion tests whether scheduling lag *grows* across a run.
Re-applying it to all 498 runs changed zero verdicts, so it has been applied
uniformly. But absolute lag was never tested, and the published
`phase-2-full-stack` 300/sec runs sat at **562.8 ms p95 absolute lag** against
63.8 ms at 200/sec, while passing the growth test with 0.6 ms to spare.

The rule stands. It was pre-registered, it was applied correctly, its logic is
defensible — steady lag offsets every submission equally and does not reduce
the offered rate, whereas growing lag means ground is being lost — and
changing a rule after seeing which runs it would exclude is precisely what
pre-registration exists to prevent. The published figures reproduce exactly
from the raw database (270.5/sec at 300 offered). The absolute-lag numbers are
disclosed here as a limitation so a reviewer meets them in our own words.

**Status of the supplementary runs.** All exploratory: one run per load level,
4-processor validators rather than the published 8, and a changed measuring
instrument. They are sufficient to establish that the published framing is
wrong and insufficient to replace the numbers. Recorded under phases
`phase-6-endpoint-1`, `phase-6-endpoint-4` and `phase-6-endpoint-ramp`, and
excluded from results.

**The waiting-room (txpool) experiment that prompted all this is abandoned as
designed.** Beyond the bottleneck making it unmeasurable at 300/sec, it
carried a selection flaw worth recording: the enlarged queue accepts payments
the default refuses, so it generates more settlement checks, so it is more
likely to trip the saturation rule and be excluded. The treatment influences
the probability of exclusion, so comparing survivors is biased and no number
of repeats fixes it.

---

### Amendment 15 — 21 August 2026: a pre-registered test of whether NEAR's collapse at 200/sec belongs to the chain or to the one machine we asked

**Sections affected:** §2 (the primary outcome metric as it applies to NEAR),
§3 and §12. **Written before any of these runs produced a number**, which is
the only reason it belongs in this log rather than in the write-up afterwards.

**No rule changes.** The 10-second warm-up cut (§7), the 60-second settlement
budget (§6.2 and amendment 11), the lag-growth saturation criterion
(amendment 1) and NEAR's validator-liveness audit all apply to these runs
unchanged. A run that trips any of them is excluded exactly as a matrix run
would be.

**What prompted it.** Amendment 14 found that Polygon's published ceiling was
not Polygon's. Every question of the form *"has this payment finished yet?"*
was sent to a single machine, and that machine — not the chain — was what ran
out of capacity. Sending the same questions to four machines instead of one,
and changing nothing else, turned a published 270.5 payments/sec with 9.97%
failures at 300 offered into **300.4/sec with 0.00% failures**, five repeats
each side, with both arms indistinguishable at the 200/sec control step
(200.9/sec, no failures, on both). Those five-repeat figures are in
`POLYGON_RPC_BOTTLENECK.md` §5d; amendment 14 above still quotes the earlier
single exploratory run (290.5/sec), which it was written from.

**Why NEAR is suspected of the same fault, and why the suspicion is stronger
here.** NEAR's published collapse — **47.5/sec settled against 200 offered,
76.30% failing, 95% interval [26.3, 68.7]** — carries a failure reason that
states in words what Polygon's had to be measured to reveal: **`reached
EXECUTED, not FINAL`**. The chain accepted the payment and executed it. What
did not happen inside the 60-second budget was our *seeing* it become final.
At 200 offered, with the published measurements putting finality around 12
seconds at the median and 19 at the 95th percentile, roughly 4,000 payments
are unfinished at any moment, each of them asked after repeatedly — and every
one of those questions went to a single one of the eight machines running the
chain. That is a claim about our measuring equipment, not about NEAR, and it
can be tested in an afternoon.

**The pre-registered prediction: the four-endpoint arm settles materially more
than 47.5/sec at 200 offered.**

"Materially" is fixed now, before the runs, at **68.7/sec — the upper end of
the published cell's own 95% interval**. Taking the line from a number already
in print means it cannot be moved later to suit whatever comes back.

**The design.**

| | |
|---|---|
| Arms | `one` — every settlement check to a single machine, as published; `four` — spread one per region across the four continents |
| Loads | **100/sec** (control) and **200/sec** (the step in question) |
| Amount | **$200 only**, the World Bank benchmark size |
| Window | 300s, as everywhere else in the study |
| Repeats | **6 per arm per load**, with the arms alternating |
| Gap between runs | 120s, plus a check that the chain is still producing blocks |
| Phases | `phase-6-near-endpoints-one`, `phase-6-near-endpoints-four` |

**Why 100/sec is run at all.** It is the control, and it is what makes the
200/sec comparison readable. The published matrix puts $200 at 100/sec at
100.0/sec settled with 0.16% failures. If the rebuilt cluster does not
reproduce that in **both** arms, then it differs from the published deployment
in some way we have not identified, and **no 200/sec figure from this
experiment may be read against the published one**. The check has to be
capable of failing: on Polygon it failed twice, and both times the fault was
ours rather than the chain's — settlement checks running ahead of block
propagation, and a run started before the previous run's backlog had drained.

**Why six repeats rather than the usual five.** Whichever arm runs second in a
pair inherits whatever the first arm left unfinished, so a fixed order would
hand one arm a standing advantage. Six repeats split the favourable position
exactly three and three; five cannot. §5 sets five as a **minimum**, so six
satisfies the protocol rather than departing from it.

**Why the sending is not spread as well as the asking.** Only *where the
answers are sought* changes between arms; both arms submit through one
machine, as the published runs did. Spreading submission across continents was
tried on Polygon and made results roughly **ten times worse**: a sender holds
its account's counter locked for the whole round trip, so a slow
intercontinental hop holds it longer. NEAR orders transactions per access key
by nonce and has the identical weakness. Spreading the asking is safe;
spreading the sending is a different experiment with a known bad answer.

**What would refute the published collapse.** The four-endpoint arm at 200
offered settles above 68.7/sec, with the one-endpoint arm reproducing the
published cell beside it. Three gradations, all decided in advance:

1. **Above 68.7/sec but still failing the §2 bar** (achieved below 90% of
   offered, or 5% or more failures): the published 150/sec ceiling stands, but
   the *size* of the collapse at 200/sec was partly our own instrument, and
   the cell must be re-described in every document that quotes it.
2. **At or above 180/sec with failures under 5%**: 200/sec becomes a
   sustainable step under §2, and NEAR's published ceiling of 150/sec moves.
   The rest of the ramp then has to be measured before any new ceiling is
   claimed — a follow-on at 250 and 300 is already provided for in the run
   script, and no ceiling may be stated from two load levels.
3. **Between the two**, i.e. achieved at or above 90% of offered but failures
   at or above 5%, or the reverse: reported as the mixed result it is, with
   both figures given, and the ceiling left at 150/sec because §2 requires
   both conditions and not either.

**What would confirm it, and why that is equally usable.** If the four-endpoint
arm lands inside the published interval with failures still dominated by
`reached EXECUTED, not FINAL`, then the collapse is not an artefact of asking
one machine too many questions. It becomes a property of the architecture as
deployed — finality genuinely falling behind execution — and the NEAR chapter
stands as written, now with a specific alternative explanation tested and
excluded rather than merely unconsidered. **A refutation and a confirmation are
both results here.** That symmetry is deliberate: the experiment was designed
so that the outcome we would prefer (our published number survives) and the
outcome we would not (it does not) are equally reportable, which is what stops
this being a search for a better number.

**Standing of these runs against the published figures.** Amendment 14's
Polygon supplementary runs could only *re-describe* the published ceiling,
never replace it, because they ran one repeat per level on half-size machines.
This experiment is built to a different standard, and the difference is
deliberate:

- The eight machines running the chain are `n2-standard-8`, **identical to the
  published NEAR deployment**, in the same four regions, at the same 2s block
  cadence, with the same injected impairment, the same competing background
  traffic and the same 836-account sender pool.
- Six repeats per cell against the protocol's five.
- Every pre-registered exclusion rule applied unchanged.

Two honest differences, both stated here rather than left to be found:

- **The machine that sends the payments is twice the size it was** —
  `n2-standard-16` against the published `n2-standard-8`. It is the measuring
  instrument, not the system under test, and enlarging it can only move the
  ceiling away from our own tooling. Its capacity on the smaller machine was
  measured at 7,379 signed payments/sec (24.6× headroom at 300/sec), so this
  is precaution, not necessity — but it is a difference from the published
  runs and it is stated as one.
- **The token contract cannot be proven byte-identical to the one the published
  runs used**, because its version was never recorded (see `METHODOLOGY_LOG.md`
  §11c). Within this experiment it cancels: both arms move the same contract.
  Across campaigns it does not, so **no absolute gas or cost figure from these
  runs may be compared with the published NEAR gas figure** until that question
  is settled.

**Both new phases are held under their own labels and out of the clean results
dataset**, on the same reasoning that holds out every other phase-6 run: a
changed measuring method must never be quietly mixed into a published results
table. If they move a published figure, that happens through a further
amendment naming what moved and quoting these runs — which the hardware match
makes legitimate, and which amendment 14's Polygon runs could not support.

⚠️ **Recorded because it is a gap between this text and the code, of the kind
amendment 8 exists to disclose:** `analysis/export.py` carries an explicit list
of phase-6 phases to hold out of the clean dataset, and at the time of writing
**`phase-6-near-endpoints-one` and `phase-6-near-endpoints-four` are not in
it.** They must be added before the clean dataset is next rebuilt, or these
runs will flow into the results file and land in the same $200 cells as the
published five-repeat matrix. Nothing has been exported yet, so no figure is
affected today.


---

**16 — The impairment was not applied to the 22–23 Aug supplementary runs; both collections discarded and re-run. Added 23 August 2026.**

**What happened.** `scripts/inject_impairment_near.sh` held the internal
addresses of the cluster built on 11 Aug. The cluster was rebuilt on 21 Aug and
seven of the eight addresses changed. The script's delay and packet-loss rules
therefore matched traffic to machines that no longer existed, while it printed
`APPLIED` for every machine — it only checked that a delay rule existed, never
that anything was routed into it. Both supplementary collections of 22–23 Aug
(the endpoint A/B and a partial block-cadence leg) were measured on an
essentially unimpaired network and **cannot be compared against published runs
that paid the full penalty**. Both are discarded, archived rather than deleted
(`runs_unimpaired_22-23aug.sqlite`). Roughly $9 of machine time.

**Why it is recorded here rather than only in the operations log.** Amendment 15
pre-registered this experiment on the stated basis that everything except the
setting under test was held identical to the published campaign. That basis was
false for those runs. Anyone reading amendment 15 must reach this entry.

**Two further departures from amendment 15's stated design, both found in the
discarded collection.** It said six repeats per arm; five were run, under
deadline pressure, undocumented at the time. It also said the rebuilt cluster
used "the same 836-account sender pool"; the recovered 13 Aug disk image shows
the published campaign used 836 senders and the rebuild used 900. The 23 Aug
re-run uses six repeats as pre-registered; the sender-pool difference stands and
is disclosed.

**The token contract question, settled.** Amendment 15 said the rebuilt contract
could not be proven byte-identical to the published one and that nothing in the
repository could settle it. The 13 Aug disk images could, and do: the original is
**148,137 bytes** (sha256 `b0ec2f43…`), the rebuild **150,621 bytes**
(`756eb555…`). Different builds, beyond argument. The published gas figure of
2.214×10¹² belongs to the 148,137-byte build. The original bytes are committed at
`data/reference/contracts/fungible_token_ORIGINAL_13aug.wasm`.

**The capacity-test claim, narrowed.** `generator_is_not_the_ceiling.md` claimed
the null-backend validation proved NEAR's measured ceiling belonged to the chain
and not our tooling. It does not. That backend answers "is this payment done?"
by sleeping and makes no network calls, whereas NEAR's adapter asks the network
about every waiting payment five times a second. The test validates the
scheduler and is silent about the watcher. Amendment 12.5's parenthetical
attributing NEAR's lag drift to congested RPC "per the null-backend validation"
is withdrawn on the same grounds.

**What the corrected 23 Aug campaign then showed, and why it matters to this
plan.** With the impairment verified applied per machine, **all 12 runs at
200/sec failed the saturation rule in both arms, and every one of the 24
exclusions across all 44 runs was our own program falling 0.32–0.74s behind a
50 ms limit. None was the chain.** Impairment slows settlement, more payments
wait, and a watcher that asks per payment saturates before the chain does. The
consequence for this plan is concrete: **the endpoint question of amendment 15
is not answerable at 200/sec with the present watcher**, and no figure from that
load may be published from either arm until the instrument is no longer the
binding limit.

**Block cadence (the amendment 12.1 queue), first measurement.** At 2000 ms
blocks settlement was p50 12.20s / p95 15.07s; at 1200 ms, **p50 7.18s / p95
8.20s** — the decision rule's 10-second bar is failed at the published cadence
and passed at 1200 ms, and the 1.70 ratio tracks the 1.67 cadence ratio as
theory predicts. **This does not yet meet this plan's five-repeat minimum**
(n=1 and n=2 survived) and may not be quoted as a result until re-run. It is
recorded now because it bears directly on the §10 latency disqualification.

**Why a straight re-run is not the fix, with the numbers.** The survivors are
not the runs where our instrument behaved; they are the runs where its
misbehaviour happened to be *steady*. Scheduling lag, p95, per run:

| Cadence | Load | Runs | Survived | p95 lag of each run |
|---|---|---|---|---|
| 1200 ms | 100/sec | 3 | 1 | 0.10, 0.41, 0.42 |
| 1200 ms | 150/sec | 3 | 1 | 0.18, 0.55, 0.56 |
| 2000 ms | 100/sec | 3 | 1 | 0.24, 0.42, 0.42 |
| 2000 ms | 150/sec | 4 | 2 | 0.31, 0.32, 0.55, 0.55 |

Every run, including all five survivors, sat far above the 50 ms threshold in
*magnitude*. They passed because amendment 1's rule tests lag **growth**, and
theirs was high but flat — the blind spot §4 of `RESUME_HERE.md` already
records. Repeating the sweep unchanged would therefore buy roughly the same
one-or-two survivors per cell for roughly the same money, so it is not
scheduled.

**What that does and does not do to the finding.** It rules out reading these
latencies as precise. It does not overturn the direction or the magnitude: the
gap between cadences is **5.0 s** (12.20 s against 7.18 s) while the largest
instrument lag in any surviving run is **0.31 s**, an order of magnitude
smaller and — note the table — *larger* on the slower cadence, which is the
direction that would shrink the gap rather than manufacture it. The ratio also
tracks the cadence ratio (1.70 against 1.67), which an instrument artefact has
no reason to do. Treat it as a strong preliminary result whose confirmation is
blocked on the watcher, not on more machine time.


---

**17 — Data collection closed. Added 24 August 2026.**

Angad closed data collection on 24 Aug 2026, with roughly $124 of the $300
budget spent. This entry fixes what that decision means so nothing is later
promoted by drift.

**The matrix of record is unchanged**: the datasets frozen on 13 Aug (Polygon
140+15, NEAR 118 measured + 22 sensitivity + 15, Lightning per amendment 5)
remain the paper's evidence base, and every published figure recomputes from
them.

**The supplementary questions close in the following states.** The block-cadence
comparison stays a preliminary sensitivity finding — direction and size are
strong (5.0 s gap against 0.31 s worst instrument error, ratio tracking the
cadence ratio) but survivorship is n=1/n=2 against the §8 five-repeat minimum,
so it may be cited only as preliminary, and amendment 16 records why simple
repetition cannot raise n. The attribution of the published 200/sec cell
remains open; that cell keeps its conditioning wherever it appears. The
original-contract test and the full-spec Polygon re-measurement were not run;
the corrected Polygon knee stands as a floor argued from smaller machines
(amendment 14).

**Infrastructure is deleted, data is not.** Both clusters and their networks
were destroyed by terraform on 24 Aug after collection. The discarded
unimpaired collection that amendment 16 promised as "archived rather than
deleted" was pulled off the generator's disk before deletion and now lives at
`data/near_supplementary/runs_unimpaired_22-23aug.sqlite` (repository working
tree, gitignored for size), with its 15 block-cadence runs additionally
committed as `unimpaired_blocktime_raw.parquet` and its 20 endpoint runs
already committed as `ab_raw.parquet` — every discarded payment therefore
remains inspectable. The nine 13-Aug disk snapshots are retained in
`project-c4c87dcb-da41-4caf-922` as the only surviving copy of the original
campaign's machines (validator health log, original contract); they are the
sole remaining billing item.

**Resumption path** is written in `RESUME_HERE.md`'s top box, including the
gate: nothing measures at 200/sec until the instrument question is resolved.
