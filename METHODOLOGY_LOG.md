# Methodology Log

**Purpose**: a complete, citable record of every methodological choice made in this study — what was done, the exact parameter values, why that choice over the alternatives, and when it was decided. Written so the paper's Methodology section can be drafted from this file alone.

**Maintained continuously.** Every new realism technique, threshold, or parameter change is recorded here as it happens, not reconstructed afterwards.

Last updated: **22 August 2026**

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

### #2 Injected latency, jitter and packet loss — **applied and validated 8 Aug 2026**

**Measured effect** (300 payments/sec): settlement rose from **3.80 s to 7.63 s**, roughly doubling. At 100/sec the effect was negligible (3.26 s → 3.35 s). Impairment therefore interacts with load rather than adding a constant penalty — at low load there is slack to absorb retransmission, at high load delays compound.

**Correction made during validation.** The first implementation attached the emulator to the whole network interface, which also delayed the load generator's own submissions. The generator's scheduling lag jumped from 10 ms to 553 ms at 100/sec and 48 s at 300/sec, invalidating both runs, while the chain itself was unaffected. Now applied through a priority queue with filters matching only other validators' addresses, so consensus traffic is impaired and the measurement path is not. **A benchmark must degrade the system under test, never the instrument measuring it.**

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

### #3 Competing background traffic — **applied and validated 8 Aug 2026**

| Parameter | Value |
|---|---|
| Transaction type | Native value transfer, **21,000 gas** |
| Rate | Varies, **60–115/sec, mean ~88** — calibrated to observed mainnet activity |
| Rate pattern | Two overlaid sine waves — one at half the run length, one at 37 s |
| Accounts | Separate pool, no overlap with the measured workload |

**Why a different transaction type**: noise consumes 21,000 gas against the measured workload's 35,865. That gap keeps the two **separable in the block data afterwards**. Identical transactions would be impossible to tell apart.

**Why two overlaid waves**: a single wave would place every test window at the same phase, letting the workload synchronise with congestion instead of meeting it at random — exactly the artificial regularity this technique exists to remove.

**Why separate accounts**: shared accounts would collide on transaction ordering, and the resulting interference would be our own doing rather than genuine congestion.

**Calibration to real mainnet activity (8 Aug 2026).** Polygon PoS carries roughly **7.5 million transactions per day — about 87 per second** — and is reported at 68–109/sec during normal operation. Our initial default of 20–80/sec (mean ~45) **understated real background load by roughly half**, which would have made our chain appear emptier, and therefore better-performing, than the network it stands in for. Raised to 60–115/sec for a mean near 87.

This is a case where checking realism made results *worse*, which is the direction that matters.

**What it corrects**: every measurement before this ran against an essentially empty chain — roughly 4% of block capacity used at 300 payments/second. Real remittances compete for block space.

**Resulting utilisation**: at 300 remittances/sec plus ~87/sec of background traffic, block utilisation reaches roughly 84% (300 × 35,865 + 87 × 21,000 gas per second, against 15M gas/sec capacity). Real Polygon at ~87/sec of mixed traffic runs nearer 29%. The difference is the experimental variable — we are deliberately offering peak remittance demand on top of realistic ambient load.

### #4 Hardware matched to real validator specs — **applied 8 Aug 2026**
Validators run **n2-standard-8 (8 vCPU / 32 GB)**, matching Polygon's published validator guidance. Generator likewise 8 vCPU. Total 40 of the 64-core quota. Storage deliberately not matched (§3.5).

**Measured effect**: at 300 payments/sec, settlement improved from **5.30 s on 4-core validators to 3.80 s on 8-core** — a 28% reduction. This is the one realism technique that makes results *better*, and it is worth stating as such: matching real hardware is not automatically a pessimising choice.

### #5 Lightning liquidity topology — Phase 3, not applicable to Polygon

### #6 Adversarial / unreliable nodes — **applied and validated; full arm run 9 Aug 2026**

⚠️ **THE MOST IMPORTANT LIMITATION IN THIS STUDY. State it in the paper before a reviewer states it for you.**

**Our failure injection is roughly 130× more hostile than real Polygon mainnet.** Measured from the actual event log across a 43-minute window: 33 complete outages, with a validator offline **51% of the time**, meaning about **13% of network capacity missing on average, continuously**.

Real conditions are nothing like that:

| | This study | Real Polygon PoS |
|---|---|---|
| Validators | 4 | ~100 |
| One validator down removes | **25%** of the network | ~1% |
| Typical availability | offline 51% of the time | 99.9%+ uptime target |
| Average capacity missing | ~13% | ~0.1% |
| Penalty for downtime | none | jailing and stake slashing |

**Two structural reasons, both unavoidable at this cluster size.** First, with only four validators the smallest possible failure unit is 25% of the network — already above the 10-20% the technique specifies, and impossible to reduce without more nodes. Second, real validators are run by professionals on redundant infrastructure and are *financially penalised* for downtime; ours are not, and fail every few seconds rather than every few months.

**What the arm therefore does and does not measure.** It does **not** predict mainnet behaviour under node failure, and no result from it should be phrased that way. It measures **sensitivity to validator loss** — how gracefully the architecture degrades when a substantial share of consensus disappears.

That reframing keeps the finding genuinely useful, because the answer turned out to depend entirely on load headroom (see §9.2). A defensible sentence for the paper: *"Under sustained validator unavailability far exceeding realistic mainnet conditions, Polygon Edge degrades negligibly where load headroom exists and severely where it does not."*

**Configuration:**

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

### #7 Calibration against mainnet — **pricing and topology data pulled 9 Aug 2026; ratios still to compute**

External figures are recorded once in `data/reference/calibration_2026-08-09.md` and cited from there. Pulled: Polygon gas price and POL price (PolygonScan), and Lightning network topology (1ML).

The **key topology finding for realism technique #5**: average Lightning node capacity is **142× the median** (0.440 BTC vs 0.003107 BTC). That extreme skew is the network's actual structure — a few dominant hubs, thousands of thin leaves. Funding our test channels evenly would produce a network far easier to route through than the real one, understating exactly the routing failures this study exists to measure.

Still outstanding: NEAR pricing (Phase 4), and observed mainnet *peak* throughput for the capability-gap figure (§11 of the analysis plan).

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
| **Generator saturated** | Median scheduling lag **grew by > 50 ms** between the first and last quarter of a run — see §7.2 |

### Cost methodology
Fees on a private chain are an artifact of our own configuration and would be circular to report. Instead: measure **gas consumed** (deterministic, architecture-determined, genuinely real), then convert using **real mainnet prices from public explorers on a single stated date**, cited once for the whole paper.

**Measured: 28,538 gas per stablecoin transfer** (mean over the results dataset; median 27,465).

The distribution is tiered by EVM storage-access cost: ~27,465 gas where both balance slots are warm (80.1% of transfers), ~31,665 with one cold access (14.4%), ~35,865 fully cold (5.6%). Within each tier values vary by ±12 gas with the number of zero bytes in the encoded amount.

**Converted to dollars: $0.0006 per remittance.** Using PolygonScan's Standard gas price of 270.927 Gwei and POL at $0.0774, both pulled 9 August 2026 — see `data/reference/calibration_2026-08-09.md`, the single pricing reference for the whole paper. Clears the pre-registered $0.10 threshold by roughly 167×, and consumes 0.01% of the UN SDG 10.c budget of $6.00 on a $200 transfer.

Note that 270 Gwei is high against Polygon's historical 30-50 Gwei range, so this figure is **conservative** — a long-run average would be cheaper. Stated as a limitation rather than silently smoothed.

**RESOLVED 8 Aug 2026 — the warm-recipient figure is the correct one to report.**

The question was whether to use 35,865 (recipient already holds the token) or roughly 40% more (first-time recipient, where writing a balance from zero is far more expensive). The resolution rests on **what a scaled remittance system actually looks like on-chain**:

Remittances at volume do not move between self-custodied personal wallets. They move through institutions — a sending service converts fiat to stablecoin, transfers on-chain to a receiving partner, and the partner pays out in local currency. **The on-chain leg is therefore between a small, fixed set of institutional treasury addresses**, not between millions of distinct individuals. This is how live crypto-remittance products are built.

Consequently the first-time-recipient cost is paid **once per corridor partner, ever**, and amortises to nothing across the millions of transfers that follow. Reporting it as a per-transaction cost would materially overstate the settlement cost of every remittance after the first.

Our test configuration reflects this: **32 reused recipient addresses**, standing in for a limited set of institutional endpoints, rather than a fresh address per payment.

**Caveat to state in the paper**: this holds for the institutional model. A fully self-custodial design — sender's own wallet to recipient's own wallet, which some advocate specifically to remove intermediaries — would pay the cold-start cost on every new recipient. That is an architectural choice, and it is the kind of tradeoff the Design Science section should weigh rather than something the measurement should hide.

*Reasoning contributed by Angad, 8 Aug 2026.*

---

## 7. Methodological corrections made during the study

These belong in the paper. Each one changed a result or a threshold.

