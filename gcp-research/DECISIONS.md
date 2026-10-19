# Technical Decision Record

Companion to `claude.md`. Records every decision made after the Aug 2026 scoping pass, with the reasoning behind it. Optimization order set by Angad: **1) realism, 2) cost, 3) technical difficulty.**

Status key: **LOCKED** = decided, proceeding. **NEEDS REVIEW** = costs money or changes scope, awaiting Angad. **DEFERRED** = decide at the relevant phase.

---

## 0. Corrections to `claude.md`

### 0.1 Run-time estimate was wrong by 10x
An earlier estimate of "~210 hours of run time" for the full test matrix was arithmetic error. The correct figure:

`3 architectures x 4 sizes x 7 load steps x 5 repeats = 420 runs`
`420 runs x 300s = 35 hours` of measured run time.

Not 210. This materially changes the cost-vs-coverage tradeoff (see §5).

### 0.2 Waugh & Holz (2020) is described backwards in `claude.md` §7 and §11
Verified against the source: **Finnegan Waugh and Ralph Holz, "An empirical study of availability and reliability properties of the Bitcoin Lightning Network," arXiv:2006.14358.**

What the paper actually found:
- Payment success rate ranged **15.32% to 72.09%**, with an **inverse relationship to payment volume** — success rate goes **DOWN as payment size goes UP**. So ~72% is the *smallest* payments and ~15% the *largest*.
- **Separately**, only about **one third of destination nodes** could be reached at all, and this was *roughly independent* of payment volume.

`claude.md` merged these two distinct findings into a single contradictory claim ("success drops as size increases" + "15-35% for the smallest payments"). The ~35% figure in §11 appears to be the *reachability* result, not a payment-size-specific success rate.

**Why this matters:** §7 calls this "one of the most important things to check your own results against." Our Lightning data must be checked against the *correct* direction, or we would have concluded our data contradicted the literature when it agreed with it. The Literature Review section of the paper needs this fixed.

### 0.3 Cross-reference fix
`claude.md` §1, §3, §5 cite "Section 7" for the phased rollout. The phasing is **Section 9**; Section 7 is Metrics. Confirmed with Angad.

---

## 1. Architecture selection

### 1.1 Sidechain: **Polygon Edge**, pinned to its final release — SIGNED OFF 7 Aug 2026

Angad explicitly approved this despite it contradicting his literal "most technologically advanced" instruction, after the reasoning below was presented.

Angad's instruction was "whichever is updated and most technologically advanced." Taken literally that selects Polygon CDK. **I am recommending against it**, because that criterion conflicts with priorities 1 and 2:

| | Polygon Edge | Polygon CDK |
|---|---|---|
| Architecture category | **PoS sidechain** | ZK validium / rollup |
| Matches the paper's taxonomy | Yes | **No — different category** |
| Maintenance | Archived read-only Dec 4 2024 | Actively maintained |
| Production zkProver hardware | n/a | **1TB RAM, 128 cores** |
| Fits budget | Yes | **No** |

Two independent reasons:

1. **Realism (priority 1).** The research question asks about *sharding, sidechain, or off-chain*. CDK is a ZK rollup/validium — it belongs to a fourth category the paper does not claim to test. Benchmarking CDK and labeling the result "sidechain" would misrepresent the finding. Edge is a genuine PoS sidechain and is the architecture the paper's taxonomy actually refers to.
2. **Cost (priority 2).** CDK's production zkProver requires ~1TB RAM and 128 cores. That is not merely over budget, it is roughly the entire budget per hour. Running CDK in mock-prover mode would remove the proving step — i.e. remove the exact thing that makes CDK "technologically advanced" — leaving us with a slower, more complex Edge.

**Mitigation for Edge being archived:** pin a specific final release commit (makes the whole study reproducible, which archived software is actually *better* at than a moving target). Note in Limitations that the software is frozen as of Dec 2024. Supporting argument for the paper: Edge is not abandonware in practice — Dogechain runs a production fork, so it is live software securing real value.

