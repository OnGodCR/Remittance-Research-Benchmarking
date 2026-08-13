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
> **The finding worth building a paragraph around is the failure MODE, not the
> ceiling.** Polygon degrades gracefully past its knee — 270.5/sec achieved when
> offered 300, 9.97% failures. NEAR *collapses*: offered 200, it achieves 47.5/sec
> with 76% failures, which is worse than it manages when offered 50. Ask it for
> more, get less. For a payment system facing payday and holiday clustering — the
> exact peak scenario this study cites — that difference matters as much as the
> headline number.
>
> **Phase 5 is next**: merge, clean, confidence intervals, calibration ratios,
> shard scaling. See §7c.
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
gcloud compute instances list --project project-c4c87dcb-da41-4caf-922
```

**Credit position: $180 of $300 consumed as of 12 Aug ~23:00**, checked by Angad
in the billing console. Phase 4's remaining spend was ~$25-30 on top. Neither
figure is a live reading — check the console for the real number.

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
| 300/sec | — | — | no valid run at any amount |

**Amount does not matter**, as predicted for an account-model chain: $10 collapses
at 200/sec exactly as $200 does. The ceiling is architectural, not value-dependent.

**The 22 unmeasurable cells** are the 200/sec and 300/sec steps where the offered
arrival pattern drifted past the pre-registered 50 ms saturation threshold. **This
is not our tooling.** The harness was validated to sustain 300/sec against a null
backend under an equivalent in-flight load, p95 scheduling lag 1.2 ms. The drift
comes from NEAR's RPC answering slowly under congestion, which holds up the send
path. Full evidence and the sentence it licenses in the paper:
`docs/near_methodology/generator_is_not_the_ceiling.md`.

**Settlement floor: 8.16 s**, mean 11.4 s at low load — much slower than Polygon's
~3.2 s, and real. It is the protocol: inclusion, then a cross-shard receipt, then
finality, each costing blocks.

**Caveat that must travel with every NEAR number:** 4 shards and 8 validators
against mainnet's 10 shards and 422 validators, with 2 producers per shard — the
protocol minimum. Scaling method in `docs/near_methodology/shard_scaling.md`.

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

| File | Contents |
|---|---|
| `POLYGON_ANALYSIS.md` | **Complete Polygon results in one place** — throughput, cost, adversarial arm, limitations, corrections |
| `METHODOLOGY_LOG.md` | Every decision, parameter, correction, dated. **The paper is written from this.** |
| `ANALYSIS_PLAN.md` | Locked pre-registered analysis. §13 is the amendment log. |
| `HANDOFF.md` | Self-contained brief for the writing agent, including claims the paper must NOT make |
| `claude.md` | Original project scope |
| `DECISIONS.md` | Technical choices vs. rejected alternatives |
| `PHASE1.md` | Plain-language walkthrough of phase 1 |
