# Resume Here — complete state, updated 13 August 2026

> ## PHASE 4 COLLECTION IS COMPLETE
>
> **All three architectures now have data.** The NEAR matrix settled at **140/140
> cells: 118 measured, 22 unmeasurable**, every measured cell having passed the
> validator-liveness audit. The adversarial arm ran at 100/150/200, plus an
> exploratory low-duty-cycle block.
>
> **NEAR sustains 150 payments/second** at $200 under the full realism stack
> (achieved 150.1/sec, 0.15% failures).
>
> ### ⚠️ WITHDRAWN 19 Aug 2026 — read `POLYGON_RPC_BOTTLENECK.md` before using
> ### anything in this section about Polygon's ceiling or its failure mode.
>
> Polygon's ~270/sec was measured with every settlement check sent to ONE node.
> That node ran at 84% busy while the other three validators sat at 8–14%.
> Spreading the checks across four nodes, on HALF the validator hardware, gave
> **290.5/sec** — better than the published figure. And past 300, which the
> published ramp never went: 290.5 → 202.5 → 108.3 → 96.5. **Polygon collapses
> too.** The "graceful degradation" contrast below came from a ramp that
> stopped at Polygon's knee rather than going past it. NEAR's collapse is still
> steeper, so a difference in degree survives; "graceful vs catastrophic" does
> not. See ANALYSIS_PLAN.md amendment 14.
>
> **The finding worth building a paragraph around is the failure MODE, not the
> ceiling.** Polygon degrades gracefully past its knee — 270.5/sec achieved when
> offered 300, 9.97% failures. NEAR *collapses*: the failure curve across its last
> three steps is 0.15% → 76.3% → 96.7% (the 300/sec step reported from raw as
> sensitivity data; see §7c). For a payment system facing payday and holiday clustering — the
> exact peak scenario this study cites — that difference matters as much as the
> headline number.
>
> **Phase 5 is done; Phase 6 (comparison + limitations) is in progress**, with
> supplementary tests queued on a NEW GCP account. See §2 and §7c.
>
> `PHASE4_HANDOFF.md` is **superseded** — kept for its bug write-ups, not for
> current state. §2 below describes 9 August and is long out of date.

**Read this, then `METHODOLOGY_LOG.md` (every decision and parameter) and `ANALYSIS_PLAN.md` (the locked analysis rules). Between them you should not need conversation history.**

---

## 1. Where the project is

| Phase | State |
|---|---|
| 1 — Pipeline validation | ✅ Complete |
| 2 — Realism techniques on Polygon | ✅ **Complete — 140/140 configurations** |
| 2b — Adversarial arm (Polygon) | ✅ **Complete — 15/15 runs** |
| 3 — Lightning | ✅ **Closed 10 Aug** — data source switched to Waugh & Holz (2020); cost + illustrative settlement time retained |
| 4 — NEAR sharding | ✅ **Complete 13 Aug — 140/140 cells (118 measured, 22 unmeasurable)** + adversarial arm + exploratory low-duty block |
| 5 — Calibration + confidence intervals | ⏳ **Next** — merge, clean, intervals, calibration ratios, shard scaling |
| 6 — Cross-architecture comparison | ❌ Not started |

**Dataset: Polygon 5,717,593 payments across 155 runs** (140 matrix + 15 adversarial), committed via Git LFS. **NEAR adds 118 measured cells plus the adversarial arm** — merged into the canonical files in Phase 5. Lightning remains in the raw file only; its reliability and throughput come from published measurement, not from us (`LIGHTNING_ANALYSIS.md`).

### Realism techniques