**Angad: this contradicts your literal instruction, so it needs your explicit sign-off.**

### 1.2 Sharding: **NEAR**, not Zilliqa — LOCKED (revisit at Phase 4)

Angad said "whichever is cheaper." Zilliqa is cheaper (`e2-highcpu-8`, 8 vCPU / 8 GB vs NEAR's 8 core / 24 GB). I am choosing NEAR anyway, on realism grounds:

- **Zilliqa 2.0 removed the sharded architecture we want to measure.** The legacy dual-layer DS-shard / network-shard design is gone, replaced by a single-tier validator set of ~32 nodes using Pipelined Fast-HotStuff. The replacement sharding concept ("x-shards", application-specific state shards) reads as roadmap material, and it is not confirmed as shipped in the node software.
- **Risk:** we could spend Phase 4's entire budget deploying Zilliqa and discover nothing is actually sharded — producing zero usable data for the sharding row of a paper whose core question is about sharding.
- **NEAR's Nightshade sharding is live in production** and demonstrably sharded. It costs more and it actually answers the question.

**Phase 4 revisit:** if x-shards have shipped by then, Zilliqa becomes viable as a cheaper option and possibly a valuable *second* sharding data point.

### 1.3 Off-chain: **LND on `regtest`** — LOCKED

**Implementation — LND.** Cost ranking is CLN (lightest) < LND (2 GB min) < Eclair (4 GB+ JVM). Realism is priority 1 and LND is the dominant implementation on the real Lightning Network, which is also the network Waugh & Holz measured — matching it makes our replication attempt more meaningful. LND also has the best tooling (lncli, gRPC/REST) and Polar for regtest orchestration, which lowers priority-3 difficulty. Cost delta vs CLN is roughly 20-30 GB RAM across the node set — real but modest.

**`regtest` over `simnet`.** regtest runs against **bitcoind (Bitcoin Core)** — the actual production Bitcoin node. simnet runs against btcd, an alternative implementation with little production deployment. Realism picks regtest, and it is also far better documented.

---

## 2. Hardware sizing — the storage insight

**Match CPU and RAM to real validator specs. Do NOT match storage.**

Published validator specs quote huge disks (Polygon 1.2 TB, NEAR 1 TB) because those numbers exist to hold *years of mainnet chain history*. Our private chains start empty and accumulate a few hours of blocks. Provisioning 1 TB per node would burn hundreds of dollars storing nothing.

CPU and RAM are what determine consensus and execution performance, so those are matched faithfully. This satisfies realism technique #4 where it affects results, and cuts the single largest avoidable cost.

| Cluster | Node spec | Count | Storage |
|---|---|---|---|
| Polygon Edge | 8 vCPU / 32 GB | 7 validators | 100 GB gp3 |
| NEAR | 8 vCPU / 32 GB | 8-12 (multi-shard) | 100 GB gp3 |
| Lightning | small, multi-node per instance | ~20 LN nodes + bitcoind | 50 GB |
| Load generator | 4-8 vCPU | 1 | 50 GB |

### 2.1 Validator counts — LOCKED

**Polygon Edge: 7 validators.** BFT message complexity is O(n²), so validator count directly drives consensus cost and must be defensible. 7 is the standard BFT size for f=2 (3f+1), exercises real quadratic messaging, and is a realistic small-production-sidechain figure. Real Polygon PoS runs ~100, which we cannot afford; we address this with a cheap **validator-count sensitivity run (7 vs 15) at a single load level**, so the paper can state the direction and rough magnitude of the effect rather than ignoring it.

**NEAR: 8-12**, sized to populate at least 4 shards with ≥2 validators each — below that the deployment is not meaningfully sharded and the data is worthless.

**Lightning: ~20 nodes**, hub-and-leaf topology per realism technique #5.

---

## 3. Measurement definitions — LOCKED

### 3.1 What counts as "settled"
- **Polygon Edge:** transaction included in a committed block. PolyBFT/IBFT provides *instant finality* — a committed block is final, so there is no N-confirmations wait to configure. This is a genuine architectural property worth stating in results.
- **Lightning:** payment preimage returned to the sender (`payment_succeeded`).
- **NEAR:** transaction outcome at `FINAL`, not `EXECUTED_OPTIMISTIC`. Optimistic execution would understate real settlement latency.

### 3.2 Failure and timeout
- **Timeout: 60 seconds.** Roughly 10x the expected p99 for the two chains (both target <5s finality), and past 60s a remittance has functionally failed regardless of what the chain eventually does. Also bounds worst-case run length.
- **Only successful transactions count toward achieved throughput** (Angad's call). Failures are reported separately as failure rate — which for Lightning is the headline result, not a footnote.

### 3.3 Transaction type — realistic assets
- **Polygon Edge: ERC-20 stablecoin transfer**, not native-token transfer. Real remittances on Polygon move USDC/USDT. An ERC-20 transfer costs ~51-65k gas vs 21k for native — roughly 3x, and that 3x is the *real* cost of a real remittance. Using native transfers would understate cost by a factor of three.
- **NEAR: NEP-141 fungible token transfer** (same reasoning).
- **Lightning: native BTC.** There is no stablecoin in the base Lightning protocol. This is a genuine asymmetry between architectures and must be *stated*, not hidden — a Lightning remittance carries BTC volatility risk that the other two do not. It is a real finding about the architecture, not a flaw in the test.

### 3.4 Value conversion
One exchange rate, pinned to a stated date at project start, held constant across every run so results stay reproducible and comparable.

Using stablecoins makes this trivial for two of three architectures: **$200 = 200 tokens**, exactly. Only Lightning needs a BTC conversion. This is a second, independent reason the ERC-20/NEP-141 choice is correct.

---

## 4. Cost per transaction methodology — LOCKED (formalized in `ANALYSIS_PLAN.md` §6.3)

**The problem:** on a private chain we set the gas price ourselves. If we set 1 gwei, every transaction "costs" 1 gwei x gas — a number we invented. Measuring it and reporting it would be circular and would not survive review.

**What is actually real:** *gas consumed*. Gas consumption is a deterministic function of the EVM opcodes executed — an ERC-20 transfer burns ~51k gas on our chain, on Polygon mainnet, and on any EVM chain. That is architecture-determined and genuinely measurable.

**Method:**
1. Measure **gas consumed per transaction** on our network (real).
2. Convert using **real mainnet gas prices** pulled from Polygonscan at a stated percentile and date, with the token price also stated and dated.
3. Report as: *"an ERC-20 transfer consumes 51,000 gas; at Polygon mainnet's median gas price of X gwei on [date] with MATIC at $Y, that is $Z per transaction."* Every input is sourced and reproducible.

**The stronger version:** on mainnet, gas price *rises with congestion*. We measure our chain's block utilization at each offered-load step and map it onto the historical mainnet gas-price-vs-utilization curve from Polygonscan. Cost per transaction then becomes a **curve over offered load**, not a single constant — which directly answers the "reduce settlement cost" half of the research question far better than one number would.

**Lightning:** fee = `base_fee + (fee_rate x amount)` summed over route hops. We configure our nodes' fee rates from the real 1ML distribution so measured fees reflect real-world levels, then measure realized route length and total fee. **Critically, we also amortize on-chain channel open/close cost across the number of payments a channel carries.** Most Lightning benchmarks omit this and thereby report Lightning as near-free; including it is the honest number and is a differentiator for the paper.

**NEAR:** gas is deterministic with a congestion-adjusted price floor. Same approach as Polygon.

---

## 5. Test matrix — RESOLVED 7 Aug 2026: full 465-run matrix

**Angad chose the full matrix over the trimmed alternative below.** Every amount tested at every load level on every architecture: 3 × 4 × 7 × 5 = 420 runs, plus the 45-run adversarial arm = **465 runs, ~38.75 hours** of measured run time. Cost of the choice — roughly $35 and one extra day of cluster time — was stated in advance. The purchase is an unqualified symmetry claim: no reviewer can ask why one architecture was tested more thoroughly than another.

Two things came out of the argument that improved the plan regardless of which option won:

1. **Lightning's size dependence is twofold — success *and* cost.** The original justification for full Lightning sweeps was success rate alone. But Lightning routing fees are partly *proportional* to the amount moved, whereas Polygon and NEAR charge a flat fee for the same computational work regardless of value. That predicts a **crossover point** where Lightning stops being cheapest as amounts rise — now a pre-registered secondary objective (`ANALYSIS_PLAN.md` §12).
2. **"Test at the knee" was a pre-registration flaw.** The trimmed design originally placed size spot-checks "at the knee," but the knee is a *result* — choosing where to measure based on it means selecting a measurement point after seeing data, exactly what pre-registration exists to prevent. Moot under the full matrix, but the reasoning is recorded so it doesn't recur.

The original trimming argument is retained below, because the prediction it rests on is now something the data must confirm.

---

### Superseded: the trimmed 240-run proposal

Full matrix is 420 runs / 35 hours. Proposed trim is **240 runs / ~20 hours**, and the cut is justified scientifically rather than only by cost:

**Transaction size barely matters on Polygon and NEAR.** An ERC-20 transfer of 10 tokens consumes *identical* gas to one of 500 tokens — the amount is a number in the calldata, and it changes neither execution cost nor latency nor success probability. A full size sweep on those two architectures would spend ~30% of the budget confirming a result that is true by construction.

**Transaction size is the entire question on Lightning**, because success depends on payment size relative to channel liquidity — that is precisely the Waugh & Holz effect we are trying to replicate. Lightning is also by far the *cheapest* cluster to run, so spending run-time there is efficient.

| Architecture | Design | Runs |
|---|---|---|
| Polygon Edge | 7 loads x 5 repeats @ $200, + 3 sizes x 1 load (the knee) x 5 repeats as a spot-check | 50 |
| NEAR | same | 50 |
| Lightning | **full** 4 sizes x 7 loads x 5 repeats | 140 |
| **Total** | | **240** |

The size spot-check on Polygon/NEAR is retained deliberately: it lets the paper *demonstrate* size-independence with data instead of merely asserting it.

**Adversarial-node arm (technique #6):** run as a **separate arm, not folded into every config.** If node failures were injected into all runs, we could not separate "degrades under load" from "degrades under node failure" — the clean baseline is what makes the adversarial data interpretable at all. Scoped to 3 load levels (low / knee / high) x $200 x 5 repeats = **15 runs per architecture, +45 total, ~4 hours.** Cheap for the value.

**Test window: 300s fixed** (Angad's call — high end, to catch degradation that only appears under sustained load).

**No warm-up discard** (Angad's call). Noting the tradeoff: cold-start effects in the first few seconds will be included in the averages. Mitigated by recording a full per-second time series, so warm-up can be excluded analytically later without re-running anything.

---

## 5.1 Phase 1 environment — cloud, not local — LOCKED

An earlier version of this plan put Phase 1 on Angad's laptop to save money. **Reversed** after Angad pushed back on realism grounds. He was right, though for a slightly different reason than stated:

Phase 1 produces **no paper data** — it exists to prove the pipeline works — so "realistic conditions" is not the bar it's judged against. But two real problems remained:

1. **arm64 vs x86_64.** The laptop is Apple Silicon; every cloud instance is x86_64. A stack built and debugged locally risks rework when it moves.
2. **`claude.md` §10 assigns Phase 1 the job of producing the real per-hour cost baseline.** A local run cannot. Pushing that to Phase 2 quietly broke a stated requirement.

And the saving was negligible: one region, ~4 small nodes, a few hours with the 30-minute idle shutdown ≈ **$3-5**. Environment fidelity is worth far more than that.

**Resolution:** Phase 1 runs in one cloud region. Local work is limited to *authoring* the harness, contract, schema and Terraform — which has no environment dependency and takes longer than the ~72h credit wait anyway, so the split costs zero calendar time. A 2-node local Docker Edge serves only as a compile-and-smoke target.

---

## 6. Infrastructure

### 6.1 Regions — LOCKED
Four AWS regions mapped to **real remittance corridors** rather than generic geography — a stronger methodological story at identical cost:

| Region | Corridor role |
|---|---|
| `us-east-1` (N. Virginia) | US sender — largest global remittance source |
| `ap-south-1` (Mumbai) | India — largest global remittance recipient |
| `ap-southeast-1` (Singapore) | SE Asia / Philippines corridor |
| `eu-west-1` (Ireland) | EU corridor |

Gives genuine intercontinental latency (~200-250ms us-east-1 ↔ ap-south-1) as the *base* on which technique #2 injects additional impairment.

### 6.2 Spot instances — LOCKED
**Spot everywhere, with preemption detection that auto-invalidates and re-queues affected runs.**

A spot reclaim mid-run does not just lose data — it looks exactly like a node failure, which is the precise variable the adversarial arm isolates. Silently keeping such a run would confound the two. Detection + re-run gets spot pricing (60-90% saving) without the confound, at some extra scripting complexity — acceptable since technical difficulty is priority 3. If observed preemption rates turn out high, we switch measured runs to on-demand.

### 6.3 Cost controls — LOCKED
Angad's question was whether ~5 min is the right runtime cap. Per *test* yes, 300s. But the relevant limits are:

- **Per test:** 300s.
- **Per unattended sweep:** ~5-6 hours (50 runs x 300s + overhead).
- **Idle auto-shutdown: 30 minutes** with no test activity.
- **Absolute cluster lifetime cap: 8 hours**, then hard shutdown requiring explicit re-provision.
- **Billing alarms at $50 / $100 / $200.**

The dominant cost risk is **not** the measured runs — it is a cluster left running during debugging. A 7-node Polygon cluster costs ~$1.15/hr on spot, so one forgotten overnight ≈ $14, and a forgotten weekend ≈ $80. The idle-shutdown timer is the single highest-value cost control in this project.

### 6.4 Terraform, not shell scripts — LOCKED
Angad asked for "cheaper and more secure." Terraform is both:
- **Cheaper:** `terraform destroy` reliably removes *everything*. Hand-rolled shell scripts leak orphaned resources — volumes, elastic IPs, NAT gateways — that bill silently. Across 4 regions this is the most likely way to waste real money.
- **More secure:** no credentials embedded in scripts, and the resource inventory is explicit and auditable.

Costs more upfront effort (priority 3, lowest weight).

### 6.5 Repo private — DONE 7 Aug 2026
Currently public. It will contain Terraform state, node keys, and eventually references to cloud credentials. **A public repo plus cloud credentials is the standard way student cloud accounts get drained by automated scrapers.** Recommend private now; flip to public at publication with secrets scrubbed and history rewritten.

### 6.6 Load generator placement — LOCKED
Dedicated instance, **same region for every test** (consistency matters more than proximity), with the generator→node baseline latency measured and reported separately so it can be stated or subtracted.

**Generator capacity validated first** against a null endpoint, to establish its maximum output rate. Without this we cannot claim an observed throughput ceiling belongs to the blockchain rather than to our own tooling — and at 300 TPS that is a live risk.

---

## 7. Harness — LOCKED

**One custom harness with per-architecture adapters.** Angad's call ("standardize the measurement instrument"), and it is the right one: Caliper has no Lightning or NEAR connector, so those need custom generators regardless. Using Caliper for Polygon only would put two different measurement instruments inside a three-way comparison — exactly the weakness a reviewer would attack in Phase 6, which is the paper's payoff section.

Shared core (identical across all three): Poisson arrival generation, concurrent submission, timing, logging schema.
Per-architecture adapters: transaction construction, submission, confirmation polling.

Known risks being designed around: **nonce management under concurrent submission** (needs a pool of pre-funded accounts, not one sender), and **generator-side bottlenecking** before 300 TPS (needs multiple worker processes).

Methodology-section consequence: Caliper is dropped as a named tool and must be justified in the write-up. The justification is straightforward — cross-architecture comparability.

---

## 8. Data — LOCKED

**SQLite** as the primary store (Angad's criterion: easiest to interpret with AI later). One file, self-describing schema, and Phase 6 cross-architecture queries become single SELECTs instead of pandas glue. **Per-run CSV exports** alongside it for portability and for anything that wants flat files.

Recorded per run: full per-transaction records (submit ts, confirm ts, status, gas used, size, load level, repeat index, architecture, run id) plus a per-second time series, the node-offline event log, and the spot-preemption log.

Storing per-transaction rather than pre-aggregated data means new questions can be answered later **without re-running anything** — the cheapest possible insurance given cluster time is the main cost.

---

## 9. Scope boundaries — LOCKED

**Interoperability with fiat rails (SWIFT/RTGS) is Design Science only.** Nothing built or prototyped for it in Phases 1-5. A minimal mock settlement bridge is a *stretch goal only* if time remains after Phase 6, and must never block or draw budget from the three-architecture benchmarking, which is the paper's empirical core. (Angad's explicit ruling.)

---

## 10. Literature credibility — IN PROGRESS

Angad asked that `claude.md` §11 figures be verified, not just used. Initial flags:

- **"Polygon PoS theoretical max ~3,800 TPS"** — this is a widely-repeated *vendor/marketing* figure, not a peer-reviewed measurement. Observed sustained mainnet throughput is far lower (order of tens of TPS). Must be labeled as a theoretical vendor claim, and it is the *wrong* thing for our measured results to be compared against as though it were an empirical benchmark.
- **OmniLedger (~6,000 TPS) and RapidChain (~7,384 TPS)** — these come from genuine peer-reviewed venues (IEEE S&P 2018; ACM CCS 2018) and are citable, but were obtained under favorable lab assumptions that must be stated alongside the numbers.
- **El Salvador ~0.7%** — traceable to central bank (BCR) reporting; credible.
- **Waugh & Holz** — verified, and `claude.md` describes it backwards. See §0.2.

Full verification pass pending.

---

## 11. Open items — all closed as of 7 Aug 2026

| Item | Resolution |
|---|---|
| §1.1 Polygon Edge over CDK | Signed off by Angad, despite contradicting his literal instruction |
| §4 Cost-per-transaction methodology | Approved; formalized in `ANALYSIS_PLAN.md` §6.3 |
| §5 Test matrix | Full 465-run matrix chosen over the 240-run trim |
| §6.5 Repo private | Done |
| Cloud provider | **GCP.** Paid billing account active, $300 credit unused, **expires 6 Nov 2026** |
| Analysis plan | Locked 7 Aug 2026 — see `ANALYSIS_PLAN.md` |

### Additional decisions made 7 Aug 2026

- **OpenTofu replaces Terraform.** Drop-in fork, identical configuration language, but MPL-licensed rather than HashiCorp's BSL — cleaner for a repo that goes public at publication. Also in Homebrew core, so it installs without adding a third-party tap.
- **Polygon finality: N = 1.** PolyBFT gives deterministic instant finality; extra confirmations would add delay that doesn't exist.
- **Architecture-selection thresholds: p95 latency < 10s, cost < $0.10/tx.** Anchored to UN SDG 10.c rather than to our expectations.
- **Warm-up: discard the first 10 seconds**, reversing the earlier no-discard call.
- **Calibration reports two figures** — demand ratio and capability gap — because mainnet observed throughput measures demand, not capacity.
- **Data lives in two committed Parquet files** (raw + clean), because GitHub rejects files over 100 MB and the SQLite dataset is ~1.3 GB.
