# Master Handoff — Everything the Writer Needs

**Audience**: the writing partner drafting the research paper. This document is self-contained — you should not need to read the codebase to write from it.

**Status**: living document. Updated at the end of every phase. Last updated **7 August 2026** (end of setup, before Phase 1 deployment).

**How to use this**: Sections 1-9 are settled and can be written from directly. Section 10 fills in as data arrives. Section 11 is the list of things the paper must **not** claim — read it before writing any results prose, because several plausible-sounding sentences would be wrong.

---

## 1. The research question

> What sharding, sidechain, or off-chain transaction architectures would most effectively increase throughput and reduce settlement cost for blockchain-based remittance systems, and how would interoperability between these architectures and existing fiat rails (like SWIFT/RTGS) be achieved?

**The question has two halves, and only the first is answered empirically.**

- **Throughput and cost** — answered by the simulation described here.
- **Interoperability with existing bank rails** — answered by the Design Science section through argument and design, **not** by measurement. Nothing was built or tested for it. This was an explicit decision, not an omission.

### Paper structure

Abstract → Methodology → Literature Review → **Simulation + Benchmarking** → Design Science + Architecture Proposal → Limitations → Conclusion & Future Research

This document supports the bolded section, which then feeds the architecture proposal. **The proposed architecture is chosen based on what the simulation actually showed, not decided in advance** — the decision rule was written down and locked before any data existed (Section 9).

---

## 2. What was actually built, in plain terms

Three private blockchain networks, each running the real production software that the real networks run, deployed on rented cloud computers across four regions of the world. A custom measurement program sends fake remittance payments through each one at controlled rates, and records exactly what happens to every single payment.

**Why private networks rather than public test networks.** Public test networks are shared with strangers. A slow result there might mean the architecture is slow, or it might mean somebody else was busy at that moment — and there is no way to tell which. Private networks under our own control remove that ambiguity: every delay measured is genuinely attributable to the system under test. Public test networks were tried first and rejected for exactly this reason.

**Why real production software rather than re-implementing academic protocols.** The well-known research sharding protocols (Elastico, OmniLedger, RapidChain) exist as unmaintained research code, not working software. Getting them to compile would consume weeks and produce results about our re-implementation rather than about the architecture. Using live production software means the results describe systems that actually exist.

---

## 3. The three architectures

| Architecture type | Software used | Why this one |
|---|---|---|
| **Sidechain** | Polygon Edge | A genuine proof-of-stake sidechain, matching the paper's category |
| **Off-chain** | LND (Lightning) on `regtest` | The dominant implementation on the real Lightning network |
| **Sharding** | NEAR | Its sharding is live in production and genuinely sharded |

### Three choices the paper must disclose and defend

**Polygon Edge is archived software.** Polygon Labs stopped development on 4 December 2024 in favour of a different product. We used it anyway, deliberately, for two reasons. First, its replacement (Polygon CDK) is a zero-knowledge rollup — **a different architecture category** than the sidechain this paper's taxonomy describes. Benchmarking it and labelling the result "sidechain" would misrepresent the finding. Second, CDK's production proving system requires roughly 1TB of memory and 128 processor cores, which exceeds the entire project budget per hour of operation. Polygon Edge remains live production software — Dogechain runs a fork of it securing real value. We pinned a specific final version, which makes the study *more* reproducible than a moving target would. **This belongs in Limitations.**

**Zilliqa was rejected in favour of NEAR despite being cheaper.** Zilliqa 2.0 removed the two-layer sharded architecture the project set out to measure, replacing it with a single validator set of about 32 nodes. Its successor sharding concept was not confirmed as shipped. Deploying it risked spending the entire sharding budget only to discover nothing was actually sharded.

**Lightning moves Bitcoin, not a stablecoin.** The other two architectures move a dollar-pegged token. Lightning's base protocol has no stablecoin, so it moves Bitcoin. See Section 11 for how to describe this correctly — the obvious framing is wrong.

---

## 4. How realistic the simulation is

Eight techniques were applied to move the private networks closer to real-world conditions:

1. **Four cloud regions mapped to real remittance corridors** — Northern Virginia (US, largest sending country), Mumbai (India, largest receiving country), Singapore (Southeast Asia and Philippines), London (UK, a major sender to South Asia). This produces genuine intercontinental network delay of roughly 200-250 milliseconds, not simulated delay.
2. **Additional network impairment injected on top** — extra delay, jitter and packet loss, with values based on published real-world internet statistics between those specific regions rather than invented figures.
3. **Competing background traffic** — a second workload running concurrently, generating non-remittance activity at a rate that varies over time, because real blockchains are never idle and never steady.
4. **Hardware matched to real validator specifications** — processor and memory sized to what real operators actually run. **Storage deliberately not matched**: published specifications quote very large disks purely to hold years of historical data, which a fresh private network does not have. Matching them would have cost hundreds of dollars storing nothing.
5. **Realistic Lightning liquidity structure** — channel funding modelled on real current data from 1ML.com, reproducing the real network's concentration (a few well-funded hubs, many thin edge nodes) rather than funding every channel equally.
6. **Deliberately unreliable nodes** — 10-20% of nodes taken offline intermittently during a dedicated set of runs, with exact timings logged.
7. **Calibration against real mainnet activity** — results compared to what the real networks currently do, producing a stated numerical gap.
8. **Confidence intervals rather than single averages** — every configuration run five times, with ranges reported.