### 7.1 Waugh & Holz (2020) was described backwards in the project's own notes
The working notes claimed success rates as low as ~15–35% for the *smallest* payments while simultaneously claiming an inverse relationship — self-contradictory. Verified against the source (arXiv:2006.14358): success ranged **15.32%–72.09%, inversely related to payment size**, so ~72% at the smallest and ~15% at the largest. The stray one-third figure was their separate **node-reachability** result, roughly independent of payment size.

**Caught before any data collection.** Had it survived, our Lightning results agreeing with the literature would have read as contradicting it.

### 7.2 The saturation criterion measures lag GROWTH, not lag magnitude
A run at 150 payments/second showed 141 ms of p95 scheduling lag — inside the original threshold, therefore recorded as **valid** — and reported 19.26 s settlement. The same configuration re-run across four processes showed 11 ms of lag and **3.51 s** settlement. The "valid" run had overstated settlement by **5.5×** and produced a reported throughput knee that does not exist.

**But magnitude turned out to be the wrong measure.** A generator sitting a constant few milliseconds behind schedule distorts nothing: the load offered still matches the load intended. What corrupts a measurement is lag that **grows**, because the arrival pattern actually delivered then drifts away from the Poisson process that was scheduled.

At 200 payments/sec the median lag was 7.2 ms in the first quarter of a run and 7.2 ms in the last — perfectly flat — and settlement (3.69 s) continued smoothly from 150/sec (3.33 s). Nothing was distorted, yet a magnitude threshold excluded every run at 200 and 300/sec: precisely the peak-demand levels this study exists to measure.

**The single criterion, applied to every run in the study:** a run is excluded when its median scheduling lag rises by more than **50 ms** between the first and last quarter.

**Validation.** Applied to seven runs independently known to be broken — the pre-fix single-process runs, and the 500 and 1000/sec ceiling tests where settlement was inflated three- to elevenfold — the criterion detects all seven, including a subtle case growing 9.7 ms to 294.9 ms. It discriminates rather than merely permitting.

**Stated limitation.** Re-judging all 131 runs moved 24 from excluded to included and none the other way. That asymmetry is the signature of a criterion devised after seeing data, and a reader is entitled to weigh it. It is mitigated by uniform application across every run and by the validation above — not dismissed. An interim magnitude threshold used between 8 and 9 Aug never produced a reported result.

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

## 9.1 Polygon Edge — completed result (Phase 2, full realism stack)

Four validators across Virginia, Mumbai, Singapore and London at published production specification (8 vCPU / 32 GB), with injected per-corridor latency, jitter and packet loss on consensus traffic, and background traffic calibrated to real mainnet activity (~88 tx/sec). 300-second windows, 5 repeats, first 10 seconds discarded.

**Complete matrix: 140 of 140 configurations.**

At the $200 World Bank benchmark size:

| Offered/sec | Achieved | Failures | p50 | p95 | p99 |
|---|---|---|---|---|---|
| 10 | 9.9 | 0.00% | 3.19s | 4.16s | 4.40s |
| 25 | 25.0 | 0.00% | 3.19s | 4.17s | 4.39s |
| 50 | 50.0 | 0.00% | 3.20s | 4.22s | 4.46s |
| 100 | 100.1 | 0.00% | 3.23s | 4.25s | 4.52s |
| 150 | 150.3 | 0.00% | 3.31s | 4.38s | 4.70s |
| **200** | **200.9** | **0.00%** | 3.43s | 4.77s | 6.35s |
| 300 | 270.5 | 9.97% | 10.61s | 24.26s | 30.49s |

**Sustainable throughput at $200 = 200/sec**, per the pre-registered primary metric (§2 of the analysis plan: achieved ≥90% of offered AND failures <5%). At 300/sec both conditions fail — 90.2% of offered load delivered and 9.97% failures — so 200 is the highest step clearing the bar.

**The knee is between 200 and 300/sec.** Settlement is essentially flat from 10 to 200 (3.19s → 3.43s at the median), then rises threefold at 300 while failures appear for the first time. That is a system passing from comfortable to overloaded within one step of the ramp.

**Against the architecture-selection thresholds (§10):** at 200/sec Polygon clears both — p95 of 4.76s against a 10s ceiling, and cost well under $0.10. At 300/sec it fails the latency ceiling (p95 24.26s) as well as the failure bar.

**Transaction size does not drive failure**, as predicted in §12. At 300/sec: $10 9.79%, $50 8.51%, $200 9.97%, $500 12.85% — no monotonic relationship with amount. Compared within a storage tier, gas differs by 12 across all four amounts (0.044%), and that residue is calldata zero-byte cost rather than value. Consistent with the prediction that these networks charge for computational work rather than value moved. Contrast this with the inverse size/success relationship expected for Lightning.

**Note on the earlier exploratory figure.** A pilot at 60-second windows suggested Polygon sustained 300/sec with zero failures. The full protocol — 300-second windows and realistic background traffic — shows that does not hold under sustained load. Short windows measured the burst, not the steady state.

---

## 9.2 Adversarial arm — completed result

Same realism stack as the clean baseline, plus validators dropping offline throughout. 3 load levels × $200 × 5 repeats = 15 runs, 300-second windows. 119 outage events recorded and joined to the payment data.

| Offered/sec | Clean | With node failures | Throughput lost |
|---|---|---|---|
| 100 | 100.1/s, 0.00% fail | 99.4/s [99–100], 0.8% fail | **0.8%** |
| 200 | 200.9/s, 0.00% fail | 148.4/s [122–173], 26.1% fail | **26.1%** |
| 300 | 270.5/s, 9.97% fail | 156.2/s [93–203], 48.0% fail | **42.2%** |

**The damage scales with how loaded the system already is.** With ample headroom, losing a quarter of the validator set costs under 1% of throughput. At the sustainable ceiling it costs 26%. Past it, 42% — and nearly half of all payments fail.

**Polygon Edge does not degrade gracefully under node loss.** It absorbs a missing validator almost for free while slack exists, and collapses once it does not. There is no gentle middle.

**Note the spread.** At 300/sec, identical configurations produced 93 to 203 payments/sec — better than a 2× range. Outage timing is random, so a run where a validator drops during a lull survives far better than one where it drops mid-surge. A single run could have reported either extreme. This is the clearest justification in the study for the five-repeat protocol, and the reason this arm in particular must be reported as ranges rather than means.

**Why this matters for remittances.** Peak demand and infrastructure strain arrive together — payday clustering and holiday surges are exactly when systems are most loaded and most likely to have something fail. This curve says that is the worst possible combination. The design rule that follows: **size for node failure, not for clean-condition throughput.** A system provisioned on the clean 200/sec figure would lose a quarter of its payments the first time a validator rebooted during a busy period.

⚠️ **Read alongside the realism limitation in §4 technique #6.** The injection is ~130× more hostile than real Polygon. These figures measure *sensitivity to validator loss*, not expected mainnet behaviour.

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
| 8 Aug 2026 | Hard shutdown cap raised 480 → 780 min | The full sweep is 11.7 h; the old cap would have killed it two-thirds through |
| 8 Aug 2026 | Warm-recipient gas confirmed as the reported figure | Scaled remittances move between institutional treasury addresses, so cold-start cost amortises to nothing — see §6 |
| 8 Aug 2026 | Exploratory load levels added above 300/sec | Polygon cleared the whole pre-registered range; the ceiling is too low to find its limit. Primary metric unchanged. |
| 8 Aug 2026 | Processor quota requested 48 → 64 | Enables 7 validators at published production spec |
| 8 Aug 2026 | Background traffic raised 20–80 → 60–115/sec | Original understated real Polygon activity (~87/sec) by roughly half |
| 8 Aug 2026 | Receipt fetching made concurrent | Was serial, one round trip per transaction per block — the likely cause of generator saturation above 300/sec |
| 8 Aug 2026 | Impairment retargeted to consensus traffic only | Interface-wide application was degrading the measurement instrument, not just the system under test |
| 8 Aug 2026 | HTTP connection pool raised 100 → 256 | Default was below our concurrent demand; excess requests queued silently and would have been recorded as chain latency |
| 9 Aug 2026 | Realism configuration now recorded per run | `config_json` was empty; test conditions were only inferable from the phase name, which is a label rather than evidence. Backfilled onto 106 existing runs from this document, marked `backfilled: true`. |
| 9 Aug 2026 | Node outage events imported into the database | The adversarial script logged them to a text file the transaction data could not be joined to, defeating the point of logging them. |
| 9 Aug 2026 | Outage timestamp format corrected | The script used `%3N`, unsupported by the remote `date`, which emitted the literal characters "3N" and produced timestamps no parser accepts. |
| 8 Aug 2026 | Quota requested 64 → 96 | Two concurrent clusters halve sweep wall-clock at identical cost. Requests that DOUBLE the limit have been denied twice (32→128, 64→128); 50% steps were approved twice (32→48, 48→64). |

## Audit — 9 Aug 2026

Full re-verification of every published Polygon figure against the dataset, at Angad's request, before moving to Phase 3. Every headline number was recomputed from `data/clean/all_runs_clean.parquet` rather than carried forward from earlier notes.

