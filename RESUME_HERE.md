# Resume Here — complete state, updated 11 August 2026

> ## ⚠️ READ `PHASE4_HANDOFF.md` FIRST
>
> **A 9-instance NEAR cluster is RUNNING and billing right now**, with **no idle watcher and
> no hard shutdown cap**. It has produced **0 of 140 valid runs**. The chain is healthy; the
> measurement harness had a race condition that discarded every transaction hash. A fix is
> written but untested and not deployed.
>
> §2 of this document ("Nothing is running") describes the state on **9 August** and is
> **no longer true**. Everything about Phases 1–3 below remains accurate.

**Read this, then `METHODOLOGY_LOG.md` (every decision and parameter) and `ANALYSIS_PLAN.md` (the locked analysis rules). Between them you should not need conversation history.**

---

## 1. Where the project is

| Phase | State |
|---|---|
| 1 — Pipeline validation | ✅ Complete |
| 2 — Realism techniques on Polygon | ✅ **Complete — 140/140 configurations** |
| 2b — Adversarial arm (Polygon) | ✅ **Complete — 15/15 runs** |
| 3 — Lightning | ✅ **Closed 10 Aug** — data source switched to Waugh & Holz (2020); cost + illustrative settlement time retained |
| 4 — NEAR sharding | ⚠️ **IN PROGRESS, 0/140 valid runs** — cluster live and billing; see `PHASE4_HANDOFF.md` |
| 5 — Calibration + confidence intervals | ❌ Not started |
| 6 — Cross-architecture comparison | ❌ Not started |

**Dataset: 5,717,593 payments across 155 runs (Polygon only)** (140 main matrix + 15 adversarial), committed and pushed via Git LFS. 211 runs collected in total; 56 excluded under the pre-registered rules.

### Realism techniques

| # | Technique | Built | Run against a real cluster |
|---|---|---|---|
| 1 | Multi-region | ✅ | ✅ |
| 2 | Injected latency, jitter, packet loss | ✅ | ✅ |
| 3 | Competing background traffic | ✅ | ✅ |
| 4 | Hardware matched to real validators | ✅ | ✅ (`n2-standard-8`) |
| 5 | Lightning liquidity topology | — | Phase 3 only |
| 6 | Adversarial nodes | ✅ | ✅ full arm, 15/15 |
| 7 | Calibration against mainnet | ✅ | Pricing + topology pulled 9 Aug; ratios pending |
| 8 | Five repeats | ✅ | ✅ |

---

## 2. What is running  *(superseded 11 Aug — this section said "Nothing is running")*

**A 9-instance NEAR cluster IS running and billing**: `near-validator-0..7` + `near-generator`,
`n2-standard-8`, across us-east4-c / asia-south1-a / asia-southeast1-a / europe-west2-b.
Roughly **$75–85 of the $300 credit** spent. **The idle watchers are disabled and the hard
lifetime cap is gone** — there is currently nothing that will shut this cluster down.
Full detail, and the four bugs found, in **`PHASE4_HANDOFF.md`**.

**Polygon is finished** — main matrix (140/140) and adversarial arm (15/15). **Lightning is
closed** (data sourced from Waugh & Holz; see `LIGHTNING_ANALYSIS.md`). **Phase 4 has 0 valid
runs**: the chain is healthy, but a race in the harness discarded every transaction hash.

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
10. **Data files exceed GitHub's 100MB limit** and live in Git LFS. Free tier 1GB; re-commit raw at phase boundaries only.
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

**Polygon did not have this problem** because it is a replicated state machine: throughput is set by the block gas limit and consensus timing, not validator count, so 4 validators measure the same ceiling as 100. That asymmetry is a finding, not an inconsistency — state it in the paper.

**What Lightning still contributes:**
- **Cost per transaction: $0.0509 at $200** — measured route length (2.53 hops) priced at 1ML mainnet rates. Polygon is $0.0006. **85x.**
- **The §12 crossover, resolved:** Polygon flat, Lightning proportional at 165 ppm. At $500 Lightning's routing fee alone ($0.1267) breaches the $0.10 threshold.
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

## 8. Open items

- **Cost crossover (pre-registered, §12).** Polygon/NEAR charge flat fees; Lightning charges partly by percentage. A crossover should exist where Lightning stops being cheapest as amounts rise. Locating it is a pre-registered secondary objective.
- **Phase 5 calibration not started.** Needs mainnet gas prices from Polygonscan and NEAR Explorer, pulled on one stated date, cited once. Plus the two-figure calibration gap (demand ratio and capability gap) per `ANALYSIS_PLAN.md` §11.
- **NEAR is capped at 8 validators by quota.** The ceiling is 96 vCPU project-wide. 12 validators (104) does not fit; a request for 144 was **denied** on 10 Aug, and 120 is pending. 8 validators + generator = 72 and fits. Eight satisfies the scope's ≥4 shards × ≥2 validators, but leaves no margin — losing one node drops a shard to a single validator, which makes NEAR's adversarial arm harsher than Polygon's. Pin the NEAR shard count to 4, and destroy Lightning before deploying NEAR (24 + 72 = 96 exactly).

---

## 9. Standing instructions from Angad

- **Begin every message with "Hi Angad!"** — every message, without exception.
- **Flag anything that spends money first**, with the rate for the pricing model actually in use.
- **No jargon.** He defends this to examiners and cannot defend what he cannot explain. Plain words for everything: "the program that sends test payments", not "the harness".
- **Keep `METHODOLOGY_LOG.md` current unprompted** — the paper is written from it.
- **Regenerate and commit both data files after every run**, unprompted.
- **One standard applied everywhere.** He rejected reporting two saturation criteria side by side: visible mid-study switches damage credibility. Amendments go in `ANALYSIS_PLAN.md` §13 and apply uniformly to all data.
- **Never edit the amendment log to hide a change.** Declined once; the reasoning holds, and the data carries the trail regardless.

---

## 10. Documents

| File | Contents |
|---|---|
| `POLYGON_ANALYSIS.md` | **Complete Polygon results in one place** — throughput, cost, adversarial arm, limitations, corrections |
| `METHODOLOGY_LOG.md` | Every decision, parameter, correction, dated. **The paper is written from this.** |
| `ANALYSIS_PLAN.md` | Locked pre-registered analysis. §13 is the amendment log. |
| `HANDOFF.md` | Self-contained brief for the writing agent, including claims the paper must NOT make |
| `claude.md` | Original project scope |
| `DECISIONS.md` | Technical choices vs. rejected alternatives |
| `PHASE1.md` | Plain-language walkthrough of phase 1 |