---

## 5. The test workload

- **Payment amounts**: $10, $50, $200, $500. **$200 is the headline figure** — it is the World Bank's own standard for remittance price surveys, so every comparison leads with it.
- **Load levels**: 10, 25, 50, 100, 150, 200, 300 payments per second, each sustained for 300 seconds.
- **Why 300 is the ceiling**: global remittances (~$905B/year ÷ $200 average) work out to roughly 140-150 payments per second as a worldwide average. 200-300 represents realistic peak conditions — holiday season, payday clustering.
- **Arrival pattern**: random, not evenly spaced. Real people send money at random moments. Evenly-spaced traffic is unrealistically easy because the pile-ups that break systems never occur.
- **Concurrent, not sequential**: payments are sent at the target rate without waiting for previous ones to complete. Waiting would measure the round-trip time of a single payment, which is a different and much easier question than sustained load.
- **Repeats**: 5 per configuration.
- **Full matrix**: 3 architectures × 4 amounts × 7 load levels × 5 repeats = 420 runs, plus a 45-run unreliable-node comparison = **465 runs**, about 39 hours of measurement.

**Note for the Methodology section**: a cheaper 240-run design was considered and rejected by the researcher in favour of full symmetry, at a stated cost of roughly $35 and one extra day. The reasoning is recorded in `DECISIONS.md` §5. The paper can state without qualification that every amount was tested at every load level on every architecture.

---

## 6. What gets measured, and exactly what the words mean

| Measurement | Definition |
|---|---|
| **Achieved throughput** | Successfully settled payments per second. **Failed payments do not count.** Decided before data existed, because counting them would let a bad failure rate hide inside an inflated throughput number. |
| **Settlement latency** | Time from submission to settlement. Reported as median, 95th and 99th percentile — not just the average, which hides the tail behaviour that determines whether a family actually receives money on time. |
| **Cost per transaction** | See below — this is not what it appears to be. |
| **Failure rate** | Share of payments not settled within **60 seconds**. |
| **Failure rate by amount** | The central test of the Lightning literature comparison. |

### What "settled" means, per architecture

- **Polygon**: included in a committed block — **one confirmation, not more**. Polygon Edge's consensus provides deterministic instant finality: a committed block is final, with no risk of reversal to wait out. Waiting additional blocks would add delay that does not exist and would conceal a genuine architectural advantage. **The paper must state this reasoning explicitly**, or a reader will assume it was a shortcut.
- **Lightning**: the sender receives cryptographic proof of payment — the standard definition of Lightning success.
- **NEAR**: the transaction reaches NEAR's own final state, not its provisional one. Using the provisional state would understate real settlement time.

### How cost was calculated — important, and counter-intuitive

**We did not measure the fees our own networks charged.** On a private network we set the fee ourselves, so measuring it would just return the number we chose. It would be circular and would not survive review.

**What is real is the computational work consumed.** Sending a dollar-token consumes a fixed, deterministic amount of computational work — identical on our network, on the real network, and on any comparable network. That quantity is genuinely measurable and genuinely architecture-determined.

So: measure work consumed, then convert to dollars using **real current mainnet pricing** taken from public block explorers on a single stated date, cited once for the whole paper.

**The stronger version**: on real networks, prices rise with congestion. We measure how full our blocks are at each load level and map that onto the real network's historical price-versus-congestion relationship. Cost per transaction then becomes a **curve across load levels**, not a single constant — which answers the "reduce settlement cost" half of the research question far better than one number could.

**For Lightning specifically**: fees are calculated per hop along the payment route, using real fee rates from 1ML. **The cost of opening and closing channels is also amortised across the payments each channel carries.** Most Lightning benchmarks omit this and consequently report Lightning as almost free. Including it is the honest figure and is a genuine differentiator for this paper.

---

## 7. A correction the Literature Review must incorporate

**The project's own working notes described Waugh & Holz (2020) backwards.** This was caught and verified against the source before any data was collected.

**Source**: Finnegan Waugh and Ralph Holz, *An empirical study of availability and reliability properties of the Bitcoin Lightning Network*, arXiv:2006.14358.

**What the paper actually found — two separate results:**