| # | Technique | Built | Run against a real cluster |
|---|---|---|---|
| 1 | Multi-region | ✅ | ✅ |
| 2 | Injected latency, jitter, packet loss | ✅ | ✅ |
| 3 | Competing background traffic | ✅ | ✅ |
| 4 | Hardware matched to real validators | ✅ | ✅ (`n2-standard-8`) |
| 5 | Lightning liquidity topology | — | Phase 3 only |
| 6 | Adversarial nodes | ✅ | ✅ full arm, 15/15 |
| 7 | Calibration against mainnet | ✅ | Polygon ratios computed (demand 2.52x, capability 0.719x); NEAR ratios pending in Phase 5 |
| 8 | Five repeats | ✅ | ✅ |

---

## 2. What is running  *(updated 13 Aug)*

**Nothing should be running.** The 9-instance NEAR cluster
(`near-validator-0..7` + `near-generator`, `n2-standard-8`, across us-east4-c /
asia-south1-a / asia-southeast1-a / europe-west2-b) was stopped at the end of
Phase 4 collection.

**Verify before assuming**, because a forgotten cluster is the single most
expensive mistake available here:

```bash
# WHERE THE MACHINES ARE (Phase 6 supplementary tests, and every NEAR run
# ever published) -- 96-processor allowance, billed to the newer account
gcloud compute instances list --project project-c4c87dcb-da41-4caf-922
# Phase 2 Polygon machines live here, stopped. Its processor request was
# refused, so NOTHING new runs here.
gcloud compute instances list --project remittances-benchmarking
```

> **⚠️ REVERSED 22 Aug 2026.** These two lines used to be the other way round,
> labelling `remittances-benchmarking` as "current" and the other as "old --
> credits exhausted". That is no longer true and it is an expensive thing to
> believe: a `stop` aimed at the empty project reports success while nine
> machines keep billing. **Money and machines are now in different places.**
> The credit sits on the newer *account*, and that account pays for a
> *project* belonging to the older one. See §"account move" below.

**ACCOUNT MOVE, 14 Aug — then PARTLY REVERSED, 21 Aug.** The original account's
$300 credit ran out on 14 Aug, the day after Phase 4 collection closed. Work
moved to a new account and its project **`remittances-benchmarking`** (org
`remitbridgesystemlabs-org`, "RemitBridge System Labs"), fresh $300 expiring
17 Nov 2026 — **a FULL account: after credits it charges a real card**, so
budget alerts are mandatory before any deployment. (Three now exist, at $50 /
$100 / $200, each also warning on forecast.)

That move did not survive contact with quota. `remittances-benchmarking` was
granted only 32 processors; a request for more went unanswered for four days
and a human reviewer then confirmed it would not be auto-approved. NEAR needs
80. So on 21 Aug the **older project `project-c4c87dcb-da41-4caf-922`, which
already held a 96-processor allowance, was attached to the NEW account's
billing.** Compute runs in the old project; the new account pays for it.

**This is the arrangement to keep straight**, because it is the reverse of the
14 Aug one and every stale note in this repo describes the old shape:

| | Where |
|---|---|
| Credit ($274 left, 21 Aug) | new account, billing `01DAB3-71DAC1-49A233` |
| Machines, 96-processor allowance | **old project** `project-c4c87dcb-da41-4caf-922` |
| Every published NEAR run | **old project** — same one. Hardware match is exact |
| Phase 2 Polygon machines | `remittances-benchmarking`, stopped |

The 9 disk snapshots (incl. the validator health log, which exists nowhere
else) live in the old project and remain readable. Terminal access
to the new project requires `angadkochar2@gmail.com` to be granted Editor.

**Polygon is finished** (140/140 + 15/15). **Lightning is closed**
(`LIGHTNING_ANALYSIS.md`). **NEAR is finished** (§7c).

---

## 3. The headline result (Phase 2, complete)

Polygon Edge, 4 validators across 4 continents, production-spec hardware, injected impairment, background traffic at real mainnet intensity (~88/sec). 300-second windows, 5 repeats, first 10 seconds discarded.

