# Project Handoff: Blockchain Remittance Scaling Architecture Benchmarking

**Purpose of this document**: This is a full context handoff for Claude Code, which will handle the scripting, infrastructure deployment, and technical debugging for the simulation portion of this research project. Read this whole document before starting any work. It explains not just *what* to build, but *why*, so you can make good judgment calls when something isn't explicitly specified.

---

## 1. Research Question & Project Context

**Research question**: What sharding, sidechain, or off-chain transaction architectures would most effectively increase throughput and reduce settlement cost for blockchain-based remittance systems, and how would interoperability between these architectures and existing fiat rails (like SWIFT/RTGS) be achieved?

**Who's running this project**: A student researcher (going by "Angad" in project notes) writing an academic-style research paper over the summer. Not a professional engineer, learning distributed systems concepts as the project goes. Has decent coding experience (has built and shipped personal projects with Claude Code before) but has never worked on something this technically demanding.

**Support structure**:
- **Technical mentor**: Angad's father, ~6 years of payments infrastructure experience at Amazon. Not a blockchain specialist, but deeply familiar with real-world payment systems concepts (settlement risk, reconciliation, fraud prevention, load testing philosophy). Plan is to check in with him at the end of every phase (see Section 7), not just at the start/end of the whole project.
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
- **The goal is a credible upper-bound production estimate, not exact mainnet replication.** Don't chase perfect realism at the expense of finishing — see the phased rollout in Section 7, which exists specifically so partial completion still produces one complete, defensible result.

---

## 4. The Three Architectures & Required Software

| Architecture | Software | Deployment Approach |
|---|---|---|
| **Sidechain** | **Polygon Edge / Supernets** | Self-hosted validator set, real production PoS sidechain toolkit |
| **Off-chain** | **Lightning Network** (`regtest`/`simnet` mode) | Self-hosted multi-node Lightning network with manually configured channel topology |
| **Sharding** | **Zilliqa or NEAR node software** | Self-hosted multi-node cluster running the actual production sharding software (whichever network has the more stable/better-documented node software at build time — check both before committing) |

All three use **actual production software**, self-hosted under our own control — not public shared testnets, not rebuilt-from-paper research code.

---

## 5. Full Realism Technique Checklist

All eight of these are in scope (this was an explicit, deliberate decision to go all-in rather than cut scope — see Section 7 for how to sequence them without it becoming unmanageable):

1. **Multi-region node deployment** — 3-4 real cloud regions (e.g., US-East, EU-West, AP-Southeast) rather than one datacenter, to get real internet latency between nodes.
2. **Injected latency & packet loss** — use `tc` (Linux traffic control) or Toxiproxy to add realistic jitter/latency/packet loss on top of natural cross-region latency. Base injected values on real published internet latency stats between the regions used, not arbitrary numbers.
3. **Competing background transaction traffic** — run a second script generating non-remittance "noise" transactions concurrently with the remittance workload, with the noise rate varying over time rather than staying constant.
4. **Hardware matched to real validator specs** — look up actual minimum/recommended specs for real Polygon validators, Lightning routing nodes, and Zilliqa/NEAR validators; size cloud instances to match rather than defaulting to cheap/convenient specs.
5. **Realistic Lightning liquidity topology** — pull real, current channel/capacity data from **1ML.com** and configure private-network channel funding to roughly match real-world concentration (small number of well-funded hubs, many thin leaf nodes) instead of funding every channel evenly.
6. **Adversarial/unreliable nodes** — toggle roughly 10-20% of nodes offline intermittently during a subset of test runs, log exactly when/which nodes, to correlate with performance dips.
7. **Calibration against real mainnet data** — compare private-network results against real, current mainnet activity via block explorers (Polygonscan, NEAR Explorer, Zilliqa Explorer). Produce a stated, quantified gap: *"our private network measured X; real mainnet activity suggests Y; results should be treated as an upper bound roughly Z% above expected real-world performance."*
8. **Confidence intervals, not single averages** — every test configuration (architecture × transaction size × offered load level) runs a minimum of 5 repeats. Report ranges, not single numbers, in every results table.

---

## 6. Test Workload Design

