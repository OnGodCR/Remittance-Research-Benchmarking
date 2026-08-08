# Resume Here — end of session, 8 August 2026

**Cloud is fully shut down.** Verified: 0 machines, 0 disks, 0 IP addresses, 0 of 32 processors in use. Nothing is billing.

**All work committed.** 207,065 payments across 23 runs in the repo.

---

## Realism techniques — status

| # | Technique | Built | Run against a real cluster |
|---|---|---|---|
| 1 | Multi-region deployment | ✅ | ✅ **yes** |
| 2 | Injected latency & packet loss | ✅ | ❌ not yet |
| 3 | Competing background traffic | ✅ | ❌ not yet |
| 4 | Hardware matched to real validators | ❌ | ⛔ blocked on quota |
| 5 | Lightning liquidity topology | — | Phase 3, not applicable to Polygon |
| 6 | Adversarial / unreliable nodes | ✅ | ❌ not yet |
| 7 | Calibration against mainnet | ❌ | Phase 5 |
| 8 | Five repeats / confidence intervals | ✅ | ❌ not yet |

**Built is not the same as validated.** Techniques 2, 3, 6 and 8 exist as working, syntax-checked code but have never executed against a live cluster. Expect bugs on first run — every previous component had them, and three of those bugs produced convincing but wrong results.

---

## Immediate next steps, in order

**1. Check the quota.** It gates everything remaining.

```bash
gcloud quotas preferences list --project=project-c4c87dcb-da41-4caf-922
```

Requested 128, granted 32 as of last check. When it reads 128, techniques #4 and the ceiling question both unblock.

**2. Shake out the three untested techniques** on a short cheap run before trusting them — impairment, background traffic, adversarial nodes, one at a time, confirming results still make sense after each. This is the phased order in `claude.md` §9 and exists precisely so that when a number moves, the cause is unambiguous.

**3. Then the real sweep**: 5 repeats, 300-second windows, full load ramp. That is the first data that qualifies as results.

---

## Two things blocked on the quota

**Hardware matching (#4).** Real Polygon validators run 8 processors; we are on 4. Needs 60 processors for 7 validators plus a generator; the cap is 32.

**Polygon's actual throughput ceiling.** Confirmed to sustain **300 payments/second across four continents with zero failures and 5.30s settlement**. Above that is unmeasured — attempts at 500 and 1000 saturated our own 4-processor generator (3.7s and 50s of scheduling lag) and auto-invalidated. The blockchain was never the limit; our machine was.

---

## Confirmed results so far

Polygon Edge, 4 validators across Virginia, Mumbai, Singapore, London. Exploratory only — 60-second windows, one repeat, against the pre-registered 300 seconds and five.

| Offered/sec | Achieved | Failures | Settlement |
|---|---|---|---|
| 10 | 9.4 | 0 | 3.18s |
| 25 | 24.8 | 0 | 3.27s |
| 50 | 49.1 | 0 | 3.41s |
| 150 | 148.8 | 0 | 3.51s |
| 200 | 199.4 | 0 | 3.90s |
| 300 | 298.6 | 0 | 5.30s |

**No knee within the tested range.** Polygon passes every pre-registered threshold at every level. An earlier report of a knee at 100–150 was wrong — it was our own measurement tool, corrected on 8 Aug.

Gas per transfer: **35,865** (warm recipient).

---

## Cost

Roughly **$2.50–3.00** total across all sessions, of the $300 credit. Google's billing reports on a 6–24 hour delay, so the console lags reality.

**$1.61 of that was one avoidable overnight run** — see the idle-shutdown bug below.

Credit expires **6 November 2026**.

---

## Bugs found so far

Ten. Each would have produced wrong data or wasted hours.

1. **Proof-of-authority headers broke settlement detection.** Every payment timed out; the run reported 100% failure. Our client refusing to read blocks, not the chain failing.
2. **A phantom throughput knee.** Reported as a finding, then disproved — single-process backpressure inflating settlement times 5.5×. Led to tightening the saturation threshold from 250ms to 40ms.
3. **Idle shutdown never fired — cost $1.61.** It counted connections on the blockchain port, assuming only our tool used it. Validators talk to each other on it constantly, so the cluster permanently looked busy to its own check. Now counts transactions inside blocks instead, which cannot be faked by the cluster's own chatter.
4. **Solidity targets an instruction set Edge v1.3.2 predates.** Deployment mined, reverted, consumed exactly the full gas limit — nothing about it resembles a compiler problem.
5. **The harness itself was the bottleneck** above 150/sec. Fixed by splitting across processes.
6. **polygon-edge v1.3.2 flags differ from its documentation.**
7. **Genesis written 0660 owned by `edge`**, so distribution silently returned an empty file.
8. **`--tunnel-through-iap=false` is invalid syntax**; swallowed failures read as "not ready yet".
9. **Directory ownership hardcoded to `ubuntu`** while gcloud logs in as the local user.
10. **Global processor cap is separate from the per-region one**, letting a deployment start that could never finish.

**Three of these produced results that looked entirely plausible.** That is the strongest argument in the project for why Phase 1 and the saturation detector exist, and it belongs in the Methodology section.

---

## Two open questions for the paper

**Gas: 35,865 or ~51,000?** Ours assumes the recipient already holds the token. A first-time recipient costs ~40% more. Depends on whether corridors are modelled as repeat transfers to family or one-off sends. Moves the headline cost figure materially.

**Should the load ramp extend past 300/sec?** Polygon clears the pre-registered ceiling without strain. Extending would be an amendment to the locked plan and needs logging in `ANALYSIS_PLAN.md` §13. Reporting "exceeds realistic peak remittance demand" is also a legitimate answer.