| Offered/sec | Achieved | Failures | p50 | p95 | p99 |
|---|---|---|---|---|---|
| 10 | 9.9 | 0.00% | 3.19s | 4.16s | 4.40s |
| 25 | 25.0 | 0.00% | 3.19s | 4.17s | 4.39s |
| 50 | 50.0 | 0.00% | 3.20s | 4.22s | 4.46s |
| 100 | 100.1 | 0.00% | 3.23s | 4.25s | 4.52s |
| 150 | 150.3 | 0.00% | 3.31s | 4.38s | 4.70s |
| **200** | **200.9** | **0.00%** | 3.43s | 4.77s | 6.35s |
| 300 | 270.5 | 9.97% | 10.61s | 24.26s | 30.49s |

**Sustainable throughput at $200 = 200/sec** (pre-registered metric: achieved ≥90% of offered AND failures <5%).

**The knee is between 200 and 300/sec.** Flat from 10 through 200, then settlement triples and failures appear for the first time.

**Size does not affect failure**, as pre-registered in §12. At 300/sec: $10 9.79%, $50 8.51%, $200 9.97%, $500 12.85% — no monotonic relationship. Within a storage tier, gas varies by 12 across all four amounts (0.044%). This flat result is the contrast that will make Lightning's expected *inverse* size/success relationship meaningful.

### Adversarial arm (node failures), same conditions plus validators dropping offline

| Offered/sec | Clean | With node failures | Lost |
|---|---|---|---|
| 100 | 100.1/s, 0.00% fail | 99.4/s [99–100], 0.8% fail | **0.8%** |
| 200 | 200.9/s, 0.00% fail | 148.4/s [122–173], 26.1% fail | **26.1%** |
| 300 | 270.5/s, 9.97% fail | 156.2/s [93–203], 48.0% fail | **42.2%** |

Damage scales with existing load: negligible with headroom, severe without. Note the 93–203 spread at 300/sec — outage timing is random, and a single run could have reported either extreme.

⚠️ **The injection is ~130× more hostile than real Polygon** (1 of 4 validators = 25% of the network vs ~1% on mainnet; offline 51% of the time vs a 99.9% uptime target). This measures *sensitivity to validator loss*, not mainnet behaviour. See `METHODOLOGY_LOG.md` §4 technique #6.

**Context:** global remittances average ~140-150/sec. Polygon clears steady-state global demand comfortably, but breaks in the middle of the 200-300/sec peak range the scope defines.

**⚠️ CONDITIONAL ON THE SINGLE-ENDPOINT SETUP (19 Aug 2026).** With settlement checks spread across four nodes, the same cluster at 300/sec produced ZERO rejections and 2,758 accepted-then-unsettled payments — the opposite failure mode. Relieving the bottleneck admits more payments and converts refusals into stuck payments. Report either mode only alongside the configuration that produced it. See `POLYGON_RPC_BOTTLENECK.md` §5b.

**Failures come in two kinds, and only one appears in the clean data.** Across all 140 clean runs every failure was a *submission rejection* (`txpool is full`) — no transaction hash, no gas, never entered the chain, retryable by the sender. Zero accepted payments failed to settle. The 9.97% at 300/sec is an overflow rate at Polygon Edge's *default* queue size, which we did not tune: the ~270/sec committed ceiling is architectural, the exact percentage is queue-dependent.

**The adversarial arm is where it gets serious:** 7,944 payments (0.91%) were accepted, given a transaction hash, and never settled — at 200 and 300/sec only. That is the "money left one side and never arrived" case, and it exists *only* under node failure. Never merge the two arms' failure rates.

**Superseded finding:** an exploratory pilot suggested Polygon sustained 300/sec with zero failures. It came from 60-second windows on a quieter chain. Under the full protocol it does not hold — short windows measured the burst, not the steady state.

---

## 4. The saturation criterion — read before touching exclusions

The rule changed twice; **only the current one is in force anywhere**:

1. 8 Aug: absolute lag threshold tightened 250ms → 40ms (p95). *Superseded, produced no reported result.*
2. **9 Aug (current): lag GROWTH.** A run is excluded when median scheduling lag rises by more than **50ms** between the first and last quarter.

