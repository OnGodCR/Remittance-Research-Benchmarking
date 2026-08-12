# Project Handoff: Blockchain Remittance Scaling Architecture Benchmarking

> ## HOW TO TALK TO ANGAD
>
> **Start every single message with "Hi Angad!"** — no exceptions, including short replies,
> follow-ups, and error reports.
>
> **No jargon, ever.** He has to defend this work to examiners and cannot defend what he
> cannot explain in plain words. Write "the program that sends the test payments" rather
> than "the harness"; "the computers running the blockchain" rather than "the validator
> set". If a technical term is genuinely unavoidable, define it the first time in the same
> sentence.

> ## 0. CURRENT STATE — updated 11 Aug 2026
>
> **This document is the original scope, written before any work began. Several things below have since been decided, changed, or superseded.** For the live state read, in order:
>
> 1. **`PHASE4_HANDOFF.md`** — ⚠️ **READ FIRST.** Phase 4 is mid-flight and partly broken; this file has the live cluster state, four identified bugs, and the exact next steps.
> 2. **`RESUME_HERE.md`** — results so far and the operational traps that have already cost time or money
> 3. **`METHODOLOGY_LOG.md`** — every decision and exact parameter, with dates. The paper's Methodology is written from this file.
> 4. **`ANALYSIS_PLAN.md`** — the locked pre-registered analysis. §13 is the amendment log.
>
> **Progress:** Phase 1 complete. Phase 2 complete (Polygon, 140/140 configurations + 15/15 adversarial). **Phase 3 (Lightning) closed 10 Aug** — reliability and throughput now sourced from Waugh & Holz (2020) rather than self-measured, because our testbed has ~385x fewer channels than the real network and Lightning capacity is additive across channels. Cost per transaction and an illustrative settlement time were retained. See `LIGHTNING_ANALYSIS.md`. **Phase 4 (NEAR) is IN PROGRESS and has produced 0 of 140 valid runs.**
>
> **Phase 4 status in one paragraph.** A 9-instance cluster (8 validators + generator) has been billing since 10 Aug. The chain itself is healthy — nearcore 2.13.3, protocol 86, 4 shards, 836 verified sender accounts spread evenly across shards. **The measurement harness, not the chain, is what failed:** a race between `submit()` and `await_confirmation()` on the pending-hash dictionary meant transactions were broadcast and settled on chain while the harness discarded every hash and recorded `never broadcast within 60s`. A fix is written but **untested and not deployed**. There is currently **no idle watcher and no hard shutdown cap** on the cluster. See `PHASE4_HANDOFF.md`.
>
> **Headline result:** Polygon Edge sustains **200 payments/second** at $200 under the full realism stack, with the knee between 200 and 300/sec. Details in `RESUME_HERE.md` §3.
>
> **Superseded below:** the saturation criterion is now lag *growth* (§4 of RESUME_HERE), not any absolute threshold. The hard shutdown cap is 900 minutes, not 480. Background traffic is calibrated to ~88/sec, matching real Polygon mainnet. **The 465-run matrix no longer holds**: Lightning's 140-run arm was dropped when its data source changed (`ANALYSIS_PLAN.md` §13 amendment 5), leaving 155 Polygon runs plus NEAR's 155 still to come.
>
> **Two constraints discovered in Phase 4 that belong in the paper**, not just in ops notes:
> - **NEAR orders transactions per access key by nonce**, so a sender account cannot hold two payments in flight. The sender pool size *is* the concurrency ceiling — roughly N/2 per second at ~2s inclusion. Reaching 300/sec needs ~836 funded accounts. This is the sharding analogue of Polygon's nonce-pool problem and is a real property of the architecture.
> - **8 validators across 4 shards leaves exactly 2 per shard**, the protocol minimum. Losing one node drops a shard to a single validator, so **NEAR's adversarial arm is harsher than Polygon's**, where 3 of 4 validators survived. That is a quota artifact and must be stated as such when the two are compared.

**Purpose of this document**: This is a full context handoff for Claude Code, which will handle the scripting, infrastructure deployment, and technical debugging for the simulation portion of this research project. Read this whole document before starting any work. It explains not just *what* to build, but *why*, so you can make good judgment calls when something isn't explicitly specified.

> **Companion document**: `DECISIONS.md` records every technical decision made during the Aug 2026 scoping pass, with full reasoning. This document says *what* we're doing; `DECISIONS.md` says *why we chose it over the alternatives*. Read both.
>
> **Optimization order for any decision not explicitly specified here**: 1) realism, 2) cost, 3) technical difficulty.