**Two material findings.**

1. **22 duplicate runs.** The sweep's resume restarted from the beginning of the load ladder rather than the point of interruption, measuring 22 configurations twice with identical arrival seeds. Four matrix cells held 10 runs instead of 5. Excluded under `ANALYSIS_PLAN.md` §13 amendment 4; the matrix is now exactly 140 runs with 5 per cell. Effect on results negligible ($200 curve 200.8 to 200.9/sec at one step); all conclusions unchanged.

2. **Failure mechanism was mischaracterised — twice, and the second correction is a finding.** The status column carries three values, not two: `confirmed`, `failed` (rejected at submission) and `timeout` (accepted, then never settled). An initial check filtered on `failed` alone and concluded no timeouts existed anywhere. Re-checked against all three: **the clean 140-run matrix genuinely has zero accepted-then-lost payments** — every failure there is a queue rejection that never entered the chain. But **the adversarial arm has 7,944** (0.91%), at 200 and 300/sec only, each carrying a transaction hash and consuming no gas.

   This makes node failure materially worse than the throughput numbers alone suggest: it does not merely cut capacity, it introduces a failure mode — money accepted and not delivered — that is completely absent under clean conditions. Recorded in `POLYGON_ANALYSIS.md` §2 and §5. The lesson for the remaining architectures: **check every value the status column can take before characterising failure.**

**Four smaller corrections.** The gas tier table accounted for only 68.7% of transactions (the ±12 gas calldata variants were listed as separate tiers rather than grouped); mean gas refined to 28,538 and cost to 167× under threshold, still $0.0006. Size-independence restated within storage tier, isolating amount from storage warmth: 12 gas, 0.044%. Exclusion counts corrected — the 9 saturation/defect runs sit inside the 34 non-result phases rather than adding to them. Node-event import had 2 exact duplicates and one orphaned run.

**Confirmed unchanged:** the whole $200 curve, the 200/sec ceiling, the knee, every adversarial figure, background traffic at mean 87.5/sec, the warm-up rule, the 290s throughput denominator, and the matrix's completeness at 28 of 28 cells.

## Exchange rate pinned — 9/10 Aug 2026

Lightning is the only architecture needing a currency conversion. Polygon and NEAR carry stablecoins, so $200 is exactly 200 tokens; Lightning carries native BTC, so a rate is unavoidable.

**Pinned: $64,803.00 BTC/USD**, CoinGecko `simple/price`, observed 2026-08-10 00:45:20 UTC. Cross-checked against Coinbase spot ($64,817.29) in the same session — the two agree to 0.022%. Recorded in `data/reference/calibration_2026-08-09.md` §4.

**Why cross-checked.** This single number multiplies into every Lightning cost and success figure in the paper. One API can be stale; two independent sources agreeing to 0.022% makes a bad quote unlikely.

**Superseded value.** The Lightning code first used $65,163, *inferred* from 1ML's capacity figures ($172.4M ÷ 2,645.64 BTC) rather than quoted. Only 0.55% out, but an inferred rate is not citable. Replaced before any Lightning run was measured, so no result was ever computed from it.

**Held constant across every run** (`claude.md` §6), as a single constant `harness.topology.BTC_USD_PINNED` that the adapter and the funding script both import — they cannot drift apart.

**What it means for the arm.** At this rate a $200 remittance is 15.2% of a median Lightning channel and **99.3% of a median node's entire capacity**; $500 is 248%. That relationship is the structural reason payment size drives success on Lightning and not on Polygon, and it is why the topology keeps capacities at true mainnet scale rather than scaling down — shrinking the network would destroy the one ratio that decides every routing outcome.

## NEAR cluster size is quota-constrained — 10 Aug 2026

**Phase 4 will run 8 NEAR validators, not 12.** This is a constraint, and the paper should say so rather than present 8 as a free choice.

**What happened.** The project-wide vCPU ceiling is 96. A 12-validator cluster needs 104 (12 × 8 vCPU plus an 8 vCPU generator), so an increase to 144 was requested and **denied**. A reduced request to 120 is pending.

**Why 8 is still sufficient.** `claude.md` §4 sizes the cluster by NEAR's sharding structure: at least 4 shards with at least 2 validators each. Eight validators satisfies that exactly. Twelve was headroom, not a requirement.

**What is genuinely lost.** With 8 validators over 4 shards there are exactly 2 validators per shard and no margin: losing one node takes a shard to a single validator. That makes the adversarial arm harsher on NEAR than it was on Polygon, where losing one of four validators still left three. **State this when reporting NEAR's adversarial results** — the comparison is not like-for-like.

**A configuration requirement this creates.** The NEAR chain config must pin the shard count to 4. If it produces more shards than that, 8 validators cannot give every shard 2, and the deployment would silently violate the sizing rule the cluster was built to satisfy.

**Sequencing.** 8 validators plus generator is 72 vCPU; the Lightning cluster is 24. Together that is exactly 96, with no margin, so **Lightning must be destroyed before NEAR is deployed**.

## Phase 3 (Lightning) — decision and closure, 10 Aug 2026

### The decision

**Lightning's reliability and throughput data comes from Waugh & Holz (2020), not from our simulation.** Full reasoning in `LIGHTNING_ANALYSIS.md` §1 and `ANALYSIS_PLAN.md` §13 amendment 5.

The short version: Lightning capacity is **additive across channels**, and our testbed has 51 against the real network's 19,644 — roughly 385× fewer. Success behaviour depends on how many routing paths exist, so a network with 385× fewer paths does not behave like the real one. This is structural, not a bug, and no amount of debugging or budget within this project closes it.

> **⚠️ Citation corrected 18 Aug 2026:** the "6,010 nodes / 19,644 channels" figure does NOT appear in Waugh & Holz — zero occurrences in the full text. The paper states **4,826–4,950 nodes and ~31.4–31.8k channels** (Nov 2019). Against our 51 channels the true ratio is **~620x fewer, not 385x** — a stronger argument. 19,644 most likely came from 1ML, which publishes no collection timestamp and disagreed with mempool.space by 40% on 18 Aug 2026 (20,004 vs 33,313 channels). See `LIGHTNING_EVIDENCE.md` §2.

**Why Polygon did not have the same problem, and why that is not inconsistency.** Polygon is a replicated state machine: every validator processes every transaction, so throughput is set by the block gas limit and consensus timing rather than by validator count. Four validators and a hundred share the same ceiling. Our 4-validator measurement therefore transfers to mainnet; a 51-channel Lightning measurement does not.

### What Lightning still contributes

- **Cost per transaction**, built the same way as Polygon's: measure the architecture-determined quantity (route length, **2.571 hops at $200**), price it with real mainnet rates (1ML, 10 Aug 2026). **$0.0523 at $200, against Polygon's $0.0006 — a factor of 87.**
- **The §12 cost crossover, resolved.** Polygon's cost is flat with amount; Lightning's is proportional at 165 ppm. At $500 the Lightning routing fee alone is $0.1467, above the $0.10 selection threshold. The crossover lies below $500.

> **Corrected 12 Aug 2026** (ANALYSIS_PLAN amendment 10). Previously $0.0509/85× and $0.1267, from a **pooled** mean route length of 2.53 hops applied to every amount. Route length in fact varies with amount — 2.651 at $10, 2.571 at $200, 2.772 at $500 — and the pooled figure also omitted the §7 warm-up cut. All corrected figures move **up**, so the earlier numbers understated Lightning's cost. Also recorded: **$50 was never run on Lightning**, so its cost row is an extrapolation, and the $200 and $500 rows rest on 3 and 2 runs against the 5-repeat minimum.
- **Settlement time under clean conditions** — p50 1.501s — labelled small-scale illustrative.
- **The scale limitation itself**, as a methodological finding: Lightning's capacity is a property of deployed capital, not of the protocol.

### Faults found and fixed during Phase 3

Each produced a plausible number that was wrong. Recorded because the pattern matters more than any individual bug.

1. **Uniform destination selection.** Round-robin sent 1/7 of all flow at a node holding 0.01 BTC of inbound — 65 payments at $10 before it was full. Three thin recipients saturated, giving a hard 3/7 = 42.9% floor; observed was 43.3%. Replaced with capacity-weighted selection (2% floor so thin nodes stay in the sample). Ceiling went from 25/sec to 47/sec at 50 offered, failure 43% → 5.4%.
2. **A rebalancer that never ran.** It checked whether any payment had succeeded one second after firing them asynchronously, so the answer was always no and it quit after 40 attempts — restoring 0.006 BTC per gap instead of ~5. Sender liquidity fell from 38.6 to 25.3 BTC and failures reached 71%, which read as Lightning degrading under load.
3. **Round-robin draining.** Even after (2), the rebalancer treated a recipient with 28 BTC of headroom the same as one with none. Now drains worst-first, re-ranking every 20s.
4. **Sequential invoice minting.** One HTTP round trip each to nodes in Mumbai and Singapore at 315ms — 81 minutes of setup per 300/sec run. Now concurrent: 3 minutes.
5. **A connection limit sized for the wrong API.** Every in-flight Lightning payment holds an *open streaming connection* until it resolves; at 300/sec that is ~1,400 at once against a limit of 256 inherited from Polygon's request/response calls. Raised to 4,096.
6. **Mission control reset — tried and reverted.** On the theory that carrying learned routing state made repeats non-independent. **Measured it making things far worse:** 3–17% failure became 71%. LND's learned routing state is what makes a topology navigable, and real senders accumulate it too. Kept, with the mild drift across repeats reported as a limitation instead.
7. **Resume logic that ignored completion.** The sweep's skip check tested `invalidated=0` but not whether a run had finished, so an interrupted run counted as complete and its configuration was silently skipped.
8. **Exploratory phases missing from the exclusion list**, which would have let smoke and diagnostic runs flow into the clean results file.