Growth, not magnitude, because a constant offset distorts nothing — offered load still matches intended load — whereas climbing lag means the delivered arrival pattern drifted from the scheduled Poisson process.

**Validated** against 7 independently-known-broken runs; detects all 7, including a subtle 9.7ms→294.9ms case. Every run it flags sits inside a non-result phase — it excluded **nothing** from the 155 results runs. **Applied uniformly to all 211 runs** via `analysis/reevaluate_saturation.py`.

**Stated limitation:** re-judging moved runs from excluded to included and none the other way. That asymmetry is the signature of a criterion devised after seeing data. Recorded in `ANALYSIS_PLAN.md` §13 and `METHODOLOGY_LOG.md` §7.2 rather than hidden.

---

## 5. Operational traps — read before touching infrastructure

Every one cost real time or money.

0. **The sweep's resume restarts from the beginning of the load ladder, not the point of interruption.** After two preemptions this silently produced 22 duplicate runs with *identical arrival seeds*, filling four matrix cells with 10 runs instead of 5. Caught 9 Aug by auditing repeat counts, not by any error. `analysis/export.py` now excludes re-executions automatically, but **check `groupby(size, tps, repeat).nunique()` after any resumed sweep.**
1. **Spot preemption wipes the generator's `.venv` and database.** Validators and the chain survive. Recovery: `./scripts/deploy_harness.sh --phase phase2`, then re-run `deploy_and_fund`.
2. **Startup scripts re-run on EVERY boot**, not just creation. This reset `/opt/benchmark` ownership to `ubuntu` (breaking writes for the SSH user), and `polygon-edge secrets init` correctly refuses to overwrite existing validator keys, so all four validators' startup scripts exited 1 on a reboot. **Both now fixed** — `validator_setup.sh` has an idempotency guard, apt-lock timeout and download retries; `generator_setup.sh` has the apt-lock timeout. The running cluster was unaffected because `edge.service` is separately enabled and restarts on boot regardless.
3. **The hard-shutdown timer re-arms from each boot**, not from creation. A reboot silently extends the deadline.
4. **SSH is firewalled to one hardcoded home IP** (`terraform/phase2/terraform.tfvars`). It gets reassigned every few weeks; if SSH hangs, check `curl -s https://ifconfig.me` against the tfvars value. IAP is not permitted — deliberate, do not widen without asking.
5. **Never nest quotes through `gcloud compute ssh --command`.** Three shell layers mangle escapes silently. Write a script, `scp` it, run it.
6. **Backgrounding through SSH holds the session open forever.** Use `setsid nohup ... < /dev/null &` inside a script *on the remote*.
7. **macOS `pgrep` has no `-c` flag** — fails with a usage error that reads as "zero processes". Use `pgrep -f X | wc -l`.
8. **`pkill -f <pattern>` can match your own SSH command line** and kill the connection.
9. **Copying SQLite needs `VACUUM INTO`.** A plain copy without `-wal`/`-shm` gives "database disk image is malformed".
10. **Data files exceed GitHub's 100MB limit** and live in Git LFS. **The included LFS allowance is 10 GiB of storage and 10 GiB/month of bandwidth** on Free and Pro alike, and billing moved from pre-paid data packs to metered usage (verified against GitHub's billing docs, 12 Aug 2026) — the "1 GB free tier" recorded here earlier was out of date. The full dataset with NEAR projects to ~1.6 GB, so storage is not a constraint. **Bandwidth might be:** every clone pulls the LFS files, so roughly six full clones a month would exhaust the allowance. Still re-commit raw at phase boundaries rather than after every run, since LFS retains each version.
11. **The 10-minute command timeout** kills long transfers and installs. Run detached and poll.
12. **Quota: ~50% steps approved, doubling denied.** Limit now 96. History: 32→128 ❌, 32→48 ✅, 48→64 ✅, 64→128 ❌, 64→96 ✅.

