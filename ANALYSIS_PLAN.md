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
