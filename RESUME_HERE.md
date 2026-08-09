# Resume Here — Session B in progress, 9 August 2026

**Cloud is LIVE right now, mid-sweep, unattended.** 5 machines running: `bench-p2-generator` (us-east4) plus 4 validators, one per region (`us-east4`, `asia-south1`, `asia-southeast1`, `europe-west2`), all `n2-standard-8`. This is expected — the full 140-run sweep for `phase-2-full-stack` is still short 43 runs (see below) and the cluster needs to stay up to finish it. **Do not tear it down until the sweep completes or you've deliberately paused it.**

**All work as of the last sync is committed** (`aff49d5`). Local `data/working/runs.sqlite` shows **131 runs recorded, 97 of them the real 140-run sweep** (`phase-2-full-stack`), 3,516,117 payments raw / 3,023,685 in the cleaned dataset. That reflects the DB as last pulled — if the sweep has advanced further on the generator since, this file is behind it; check `sweep.log` on `bench-p2-generator` for the live count before trusting the numbers below.

## Live infrastructure check, 9 Aug ~08:20–08:40 UTC (verified without SSH — see note)

Checked while the cluster was unattended, using `gcloud` metadata/monitoring only (SSH is not reachable from this environment — see below):

- **All 5 machines rebooted together at ~05:45–05:46 UTC today.** Root cause: the cluster was switched from **spot to on-demand** provisioning (`scheduling.provisioningModel` confirmed `STANDARD`/`preemptible: false` on all 5, where the terraform default is spot) — almost certainly a deliberate response to the earlier 43-run spot-preemption loss, and exactly the fallback `claude.md` §8 anticipates ("If observed preemption rates turn out high, switch measured runs to on-demand"). Changing provisioning model requires a stop/start cycle, which explains the synchronized reboot. **Good news: no more preemption risk to the remaining 43 runs.**
- **The reboot re-armed the shutdown guard's hard-lifetime timer from the new boot time**, not the original creation time. New hard-shutdown deadline: **~20:45–21:01 UTC today**, one per machine, independently armed by the kernel at boot — confirmed sound, confirmed will fire regardless of what else happens. The 30-minute idle-watcher is the earlier, softer guard on top of that.
- **All 4 validators' startup scripts failed (exit 1) on this reboot** — the generator's succeeded. Root-caused: `validator_setup.sh` wasn't idempotent — `polygon-edge secrets init` correctly refuses to overwrite a validator's already-existing key material, which only surfaces on a *second* run of the script (i.e. a reboot, not first boot). **This did not affect the running cluster**: `edge.service` is a separately `systemctl enable`d unit that auto-restarts on boot regardless of the startup-script's own exit code, and it — along with the shutdown guard — runs *before* the point of failure in the combined script. Confirmed via Cloud Monitoring CPU utilization (checked ~08:23 UTC): generator ~31%, same-region validator ~20%, remote validators ~7% each — the signature of a live, asymmetric, active sweep, not a stalled cluster. **Fixed anyway** in `terraform/phase1/scripts/validator_setup.sh` (idempotency guard + apt-lock timeout + download retries) and `generator_setup.sh` (apt-lock timeout), so the next fresh deploy or reboot doesn't hit this. Not yet applied to the live machines — they don't need it since they're already provisioned and running; the fix matters for the *next* boot.
- **SSH is unreachable from this environment**: the `remittance-bench-p2-operator` firewall rule allows port 22 only from one hardcoded home IP (`terraform/phase2/terraform.tfvars`, "gets reassigned every few weeks"), not from IAP's range. That's a deliberate security choice from earlier in the project, not a bug — did not change it, since firewall/security changes need your explicit go-ahead. This means live run-counts and `sweep.log` couldn't be read directly; everything above was inferred from `gcloud` metadata, serial console, and Cloud Monitoring instead.

---

## Realism techniques — status

| # | Technique | Built | Run against a real cluster |
|---|---|---|---|
| 1 | Multi-region deployment | ✅ | ✅ **yes** |
| 2 | Injected latency & packet loss | ✅ | ✅ **yes** — part of the full-stack sweep |
| 3 | Competing background traffic | ✅ | ✅ **yes** — noise generator runs alongside every sweep |
| 4 | Hardware matched to real validators | ✅ | ✅ **yes** — quota raised, `n2-standard-8` per node |
| 5 | Lightning liquidity topology | — | Phase 3, not applicable to Polygon |
| 6 | Adversarial / unreliable nodes | ✅ | Partially — `step4-adversarial` has 1 shakeout run; full arm not yet in the matrix |
| 7 | Calibration against mainnet | ❌ | Phase 5 |
| 8 | Five repeats / confidence intervals | ✅ | ✅ **yes** — `phase-2-full-stack` runs 5 repeats per configuration |