---

## 6. Cost

**~$29 spent of $300** (expires 6 Nov 2026).

The avoidable part was an estimation error: after switching spot→on-demand, the quoted rate stayed at the *spot* figure (~$0.45/hr) when the real rate was ~$1.95/hr. Roughly $9 was on-demand when spot would have done.

**Use SPOT for everything.** Preemption costs ~15 minutes of rebuild; on-demand costs 4.5×. The sweep's `--resume` flag makes preemption cheap.

---

## 7. Phase 3 (Lightning) — closed, and why

**Read `LIGHTNING_ANALYSIS.md` for the full account.** Summary:

**Lightning's reliability and throughput data comes from Waugh & Holz (2020), not from our simulation.** Lightning capacity is additive across channels; our testbed had 51 against the real network's 19,644 — ~385x fewer. Success depends on how many routing paths exist, so a 51-channel network does not behave like the real one. Structural, not a bug.

> **⚠️ Citation corrected 18 Aug 2026:** the "6,010 nodes / 19,644 channels" figure does NOT appear in Waugh & Holz — zero occurrences in the full text. The paper states **4,826–4,950 nodes and ~31.4–31.8k channels** (Nov 2019). Against our 51 channels the true ratio is **~620x fewer, not 385x** — a stronger argument. 19,644 most likely came from 1ML, which publishes no collection timestamp and disagreed with mempool.space by 40% on 18 Aug 2026 (20,004 vs 33,313 channels). See `LIGHTNING_EVIDENCE.md` §2.

**Polygon did not have this problem** because it is a replicated state machine: throughput is set by the block gas limit and consensus timing, not validator count, so 4 validators measure the same ceiling as 100. That asymmetry is a finding, not an inconsistency — state it in the paper.

**What Lightning still contributes:**
- **Cost per transaction: $0.0523 at $200** — measured route length (2.571 hops at $200) priced at 1ML mainnet rates. Polygon is $0.0006. **87x.** *(Corrected 12 Aug from $0.0509/85x: one pooled hop count had been applied to every amount, when route length varies by amount. ANALYSIS_PLAN amendment 10.)*
- **The §12 crossover, resolved:** Polygon flat, Lightning proportional at 165 ppm. At $500 Lightning's routing fee alone ($0.1467) breaches the $0.10 threshold. **Caveat:** $200 and $500 rest on 3 and 2 runs against a 5-repeat minimum, and $50 was never run. The mechanism is certain; the exact crossing point is not.
- **Settlement time p50 1.501s** — small-scale illustrative only.
- Channel-open cost — **cited, not measured** (cluster destroyed first).

**All Lightning runs are in the raw parquet, none in the clean one.** No further Lightning testing is scheduled (`ANALYSIS_PLAN.md` §13 amendment 7).

---

## 7b. Next: Phase 4 (NEAR)

**Quota constraint decided the design.** The project-wide ceiling is 96 vCPU. 12 validators (104) does not fit; a request for 144 was **denied**, 120 is pending. **8 validators + generator = 72 fits.**

Eight satisfies the scope's ≥4 shards × ≥2 validators, but leaves no margin — losing one node drops a shard to a single validator, making NEAR's adversarial arm harsher than Polygon's. Say so when comparing them.

Two hard requirements:
1. **Pin the NEAR shard count to 4**, or 8 validators cannot cover every shard.
2. **The Lightning cluster is already destroyed**, so the ceiling is clear.

Work required: a NEAR adapter implementing `harness/adapters/base.py`, NEP-141 token transfers, settlement at `FINAL` (not `EXECUTED_OPTIMISTIC`), and NEAR mainnet gas pricing pulled at Phase 4 with its own stated date.

---

## 7c. Phase 4 (NEAR) — complete, 13 Aug 2026

**Sustainable throughput at $200, full realism stack** (warm-up cut applied;
success = settled FINAL within 60s):

