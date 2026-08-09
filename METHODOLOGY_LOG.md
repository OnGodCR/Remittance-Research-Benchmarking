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

**Measured: 28,467 gas per stablecoin transfer** (mean over the results dataset; median 27,465).

The distribution is tiered by EVM storage-access cost: 27,465 gas where both balance slots are warm (55.3% of transfers), 31,665 with one cold access (9.8%), 35,865 fully cold (3.6%).

**Converted to dollars: $0.0006 per remittance.** Using PolygonScan's Standard gas price of 270.927 Gwei and POL at $0.0774, both pulled 9 August 2026 — see `data/reference/calibration_2026-08-09.md`, the single pricing reference for the whole paper. Clears the pre-registered $0.10 threshold by roughly 168×, and consumes 0.01% of the UN SDG 10.c budget of $6.00 on a $200 transfer.

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
| **200** | **200.8** | **0.00%** | 3.43s | 4.76s | 6.48s |
| 300 | 270.5 | 9.97% | 10.61s | 24.26s | 30.49s |

**Sustainable throughput at $200 = 200/sec**, per the pre-registered primary metric (§2 of the analysis plan: achieved ≥90% of offered AND failures <5%). At 300/sec both conditions fail — 90.2% of offered load delivered and 9.97% failures — so 200 is the highest step clearing the bar.

**The knee is between 200 and 300/sec.** Settlement is essentially flat from 10 to 200 (3.19s → 3.43s at the median), then rises threefold at 300 while failures appear for the first time. That is a system passing from comfortable to overloaded within one step of the ramp.

**Against the architecture-selection thresholds (§10):** at 200/sec Polygon clears both — p95 of 4.76s against a 10s ceiling, and cost well under $0.10. At 300/sec it fails the latency ceiling (p95 24.26s) as well as the failure bar.

**Transaction size does not drive failure**, as predicted in §12. At 300/sec: $10 10.86%, $50 10.83%, $200 9.97%, $500 12.85% — no monotonic relationship with amount, consistent with the prediction that these networks charge for computational work rather than value moved. Contrast this with the inverse size/success relationship expected for Lightning.

**Note on the earlier exploratory figure.** A pilot at 60-second windows suggested Polygon sustained 300/sec with zero failures. The full protocol — 300-second windows and realistic background traffic — shows that does not hold under sustained load. Short windows measured the burst, not the steady state.

---

## 9.2 Adversarial arm — completed result

Same realism stack as the clean baseline, plus validators dropping offline throughout. 3 load levels × $200 × 5 repeats = 15 runs, 300-second windows. 123 outage events recorded and joined to the payment data.

| Offered/sec | Clean | With node failures | Throughput lost |
|---|---|---|---|
| 100 | 100.1/s, 0.00% fail | 99.4/s [99–100], 0.8% fail | **0.8%** |
| 200 | 200.8/s, 0.00% fail | 148.4/s [122–173], 26.1% fail | **26.1%** |
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
