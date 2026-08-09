# Resume Here — complete state, 9 August 2026

**Read this, then `METHODOLOGY_LOG.md` (every decision and parameter) and `ANALYSIS_PLAN.md` (the locked analysis rules). Between them you should not need conversation history.**

---

## 1. Where the project is

| Phase | State |
|---|---|
| 1 — Pipeline validation | ✅ Complete |
| 2 — Realism techniques on Polygon | ✅ **Complete — 140/140 configurations** |
| 2b — Adversarial arm (Polygon) | ✅ **Complete — 15/15 runs** |
| 3 — Lightning | ❌ Not started |
| 4 — NEAR sharding | ❌ Not started |
| 5 — Calibration + confidence intervals | ❌ Not started |
| 6 — Cross-architecture comparison | ❌ Not started |

**Dataset: 7,019,566 payments across 196 runs**, committed and pushed via Git LFS.

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

## 2. Nothing is running

**Cloud fully destroyed and verified: 0 instances, 0 disks, 0 addresses, 0 of 96 processors.** Nothing is billing.

**Polygon is finished.** Main matrix (140/140) and adversarial arm (15/15) both complete. Next work is Phase 3 (Lightning) — see §7.

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
| **200** | **200.8** | **0.00%** | 3.43s | 4.76s | 6.48s |
| 300 | 270.5 | 9.97% | 10.61s | 24.26s | 30.49s |

**Sustainable throughput at $200 = 200/sec** (pre-registered metric: achieved ≥90% of offered AND failures <5%).

**The knee is between 200 and 300/sec.** Flat from 10 through 200, then settlement triples and failures appear for the first time.

**Size does not affect failure**, as pre-registered in §12. At 300/sec: $10 10.86%, $50 10.83%, $200 9.97%, $500 12.85% — no monotonic relationship. This flat result is the contrast that will make Lightning's expected *inverse* size/success relationship meaningful.

### Adversarial arm (node failures), same conditions plus validators dropping offline

| Offered/sec | Clean | With node failures | Lost |
|---|---|---|---|
| 100 | 100.1/s, 0.00% fail | 99.4/s [99–100], 0.8% fail | **0.8%** |
| 200 | 200.8/s, 0.00% fail | 148.4/s [122–173], 26.1% fail | **26.1%** |
| 300 | 270.5/s, 9.97% fail | 156.2/s [93–203], 48.0% fail | **42.2%** |

Damage scales with existing load: negligible with headroom, severe without. Note the 93–203 spread at 300/sec — outage timing is random, and a single run could have reported either extreme.

⚠️ **The injection is ~130× more hostile than real Polygon** (1 of 4 validators = 25% of the network vs ~1% on mainnet; offline 51% of the time vs a 99.9% uptime target). This measures *sensitivity to validator loss*, not mainnet behaviour. See `METHODOLOGY_LOG.md` §4 technique #6.

**Context:** global remittances average ~140-150/sec. Polygon clears steady-state global demand comfortably, but breaks in the middle of the 200-300/sec peak range the scope defines.

**Superseded finding:** an exploratory pilot suggested Polygon sustained 300/sec with zero failures. It came from 60-second windows on a quieter chain. Under the full protocol it does not hold — short windows measured the burst, not the steady state.

---

## 4. The saturation criterion — read before touching exclusions

The rule changed twice; **only the current one is in force anywhere**:

1. 8 Aug: absolute lag threshold tightened 250ms → 40ms (p95). *Superseded, produced no reported result.*
2. **9 Aug (current): lag GROWTH.** A run is excluded when median scheduling lag rises by more than **50ms** between the first and last quarter.

Growth, not magnitude, because a constant offset distorts nothing — offered load still matches intended load — whereas climbing lag means the delivered arrival pattern drifted from the scheduled Poisson process.

**Validated** against 7 independently-known-broken runs; detects all 7, including a subtle 9.7ms→294.9ms case. **Applied uniformly to all 196 runs** via `analysis/reevaluate_saturation.py`.

**Stated limitation:** re-judging moved runs from excluded to included and none the other way. That asymmetry is the signature of a criterion devised after seeing data. Recorded in `ANALYSIS_PLAN.md` §13 and `METHODOLOGY_LOG.md` §7.2 rather than hidden.

---

## 5. Operational traps — read before touching infrastructure

Every one cost real time or money.

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

## 7. Next: Phase 3 (Lightning)

A substantial build, not a configuration change.

**Transfers unchanged:** the measurement core (`harness/core/`) — arrival timing, concurrency, storage, saturation criterion. Deliberately architecture-agnostic.

**Does not transfer:**

| | Polygon | Lightning |
|---|---|---|
| Moves | Transactions in blocks | Payments through pre-funded channels |
| Settled when | In a committed block | Sender receives the preimage |
| Fails because | Out of gas | No route with enough liquidity |
| Needs | Funded wallets | A funded channel *topology* |

Work required:
1. New adapter implementing `harness/adapters/base.py` for LND
2. Infrastructure: bitcoind + ~20 LND nodes on `regtest`
3. **Realism technique #5**: pull real channel/capacity data from 1ML.com, fund channels to match real-world concentration (few well-funded hubs, many thin leaves) rather than evenly
4. Record route length and liquidity failures

**Why it matters most:** the only architecture where payment size genuinely changes behaviour — both success rate and cost. Direct test against Waugh & Holz (2020); pre-registered expectation is an *inverse* size/success relationship (~72% at smallest, ~15% at largest). Also the cheapest cluster to run.

---

## 8. Open items

- **Cost crossover (pre-registered, §12).** Polygon/NEAR charge flat fees; Lightning charges partly by percentage. A crossover should exist where Lightning stops being cheapest as amounts rise. Locating it is a pre-registered secondary objective.
- **Phase 5 calibration not started.** Needs mainnet gas prices from Polygonscan and NEAR Explorer, pulled on one stated date, cited once. Plus the two-figure calibration gap (demand ratio and capability gap) per `ANALYSIS_PLAN.md` §11.
- **NEAR will need more quota.** 8-12 validators at 8 vCPU ≈ 96-100 processors. Limit is 96 — request early, in ~50% steps.

---

## 9. Standing instructions from Angad

- **Flag anything that spends money first**, with the rate for the pricing model actually in use.
- **No jargon.** He defends this to examiners and cannot defend what he cannot explain.
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