| Offered | Achieved | Failures | Verdict |
|---|---|---|---|
| 10/sec | 9.8 | 1.37% | sustained |
| 25/sec | 24.8 | 0.88% | sustained |
| 50/sec | 49.8 | 0.41% | sustained |
| 100/sec | 100.2 | 0.12% | sustained |
| **150/sec** | **150.1** | **0.15%** | **sustained — the ceiling** |
| 200/sec | 47.5 | 76.3% | collapsed |
| 300/sec† | 9.9 | 96.7% | rule-excluded; reported from raw as sensitivity data |

**Amount does not matter**, as predicted for an account-model chain: $10 collapses
at 200/sec exactly as $200 does. The ceiling is architectural, not value-dependent.

**The 22 rule-excluded cells** (20 at 300/sec, 2 at 200/sec) drifted past the
50 ms lag-growth threshold — by 7–33 ms at 300/sec, with the attribution of that drift now an open question — the null-backend validation proved the scheduler holds 300/sec, but its backend makes no network calls, so it cannot rule out our per-payment settlement watcher as a contributor (`docs/near_methodology/generator_is_not_the_ceiling.md`, corrected 23 Aug). **They are now
REPORTED, from raw, as marked sensitivity data rather than hidden as
'unmeasurable'**: all 20 runs at 300/sec are internally consistent at 94–99.7%
failure, completing the collapse curve 0.15% → 76.3% → 96.7%. The threshold
itself sits 5 ms above the knee's data cluster (kept runs 22.8–46.8 ms,
excluded pair 51.9/54.3) — disclosed in `NEAR_ANALYSIS.md` §1b, with a
both-versions sensitivity showing no conclusion at the knee depends on it.

**Settlement floor: 7.90 s, at a 2s block interval** (nearcore default 600ms —
unstable across four continents; see `NEAR_ANALYSIS.md` §1b). Latency scales
with cadence, so every NEAR latency figure — including the decision-rule
latency disqualification — is conditional on the 2s setting. Also disclosed:
every transfer executed on the single token contract's shard; sharding
distributed inclusion, never execution.

**Caveat that must travel with every NEAR number:** 4 shards and 8 validators
against mainnet's 10 shards and 422 validators, with 2 producers per shard — the
protocol minimum. Scaling method in `docs/near_methodology/shard_scaling.md`.

**Node failures — NEAR is far more fragile than Polygon:**

| Offered | Baseline | With node failures | Lost |
|---|---|---|---|
| 100/sec | 100.0/sec, 0.16% | 68.4/sec [39.1, 95.3], 31.7% | **32%** |
| 150/sec | 150.1/sec, 0.15% | 35.4/sec [3.8, 69.3], 76.4% | **76%** |
| 200/sec | 47.5/sec, 76.3% | 0.1/sec [0.0, 0.3], 99.9% | **100%** |

Polygon lost 26% at its knee; NEAR loses 76% at its own. **The intervals are very
wide** because outage timing is random — report the range, never the mean alone.
The structural cause is 2 producers per shard (protocol minimum), so one validator
down halves the affected shard. That is a quota artefact of our cluster, not a
property of sharding, and must be stated wherever the comparison appears.

**Cost per payment: $0.000365** — 2.214x10^12 gas over 2,423,969 confirmed
payments, priced at mainnet rates. **The cheapest of the three** (Polygon $0.0006,
Lightning $0.0523), though all three are far under the $0.10 threshold, so cost
does not discriminate between the two on-chain architectures.

**Exploratory downtime block: the calibration argument did NOT work.** Cutting
outage frequency 10x (43% -> 4% downtime) produced no distinguishable improvement
(35.4/sec vs 47.9/sec, intervals overlapping almost completely). There is no
measured relationship to extrapolate toward mainnet's 0.1%. Claims about real-world
failure behaviour must rest on the hostility ratios as bounds. See
`NEAR_ANALYSIS.md` S6.

