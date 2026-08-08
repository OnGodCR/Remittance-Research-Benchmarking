# Resume Here — state as of 8 August 2026

Everything in the cloud is **destroyed**. Nothing is billing.

---

## Where things stand

| Phase | State |
|---|---|
| Setup — measurement program | Complete, verified |
| Phase 1 — pipeline validation, one region | **Complete.** 1,499 payments, zero failures, 3.115s settlement |
| Phase 2 step 1 — multi-region | **Complete.** 4 continents, first capacity curve measured |
| Phase 2 step 2 — injected latency | Not started |
| Phase 2 step 3 — hardware matching | **Blocked on quota** |
| Phase 2 step 4 — background traffic | Not started |
| Phase 2 step 5 — adversarial nodes | Not started |

**Data on record:** 69,801 payments across 17 runs, all committed. Four runs correctly flagged invalid. The clean dataset is empty and correctly so — nothing yet meets the pre-registered protocol of 300-second windows and five repeats.

---

## The headline result so far

Polygon Edge, four validators across Virginia, Mumbai, Singapore and London:

| Offered/sec | Achieved | Failures | Settlement |
|---|---|---|---|
| 10 | 9.4 | 0 | 3.18s |
| 25 | 24.8 | 0 | 3.27s |
| 50 | 49.1 | 0 | 3.41s |
| 100 | 99.3 | 0 | 4.13s |
| 150 | 148.8 | 0 | **19.26s** |

**The knee is between 100 and 150.** Flat to 100, then a 4.7× jump in settlement with still zero failures — a queue building rather than the chain rejecting work.

Exploratory only: 60-second windows and one repeat, against the pre-registered 300 seconds and five.

---

## Immediate next step

**Re-run 200 and 300 per second with 4 workers.**

Those two levels are currently unmeasured. The earlier attempts failed because the harness itself ran out of processor capacity (2.0s and 20.4s of scheduling lag against a 250ms threshold), and both auto-invalidated. The multi-process fix is built and tested but has never been run against a real chain.

Open question worth answering: at 200 and 300, how much of the earlier collapse was us and how much was the chain? Best guess is mostly us, but that is exactly the kind of guess worth replacing with data.

Cost: roughly $0.30, about 30 minutes.

```
cd terraform/phase2 && tofu apply -auto-approve
./scripts/bootstrap_cluster.sh --phase phase2
./scripts/deploy_harness.sh --phase phase2
# then deploy_and_fund and run with --workers 4
cd terraform/phase2 && tofu destroy -auto-approve   # ALWAYS
```

---

## Blocked

**Hardware matching (Phase 2 step 3) needs the quota increase.** Requested 8 Aug 05:28: `CPUS_ALL_REGIONS` from 32 to 128. Still granted 32. Seven validators at 8 processors plus a generator needs 60.

Check with:

```
gcloud quotas preferences list --project=project-c4c87dcb-da41-4caf-922
```

**Do not request "Preemptible CPUs".** It reads 0, which means it has never been requested — and in that state spot machines draw on the regular processor quota. Requesting it would lock them into a separate, smaller bucket and make things worse.

---

## Bugs found and fixed so far

Each would have produced wrong data or wasted hours. All fixed and committed.

1. **Proof-of-authority block headers broke settlement detection.** Edge stores validator signatures in `extraData`, exceeding Ethereum's 32-byte limit, so web3 rejected every block and every payment timed out. The run reported **100% failure** — a plausible-sounding result that was purely our client refusing to read blocks. The single strongest argument for why Phase 1 exists.
2. **Solidity 0.8.20+ targets an instruction set Edge v1.3.2 predates.** Deployment is accepted, mined, and reverts having consumed *exactly* the full gas limit. Nothing about it looks like a compiler problem. Fixed with `evm_version="london"`.
3. **The harness was the bottleneck, not the chain**, at 200+ per second. Fixed by splitting across processes.
4. **polygon-edge v1.3.2 flags differ from its documentation** — `--ibft-validator` and `--force` do not exist; genesis must run from a directory the `edge` user can read.
5. **Genesis is written 0660 owned by `edge`**, so distribution returned an empty file without erroring.
6. **`--tunnel-through-iap=false` is invalid syntax.** gcloud rejected every remote command and the swallowed failures read as "not ready yet".
7. **Directory ownership hardcoded to `ubuntu`** while gcloud logs in as the local username.
8. **macOS bash 3.2 lacks `mapfile`.**
9. **Global processor cap is separate from the per-region one.** Checking only the regional quota let a deployment start that could never finish.

---

## Two open questions for the paper

**Gas per transfer: 35,865 or ~51,000?** Ours assumes the recipient already holds the token. A first-time recipient costs roughly 40% more, because writing a balance from zero is far more expensive than updating one. Which belongs in the cost analysis depends on whether corridors are modelled as repeat transfers to family or one-off sends. Both are defensible; the choice moves the headline cost figure materially.

**Two pre-registered criteria disagree at 150 per second.** It passes the primary metric (99.2% delivered, 0% failures) but fails the architecture-selection latency ceiling (19.26s against 10s). Both were locked before any data existed. Report the tension rather than resolving it quietly — "moves 150/sec but does not settle acceptably at that rate" is a better finding than a single number.
