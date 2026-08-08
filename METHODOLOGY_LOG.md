# Methodology Log

**Purpose**: a complete, citable record of every methodological choice made in this study — what was done, the exact parameter values, why that choice over the alternatives, and when it was decided. Written so the paper's Methodology section can be drafted from this file alone.

**Maintained continuously.** Every new realism technique, threshold, or parameter change is recorded here as it happens, not reconstructed afterwards.

Last updated: **8 August 2026**

---

## 1. Software under test — exact versions

| Component | Version | Notes for the paper |
|---|---|---|
| Polygon Edge | **v1.3.2**, released 24 Jan 2024 | The final release. Repository archived read-only 4 Dec 2024, so this version is permanent and the study is exactly reproducible. Verified against the GitHub releases API on 7 Aug 2026. |
| Consensus | **IBFT, proof-of-authority** | Chosen over PolyBFT — see §3.2 |
| Operating system | Ubuntu 22.04 LTS | |
| Solidity compiler | 0.8.24, **targeting the "london" instruction set** | Not the compiler default — see §3.3 |
| Measurement harness | Custom, this repository | Hyperledger Caliper rejected — see §3.1 |
| Python | 3.11 (cloud), 3.12 (local) | |
| web3 library | 7.16.0, pinned | |
| Infrastructure tooling | OpenTofu 1.12.5 | Chosen over Terraform for licensing — see §3.4 |

---

## 2. The private network

| Parameter | Value | Reasoning |
|---|---|---|
| Chain ID | 100100 | Arbitrary, unused by any public network |
| Validators | 4 | Smallest genuinely Byzantine-fault-tolerant set (tolerates one failure) |
| Block gas limit | 30,000,000 | Matches Polygon mainnet |
| Block time | ~2s | Polygon Edge default |
| Premined balance | 1,000,000 native coin | Funds contract deployment and wallet setup |
| Disk per node | 100 GB | See §3.5 — deliberately not matched to published specs |

### Regions, mapped to real remittance corridors

Chosen to model actual money flows rather than arbitrary geography. Same cost, stronger methodological claim.

| Validator | Region | Corridor role |
|---|---|---|
| 0 | `us-east4` (Virginia) | US — largest sending country |
| 1 | `asia-south1` (Mumbai) | India — largest receiving country |
| 2 | `asia-southeast1` (Singapore) | SE Asia / Philippines corridor |
| 3 | `europe-west2` (London) | UK — major sender to South Asia |

Validators communicate over internal addressing across Google's global network: real physical distance, but off the public internet. Measured generator-to-validator round trip inside one region: **0.165 ms**.

---

## 3. Decisions that need defending in the paper

### 3.1 Hyperledger Caliper was dropped
Caliper has no connector for Lightning or NEAR, so those needed custom generators regardless. Using Caliper for Polygon alone would have placed **two different measuring instruments inside a three-way comparison** — precisely the weakness a reviewer would attack in the cross-architecture section. One custom harness with per-architecture adapters keeps every number produced by identical timing, arrival and logging code.

### 3.2 IBFT rather than PolyBFT
PolyBFT requires a second "root" blockchain to anchor to, which would mean deploying and measuring a bridge alongside the sidechain. The study concerns the sidechain's own settlement performance, not bridge latency. IBFT isolates the subject. No cost to the finality claim: IBFT is also deterministically final. Note that Polygon Edge prints a deprecation warning for IBFT — worth acknowledging in Limitations.

### 3.3 Solidity targets "london", not the compiler default
Solidity 0.8.20+ targets the Shanghai instruction set (April 2023), which includes the PUSH0 opcode. Polygon Edge v1.3.2 predates it. Shanghai-compiled bytecode is accepted, mined, and reverts having consumed **exactly the full gas limit** — a failure that resembles nothing about a compiler problem. PUSH0 is a minor gas optimisation, not a feature; contract behaviour is identical either way.

### 3.4 OpenTofu rather than Terraform
Drop-in fork with identical configuration language, but MPL-licensed rather than HashiCorp's BSL. Relevant because this repository becomes public at publication.

### 3.5 Processor and memory matched to real validators; storage deliberately not
Published validator specifications quote very large disks (Polygon ~1.2 TB, NEAR ~1 TB) **purely to hold years of mainnet history**, which a freshly created private chain does not have. Processor and memory determine consensus and execution performance; storage is an artifact of history we do not possess. Provisioning 1 TB per node would have cost hundreds of dollars storing nothing.