**Shard projection: WITHDRAWN.** All execution lands on the token contract's
single shard, so 150/sec is a single-execution-shard ceiling and shard count
cannot scale it. Replacement finding: sharding provides no execution-throughput
scaling for a single-contract stablecoin workload — the dominant real
remittance pattern.

**Phase 4 documentation** lives in `docs/near_methodology/`, indexed by its
`README.md`. Beyond the two files above: `adversarial_arm.md` (the three
asymmetries against Polygon and the four-hour expulsion cost),
`restart_recovery_effect.md`, `finishing_runbook.md`, `cost_per_transaction.md`,
`settlement_definition.md`.

---

## 8. Open items

- **Cost crossover (pre-registered, §12).** Polygon/NEAR charge flat fees; Lightning charges partly by percentage. A crossover should exist where Lightning stops being cheapest as amounts rise. Locating it is a pre-registered secondary objective.
- **Phase 5 calibration not started.** Needs mainnet gas prices from Polygonscan and NEAR Explorer, pulled on one stated date, cited once. Plus the two-figure calibration gap (demand ratio and capability gap) per `ANALYSIS_PLAN.md` §11.
- **NEAR is capped at 8 validators by quota.** The ceiling is 96 vCPU project-wide. 12 validators (104) does not fit; a request for 144 was **denied** on 10 Aug, and 120 is pending. 8 validators + generator = 72 and fits. Eight satisfies the scope's ≥4 shards × ≥2 validators, but leaves no margin — losing one node drops a shard to a single validator, which makes NEAR's adversarial arm harsher than Polygon's. Pin the NEAR shard count to 4, and destroy Lightning before deploying NEAR (24 + 72 = 96 exactly).

---

## 9. Standing instructions from Angad

- **Begin every message with "Hi Angad!"** — every message, without exception.
- **Commit and push to `main` without asking** (standing permission, 12 Aug 2026) — but **say so every time**, naming what went in. No branch workflow on this repo.
- **Flag anything that spends money first**, with the rate for the pricing model actually in use.
- **No jargon.** He defends this to examiners and cannot defend what he cannot explain. Plain words for everything: "the program that sends test payments", not "the harness".
- **Keep `METHODOLOGY_LOG.md` current unprompted** — the paper is written from it.
- **Regenerate and commit both data files after every run**, unprompted.
- **One standard applied everywhere.** He rejected reporting two saturation criteria side by side: visible mid-study switches damage credibility. Amendments go in `ANALYSIS_PLAN.md` §13 and apply uniformly to all data.
- **Never edit the amendment log to hide a change.** Declined once; the reasoning holds, and the data carries the trail regardless.

---

## 10. Documents

**Results write-ups, one per architecture, plus the comparison:**
- `POLYGON_ANALYSIS.md` — Polygon Edge results
- `NEAR_ANALYSIS.md` — **new 13 Aug** — NEAR results, cost, adversarial arm, shard projection
- `LIGHTNING_ANALYSIS.md` — Lightning, and why its data source changed
- `COMPARISON.md` — **new 13 Aug** — the three-way evidence table for Phase 6. Assembles what was measured and flags where the columns are NOT the same kind of evidence. Deliberately stops short of a recommendation, which is Phase 6 and Angad's work.


| File | Contents |
|---|---|
| `POLYGON_ANALYSIS.md` | **Complete Polygon results in one place** — throughput, cost, adversarial arm, limitations, corrections |
| `METHODOLOGY_LOG.md` | Every decision, parameter, correction, dated. **The paper is written from this.** |
| `ANALYSIS_PLAN.md` | Locked pre-registered analysis. §13 is the amendment log. |
| `HANDOFF.md` | Self-contained brief for the writing agent, including claims the paper must NOT make |
| `claude.md` | Original project scope |
| `DECISIONS.md` | Technical choices vs. rejected alternatives |
| `PHASE1.md` | Plain-language walkthrough of phase 1 |