- **Transaction sizes**: $10, $50, $200, $500 (equivalent value in whatever token/asset each testnet uses). **$200 is the primary benchmark size** — it's the World Bank's own standard for remittance price surveys (see `remittanceprices.worldbank.org/methodology`), so it should be the headline number in every comparison.
- **Offered load ramp**: step through 10 → 25 → 50 → 100 → 150 → 200 → 300 TPS, sustained, not single bursts. The goal is finding the point where each architecture starts degrading — that curve is the actual data product, not a single throughput number.
  - *Context on why 200-300 TPS is the ceiling target*: global remittances (~$905B/year ÷ $200 average transfer) work out to roughly 140-150 TPS as a global average; 200-300 TPS represents realistic peak conditions (holiday season, payday clustering).
- **Rate control method**: **Poisson-distributed arrival**, not fixed-interval — this mimics natural, randomly-timed real-world transaction arrival. Hyperledger Caliper has a built-in Poisson rate controller for exactly this.
- **Test window**: 60-300 seconds sustained per configuration, not a quick burst.
- **Repeats**: 5 per configuration minimum (ties to realism technique #8).

**Concurrent submission, not sequential**: transactions must be submitted concurrently at the target rate, not one-at-a-time waiting for each confirmation — that's the only way to actually test sustained throughput rather than just round-trip latency of a single transaction.

---

## 7. Metrics to Collect (Every Test Run)

- Offered load vs. **achieved** throughput (TPS)
- Settlement/finality latency — timestamp at submission, timestamp at confirmation, delta between them
- Cost per transaction
- Failure/timeout rate
- **Failure rate broken out by transaction size specifically** — this directly tests whether your own data reproduces the pattern found in Waugh & Holz (2020), which found Lightning success rates dropping sharply as payment size increases (as low as ~15-35% success for the smallest payments in their independent testing). This is one of the most important things to check your own results against.
- Node-offline event log (timestamp + which nodes), to correlate with performance data from realism technique #6

---

## 8. Tools & Stack

- **Hyperledger Caliper** — core benchmarking framework, use its Poisson rate controller
- **Polygon Edge / Supernets** — sidechain deployment
- **Lightning `regtest`/`simnet`** — off-chain deployment
- **Zilliqa or NEAR node software** — sharding deployment
- **`tc` / Toxiproxy** — network condition injection
- **1ML.com** — Lightning topology reference data
- **Polygonscan / NEAR Explorer / Zilliqa Explorer** — mainnet calibration data sources
- **AWS or GCP** — multi-region compute (check for GitHub Student Developer Pack credits and GCP's ~$300 free trial in addition to AWS free tier — budget is tighter than originally planned, see Section 10)
- **Spot/preemptible instances** — use these for non-critical test infrastructure; can cut compute cost 60-90% vs. on-demand pricing

---

## 9. Phased Rollout — Follow This Sequence

This project scope is genuinely large (a real distributed-systems undertaking, not a benchmarking script), so it's deliberately broken into phases. **Do not attempt all 8 realism techniques across all 3 architectures simultaneously.** The phasing exists so that if time or budget runs out at any point, there's still one complete, methodologically sound result rather than three incomplete ones.

**Phase 1 — Single architecture, minimal realism.**
Get Polygon Edge running on a single region, single node set, single test configuration. Confirm the whole pipeline (deploy → load test → data collection) works end to end before adding any complexity. This phase also produces the **real per-hour cost baseline** needed to give Angad's parents an actual budget number instead of a guess.

**Phase 2 — Add realism techniques one at a time, same architecture (Polygon).**
Order: multi-region (#1) → injected latency (#2) → hardware matching (#4) → background traffic (#3) → adversarial nodes (#6). Test after each addition that results still make sense before adding the next.

**Phase 3 — Full realism stack on Polygon, then replicate to Lightning.**
Apply the complete stack from Phase 2, then rebuild the same deployment approach for Lightning, including liquidity topology realism (#5).

**Phase 4 — Replicate to sharding (Zilliqa or NEAR).**
Same full stack, adapted to whichever network has better node software support at the time.

**Phase 5 — Calibration and confidence intervals, all three architectures.**
Run the full repeat/interval protocol (#8) and calibrate against real mainnet data (#7) using consistent workload parameters across all three.

**Phase 6 — Cross-architecture comparison and results write-up.**
This phase is primarily Angad's work (feeds directly into the paper), but you may be asked to help generate comparison visualizations/tables from the collected data.

**Check in with Angad's dad at the end of every phase**, not just at the start and end of the whole project — this is a deliberate change from earlier in the project, given how much more technical surface area this phased approach covers.

---

## 10. Budget Reality Check

- **Original budget was $200** (AWS free credits + parental contribution). This is now understood to be outdated given the expanded scope.
- **Realistic updated estimate: $500-1,000 total**, with $600-800 as a reasonable middle estimate.
- **Rough phase-by-phase cost expectation**:
  - Phase 1: ~$20-40
  - Phase 2: ~$100-200
  - Phase 3: ~$100-150 (Lightning nodes are lighter weight than full validators)
  - Phase 4: ~$150-300 (sharded clusters typically need more nodes for a meaningful multi-shard setup)
  - Phase 5: ~$150-250
- **Cost-reduction tactics to actively use**: spot/preemptible instances, shutting nodes down between active test sessions rather than running 24/7, checking GitHub Student Developer Pack and GCP's free trial credits in addition to AWS.
- **Get Angad a real number after Phase 1** rather than continuing to operate on estimates — this was explicitly identified as the point where the budget conversation with parents should happen for real.

---

## 11. What to Expect From the Literature (Calibration Priors)

These are the published benchmark figures already gathered for the Literature Review section — useful context for sanity-checking your own results, not numbers to force your results to match:

- **Sharding (academic lab conditions)**: OmniLedger ~6,000 TPS at ~10s latency; RapidChain ~7,384 TPS at ~8.7s latency. These are lab/testbed numbers on generic workloads — expect your live Zilliqa/NEAR results to land meaningfully below these, since production sharded networks (even self-hosted) won't match idealized academic lab conditions.
- **Sidechain**: Polygon PoS theoretical max ~3,800 TPS, ~$0.002/tx, ~5s finality. Real sustained production throughput tends to run well below the theoretical max.
- **Off-chain**: Lightning offers sub-second settlement and near-zero fees in the best case, but **reliability is the real bottleneck, not throughput** — Waugh & Holz (2020) found first-attempt success rates ranging from ~15% to ~72% depending on payment size, with only ~35% success at the smallest payment sizes tested. **This is the single most important pattern to check your own data against.**
- **Real-world adoption caveat (not a technical metric, but important context)**: El Salvador's crypto remittances sit around ~0.7% of total national remittance volume despite years of government push — a reminder that even a well-performing architecture doesn't guarantee adoption, which is a separate problem the paper's Design Science section addresses, not something the simulation needs to solve.

---

## 12. Framing for Results — What NOT to Overclaim

- Results are an **upper-bound production estimate under controlled, partially-realistic conditions** — not a claim of exact mainnet replication. State this explicitly in any results summary.
- Sharding results reflect **one specific live implementation** (Zilliqa or NEAR), not sharding as a general architectural concept.
- This simulation tests **on-chain/off-chain settlement performance only** — it does not model the fiat on/off-ramp conversion step (the "last mile problem"), which prior research suggests may be a significant share of real-world remittance friction. Don't let results imply the full end-to-end remittance experience was tested.

---

## 13. Immediate Next Steps (Start Here)

1. Confirm Polygon Edge / Supernets setup requirements and get a minimal single-region validator set running.
2. Get Hyperledger Caliper installed and configured to talk to that deployment.
3. Write a basic workload generator script for a single transaction size ($200) at a low, fixed rate (start well below 10 TPS) to confirm the whole pipeline works end to end — deploy, submit, measure, log.
4. Once the pipeline is confirmed working, report back the actual cloud cost incurred so far, this becomes the real per-hour baseline referenced in Section 10.
5. Only after Phase 1 is fully working end-to-end, begin layering in Phase 2 realism techniques one at a time per Section 9.

Ask Angad before making any decision that trades off scope, cost, or timeline in a way not already covered by this document — but feel free to make implementation-level technical judgment calls independently.