Infrastructure faults, recorded in `RESUME_HERE.md` §5: bitcoind requiring network options under `[regtest]`; ZMQ ports never opened; an empty chain blocking LND startup; the Polygon idle watcher shipping onto Lightning hosts and shutting the cluster down five times; funding by mining instead of transfer, which mined 25,000 blocks while funding nobody; channel-size caps refused by the peer; and `pkill` matching its own SSH command line.

### Cost methodology — why our own fees were not reported

Our LND nodes ran the stock policy: 1,000 msat base per hop plus 1 ppm. At $200 that predicts 1,308.6 msat per charging hop × 1.571 hops = 2,056 msat, and the measured mean was 2,016 — i.e. the "measured" fee was essentially our own configuration, reproducible to within 2% from the config file alone. Reporting it would repeat the exact circularity §6.3 identifies for Polygon's gas price. Route length is measured; the price comes from 1ML.

### Scope closure

No further Lightning testing is scheduled. Four candidates were assessed and recorded in `ANALYSIS_PLAN.md` §13 amendment 7. One — even versus hub-and-spoke liquidity funding — is **parked rather than rejected**, since real providers concentrate liquidity along the corridors they serve; revisit only if NEAR and Phases 5-6 finish with time and budget to spare.

---

## Phase 4 (NEAR) — constraints and corrections, 11 August 2026

**Status at the time of writing: 0 of 140 configurations collected.** The entries below are
recorded now because two of them are properties of the architecture that belong in the
paper regardless of how the run eventually goes, and one is a measurement error that must
not be quietly forgotten.

### 4a. The sender pool size is a NEAR concurrency limit, not a harness detail

NEAR orders transactions **per access key by nonce**. A single account therefore cannot hold
two payments in flight: the second is either rejected or must wait. At roughly 2s to
inclusion, a pool of N sender accounts imposes a ceiling near **N/2 transactions per
second**.

The 64-account pool inherited from the smoke tests capped throughput near **32/sec** against
a matrix whose top step is **300/sec**. The pool was therefore rebuilt at 900 accounts, of
which **836 are verified usable** (see 4c), giving a ceiling near 418/sec.

**This is the sharding analogue of Polygon's nonce-pool problem** (§7 of this log) and it is
a real architectural property, not an artifact of our tooling: any NEAR remittance operator
sending at scale must shard its own sending keys. It should be stated in the Methodology
alongside the Polygon equivalent, and it is a genuine finding about operating on NEAR.

### 4b. Four valid runs were invalidated as *superseded*, not as faulty

Four `phase-4-full-stack` runs ($10 at 10/sec and 25/sec) were collected successfully with
the 64-account pool before the pool was enlarged. They are marked `invalidated = 1` with
reason `superseded: measured with the 64-account sender pool …`.

**They were not wrong; they were measured under a different configuration.** Reporting them
in the same table as 836-account runs would place a mid-study parameter change inside one
results table. Nothing was deleted — the rows and their transactions remain in the raw
data, per the "nothing is ever deleted" rule in §8.

### 4c. Sixty-four sender accounts had keys that did not match the chain

The 900-account bootstrap reused account names that already existed from the 64-account
pool. `CreateAccount` failed for those names, but the newly generated keys were written to
the keys file regardless, producing 64 accounts whose private keys corresponded to no
on-chain access key (`access key … does not exist while viewing`).

They were dropped rather than repaired — an account's key can only be replaced by a
transaction signed with the key we did not have. **836 senders remain, verified against
chain, funded, registered with the token contract, and spread 209/209/209/209 across the
four shards.** `scripts/near_bootstrap.py` still needs a guard so this cannot recur.

### 4d. Measurement error: every Phase 4 "failure" so far is an artifact

All Phase 4 runs to date recorded 100% failure with the error `never broadcast within 60s`.
**The chain was not at fault and the payments were settling normally.** Two client-side
defects produced this:

1. **`py-near` 1.2.22's `nowait=True` does not mean "do not wait."** Its own docstring
   marks it legacy and aliases it to `included`, which blocks server-side until block
   inclusion (~2s) against a 10s node ceiling. Replaced with local signing plus
   `broadcast_tx_async`.
2. **A race on the pending-hash dictionary.** `await_confirmation` popped the entry before
   the newly created send task had run, so the task broadcast the payment and then
   discarded its hash.

**No Phase 4 failure rate from before this date carries any information about NEAR**, and
none of it may be reported. The affected runs are invalidated and retained. This is the
same class of error as the Lightning rebalancer no-op recorded in §7: a measurement
instrument reporting confidently on something it was not measuring.

---

## Phase 4 (NEAR) — validator churn, and why spot was abandoned, 12 August 2026

### 5a. The race fix is verified working

The `_hashes` race described in §4d is fixed and **executed against the live chain for the
first time on 12 Aug**: 400 payments at 50/sec produced **382 confirmed, 18 timeouts**,
against 0 confirmed on every previous attempt. Cross-shard share was **73.8%**, against the
75% that $(S-1)/S$ predicts at 4 shards.

Run as a standalone probe (`submit()` then `await_confirmation()` immediately, the exact
ordering that triggered the race) rather than through the harness, because the harness
health check correctly refuses to run against an incomplete validator set. **These numbers
are a test of our own code and are not a measurement of NEAR.** They are recorded here only
as evidence that the instrument works.

### 5b. Settlement deadline corrected — NEAR had twice Polygon's budget

`NearAdapter.await_confirmation` allowed `timeout_seconds` for the broadcast future and
then started a **fresh** `timeout_seconds` for the FINAL poll, so a NEAR payment had up to
**120s** where the pre-registered timeout is 60s (claude.md §7) and where Polygon enforces a
single 60s across submission and settlement.

A NEAR payment could therefore have been recorded as settled while the identical Polygon
payment was already a failure. That is a real advantage for one architecture sitting inside
the three-way comparison the study exists to make. Corrected to one shared deadline started
when `await_confirmation` is entered, matching Polygon exactly.

**No results are affected**: Phase 4 had zero valid runs when this was found. Had it been
found later, every NEAR run would have needed re-running.

### 5c. Spot instances abandoned for this phase — preemption causes EXPULSION, not a restart

The cost of a reclaimed validator was badly underestimated in the earlier planning. It is
not a restart. The sequence is:

1. GCP reclaims the instance; it is down for minutes.
2. It returns and resumes producing normally.
3. But it has missed blocks and chunks it was scheduled to produce, and NEAR scores each
   validator per epoch against `block_producer_kickout_threshold` and
   `chunk_producer_kickout_threshold`, **both 90%** on this chain.
4. Below either threshold the protocol **expels** it. The deficit is arithmetic and cannot
   be recovered inside the epoch.
5. Re-admission requires a fresh `StakeAction` and takes effect **two epochs later**. At
   `epoch_length` 3600 and 2s blocks that is **four hours**.

Observed directly: `node0` was reclaimed at 11:31 UTC on 11 Aug, scored 91/467 blocks
(19%) and was expelled. `node1` was reclaimed at 00:04 UTC on 12 Aug, recovered to 100%
block production within minutes, and was still expelled on a 63% epoch score.

With 8 validators over 4 shards, losing one leaves a shard with a single producer, and the
harness health check then refuses to run at all. **A single preemption therefore costs four
hours of collection, not fifteen minutes** — and over a 13-hour sweep across 7 spot machines
it was close to certain to happen more than once.

All nine machines were converted to `STANDARD` (on-demand) on 12 Aug. Cost rises from
~$1.40/hr to ~$3.50/hr; expected total for the phase ~$70 against ~$215 of remaining credit.

**The conversion is possible in place** — stop, `set-scheduling`, start — which an earlier
attempt had concluded it was not. The missing piece was
`--clear-instance-termination-action`: GCP rejects SPOT→STANDARD while a termination action
is stored, and will not drop it implicitly. Disks, chain state, validator keys and the
static internal IP all survive; genesis was verified byte-identical by SHA-256 before and
after.

**This belongs in the paper, not just in ops notes.** It is a real operational property of
proof-of-stake sharding: a validator interruption is penalised for hours, where Polygon
Edge's IBFT validators rejoin immediately on restart. It also sharpens the caveat already
recorded for the adversarial arm — see 5e.