### 3.6 Stablecoin transfers, not native coin
Real remittances on Polygon move USDC/USDT. A token transfer costs roughly **three times** the computational work of a native transfer, because it reads and writes balances held inside a contract. Benchmarking native transfers would understate the true cost of a remittance threefold. The test token uses **6 decimals**, matching USDC and USDT, so $1 = 1,000,000 base units and the test amounts require no exchange rate.

---

## 4. Realism techniques — exact parameters

### #1 Multi-region deployment — **applied and validated**
Four regions as listed in §2. Confirmed working 8 Aug 2026: consensus reached and blocks produced across four continents.

### #2 Injected latency, jitter and packet loss — **built, not yet run**

Applied with the Linux kernel's own network emulator (`netem`) to each validator's primary interface, affecting consensus traffic between validators. The generator's path is deliberately left unimpaired — the measuring instrument should not be degraded, only the system under test.

| Validator | Corridor | Added one-way delay | Jitter | Packet loss |
|---|---|---|---|---|
| 0 | US (Virginia) | +20 ms | ±4 ms | 0.10% |
| 1 | India (Mumbai) | +45 ms | ±12 ms | 0.40% |
| 2 | SE Asia (Singapore) | +40 ms | ±10 ms | 0.30% |
| 3 | UK (London) | +25 ms | ±6 ms | 0.15% |

Jitter uses a normal distribution rather than uniform, matching how real networks vary.

**Why this is needed on top of real geography**: multi-region already provides genuine intercontinental distance, but across Google's private backbone — dedicated fibre, near-zero loss, stable timing. Real validators sit behind ordinary ISPs. The distinction matters because **consensus protocols tolerate latency well but loss badly**: everyone simply waits longer for delay, whereas a dropped vote is indistinguishable from a silent validator until a timeout expires.

**Values add only the difference** between backbone and public-internet paths, not the full public-internet figure, which would double-count the latency already present.

**Sources** (to be cited, pulled 8 Aug 2026):
- ITU-T Y.1541 network performance classes — international paths target ≤0.1% loss for real-time classes; general internet paths commonly exceed this
- National broadband measurement programmes (Ofcom UK, FCC US) — typical fixed-line loss 0.1–0.5%, jitter 2–10 ms domestically, rising on long-haul international routes
- Long-haul intercontinental public-internet routes typically add 20–60 ms over the equivalent private-backbone path, chiefly from less direct routing and additional hops

Values are deliberately conservative. Overstating impairment would bias results pessimistically, which is as misleading as understating it.

### #3 Competing background traffic — **built, not yet run**

| Parameter | Value |
|---|---|
| Transaction type | Native value transfer, **21,000 gas** |
| Rate | Varies between a configurable floor and ceiling (default 20–80/sec) |
| Rate pattern | Two overlaid sine waves — one at half the run length, one at 37 s |
| Accounts | Separate pool, no overlap with the measured workload |

**Why a different transaction type**: noise consumes 21,000 gas against the measured workload's 35,865. That gap keeps the two **separable in the block data afterwards**. Identical transactions would be impossible to tell apart.

**Why two overlaid waves**: a single wave would place every test window at the same phase, letting the workload synchronise with congestion instead of meeting it at random — exactly the artificial regularity this technique exists to remove.

**Why separate accounts**: shared accounts would collide on transaction ordering, and the resulting interference would be our own doing rather than genuine congestion.

**What it corrects**: every measurement to date ran against an essentially empty chain — roughly 4% of block capacity used at 300 payments/second. Real remittances compete for block space.

### #4 Hardware matched to real validator specs — **NOT YET BUILT**
Unblocked 8 Aug 2026 when the processor quota rose from 32 to 48. Constraint: 4 validators at 8 processors plus an 8-processor generator = 40, within the cap. Seven validators at real spec would need 64. **The trade-off between validator count and realistic hardware is an open decision.**

### #5 Lightning liquidity topology — Phase 3, not applicable to Polygon

### #6 Adversarial / unreliable nodes — **built, not yet run**

| Parameter | Value |
|---|---|
| Outage duration | Random, 15–45 s |
| Gap between outages | Random, 20–60 s |
| Maximum simultaneously offline | **1** (enforced, not assumed) |
| Never targeted | Validator 0 |
| Logging | Every event timestamped to millisecond, with node and cause |