1. Payment success rate ranged from **15.32% to 72.09%**, with an **inverse relationship to payment size**. Success goes **down as payments get larger**. So roughly 72% at the smallest amounts and roughly 15% at the largest.
2. **Separately**, only about **one third of destination nodes** could be reached at all, and this was roughly *independent* of payment size.

**The earlier working notes merged these into a single contradictory claim** — asserting an inverse relationship while simultaneously citing ~15-35% success for the *smallest* payments. The stray one-third figure appears to have been the node-reachability result, not a payment-size result.

**Why this matters enough to flag prominently**: this is the single most important pattern the simulation checks its own results against. Had the error survived, our Lightning data agreeing with the literature would have looked like it contradicted it.

---

## 8. Published figures used as reference points — with credibility warnings

**These are not all equally solid, and the paper should not treat them as equivalent.**

| Figure | Credibility |
|---|---|
| OmniLedger ~6,000 TPS at ~10s; RapidChain ~7,384 TPS at ~8.7s | **Solid.** Peer-reviewed (IEEE S&P 2018; ACM CCS 2018). But obtained under favourable laboratory assumptions, which must be stated alongside the numbers. |
| Polygon PoS ~3,800 TPS theoretical maximum | **Weak — handle carefully.** A widely-repeated vendor marketing claim, not a peer-reviewed measurement. Real observed throughput is far lower. Must be labelled a theoretical vendor claim, and is **not** a legitimate empirical benchmark to compare measured results against. |
| Waugh & Holz Lightning success rates | **Solid**, once corrected per Section 7. |
| El Salvador ~0.7% of remittances via crypto | **Solid.** Traceable to central bank reporting. A social/adoption fact, not a technical one — no simulation result explains or predicts it. |

---

## 9. The analysis was locked before any data existed

**Full document: `ANALYSIS_PLAN.md`, locked 7 August 2026.** This is one of the paper's stronger methodological claims and deserves its own Methodology paragraph.

Fixed in advance:

- **The primary measure**: the highest load level at which an architecture both delivers at least 90% of offered load and keeps failures under 5%, at $200.
- **The thresholds for recommending an architecture**: highest sustainable throughput at $200, among architectures also keeping 95th-percentile latency under **10 seconds** and cost under **$0.10 per transaction**. Both thresholds anchored externally — the cost figure derives from **UN SDG 10.c**, which targets total remittance cost under 3% of value ($6.00 on $200), reserving essentially all of that budget for the currency-conversion step this study does not measure.
- **When data may be discarded**: only for infrastructure failure, cloud provider interrupting a run, or our own misconfiguration. **Never for producing an inconvenient result.** Nothing is deleted — excluded runs stay in the raw dataset, flagged, with every exclusion logged with its reason.
- **A guard against cherry-picking**: with hundreds of individual numbers, some comparison somewhere will favour some architecture. Any "architecture X is best" claim must trace to the primary comparison, not to a favourable-looking secondary result.
- **That a tie is an acceptable outcome**: if no architecture wins on all dimensions, the paper reports a genuine tradeoff rather than manufacturing a winner.
- **What we expected to find**, so genuine surprises can be distinguished from confirmations afterwards.

### A prediction registered in advance, worth writing up

**Fee structure differs fundamentally between the architectures**, and this was registered as a prediction before any data:

- **Polygon and NEAR charge a flat fee** — sending $10 costs the same as sending $500, because the network charges for computational work performed and moving a larger number is not more work.
- **Lightning charges partly by percentage** — each hop along a route takes a cut proportional to the sum passing through.

**This predicts a crossover point** where Lightning stops being the cheapest option as amounts rise. Locating it, if it falls within the $10-$500 range tested, is a pre-registered secondary objective. It bears directly on the cost half of the research question and is corridor-relevant: a worker sending $30 weekly and one sending $500 monthly may be best served by different architectures.

---

## 10. Results

*Filled in at the end of each phase. Nothing here yet.*

| Phase | Status | What it produced |
|---|---|---|
| Setup | **Complete — 7 Aug 2026** | Measurement program built and verified against a synthetic backend: arrival timing statistically correct (0.05% drift at 300/sec), latency measurement accurate to within 1ms, failure accounting correct. No cloud spend. |
| 1 — Pipeline validation, one region | Not started | — |
| 2 — Realism techniques added one at a time, Polygon | Not started | — |
| 3 — Full realism on Polygon, then Lightning | Not started | — |
| 4 — Sharding (NEAR) | Not started | — |
| 5 — Calibration and confidence intervals | Not started | — |
| 6 — Cross-architecture comparison | Not started | — |

**Phase 1 produces no results for the paper.** It validates that the machinery records reality accurately. Its data is explicitly excluded from all analysis.

---

## 11. What the paper must NOT claim