All eight techniques are now built and at least shaken out; the full realism stack (#1–4, #8) is what's running in the current sweep.

---

## Immediate next steps, in order

**1. Let the sweep finish, or resume it.** `phase-2-full-stack` needs 4 sizes × 7 loads × 5 repeats = 140 runs; 97 are in. Missing:

| Amount | Missing loads |
|---|---|
| $200 | tps200 (3 more repeats), tps300 (all 5) |
| $500 | everything (all 35 — this size hasn't started) |

That's 43 runs remaining. Resume via:
```bash
./scripts/run_sweep_detached.sh phase-2-full-stack 8 --resume
```
(`harness.cli sweep --resume` skips configurations already recorded, so it's safe to re-run without duplicating completed work.)

**2. Watch for spot preemption.** The last attempt lost 43 of 140 runs this way — that's exactly the 43 still outstanding, though not necessarily the same configurations. Preemption auto-invalidates and re-queues per `claude.md` §8; check `data/working/node_events_*.log` for `preemption` entries after the sweep finishes.

**3. Once phase-2-full-stack hits 140/140**, re-run `analysis/export.py` to refresh the two canonical parquet files, then move to Phase 5 (calibration against mainnet, confidence intervals across the full matrix — technique #7 is the only one not yet run).

---

## The saturation criterion changed — read this before touching exclusions

The rule for "generator fell behind and the run's numbers can't be trusted" changed **twice**:

1. 8 Aug: absolute lag threshold tightened 250ms → 40ms (p95).
2. **9 Aug (current): replaced with lag GROWTH.** A run is excluded when its median scheduling lag rises by more than **50ms** between the first and last quarter of the run — not when lag is merely large. A generator sitting a constant few ms behind schedule distorts nothing; a generator progressively falling further behind means the arrival pattern drifted from the Poisson process that was scheduled. See `ANALYSIS_PLAN.md` §13 and `METHODOLOGY_LOG.md` §7.2 for the full reasoning and validation (detects all 7 independently-known-broken runs, including a subtle 9.7ms→294.9ms case).

**This is now the single criterion, applied uniformly to all 131 runs recorded so far** (`analysis/reevaluate_saturation.py`). Re-judging moved 24 runs from excluded to included and none the other way — mostly high-TPS runs in the real sweep that the old magnitude threshold was wrongly excluding. That asymmetry is stated as a limitation in the methodology log rather than hidden.

**Bug caught in that re-judging script, now fixed:** its matcher for "was this run invalidated for a saturation reason" checked for the substring `"saturat"`, but the superseded 8-Aug wording ("...exceeds the tightened 40ms threshold") never contains that word — so two runs invalidated under the old rule were silently skipped and stuck judged by a rule that no longer exists. Fixed to match on `"lag"` instead, which every saturation-reason string contains (verified: zero runs now carry a superseded reason). Had no effect on the paper's actual results — both affected runs are in `phase-2-step1-pilot`, a non-result phase excluded entirely regardless — but it's now correct rather than accidentally-harmless.

---

## Confirmed results so far (phase-2-full-stack, real 5-repeat data — supersedes the old exploratory table)

Full per-size/per-load breakdown isn't pulled together here yet (do that in Phase 6 write-up, or ask Claude Code to summarize `data/clean/all_runs_clean.parquet` directly). What's confirmed:

- **No saturation-excluded runs in the real sweep** — 97/97 recorded runs pass the current criterion.
- The earlier exploratory finding still holds directionally: Polygon showed no throughput knee in the 10–300/sec range during the pilot ramp. The full-stack sweep (with realism techniques #2–4 now actually active, not just built) is the first data that can confirm whether that holds under real injected latency, background traffic, and matched hardware — check this once 140/140 is in, since it's a materially different (harder) condition than the pilot.

Gas per transfer: **35,865** (warm recipient) — unchanged, see open question below.

---

## Cost

**Last confirmed figure: ~$2.50–3.00, as of 8 Aug** (before Session B). Session B has since run a live 5-machine matched-hardware cluster across 4 regions for an extended sweep — actual cost for this session has **not been confirmed** (billing console lags 6–24h, and the sweep is still running as of this update). Check the console before assuming the old figure still applies:
```bash
gcloud billing accounts list
```
Credit expires **6 November 2026**; $300 in hand.

---

## Bugs found so far

**Thirteen.** Each would have produced wrong data or wasted hours.

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
11. **The 40ms magnitude threshold was itself mis-specified** — it excluded runs with flat, harmless constant lag (e.g. 7.2ms in both the first and last quarter at 200/sec) purely because that constant offset happened to sit above 40ms, while a run whose lag genuinely climbed into the seconds could in principle pass if its *average* stayed low. Replaced with the growth criterion above.
12. **`reevaluate_saturation.py`'s reason-text matcher missed the superseded threshold's wording**, silently leaving 2 runs judged by a rule that no longer existed instead of re-judging them under the current one. Caught on review before it reached a result-bearing phase.
13. **The sweep progress monitor's pattern needed a bracket escaped through three shell layers** (local → SSH → nohup), which mangled it into matching nothing — so it reported the sweep stuck at zero runs while it was actually running normally. Fixed twice; now matches a string needing no escaping.

**Several of these produced results that looked entirely plausible.** That is the strongest argument in the project for why Phase 1 and the saturation detector exist, and it belongs in the Methodology section.

---

## Two open questions for the paper

**Gas: 35,865 or ~51,000?** Ours assumes the recipient already holds the token. A first-time recipient costs ~40% more. Depends on whether corridors are modelled as repeat transfers to family or one-off sends. Moves the headline cost figure materially.

**Should the load ramp extend past 300/sec?** Polygon cleared the pre-registered ceiling without strain in the pilot. Extending would be an amendment to the locked plan and needs logging in `ANALYSIS_PLAN.md` §13. Reporting "exceeds realistic peak remittance demand" is also a legitimate answer. Worth revisiting once the full-stack sweep (with real injected latency/background traffic, not just the pilot's bare cluster) is in — the ceiling under the full realism stack may differ from the pilot's.