**Why at most one node down**: Byzantine fault tolerance survives fewer than one third of nodes failing. With four validators that is exactly one — two halts the chain entirely, which measures nothing except that we broke it. The script enforces this rather than trusting a percentage.

**Why validator 0 is never targeted**: it hosts the endpoint the harness submits through. Taking it down would measure our own loss of connectivity rather than the network's tolerance of a missing validator.

**Why a separate arm rather than folded into every run**: with failures injected everywhere, "degrades under load" and "degrades under node failure" could never be separated. The finding is the *difference* between clean and adversarial arms at the same load, and that difference requires a clean comparison to exist.

**Why every event is logged**: a deliberate outage is indistinguishable from a cloud provider reclaiming a spot instance. Conflating the two would corrupt exactly the comparison this arm exists to make.

### #7 Calibration against mainnet — Phase 5, not yet started

### #8 Five repeats / confidence intervals — **wired, not yet run**
Five repeats per configuration, each with a **different arrival seed** derived deterministically from one project-wide base seed (20260807). Repeats sharing an arrival pattern would understate variance and produce artificially narrow intervals.

---

## 5. Workload parameters

| Parameter | Value | Source / reasoning |
|---|---|---|
| Transaction amounts | $10, $50, **$200**, $500 | $200 is the World Bank's standard for remittance price surveys |
| Load levels | 10, 25, 50, 100, 150, 200, 300 /sec | ~140–150/sec is the global remittance average ($905B/yr ÷ $200); 200–300 represents realistic peak |
| Window per run | **300 s** | High end of the range, to catch degradation appearing only under sustained load |
| Repeats | 5 | |
| Arrival pattern | **Poisson** | Real payments arrive at random moments. Evenly-spaced traffic never produces the bursts where queues form. |
| Base seed | 20260807 | Makes every arrival pattern reproducible |
| Submission | **Concurrent**, never send-and-wait | Sequential submission measures single-payment round trip, a different and much easier question |
| Gas limit per transaction | 120,000 | Ceiling only; actual consumption is measured |

---

## 6. Measurement definitions

| Term | Definition |
|---|---|
| **Achieved throughput** | Successfully settled payments per second. **Failures excluded.** |
| **Settled (Polygon)** | Included in a committed block — **N = 1**. PolyBFT/IBFT give deterministic instant finality; there is no reorg window to wait out. Waiting extra blocks would add delay that does not exist and mask a genuine architectural advantage. |
| **Settled (Lightning)** | Sender receives the payment preimage |
| **Settled (NEAR)** | Outcome at `FINAL`, not `EXECUTED_OPTIMISTIC` |
| **Failed** | Not settled within **60 s** — roughly 10× expected p99; past that a remittance has functionally failed |
| **Warm-up exclusion** | Payments with submission time **< 10.0 s** excluded, by submission not by window, so no settlement is counted with a truncated latency |
| **Generator saturated** | Harness p95 scheduling lag **> 40 ms** — see §7.2 |

### Cost methodology
Fees on a private chain are an artifact of our own configuration and would be circular to report. Instead: measure **gas consumed** (deterministic, architecture-determined, genuinely real), then convert using **real mainnet prices from public explorers on a single stated date**, cited once for the whole paper.

**Measured: 35,865 gas per stablecoin transfer.**

⚠️ **Open question.** This assumes the recipient already holds the token. A first-time recipient costs roughly 40% more, because writing a balance from zero is far more expensive than updating one. We warm recipients deliberately, so ours is the **repeat-transfer** cost. Whether that or the first-time figure belongs in the paper depends on whether corridors are modelled as recurring family transfers or one-off sends.

---

## 7. Methodological corrections made during the study

These belong in the paper. Each one changed a result or a threshold.

### 7.1 Waugh & Holz (2020) was described backwards in the project's own notes
The working notes claimed success rates as low as ~15–35% for the *smallest* payments while simultaneously claiming an inverse relationship — self-contradictory. Verified against the source (arXiv:2006.14358): success ranged **15.32%–72.09%, inversely related to payment size**, so ~72% at the smallest and ~15% at the largest. The stray one-third figure was their separate **node-reachability** result, roughly independent of payment size.