### 5d. Validator liveness is now recorded continuously, and runs are auto-invalidated

claude.md §8 requires that any run touched by preemption be invalidated, and
`analysis/export.py` already drops runs carrying a `node_events` row with
`source='preemption'`. **Nothing had ever written one.** On 12 Aug the cluster had lost a
validator, the protocol had expelled it, shard 3 was down to a single producer, and the
database recorded none of it; it was found by hand.

`scripts/near_liveness_watch.py` now samples the chain every 10s and records validator
count, per-shard producer counts, peer count and sync state.
`analysis/apply_validator_liveness.py` invalidates any run overlapping a degraded sample,
and — deliberately — any run whose window is not densely covered by samples, on the grounds
that absence of evidence of degradation is not evidence of health.

This is **stronger than a preemption hook** would have been: it records what the chain
believes, so it catches a validator lost to a crash, a partition, or the protocol's own
kickout rule, none of which a hook on the instance would have seen. The expulsions above
were exactly that case — by the time they mattered, the machines were running fine.

### 5e. Consequence for the adversarial arm — it is not symmetric with Polygon's

Polygon's adversarial arm took validators offline and they rejoined on restart, so each run
was measured against the same 4-validator network. **On NEAR a validator taken offline is
expelled for four hours**, so outages contaminate every subsequent run rather than only the
one they occur in, and the network shrinks progressively through the arm.

The NEAR adversarial arm therefore needs its own design and must run after the full
baseline. This is a second reason NEAR's adversarial result is harsher than Polygon's,
alongside the quota-driven 2-validators-per-shard minimum already recorded. **Both must be
stated when the two architectures are compared.**

### 5f. A third py-near defect

`Account.stake` calls `create_staking_action(public_key, amount)`, but that builder's
signature is `(amount, pk)`. It therefore base58-decodes the stake amount as a key and
fails on `Invalid character '0'`. Staking is done by building the action directly.

Three defects in one library now (`nowait` semantics, this, plus the unclosed-session
warnings). Worth one sentence in Limitations: the NEAR client tooling is materially less
mature than web3.py, and two of the three produced *silent wrong behaviour* rather than an
error.

### 5g. Generator capacity for NEAR — signing is not the constraint

claude.md §8 and §13 step 8 require the generator's own ceiling to be known
*before* collecting, so that an observed plateau can be attributed to the chain
rather than to our tooling. This had not been done for NEAR, and there was a
specific reason to worry.

`_run_near` is deliberately single-process, on the reasoning recorded in
`harness/cli.py` that "a NEAR submission is one RPC call and the work happens on
the validators." **That reasoning predates the Bug 2 fix.** The adapter now signs
every transaction locally — borsh-serialising it twice (once in `calc_trx_hash`,
once in `sign_and_serialize_transaction`), ed25519-signing it, and base58-decoding
a block hash. That is precisely the CPU-bound work that capped the Polygon
harness near 150/sec and forced it onto eight worker processes. `harness.cli
capacity` cannot detect it, because the null adapter it ramps against performs
no signing at all.

Measured directly (`analysis/near_signing_capacity.py`, 12 Aug 2026, on the
`n2-standard-8` generator):

| | |
|---|---|
| Build-and-sign throughput | **7,379 payments/sec** (0.136 ms each) |
| CPU cost at the 300/sec top step | **4.1% of one core** |
| Headroom at 300/sec | **24.6×** |
| Share spent in `calc_trx_hash` | 37% |

**Signing is not the constraint and single-process NEAR is safe for the full
ramp.** The governing number is the scheduler ceiling from `harness.cli
capacity`, run separately at the same 300s window as the real runs.

Recorded because the *absence* of this check was the live risk: had signing come
in near 300/sec, every NEAR result at 200 and 300/sec would have been measuring
our own client, and the Polygon phantom-knee error would have been repeated in
the second architecture. The 37% figure also notes that the transaction is
serialised twice per payment — worth knowing before anyone optimises, though at
24.6× headroom there is nothing to optimise.

---

## Phase 5 preparation — mainnet calibration inputs, 12 August 2026

### 6a. Zilliqa "x-shards" — checked and RULED OUT as a second sharding data point

claude.md §4 and §9 require this be re-checked at Phase 4: *"if shipped, Zilliqa
becomes a cheap second sharding data point"*, which would meaningfully soften
§12's caveat about generalising from one implementation.

**Checked 12 Aug 2026. It is not shipped, and it is no longer on the roadmap.**

- The x-shards roadmap page (`roadmap.zilliqa.com/pillars/x-shards`) now **301
  redirects** to the general roadmap, which covers four phases from Q2 2026 to
  Q2 2027 — credential infrastructure, regulated flows, cross-chain settlement,
  proving the business model — and **does not mention x-shards at all**.
- The developer documentation describes the EVM execution layer and Scilla. It
  documents no x-shard, and the only sharding-related API is
  `GetShardingStructure`, a Zilliqa 1.0 holdover.

**Secondary sources say otherwise and should not be believed.** Several exchange
and "what is ZIL in 2026" articles state x-shards shipped. They are marketing
copy, they cite nothing, and they contradict both of Zilliqa's own properties.
This is worth recording precisely because the easy version of this check —
searching and reading the top results — returns the wrong answer.

**Consequence for the paper.** The sharding arm rests on **one** implementation,
NEAR's Nightshade. §12's existing caveat stands unsoftened, and the reason is now
evidenced rather than assumed: the only affordable alternative does not have
shipped sharding to measure. No Zilliqa budget is required.

### 6b. Mainnet calibration inputs, pulled on one date

`analysis/pull_mainnet_pricing.py` pulls every mainnet figure the cost and
calibration sections need, together, and writes `docs/mainnet_pricing.json`.
ANALYSIS_PLAN §6.3 and §11 both require them dated to a single pull; gathered
piecemeal they drift, and the paper would price two architectures at two
exchange rates without saying so.

Gas prices come from each chain's own RPC rather than an explorer front page:
same number, no API key, and it cannot be a stale cached widget.

**Snapshot, 12 August 2026 01:37 UTC:**

| | |
|---|---|
| NEAR gas price | 100,000,000 yoctoNEAR/gas (the protocol floor — mainnet uncongested) |
| NEAR protocol version | **86 — the same version our testbed runs** |
| NEAR shards | **10** (layout V3) |
| NEAR validators | **422, exactly 10 per shard** |
| Polygon gas price | 273.508 Gwei (block 91,862,423) |
| NEAR / USD | $1.65 |
| POL / USD | $0.075258 |

**A stale-feed trap, worth stating.** CoinGecko's `matic-network` feed still
returns a price ($0.126) but **has not updated since February 2026**, because
MATIC migrated to POL. A script taking it at face value would price Polygon with
a six-month-old rate roughly 68% too high. The published Polygon cost correctly
used **POL at $0.0774**; the puller now records each feed's `last_updated_at` and
flags anything over 24 hours old rather than trusting it.

**Polygon's cost figure is robust to the re-pull.** At today's 273.508 Gwei and
POL $0.075258, 28,538 gas prices at **$0.000587**, against the published
$0.000598 at 270.927 Gwei and $0.0774. Both round to **$0.0006**, so the headline
is unchanged and no published figure needs revising.

### 6c. Correction: NEAR mainnet runs 10 shards, not 8–9

`docs/near_methodology/shard_scaling.md` was written against a planning
assumption of 8–9 shards. Measured directly, mainnet runs **10**. The document
and `README.md` are corrected.

**This makes the cross-shard blend larger, not smaller.** $P(\text{cross-shard})
= (S-1)/S$ rises from 87.5% at $S=8$ to **90.0% at $S=10$**, so our 4-shard
measurement (75%) understates mainnet's cross-shard share by even more than
previously stated. The bias remains **conservative** — we understate mainnet cost
and latency rather than overstating them — which is the safe direction, and the
$c(S)$ scaling method is unaffected in form.

**A second gap, newly measured:** mainnet carries **10 validators per shard**
against our **2**, the protocol minimum. This does not affect throughput scaling
— per-shard capacity is set by block gas limit and timing, not producer count —
but it is a further reason the NEAR adversarial arm is harsher than any mainnet
failure model, and must be stated alongside the quota caveat.

---

## Phase 4 codebase audit — 12 August 2026, second pass

Run against the handoff's own trap list while the sweep was live. Five findings,
two of which would have corrupted results silently.

### 7a. Account balances were too tight to finish the matrix — FIXED

Measured senders held **1.993 NEAR** each. A confirmed NEP-141 transfer costs
**0.00020190 NEAR** (measured, n=2,757), and the full matrix is ~5,978 payments
per sender, so the requirement is **1.207 NEAR** — only **1.6x headroom**. Noise
accounts held **1.000 NEAR** against an upper bound of 2.27.

**Why this mattered more than the numbers suggest.** Exhaustion would not have
failed loudly or early. It would have starved the LAST runs of the matrix — the
$500 high-load cells, which the sweep reaches after twelve hours — and those
runs would have failed for want of gas. Read naively, that is *NEAR collapsing
at scale*: a headline finding, entirely false, and perfectly consistent with a
system that had been working all night.