---

## 1. Research Question & Project Context

**Research question**: What sharding, sidechain, or off-chain transaction architectures would most effectively increase throughput and reduce settlement cost for blockchain-based remittance systems, and how would interoperability between these architectures and existing fiat rails (like SWIFT/RTGS) be achieved?

**Who's running this project**: A student researcher (going by "Angad" in project notes) writing an academic-style research paper over the summer. Not a professional engineer, learning distributed systems concepts as the project goes. Has decent coding experience (has built and shipped personal projects with Claude Code before) but has never worked on something this technically demanding.

**Support structure**:
- **Technical mentor**: Angad's father, ~6 years of payments infrastructure experience at Amazon. Not a blockchain specialist, but deeply familiar with real-world payment systems concepts (settlement risk, reconciliation, fraud prevention, load testing philosophy). Plan is to check in with him at the end of every phase (see Section 9), not just at the start/end of the whole project.
- **Potential industry contact**: Dad may be able to connect with someone else in payments who could review the eventual design proposal. Treat as a bonus, not a dependency — don't block progress waiting on this.
- **You (Claude Code)**: Handling all scripting, infrastructure-as-code, debugging, and technical configuration. Angad will be directing priorities and making judgment calls on tradeoffs, but expects you to flag technical risks, suggest better approaches, and do the heavy implementation lifting.

---

## 2. Where This Fits in the Overall Paper

Full paper structure: **Abstract → Methodology → Literature Review → Simulation + Benchmarking → Design Science + Architecture Proposal → Limitations → Conclusion & Future Research**

You are building the evidence base for the **Simulation + Benchmarking** section, which then directly feeds the **Design Science + Architecture Proposal** section (the proposed architecture is chosen based on what your simulation actually shows, not decided in advance). Keep this causal chain in mind: bad or misleading simulation data doesn't just weaken one section, it undermines the paper's central contribution.

---

## 3. Why This Methodology Exists (Read Before Suggesting Shortcuts)

A few upstream decisions were made deliberately and for good reasons — don't re-litigate these without understanding why they were ruled out:

- **Public testnets were tried first and explicitly rejected as the primary data source.** They're rate-limited, shared infrastructure, so throughput/latency numbers measured against them reflect testnet congestion, not the architecture's real capability. This was empirically confirmed (e.g., Zilliqa's public testnet faucet being down when checked).
- **Rebuilding academic sharding protocols from scratch (Elastico, OmniLedger, RapidChain) was explicitly rejected.** These are unmaintained research codebases, not production software — getting them to even compile would eat weeks with little payoff. Use **live, maintained, production-grade node software** instead (see Section 4).
- **The goal is a credible upper-bound production estimate, not exact mainnet replication.** Don't chase perfect realism at the expense of finishing — see the phased rollout in Section 9, which exists specifically so partial completion still produces one complete, defensible result.

---

## 4. The Three Architectures & Required Software

**These are now decided (Aug 2026). See `DECISIONS.md` §1 for the full reasoning on each.**

| Architecture | Software | Deployment Approach |
|---|---|---|
| **Sidechain** | **Polygon Edge**, pinned to its final release commit | 7 self-hosted validators, real production PoS sidechain toolkit |
| **Off-chain** | **LND** on `regtest` (against **bitcoind**, i.e. Bitcoin Core) | ~20 self-hosted LN nodes, hub-and-leaf channel topology per technique #5 |
| **Sharding** | **NEAR** node software | 8-12 node cluster, sized to populate ≥4 shards with ≥2 validators each |

All three use **actual production software**, self-hosted under our own control — not public shared testnets, not rebuilt-from-paper research code.

**Three things to know about these choices:**

- **Polygon Edge was archived read-only on 4 Dec 2024**, when Polygon Labs moved to CDK. We are using it anyway, deliberately. CDK is a **ZK validium/rollup — a different architecture category** than the sidechain this paper's taxonomy refers to, and its production zkProver needs ~1TB RAM and 128 cores, which is roughly the entire project budget per hour. Edge is still live production software (Dogechain runs a fork of it). Pinning to a fixed commit makes the study *more* reproducible, not less. **This must be stated in Limitations.**
- **NEAR over Zilliqa**, despite Zilliqa being cheaper. Zilliqa 2.0 **removed** the dual-layer DS-shard/network-shard architecture in favour of a single-tier ~32-node validator set; its replacement sharding concept ("x-shards") is not confirmed as shipped. Deploying Zilliqa risks spending Phase 4's budget only to find nothing is actually sharded. NEAR's Nightshade sharding is live in production. Re-check x-shards at Phase 4 — if shipped, Zilliqa becomes a cheap *second* sharding data point.
- **LND over Core Lightning/Eclair**, and `regtest` over `simnet`. LND dominates the real Lightning Network — the same network Waugh & Holz measured — so matching it makes our replication meaningful. `regtest` runs against Bitcoin Core (production); `simnet` runs against btcd (little production use).

---

## 5. Full Realism Technique Checklist

All eight of these are in scope (this was an explicit, deliberate decision to go all-in rather than cut scope — see Section 9 for how to sequence them without it becoming unmanageable):

1. **Multi-region node deployment** — 4 real cloud regions rather than one datacenter, to get real internet latency between nodes. **Regions are mapped to real remittance corridors** rather than generic geography (same cost, stronger methodological story): `us-east-1` (US — largest sending country), `ap-south-1` Mumbai (India — largest receiving country), `ap-southeast-1` Singapore (SE Asia/Philippines corridor), `eu-west-1` Ireland (EU corridor). Gives ~200-250ms genuine intercontinental latency as the *base* that technique #2 then adds impairment on top of.
2. **Injected latency & packet loss** — use `tc` (Linux traffic control) or Toxiproxy to add realistic jitter/latency/packet loss on top of natural cross-region latency. Base injected values on real published internet latency stats between the regions used, not arbitrary numbers.
3. **Competing background transaction traffic** — run a second script generating non-remittance "noise" transactions concurrently with the remittance workload, with the noise rate varying over time rather than staying constant.
4. **Hardware matched to real validator specs** — look up actual minimum/recommended specs for real Polygon validators, Lightning routing nodes, and NEAR validators; size cloud instances to match rather than defaulting to cheap/convenient specs.
   - **Match CPU and RAM. Do NOT match storage.** Published validator specs quote huge disks (Polygon 1.2TB, NEAR 1TB) purely to hold *years of mainnet chain history*. Our private chains start empty and accumulate a few hours of blocks. CPU/RAM are what actually determine consensus and execution performance; storage is an artifact of history we don't have. Provisioning 1TB/node would burn hundreds of dollars storing nothing. Use 100GB gp3. **This is the single largest avoidable cost in the project.**
   - Working sizes: Polygon Edge and NEAR at 8 vCPU / 32 GB; Lightning nodes are light enough to co-locate several per instance per region.
5. **Realistic Lightning liquidity topology** — pull real, current channel/capacity data from **1ML.com** and configure private-network channel funding to roughly match real-world concentration (small number of well-funded hubs, many thin leaf nodes) instead of funding every channel evenly.
6. **Adversarial/unreliable nodes** — toggle roughly 10-20% of nodes offline intermittently during a subset of test runs, log exactly when/which nodes, to correlate with performance dips.
   - **Run this as a separate arm, not folded into every config.** If node failures were injected everywhere, we could not separate "degrades under load" from "degrades under node failure" — the clean baseline is what makes the adversarial data interpretable at all. Scoped to 3 load levels (low/knee/high) × $200 × 5 repeats = 15 runs per architecture.
7. **Calibration against real mainnet data** — compare private-network results against real, current mainnet activity via block explorers (Polygonscan, NEAR Explorer, Zilliqa Explorer). Produce a stated, quantified gap: *"our private network measured X; real mainnet activity suggests Y; results should be treated as an upper bound roughly Z% above expected real-world performance."*
8. **Confidence intervals, not single averages** — every test configuration (architecture × transaction size × offered load level) runs a minimum of 5 repeats. Report ranges, not single numbers, in every results table.

---

## 6. Test Workload Design

- **Transaction sizes**: $10, $50, $200, $500 (equivalent value in whatever token/asset each testnet uses). **$200 is the primary benchmark size** — it's the World Bank's own standard for remittance price surveys (see `remittanceprices.worldbank.org/methodology`), so it should be the headline number in every comparison.
- **Transaction type — use realistic assets, not native tokens**:
  - **Polygon Edge: ERC-20 stablecoin transfer.** Real remittances on Polygon move USDC/USDT, not native MATIC. An ERC-20 transfer burns ~51-65k gas vs 21k for a native transfer — roughly 3×, and that 3× is the *real* cost of a real remittance. Using native transfers would understate cost threefold.
  - **NEAR: NEP-141 fungible token transfer** (same reasoning).
  - **Lightning: native BTC.** There is no stablecoin in the base Lightning protocol. This asymmetry is real and must be **stated, not hidden** — a Lightning remittance carries BTC volatility risk the other two don't. That's a finding about the architecture, not a flaw in the test.
- **Value conversion**: one exchange rate, pinned to a stated date at project start, held constant across every run so results stay reproducible. Stablecoins make this trivial for two of three architectures ($200 = 200 tokens, exactly); only Lightning needs a real BTC conversion. This is a second, independent reason the ERC-20/NEP-141 choice is right.
- **Offered load ramp**: step through 10 → 25 → 50 → 100 → 150 → 200 → 300 TPS, sustained, not single bursts. The goal is finding the point where each architecture starts degrading — that curve is the actual data product, not a single throughput number.
  - *Context on why 200-300 TPS is the ceiling target*: global remittances (~$905B/year ÷ $200 average transfer) work out to roughly 140-150 TPS as a global average; 200-300 TPS represents realistic peak conditions (holiday season, payday clustering).
- **Rate control method**: **Poisson-distributed arrival**, not fixed-interval — this mimics natural, randomly-timed real-world transaction arrival. Implemented in our own harness (see Section 8).
- **Test window**: **300 seconds fixed** — the high end of the range, deliberately, to catch degradation that only shows up under sustained load.
- **Repeats**: 5 per configuration minimum (ties to realism technique #8).
- **Discard the first 10 seconds of every run** (reversed 7 Aug 2026 — the earlier "no warm-up discard" call was superseded by `ANALYSIS_PLAN.md` §7). Cold-start effects — connection setup, initial route discovery — would otherwise skew every average. Applied uniformly to all three architectures.
  - *Precise rule*: exclude transactions whose **submission** time is under 10.0s. Confirmation may land after the 10s mark; what's excluded is the transaction, not the time window, so nothing is counted with a truncated latency.
  - This costs nothing retroactively: the harness records a per-second time series, so the cut happens in analysis, not at collection.
- **"300 TPS" means the whole architecture is processing 300 TPS in aggregate**, across all sender nodes — not per-node and not per-channel. Same definition for all three architectures so the ramp is comparable.

**Concurrent submission, not sequential**: transactions must be submitted concurrently at the target rate, not one-at-a-time waiting for each confirmation — that's the only way to actually test sustained throughput rather than just round-trip latency of a single transaction.

### Test matrix — full grid, 465 runs

**Every amount tested at every load level on every architecture.** Decided 7 Aug 2026; see `ANALYSIS_PLAN.md` §5.

| Architecture | Design | Runs |
|---|---|---|
| Polygon Edge | 4 sizes × 7 loads × 5 repeats | 140 |
| NEAR | 4 sizes × 7 loads × 5 repeats | 140 |
| Lightning | 4 sizes × 7 loads × 5 repeats | 140 |
| Adversarial arm (technique #6) | 3 loads × $200 × 5 repeats × 3 architectures | +45 |
| **Total** | | **465** ≈ 38.75 h measured run time |

**Why a trimmed matrix was considered and rejected.** A 240-run alternative would have run full size sweeps only on Lightning and spot-checked the other two. The reasoning: **transaction amount cannot affect Polygon or NEAR.** Those networks charge for computational work performed, and moving a larger number is not more work — an ERC-20 transfer of 10 tokens consumes identical gas to one of 500. The three extra size curves are predicted to land exactly on top of the $200 curve.

Angad chose the full matrix regardless, at roughly $35 and one extra day, to be able to claim without qualification that every amount was tested at every load on every architecture.

**Where size genuinely matters — Lightning, and it matters twice:**
- **Success rate** — a payment must find a route where *every* hop holds enough liquidity in the right direction. Larger payments have fewer viable routes and fail more. This is the Waugh & Holz effect we are replicating.
- **Cost** — Lightning routing fees are partly *proportional* to the amount, while Polygon and NEAR charge a flat fee regardless of value. This predicts a **crossover point** where Lightning stops being the cheapest option as amounts rise. Locating it is a pre-registered secondary objective (`ANALYSIS_PLAN.md` §12).

---

## 7. Metrics to Collect (Every Test Run)

- Offered load vs. **achieved** throughput (TPS). **Only successful transactions count toward achieved throughput.** Failures are reported separately — for Lightning that failure rate *is* the headline result, not a footnote.
- Settlement/finality latency — timestamp at submission, timestamp at confirmation, delta between them
- Cost per transaction (see the methodology note below — this is not as simple as it looks)
- Failure/timeout rate. **Timeout threshold: 60 seconds** — roughly 10× the expected p99 for both chains (each targets <5s finality), and past 60s a remittance has functionally failed regardless of what the chain eventually does.
- **Failure rate broken out by transaction size specifically** — this directly tests whether our data reproduces the pattern in Waugh & Holz (2020). See the corrected description of that finding in Section 11; the version previously in this document had the direction backwards.
- Node-offline event log (timestamp + which nodes), to correlate with performance data from realism technique #6
- Spot-instance preemption log (see Section 8) — any run touched by a preemption is auto-invalidated and re-queued

### What counts as "settled", per architecture

- **Polygon Edge**: transaction included in a committed block — **N = 1 confirmation**, locked. PolyBFT/IBFT gives *deterministic instant finality*: a committed block is final, with no probabilistic reorg window to wait out. Waiting extra blocks would add delay that doesn't exist and would mask a genuine Polygon advantage. **State the reason explicitly in the Methodology** so no reader mistakes N = 1 for a shortcut.
- **Lightning**: payment preimage returned to the sender (`payment_succeeded`).
- **NEAR**: transaction outcome at `FINAL`, **not** `EXECUTED_OPTIMISTIC` — optimistic execution would understate real settlement latency.

### Cost per transaction — methodology

**The trap**: on a private chain *we* set the gas price. Set it to 1 gwei and every transaction "costs" 1 gwei × gas — a number we invented. Measuring and reporting that would be circular and wouldn't survive review.

**What's actually real is gas *consumed***. Gas consumption is a deterministic function of the opcodes executed — an ERC-20 transfer burns ~51k gas on our chain, on Polygon mainnet, and on any EVM chain. That's architecture-determined and genuinely measurable.

1. Measure **gas consumed per transaction** on our network (real).
2. Convert using **real mainnet gas prices** from Polygonscan at a stated percentile and date, with token price also stated and dated.
3. Report as: *"an ERC-20 transfer consumes 51,000 gas; at Polygon mainnet's median gas price of X gwei on [date] with MATIC at $Y, that is $Z per transaction."* Every input sourced and reproducible.

**The stronger version**: on mainnet, gas price *rises with congestion*. We measure our chain's block utilization at each offered-load step and map it onto the historical mainnet gas-price-vs-utilization curve from Polygonscan. Cost per transaction then becomes a **curve over offered load**, not a single constant — which answers the "reduce settlement cost" half of the research question far better than one number would.

**Lightning**: fee = `base_fee + (fee_rate × amount)` summed over route hops. We set our nodes' fee rates from the real 1ML distribution, then measure realized route length and total fee. **Critically, also amortize on-chain channel open/close cost across the number of payments a channel carries.** Most Lightning benchmarks omit this and thereby report Lightning as near-free. Including it is the honest number and is a differentiator for the paper.

**NEAR**: gas is deterministic with a congestion-adjusted price floor. Same approach as Polygon.

---

## 8. Tools & Stack

- **Custom benchmarking harness (replaces Hyperledger Caliper)** — one harness, per-architecture adapters. **Caliper is dropped.** It has no Lightning or NEAR connector, so those needed custom generators regardless; using Caliper for Polygon only would put *two different measurement instruments inside a three-way comparison* — exactly the weakness a reviewer would attack in Phase 6, the paper's payoff section. Shared core (identical across all three): Poisson arrival, concurrent submission, timing, logging schema. Per-architecture adapters: transaction construction, submission, confirmation polling. **The Methodology section must justify dropping Caliper; the justification is cross-architecture comparability.**
  - Known risks being designed around: **nonce management under concurrent submission** (needs a pool of pre-funded accounts, not one sender) and **generator-side bottlenecking** before 300 TPS (needs multiple worker processes).
  - **Validate generator capacity first**, against a null endpoint. Without this we cannot claim an observed throughput ceiling belongs to the blockchain rather than to our own tooling — and at 300 TPS that's a live risk.
  - **Generator placement**: dedicated instance, *same region for every test* (consistency beats proximity). Measure and report the generator→node baseline latency separately so it can be stated or subtracted.
- **Polygon Edge** (pinned final release) — sidechain deployment
- **LND on `regtest` + bitcoind** — off-chain deployment
- **NEAR node software** — sharding deployment
- **`tc` / Toxiproxy** — network condition injection
- **1ML.com** — Lightning topology reference data
- **Polygonscan / NEAR Explorer** — mainnet calibration data sources
- **Terraform** — all infrastructure as code. Chosen over shell scripts because `terraform destroy` reliably removes *everything*; hand-rolled scripts leak orphaned volumes, elastic IPs and NAT gateways that bill silently, which across 4 regions is the most likely way to waste real money. Also keeps credentials out of scripts.
- **SQLite** — the harness's working data store during runs. Per-transaction records, never pre-aggregated summaries, so new questions can be answered later *without re-running anything* — the cheapest insurance available when cluster time is the main cost.
- **Two canonical data files in the repo, updated after every run without being asked:**
  - `data/raw/all_runs_raw.parquet` — every transaction from every run, nothing removed, invalidated runs included and flagged
  - `data/clean/all_runs_clean.parquet` — the post-cleaning dataset the paper's results are built from
  - `data/clean/exclusions.log` — every exclusion, with run ID, the rule that triggered it, and the reason

  **Why Parquet rather than committing the SQLite file:** GitHub hard-rejects any file over 100 MB, and the finished dataset is roughly 1.3 GB as SQLite. Parquet with zstd compresses this kind of data (sorted timestamps, low-cardinality status and run-ID columns) by roughly 10-25×, which should fit. If raw crosses ~90 MB, move it to **Git LFS** rather than downsampling. Re-commit raw at phase boundaries, not after every run — git stores a full copy of every version.

  **Nothing is ever deleted.** A reviewer must be able to see the untouched data beside the cleaned data and verify that nothing inconvenient was quietly dropped.
- **AWS or GCP** — multi-region compute. Provider choice is pending GitHub Student Developer Pack activation (applied Aug 2026, up to 72h). Region plan currently assumes AWS.
- **Spot/preemptible instances** — used *everywhere*, with **preemption detection that auto-invalidates and re-queues affected runs**. A mid-run reclaim doesn't just lose data, it looks exactly like a node failure — the precise variable the adversarial arm isolates — so silently keeping such a run would confound the two. If observed preemption rates turn out high, switch measured runs to on-demand.

### Cost controls (highest-value item in this document)

The dominant cost risk is **not** the measured runs — it's a cluster left running during debugging. A 7-node Polygon cluster is ~$1.15/hr on spot: one forgotten overnight ≈ $14, a forgotten weekend ≈ $80.

- Per test: **300s**
- Per unattended sweep: ~5-6 hours (50 runs × 300s + overhead)
- **Idle auto-shutdown: 30 minutes** with no test activity
- **Absolute cluster lifetime cap: 8 hours**, then hard shutdown requiring explicit re-provision
- **Billing alarms at $50 / $100 / $200**

---

## 9. Phased Rollout — Follow This Sequence

This project scope is genuinely large (a real distributed-systems undertaking, not a benchmarking script), so it's deliberately broken into phases. **Do not attempt all 8 realism techniques across all 3 architectures simultaneously.** The phasing exists so that if time or budget runs out at any point, there's still one complete, methodologically sound result rather than three incomplete ones.

**Phase 1 — Single architecture, minimal realism. Runs in ONE cloud region.**
Get Polygon Edge running as a single-region validator set with a single test configuration, and confirm the whole pipeline (deploy → load test → data collection) works end to end before adding any complexity. This phase produces the **real per-hour cost baseline** needed to give Angad's parents an actual budget number instead of a guess.

**Phase 1 is cloud, not local — deliberately.** An earlier plan put it on Angad's laptop to save money. That was wrong on two counts: (a) his machine is **arm64** while every cloud instance is **x86_64**, so a stack built and debugged locally risks rework; (b) a local run cannot produce the cost baseline this phase exists to produce. The saving would have been about **$3** — one region, ~4 small nodes, a few hours, with the 30-minute idle shutdown on. Not worth trading environment fidelity for.

**What *is* local: writing the code.** The harness core, the ERC-20 contract, the SQLite schema and the Terraform modules are authoring work with no environment dependency, and they take well over 72 hours regardless — so this runs in parallel with waiting on Student Pack credits and costs zero calendar time. Keep a 2-node Docker Edge on the laptop purely as a **compile-and-smoke target** to catch syntax-level bugs while writing. It is not a measurement environment.

Machine constraints for that scaffold only: **M2, 8 GB RAM, ~22 GB free disk** (free up more — aim for 50 GB+). That RAM cannot host the real 7-validator configuration, which is itself proof local work can't stand in for Phase 1.

**Phase 2 — Add realism techniques one at a time, same architecture (Polygon).**
Order: multi-region (#1) → injected latency (#2) → hardware matching (#4) → background traffic (#3) → adversarial nodes (#6). Test after each addition that results still make sense before adding the next.

**Phase 3 — Full realism stack on Polygon, then replicate to Lightning.**
Apply the complete stack from Phase 2, then rebuild the same deployment approach for Lightning, including liquidity topology realism (#5).

**Phase 4 — Replicate to sharding (NEAR).**
Same full stack, adapted to NEAR. Re-check whether Zilliqa's "x-shards" have actually shipped by this point — if they have, Zilliqa becomes a cheap *second* sharding data point, which would meaningfully strengthen Section 12's caveat about generalizing from one implementation.

**Phase 5 — Calibration and confidence intervals, all three architectures.**
Run the full repeat/interval protocol (#8) and calibrate against real mainnet data (#7) using consistent workload parameters across all three.

**Phase 6 — Cross-architecture comparison and results write-up.**
This phase is primarily Angad's work (feeds directly into the paper), but you may be asked to help generate comparison visualizations/tables from the collected data.

**Check in with Angad's dad at the end of every phase**, not just at the start and end of the whole project — this is a deliberate change from earlier in the project, given how much more technical surface area this phased approach covers.

---

## 10. Budget Reality Check

- **Original budget was $200** (AWS free credits + parental contribution).
- **Earlier revised estimate was $500-1,000.** **This now looks too high.** Three findings since have cut the projection substantially:
  1. **Not matching validator storage** (Section 5 #4) — avoids ~1TB/node of disk that would have stored nothing. Largest single saving.
  2. **Polygon Edge over CDK** — avoids a zkProver requiring ~1TB RAM / 128 cores, which alone would have consumed the entire budget.
  3. **Phase 1 is a single region for a few hours** — ~$3-5, negligible against the total. (It is *not* run locally; see Section 9 for why that was reversed.)
- **Current working estimate: $300-450 total**, for the full 465-run matrix. Rough build-up, spot pricing, storage/egress included:

| Cluster | Rate | Est. hours | Est. cost |
|---|---|---|---|
| Polygon Edge (7 × 8vCPU/32GB + generator) | ~$1.15/hr | ~50 | ~$58 |
| NEAR (12 nodes + generator) | ~$1.90/hr | ~38 | ~$72 |
| Lightning (4 small instances) | ~$0.40/hr | ~45 | ~$18 |
| Cross-region egress | — | — | ~$15-30 |
| Disk (100GB × ~20 nodes) | — | — | ~$20 |
| **Subtotal** | | | **~$185-240** |
| Slack for failed runs, re-provisioning, mistakes | | | **~$115-210** |

- **$300 of GCP credit is already in hand and expires 6 November 2026.** If Phases 1-4 land inside that window, most or all of this is covered by credit rather than out of pocket.

- **Treat this as an estimate with real uncertainty, not a quote.** The trustworthy number comes from the first Phase 2 cloud deployment — that's when the budget conversation with parents should happen for real.
- **Credits may cover most or all of this.** GitHub Student Developer Pack (applied Aug 2026, activating within 72h) plus GCP's ~$300 free trial could plausibly cover the entire project. Confirm exact credit amounts once the pack lands, *before* spending anything out of pocket.
- **Watch out for NAT gateways** — ~$0.045/hr each *plus* data processing charges, and across 4 regions they bill continuously whether or not tests are running. Avoid by using public subnets with tight security groups instead. This is the classic way a small multi-region deployment quietly triples in cost.
- **Cost-reduction tactics to actively use**: spot instances everywhere (with preemption detection per Section 8), the idle auto-shutdown and lifetime caps in Section 8, and running Phase 1 locally.

---

## 11. What to Expect From the Literature (Calibration Priors)

These are the published benchmark figures already gathered for the Literature Review section — useful context for sanity-checking your own results, not numbers to force your results to match. **Credibility flags added Aug 2026 — these are not all equally solid.**

- **Sharding (academic lab conditions)**: OmniLedger ~6,000 TPS at ~10s latency; RapidChain ~7,384 TPS at ~8.7s latency. *Credibility: solid* — genuine peer-reviewed venues (IEEE S&P 2018; ACM CCS 2018), but obtained under favourable lab assumptions that must be stated alongside the numbers. Expect live NEAR results meaningfully below these.
- **Sidechain**: Polygon PoS theoretical max ~3,800 TPS, ~$0.002/tx, ~5s finality. **⚠️ Credibility: weak.** The 3,800 TPS figure is a widely-repeated *vendor/marketing* claim, not a peer-reviewed measurement — observed sustained mainnet throughput is far lower (order of tens of TPS). It must be labelled a theoretical vendor claim, and it is **the wrong thing to compare our measured results against** as though it were an empirical benchmark.
- **Off-chain**: Lightning offers sub-second settlement and near-zero fees in the best case, but **reliability is the real bottleneck, not throughput**.

  **⚠️ CORRECTED — the earlier version of this document had this backwards.** Verified against the source: **Finnegan Waugh & Ralph Holz, "An empirical study of availability and reliability properties of the Bitcoin Lightning Network," arXiv:2006.14358.** What they actually found was *two distinct results*, which this document had merged into one contradictory claim:

  1. Payment success rate ranged **15.32% to 72.09%**, with an **inverse relationship to payment volume** — success goes **DOWN as payment size goes UP**. So ~72% is at the *smallest* payments and ~15% at the *largest*.
  2. **Separately**, only about **one third of destination nodes** could be reached at all, and this was *roughly independent* of payment volume. (The stray "~35%" in the old text appears to have been this reachability figure, not a payment-size result.)

  **This still is the single most important pattern to check our data against** — but against the *correct* direction. Had this not been caught, we would have concluded our Lightning data contradicted the literature when it in fact agreed with it. **The Literature Review section of the paper needs this fixed.**
- **Real-world adoption caveat (not a technical metric, but important context)**: El Salvador's crypto remittances sit around ~0.7% of total national remittance volume despite years of government push — a reminder that even a well-performing architecture doesn't guarantee adoption, which is a separate problem the paper's Design Science section addresses, not something the simulation needs to solve.

---

## 12. Framing for Results — What NOT to Overclaim

- Results are an **upper-bound production estimate under controlled, partially-realistic conditions** — not a claim of exact mainnet replication. State this explicitly in any results summary.
- Sharding results reflect **one specific live implementation** (NEAR), not sharding as a general architectural concept.
- Sidechain results reflect **software frozen as of Dec 2024** (Polygon Edge, archived). State this explicitly.
- **The three architectures do not carry the same asset.** Polygon and NEAR move stablecoins; Lightning moves native BTC, because the base Lightning protocol has no stablecoin. A Lightning remittance therefore carries exchange-rate volatility risk the other two don't. This is a real architectural difference, not a testing artifact — report it, don't paper over it.
- This simulation tests **on-chain/off-chain settlement performance only** — it does not model the fiat on/off-ramp conversion step (the "last mile problem"), which prior research suggests may be a significant share of real-world remittance friction. Don't let results imply the full end-to-end remittance experience was tested.
- **Interoperability with fiat rails (SWIFT/RTGS) is Design Science only.** Nothing is built or prototyped for it in Phases 1-5. A minimal mock settlement bridge is a *stretch goal only* if time remains after Phase 6, and must never block or draw budget from the three-architecture benchmarking, which is the paper's empirical core.

---

## 13. Immediate Next Steps (Start Here)

Split into work that can start **now** (writing, local, free) and work that needs **credits** (Phase 1 proper, one cloud region, ~$3-5).

**Now — authoring, while Student Pack credits activate (~72h):**

1. Install prerequisites: Docker, Go toolchain, Terraform. Free up disk first — only ~22 GB available, aim for 50 GB+.
2. Stand up a **2-node Polygon Edge in Docker** locally as a *compile-and-smoke target only*. Not a measurement environment.
3. Write the **ERC-20 test stablecoin** contract and the account-funding script — fund a *pool* of senders, not one account; single-sender nonce contention is the known failure mode under concurrent submission.
4. Write the **harness core** — Poisson arrival, concurrent submission, timing, SQLite logging — plus the Polygon adapter. This core is reused unchanged for Lightning and NEAR, so getting the schema right now pays off three times.
5. Write the **Terraform modules** for a single-region deployment, targeting x86_64 Linux.

**Then — Phase 1 proper, one cloud region, once credits land:**

6. Deploy the single-region validator set via Terraform. Confirm the idle auto-shutdown and billing alarms fire *before* anything else runs.
7. Run the pipeline end to end at a **low fixed rate (well under 10 TPS)** for a single $200 configuration. The goal is confirming deploy → submit → measure → log works, **not** producing publishable numbers.
8. Validate **generator capacity** against a null endpoint, so we know the harness's own ceiling before it matters.
9. **Report actual cost incurred** — this is the real per-hour baseline for Section 10 and the trigger for the budget conversation with Angad's parents.
10. Only once Phase 1 works end to end, begin layering Phase 2 realism techniques one at a time per Section 9.

**Angad runs all scripts himself; Claude Code writes them and does not provision cloud resources or spend money.** Anything that costs money, or any change in scope, goes to Angad for review first.

Beyond that, feel free to make implementation-level technical judgment calls independently, using the optimization order at the top of this document: realism, then cost, then technical difficulty.