**Caught before any data collection.** Had it survived, our Lightning results agreeing with the literature would have read as contradicting it.

### 7.2 The saturation threshold was tightened from 250 ms to 40 ms
A run at 150 payments/second showed 141 ms of p95 scheduling lag — inside the original threshold, therefore recorded as **valid** — and reported 19.26 s settlement. The same configuration re-run across four processes showed 11 ms of lag and **3.51 s** settlement. The "valid" run had overstated settlement by **5.5×** and produced a reported throughput knee that does not exist.

**Lesson**: passing a saturation check is not the same as being unaffected by saturation. Client-side backpressure distorts measurements long before it appears as gross lag. Two runs were retroactively invalidated under the new threshold, with reasons recorded rather than silently dropped.

### 7.3 A reported finding was retracted
An earlier session reported a throughput knee between 100 and 150 payments/second. **It did not exist** — it was single-process backpressure in our own harness. Corrected 8 Aug 2026. Polygon sustains the full tested range with zero failures.

### 7.4 Proof-of-authority headers broke settlement detection entirely
Polygon Edge stores validator signatures in each block header's `extraData`, exceeding Ethereum's 32-byte limit. The web3 library rejected every block as malformed, so no settlement was ever detected, every payment timed out, and the run reported **100% failure** — a plausible-sounding architectural result that was purely our client refusing to read blocks.

**This is the single strongest argument for why the pipeline-validation phase exists**, and belongs in the Methodology.

---

## 8. Data handling

| File | Contents |
|---|---|
| `data/raw/all_runs_raw.parquet` | Every payment from every run. Nothing removed. Invalidated runs retained and flagged. |
| `data/clean/all_runs_clean.parquet` | The dataset results are built from |
| `data/clean/exclusions.log` | Every exclusion with run ID, triggering rule and reason |

Per-payment records, never pre-aggregated, so questions thought of later can be answered by query rather than by re-running experiments.

**Exclusion rules were locked before any data existed** (`ANALYSIS_PLAN.md` §7): warm-up, generator saturation, spot-instance reclamation, and infrastructure faults outside the adversarial arm. **Runs are never excluded for producing an inconvenient result.**

As of 8 Aug 2026: **207,065 payments across 23 runs**, of which 9 are flagged invalid. The clean dataset is **empty**, correctly — no run yet meets the pre-registered protocol of 300-second windows and five repeats.

---

## 9. Known limitations to state in the paper

1. Results are an **upper-bound estimate under controlled, partially-realistic conditions**, not a replication of mainnet behaviour.
2. Polygon Edge is **archived software**, frozen December 2024.
3. **IBFT is deprecated** within Polygon Edge itself.
4. Sharding results will describe **NEAR specifically**, not sharding as a concept.
5. **Only settlement is measured** — the fiat conversion at each end is not modelled, and prior research suggests it may dominate real-world remittance friction.
6. **Validator count is below mainnet.** Real Polygon PoS has ~100; this study uses 4. Consensus messaging grows with the square of node count, so a larger set would be slower.
7. The three architectures **do not carry the same asset** — Polygon and NEAR move stablecoins, Lightning moves BTC, because the base Lightning protocol has no stablecoin.

---

## 10. Change log

| Date | Change | Reason |
|---|---|---|
| 7 Aug 2026 | Analysis plan locked | Before any Phase 2+ data collection |
| 7 Aug 2026 | Warm-up discard reversed to 10 s | Cold-start effects were skewing averages |
| 7 Aug 2026 | Full 465-run matrix adopted over a 240-run trim | Unqualified symmetry claim, ~$35 |
| 8 Aug 2026 | Polygon finality fixed at N = 1 | Deterministic instant finality; extra confirmations would add delay that does not exist |
| 8 Aug 2026 | Solidity pinned to "london" | v1.3.2 predates PUSH0 |
| 8 Aug 2026 | Saturation threshold 250 ms → 40 ms | See §7.2 |
| 8 Aug 2026 | Load split across worker processes | Single process capped near 150/sec |
| 8 Aug 2026 | Reported knee at 100–150/sec retracted | Was our harness, not the chain |
| 8 Aug 2026 | Idle-shutdown signal changed to block contents | Original watched a port validators use among themselves; cost $1.61 |
| 8 Aug 2026 | Processor quota raised 32 → 48 | Unblocks hardware matching |