Both pools topped up (10 NEAR measured, 8 NEAR noise), giving roughly 8x
headroom. The master account holds 949 million NEAR, so the original 2-NEAR
allocation was over-cautious rather than necessary — `near_bootstrap.py`'s note
that a larger figure would need "9,000 NEAR of the master's balance" was true and
irrelevant.

### 7b. Cross-shard mix is correct — and the check that said otherwise was wrong

The first audit query reported a **62.9%** cross-shard share against the 75%
that $(S-1)/S$ predicts at 4 shards, which `PHASE4_HANDOFF.md` §6 names as a
silent, healthy-looking failure. It was the query that was wrong: it aggregated
across *invalidated* runs, including the 11 Aug runs built on the earlier
64-account pool with a different shard distribution.

Restricted to the live sweep: **74.6%**, with every individual run between 72.9%
and 77.8%. Recorded because a check that produces false alarms gets ignored, and
because the fix — filter to valid runs — belongs in the check itself.

### 7c. Disk is not a constraint

87 GB free on the generator; the full matrix projects to ~1.07 GB of SQLite at
the measured 215 bytes per payment.

### 7d. The dataset fits in Git LFS after all — the 1 GB figure was out of date

Initially flagged as a problem: raw grows 539 MB -> ~903 MB and clean 373 MB ->
~700 MB once NEAR lands, ~1.6 GB against what `RESUME_HERE.md` recorded as a
1 GB free tier.

**Checked against GitHub's billing documentation on 12 Aug 2026, and the figure
was stale.** The included allowance is **10 GiB of storage and 10 GiB per month
of bandwidth**, identical on Free and Pro, and billing has moved from pre-paid
data packs to metered usage. GitHub Education grants Pro, which does not change
the LFS allowance because Free already carries the same 10 GiB.

**Storage is therefore not a constraint** — 1.6 GB against 10 GiB, with room for
the prior versions LFS retains.

**Bandwidth might be.** Every clone pulls the LFS objects, so roughly six full
clones a month would exhaust the 10 GiB. Worth knowing before circulating the
repository to reviewers, and an argument for pointing them at the clean file
rather than the raw one.

**The savings identified while investigating remain true and remain optional:**
`tx_ref` is 51% of the raw file (274 MB) and serves on-chain verification rather
than analysis; `latency_s` and `schedule_lag_s` are 18% (97 MB) and are exactly
recomputable from the offsets, so storing them duplicates data already present.
Neither needs acting on now.

### 7e. Traps re-encountered, both already documented

`pgrep -f` over SSH matched the checking command's own arguments and reported
three duplicate sweeps where there was one; `pkill -f` matching the SSH command
line killed the connection mid-cleanup. Both are in the handoff. Both were hit
anyway, which is an argument for tooling rather than for warnings:
`scripts/near_count_procs.sh` now answers the question from a file, printing full
command lines rather than a count to be trusted.

---

## Phase 4 — the NEAR submission-drop rate, 12 August 2026

### 8a. What was measured

At the lowest load step (10/sec, $10), **3–4% of payments are accepted for
broadcast and never appear on the chain at all**. Consistent across runs: 94 of
2,956, 89 of 3,009, 45 of 1,190, 52 of 1,205.

### 8b. What they are, and what they are NOT