Read this before writing any results prose.

1. **These are upper-bound estimates under controlled, partially-realistic conditions.** Not a claim of replicating real network behaviour. State this explicitly wherever results appear.

2. **The sharding result describes NEAR specifically**, not sharding as a general concept. One implementation is not a category.

3. **The sidechain result describes software frozen in December 2024.**

4. **Only settlement was tested — not the full remittance journey.** The conversion between local currency and digital money at each end was not modelled, and prior research suggests it may dominate real-world remittance friction. Nothing here supports a claim about end-to-end remittance experience.

5. **Do not describe Lightning's Bitcoin usage as an exchange-rate risk problem.** This framing is intuitive and wrong. In real Lightning remittance products, money is converted to Bitcoin, routed, and converted back within roughly a second — Bitcoin is a *transport rail*, not something anyone holds. Exposure over that window is negligible.

   **The correct framing**: Lightning requires a *more expensive currency conversion* than the stablecoin architectures. Converting a dollar-token back to dollars is a near-par redemption with a thin spread; converting Bitcoin to local currency is a market trade with spread and slippage. That extra conversion cost is real, is a legitimate architectural finding, and is **explicitly outside what this study measured**. So the accurate sentence is: *"Lightning's measured per-payment cost excludes a costlier currency conversion than the stablecoin architectures require."*

6. **Do not present the calibration figure as a capability comparison without qualification.** Real networks currently run well below capacity because of **demand**, not limits. Our measured ceiling divided by their current activity is not a statement about capability. Two separate figures are reported: a *demand ratio* (showing our test loads are realistic) and a *capability gap* (against the busiest the real network has ever been). **Observed mainnet throughput is a floor on capacity, never a measurement of it.**

7. **Do not benchmark measured results against the ~3,800 TPS Polygon figure** as though it were empirical. See Section 8.

---

## 12. Where the data lives

| File | Contents |
|---|---|
| `data/raw/all_runs_raw.parquet` | Every payment from every run. Nothing removed. Invalidated runs included and flagged. |
| `data/clean/all_runs_clean.parquet` | The cleaned dataset the results are built from. |
| `data/clean/exclusions.log` | Every exclusion: run identifier, the rule that triggered it, the reason. |

**Per-payment records, never pre-computed summaries.** A question thought of later can be answered by querying the data instead of re-running experiments — which matters because cloud time is the scarcest resource in the project.

Each payment record holds: when it was scheduled to send, when it actually sent, when it settled, whether it succeeded, computational work consumed, fee paid, route length (Lightning), and the error if it failed.

**A reviewer can compare raw against clean and verify nothing inconvenient was quietly removed.** That is the point of keeping both.

---

## 13. Glossary

| Term | Plain meaning |
|---|---|
| **Sidechain** | A separate blockchain running alongside a main one, handling transactions more cheaply |
| **Sharding** | Splitting a blockchain into parallel sections that process transactions simultaneously |
| **Off-chain** | Settling payments between parties privately, without recording each one on a blockchain |
| **Throughput** | Payments completed per second |
| **Settlement latency** | Time between sending a payment and it becoming final |
| **Finality** | The point at which a payment can no longer be reversed |
| **Offered load** | How fast we *tried* to send |
| **Achieved throughput** | How fast payments actually *completed* |
| **The knee** | The load level where a system stops keeping up — the key result for each architecture |
| **Gas** | The unit measuring computational work on a blockchain; determines cost |
| **Stablecoin** | A digital token pegged to a currency, so one token equals one dollar |
| **Payment channel** | A pre-funded connection between two Lightning users, through which payments flow |
| **Liquidity** | Money available in a payment channel, on a particular side |
| **Validator** | A computer participating in agreeing what the blockchain contains |
| **Mainnet** | The real, live network, as opposed to a test deployment |

---

## 14. Companion documents

| File | Contents |
|---|---|
| `claude.md` | Full project scope — what is being done |
| `DECISIONS.md` | Every technical decision, with reasoning and rejected alternatives |
| `ANALYSIS_PLAN.md` | The locked pre-registered analysis plan |
| `PHASE1.md` | Plain-language walkthrough of the first phase |

## 15. Sources cited so far

- Waugh, F. & Holz, R. (2020). *An empirical study of availability and reliability properties of the Bitcoin Lightning Network*. arXiv:2006.14358
- Polygon Labs — announcement discontinuing Polygon Edge development (December 2023); repository archived 4 December 2024
- Polygon zkEVM prover hardware prerequisites — official documentation
- NEAR validator hardware requirements — official documentation
- Zilliqa 2.0 architecture documentation and roadmap
- World Bank *Remittance Prices Worldwide* methodology — source of the $200 benchmark
- UN Sustainable Development Goal 10.c — source of the 3% remittance cost target