The chain's own answer, recorded per payment: **`Transaction <hash> doesn't
exist`**. Queried against three validators on three continents — validator-0
(Virginia), validator-2 (Mumbai), validator-6 (London) — all three return
`UNKNOWN_TRANSACTION`. The transaction is absent from the chain, not merely
absent from the node we happen to poll.

So these are **submission rejections**: broadcast accepted by the node, never
included in a block, **no gas charged, no state changed, retryable by the
sender**. This is the same class as Polygon's `txpool is full` rejections, and
it is emphatically **not** the accepted-but-never-settled case — money leaving
one side and not arriving — which on Polygon appeared **only** under deliberate
node failure. The two must never be merged in reporting.

The slowest payment that *did* settle took 29.6s against a 60s budget, and
nothing settled between 30s and 60s, so these are not slow payments. They are
absent.

### 8c. Causes ruled out, by experiment rather than argument

| Hypothesis | Test | Result |
|---|---|---|
| Competing background traffic | Same configuration run with traffic on and off, minutes apart | **3.78% with, 4.32% without** — not the cause |
| Transaction expiry | `transaction_validity_period` is 100 blocks = 200s; py-near re-signs with a block hash at most 50s old | not the cause |
| Nonce contention on particular senders | Distribution of losses across the 836 senders | spread evenly, max 3 on any one sender | 
| Single-node view (RPC tracking only some shards) | Same hashes queried on three validators in three regions | all three agree the transaction never existed |
| Slow settlement hitting the 60s budget | Latency distribution of settled payments | p99 16.1s, max 29.6s — nothing between 30s and 60s |

### 8d. What remains open, and how the sweep itself will narrow it

The mechanism is not isolated. `broadcast_tx_async` returns a hash without
validating, so a transaction rejected after that point disappears silently — and
that is the only route by which a node can accept a broadcast and the chain
never see it.

**The load ramp will discriminate.** If the rate stays near 3–4% from 10/sec
through 300/sec, it is a per-transaction submission property independent of
load, most likely in the client path. If it climbs with offered load, it is
capacity — a real finding about NEAR under pressure. That data is being
collected regardless, so no extra runs are needed to answer it.

**Until it is resolved, the honest reporting is:** a measured submission-rejection
rate under our stated conditions, of the retryable kind, with the cause not
established. It must not be presented as NEAR losing payments.

---

## Phase 4 — the TIER1 misconfiguration, 12 August 2026

### 9a. What happened

At 08:37 UTC the sweep began degrading, and from 08:56 **eleven consecutive runs
recorded ZERO settled payments** out of 30,000 to 60,000 each — 100/sec through
200/sec. The runs were being written down as valid.

Both `asia-south1` validators had fallen ~460 blocks behind the chain and were
stuck in slow sync. NEAR finality requires chunks from **every** shard, so two
shards without a producing validator stalled settlement network-wide, not just
for payments addressed to those shards.

### 9b. Root cause

**Every validator advertised `[::1]` — IPv6 localhost — as its `public_addrs`.**

```
network.public_addrs = ["ed25519:...@[::1]:37223"]
```

TIER1 is NEAR's direct validator-to-validator layer, used to propagate blocks
and chunks among validators without traversing general gossip. Each validator
was telling the others to reach it at *their own* localhost, so **no TIER1
connection could ever be established** and all validator traffic fell back to
the slower TIER2 path.

This was survivable to 50/sec and fatal above it.

`PHASE4_HANDOFF.md` §6 already lists **"P2P must not bind `[::1]` — this broke
the chain twice."** It is now three times. The fix is written into each node's
`config.json` (`scripts/near_fix_tier1_addrs.sh`) rather than applied by hand, so
a restart cannot undo it.

### 9c. Evidence that this was the cause, not a symptom

| | Before the fix | After the fix |
|---|---|---|
| asia-south1 validators | ~460 blocks behind, stuck for **hours**, not recovering | **at the tip within one minute** |
| Recovery with impairment removed | still stuck — impairment was **not** the cause | — |
| Recovery after a plain restart | node2 partially, node3 not at all | — |
| A 100/sec run | **0 settled of 30,000** | **11,970 settled, 99.8/sec achieved, 0.4% failed** |
| TIER1 connection failures in the log | continuous | **0 in three minutes** |

### 9d. Consequence for the data — all prior phase-4 runs invalidated

**23 runs, including the 15 low-load configurations that had looked clean.**
Everything collected on this cluster ran without the validator network NEAR is
designed to use. Those numbers describe a misconfigured deployment, not NEAR,
and reporting them would understate it for a reason that has nothing to do with
sharding.

This also very likely explains the **3–4% submission-drop rate** investigated in
§8, which was measured entirely under the broken configuration. At 100/sec after
the fix the failure rate is **0.4%**. §8's conclusion about what those failures
*were* (submission rejections, nothing charged, retryable) still stands; the
*rate* should be re-measured and the earlier figures not quoted.

### 9e. The monitoring gap this exposed, now closed

The liveness watch checked validator count, per-shard coverage, and peer count.
All three read **healthy** throughout, because a validator stuck syncing stays in
the set, keeps its peers, and is counted. It produced nothing.

`scripts/near_liveness_watch.py` now also polls **every validator's own view of
the chain tip** and marks the sample degraded if any is more than 30 blocks
behind (≈60s) or reports itself syncing. Confirmed against the live failure: it
immediately reported `max_behind=477, behind={node2: 477, node3: 444}`.

### 9f. A limitation this surfaced, which must be stated in the paper

`tracked_shards_config: AllShards` — **every validator tracks and executes all
four shards.** For a cluster this small that is the safe configuration, because
chunk-producer assignment rotates each epoch and a node reassigned to a shard it
does not track cannot produce for it.

But it means our deployment does **not** realise sharding's execution-division
benefit: each node does all four shards' work, so total capacity is bounded by
one node rather than the sum over shards. **Our NEAR throughput figures are
therefore conservative relative to a production deployment where validators track
only their assigned shards.** The cross-shard *latency and gas* measurements are
unaffected — those are properties of receipt routing, which happens regardless.

---

## Phase 5 — calibration against mainnet, 12 August 2026

`analysis/calibration.py` computes the two figures ANALYSIS_PLAN §11 requires,
from the dataset and from each chain's own RPC rather than a scraped explorer
page.

### 10a. Mainnet observed throughput, measured rather than cited

| Chain | Observed | Block utilisation | Source |
|---|---|---|---|
| Polygon | **79.6 tx/sec** | **28.5%** | `polygon-bor-rpc.publicnode.com`, 25 contiguous blocks, head 91,888,830, 12 Aug 2026 12:37 UTC |
| NEAR | **~4.8 tx/sec** | ~0.04% | `rpc.mainnet.near.org`, 8 contiguous blocks across 10 shards, 12 Aug 2026 01:35 UTC — small sample, indicative only |

The project notes quoted Polygon at "~87 tx/sec (7.5M/day)" from a secondary
source. Measured from the chain it is 79.6, which corroborates it.

### 10b. Polygon result

- **Demand ratio = 2.52×.** We sustain 2.5× what Polygon mainnet currently
  carries. A statement about **workload realism**: the loads tested are of the
  same order as real activity, slightly above it.
- **Capability gap = 0.719×.**

### 10c. A finding that contradicts an assumption in the project scope

claude.md §5 technique #7 anticipates reporting *"our private network measured X;
real mainnet activity suggests Y; results should be treated as an **upper bound**
roughly Z% above expected real-world performance."*

**For Polygon that is the wrong direction.** Our 4-validator testbed sustains
**71.9%** of Polygon mainnet's estimated capacity — it is *less* capable, not
more. The results are therefore **conservative** on this axis rather than an
upper bound, and the scope's framing should be corrected rather than repeated.

The reason is the one §11 already gives: mainnet's *observed* 79.6 tx/sec is
demand, not capacity. Its blocks run **28.5% full**, so the same traffic mix at
full blocks implies roughly **279 tx/sec** of capacity — comfortably above the
200/sec our cluster sustains.

**The assumption this rests on, stated plainly:** implied capacity =
observed ÷ utilisation presumes the marginal transaction costs what the average
one costs. Reasonable on a chain of mostly simple transfers, and it would
overstate capacity on one dominated by heavy contract calls. §11 asks instead for
the highest sustained throughput in explorer history, which cannot be pulled from
an RPC; `--mainnet-peak` accepts that figure if it is looked up by hand, and both
the derived number and its inputs are printed so a reader can substitute it.

**NEAR's figures follow once its matrix completes.** Its demand ratio will be
very large — mainnet NEAR carries ~5 tx/sec — and that number says nothing about
NEAR's capability, only that the network is lightly used today. It must be
labelled as such wherever it appears.

---

## Phase 4 — sweep order changed to protect the headline size, 12 August 2026

**Change.** The sweep now measures amounts in the order **$200, $10, $50, $500**
rather than $10, $50, $200, $500.

**Why.** $200 is the World Bank's standard remittance size (claude.md §6) and the
headline figure of every comparison the paper makes. In the original order it was
measured *third*, landing seven to ten hours into a 13.5-hour sweep. Anything
cutting the sweep short — a validator expulsion, a budget ceiling, a stall — would
have left the two least important sizes complete and **no $200 data at all.**

Phase 4 has already lost four hours to one expulsion cycle, so this is not a
hypothetical.

**Why it does not affect a result.** Each cell is five repeats under identical
conditions, and the runs are independent of one another. Amount is additionally
already known not to change gas or latency on an account-model chain — Polygon's
own finding, where gas varied by 12 units across all four amounts (0.044%).

**The one honest caveat.** Polygon's sweep ran $10 → $500 in ascending order, so
NEAR's cells now sit at slightly different points in the chain's accumulated
history than Polygon's did. That is a second-order effect on a chain a few hours
old with negligible state, and it is stated here rather than left for a reader
to notice.

**Measured pace, for the record:** 336s mean run duration plus a 23s gap = **6.0
minutes per configuration**, so 140 configurations is **14 hours** of clean
running.

---

## Phase 6 — the rebuilt NEAR cluster and what rebuilding it exposed, 21–22 August 2026

**Why this is written before there are any numbers.** `ANALYSIS_PLAN.md`
amendment 15 pre-registers a single experiment: run NEAR again at 100 and 200
payments per second and change exactly one thing — whether the question *"has
this payment finished yet?"* is put to one machine or to four. Doing that meant
rebuilding the NEAR cluster from nothing, and the rebuild turned up four things
that belong in the permanent record whatever the experiment eventually shows.
One of them is a fault that would have produced a believable wrong answer rather
than an obvious failure. **Nothing below reports a result** — the runs were
still going when this was written.

Throughout, "the machine that sends the test payments" is the ninth machine, the
one running our own measuring program; the other eight are the computers running
the blockchain.

### 11a. The cluster was rebuilt at the published specification, not a cheaper one

Nine machines in Google Cloud project **`project-c4c87dcb-da41-4caf-922`** —
**the same project the published NEAR campaign ran in**. Eight run the
blockchain, one sends the test payments. Four shards with two blockchain
machines each: the protocol minimum, and the same shape as the published
campaign (§ "NEAR cluster size is quota-constrained", 10 Aug).

| | Published NEAR campaign | Rebuild, 21 Aug |
|---|---|---|
| Cloud project | `project-c4c87dcb-da41-4caf-922` | identical |
| Machines running the chain | 8 × `n2-standard-8` (8 processors, 32 GB memory) | identical |
| Machine sending the payments | 1 × `n2-standard-8` | 1 × `n2-standard-16` |
| Shards / chain machines per shard | 4 / 2 | identical |
| Regions | us-east4, asia-south1, asia-southeast1, europe-west2 | identical |
| Block cadence | 2s | identical |

One row differs, and it is the measuring instrument rather than the thing being
measured (amendment 15 states the same). Everything that could plausibly move a
throughput figure — project, regions, machine size, shard layout, block cadence
— is unchanged.

Processor count: 8 × 8 + 16 = **80 of the 96 this project is allowed**. Machines
are ordinary on-demand ones rather than the cheaper interruptible kind, because
this account's interruptible allowance is zero in every region — which also
matches how the published runs were measured, for the reasons in §5c.

**How it nearly ran at half size, and why it is back where it started.** The
original account's free credit ran out on **14 Aug**, the day after Phase 4
collection finished, so the work moved to a new account and a newer cloud
project. That newer project's request for more processors **sat unanswered for
four days**, after which a human reviewer confirmed it would not be approved
automatically. An interim plan was written to run the whole experiment on
**half-size machines** (`n2-standard-4`) under a 64-processor ceiling.

That plan was abandoned, because there was a better option. The **original**
project already held a 96-processor allowance and still holds the nine disk
images from the published campaign, so the work went back to it and the project
was attached to the **new account's billing**, which carries the remaining
credit. Money now comes from the newer account; the machines run exactly where
they always ran. Recorded in `terraform/phase4/terraform.tfvars`, with the
reasoning kept beside the values.

**Why the size mattered more than it looks.** Half-size machines could only ever
have produced an *internal* comparison — one setting against another on weaker
hardware — and its absolute numbers could never have stood beside the published
150 payments/sec. At full specification the hardware is identical to the
published runs, so **if the measured ceiling moves, the new figure replaces the
published one instead of sitting next to it with a caveat.** That is the whole
point of matching, and it is why amendment 15 is allowed to claim a standing
that amendment 14's Polygon supplementary runs (one repeat, half-size machines)
explicitly could not.

**A risk it also retires.** The half-spec plan carried a stated danger: consensus
across four continents had *already* failed at nearcore's own 600ms default block
interval on 8-processor machines (amendment 12), and there was a real chance it
would not hold at all on 4. Running at full specification removes that question
rather than gambling on it.

### 11b. The node software was built from source, because there is nothing to download

The chain runs **nearcore 2.13.3**, compiled on the payment-sending machine and
copied to the eight blockchain machines.

| | |
|---|---|
| Version | 2.13.3 |
| Commit | `5af9ca74631e6cf0dae33e77d1a632e94d2952ce` |
| Commit date | 4 August 2026 |
| Protocol version spoken | 86 |
| Oldest protocol version accepted | 83 |
| Compiler that built it | rustc 1.93.0 |
| On-disk database format | 49 |

**These are read off the running chain, not copied from the build script.** On
22 Aug `neard --version` on `near-validator-0` reported: `(release 2.13.3)
(build 2.13.3) (commit 5af9ca74631e6cf0dae33e77d1a632e94d2952ce) (rustc 1.93.0)
(min_protocol 83) (protocol 86) (db 49)`. What the deploy script *intended* to
install and what is actually running are different claims, and only the second
one is evidence.

**Why not download a ready-made copy.** There is not one. NEAR's release entry
for 2.13.3 carries no downloadable files, and the storage locations that served
older versions answer "forbidden". Compiling it is the only way to obtain exactly
this version, and exactness is the point: `claude.md` §3 requires live,
maintained production node software pinned to a fixed commit, which aids
reproducibility rather than harming it.

**Why not fall back to an older version that does have a binary.** The cluster
was originally pinned to 2.3.1, which speaks protocol version 72. The token
contract has to be built with a toolkit that speaks the same protocol as the
node; if it does not, the contract **deploys successfully and then every single
call fails with a parsing error** — a failure that looks like a broken contract
and says nothing about versions. Node and contract toolkit have to move together,
and the toolkit is the harder of the two to pin backwards. `scripts/build_nearcore.sh`
does the build; it takes 45–90 minutes and is run with the eight blockchain
machines stopped, so only one machine bills during it.

### 11c. The token contract is now pinned — and cannot be proven identical to the published one

Every NEAR test payment moves a **NEP-141 fungible token** — NEAR's equivalent of
the ERC-20 stablecoin standard used on Polygon, chosen for the reason in §3.6.

**What was found on 21 Aug.** `scripts/near_bootstrap.py` has always instructed
the operator to *"run `scripts/build_ft.sh` first"*, and **that script was never
in this repository.** It existed only on the old payment-sending machine's disk,
which went when that cluster was destroyed. The rebuild stopped dead at the token
step.

**The more serious half of the problem.** The contract's version was never
written down anywhere — not in this log, not in `NEAR_ANALYSIS.md`, not in the
deploy scripts. Gas consumed per transfer is a **published figure**
(2.214 × 10¹², `NEAR_ANALYSIS.md` §4, and the $0.000365 cost per payment is
derived from it), and gas is a property of the contract that actually ran. A
published number therefore rested on a dependency nobody had recorded.

**What is pinned now**, in `scripts/build_ft.sh`, which is in the repository from
this date:

| | |
|---|---|
| Source | `near-sdk-rs`, tag `near-sdk-v5.29.0` |
| What is built | `examples/fungible-token` — the reference NEP-141 implementation, the one real NEAR stablecoins derive from, so nobody has to take our word for what the contract does |
| Compiler flags | `RUSTFLAGS="-C target-cpu=mvp -C link-arg=-s"` |
| Output | 150,621 bytes of WebAssembly — checked on the machine itself on 22 Aug, not taken from the build log |

`target-cpu=mvp` holds the compiler to WebAssembly's original feature set.
Without it a current compiler emits newer features and the contract deploys and
then fails on every call with the same confusing parsing error described in
§11b. The pinned toolkit release is from within three weeks of the node commit,
so the two belong to the same era of the protocol rather than being matched by
guesswork.

**⚠️ The caveat, stated plainly rather than buried.** Because the original
contract's version was never recorded, **we cannot prove this rebuild is
byte-identical to the contract behind the published NEAR runs.** The two
consequences are different from each other and both need saying:

- **Inside the endpoint experiment it does not matter.** Both arms move the same
  contract on the same chain, so whatever the contract is, it cancels out of the
  comparison. Amendment 15 says the same.
- **Across the two campaigns it does matter.** Any absolute gas or cost figure
  from the rebuilt cluster carries this uncertainty when set against the
  published 2.214 × 10¹² and $0.000365, and **must not be compared with them as
  though both had been measured on the same contract.**

Nothing held in this repository can settle it after the fact, so the uncertainty
stands and should be repeated wherever those two published figures are quoted
alongside anything measured on the rebuilt cluster.

### 11d. A wrong project name in the impairment script — a near-miss worth recording

`scripts/inject_impairment_near.sh` is the script that adds extra delay, jitter
and packet loss to the connections between the blockchain machines, so that a
private cloud network behaves more like the public internet (realism technique
#2, §4). On 21 Aug it was found with the Google project name **hardcoded to
`remittances-benchmarking`** — a project the NEAR cluster has never run in.

**First, the reassuring half, because a reader who sees this reported will
otherwise reasonably wonder about it: the published NEAR figures WERE measured
with the impairment applied.** The stale name was introduced on **18 Aug**, five
days after Phase 4 collection finished on 13 Aug. Throughout the published
campaign this script named `project-c4c87dcb-da41-4caf-922`, which is where the
cluster was and still is (§11a), so the delay and loss reached the machines they
were meant to reach. That was checked rather than assumed, because if it had
gone the other way every published NEAR number would have been measured on a
clean network while Polygon's was measured on a dirty one, and the headline
comparison of the paper would have been invalid.

**Why the wrong name was there at all.** When the original account's credit ran
out on 14 Aug, several scripts were repointed on 18 Aug to the new account's
project in preparation for Phase 6 work there. **That work never happened** — the
processor request on the new project was refused (§11a) — so the cluster went
back to the original project and the 18 Aug edit was left pointing somewhere
nothing runs.

**What would have happened had it not been caught.** The commands that add delay
and loss are sent to named machines inside a named project. With the wrong
project name they reach nothing, and the run proceeds normally with no error that
anyone reading the results would ever see. The **rebuilt** cluster's runs would
then have been measured on a clean network, and any comparison drawn from them
would have been decided partly by network conditions rather than by the designs
under test.

This is not hypothetical. Exactly that state was found once before, on 12 Aug:
the impairment tool reported nothing configured on the NEAR machines while every
Polygon run had recorded impairment in its configuration. That discovery is why
the script exists at all.

**The fix.** The script now reads the project name out of
`terraform/phase4/terraform.tfvars`, the same place every other script reads it
from, so there is one value in one file rather than several copies drifting
apart.

**Why it is in this log rather than an operations note.** It belongs to the class
of fault this study keeps meeting: not a crash, but a **plausible-looking wrong
number**. The same class as the Lightning rebalancer that quietly did nothing
(Phase 3, fault 2), the `py-near` call that blocked when told not to (§4d), and
the settlement checks that all went to one machine (amendment 14). A benchmark
that fails loudly costs an afternoon; one that fails quietly costs a chapter.

**Two other NEAR scripts carried the same stale value, and both are now fixed the
same way.** `scripts/near_cluster_control.sh` — the operator helper that
`docs/near_methodology/finishing_runbook.md` points at for `status`, `renew` and
`stop` — and `scripts/near_adversarial_nodes.sh`, which drives the node-failure
arm. The control script is the dangerous one, and it is worth stating exactly
why: **a `stop` issued against a project the machines are not in reports success
and leaves nine machines billing.** That is the same shape of fault as the
impairment bug — a command that appears to work and does nothing — with money as
the consequence instead of a wrong number.

Six older Polygon- and Lightning-era scripts still name the newer project. They
drive clusters that no longer exist, so nothing turns on them today, but they
should not be read as a record of where anything actually ran.

### 11e. Two operational lessons from a laptop restart, 04:20 UTC on 22 August

The operator's laptop restarted at about **04:20 UTC on 22 Aug**, part-way through
the first attempt at the experiment. It cost hours, and it exposed two things
that had been true for some time without being noticed. Both changed how the
experiment is run, which is why they are recorded here.

**(a) The eight most expensive machines were set to shut down a day after the
ninth.** Every machine halts itself at a set time held on the machine itself, so
that a forgotten cluster cannot bill for days. The eight blockchain machines were
found carrying a deadline **34 hours** away — the default armed automatically at
every boot by the deployment's own guard script (`max_lifetime_minutes = 2040`
in `terraform/phase4/variables.tf`), a figure originally sized to cover the
14-hour matrix sweep. The payment-sending machine's deadline was about **7
hours** away, set for this much shorter job.

The consequence of that gap: when the experiment finished, the machine doing the
measuring would stop on schedule and **the eight machines it had been measuring
would keep billing for another day.** Those eight are most of the cluster's
roughly $4.50 an hour, so the overhang is on the order of $90 for machines doing
nothing at all.

All nine were realigned to a single deadline, and the run script now sets one
absolute stop time on all nine before it does anything else. The rule this gives
is **one deadline, in one place, checked on the machines that are not in front of
you.** The deadline stays armed inside each machine's own operating system rather
than in the supervising script, precisely because it has to survive the
supervisor dying — which is what happened at 04:20.

**(b) The laptop could end a three-hour job, and did.** In the first attempt each
run was driven over a remote connection from the laptop, which made the laptop a
single point of failure for a multi-hour unattended job. The restart ended it,
and also destroyed the log, because the log had been written to `/tmp` and macOS
clears `/tmp` on restart.

The run now happens on the payment-sending machine: the script is copied there
and started detached from any connection, and **the laptop only watches**, so
closing it costs nothing. The log is written to the home directory instead of
`/tmp`. The supervising script also stops all nine machines on its way out
however it exits — normal finish, error, or interruption — because the way this
project wastes real money is not a long experiment but a short one that died
unattended at 3am.

The general lesson, which applies to every remaining phase: **the machine
watching an experiment must not be able to end it, and the thing that stops the
cluster must not depend on the thing that started it.**
