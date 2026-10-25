# Blockchain Remittance Scaling Architecture Benchmarking

Measuring how three blockchain scaling architectures perform as remittance rails — throughput, settlement time, and cost — under realistic load.

| | |
|---|---|
| **Sidechain** | Polygon Edge v1.3.2 |
| **Off-chain** | LND (Lightning) on `regtest` |
| **Sharding** | NEAR |

Everything runs on private networks we control, using the real production software each network runs. Public test networks were tried first and rejected: they are shared with strangers, so a slow result there might mean the architecture is slow or might mean somebody else was busy, and there is no way to tell which.

---

## Documents

Read in this order.

| File | What it is |
|---|---|
| [COMPARISON.md](COMPARISON.md) | **Start here.** The cross-architecture evidence table, with where every number comes from |
| [METHODOLOGY_LOG.md](METHODOLOGY_LOG.md) | Every decision and exact parameter, with dates |
| [ANALYSIS_PLAN.md](ANALYSIS_PLAN.md) | The locked pre-registered analysis plan; §13 is the amendment log |
| [DECISIONS.md](DECISIONS.md) | Every technical decision, with the alternatives that were rejected |
| [POLYGON_ANALYSIS.md](POLYGON_ANALYSIS.md), [NEAR_ANALYSIS.md](NEAR_ANALYSIS.md), [LIGHTNING_ANALYSIS.md](LIGHTNING_ANALYSIS.md) | Results for each network |
| [docs/near_methodology/](docs/near_methodology/) | The detailed defence of specific NEAR findings, one file per topic |
| [claude.md](claude.md) | Original scope, written before any work began |

Older documents mention six working notes deleted on 25 Oct 2026 (`RESUME_HERE.md`, `PHASE1.md`, `PHASE4_HANDOFF.md`, `docs/spend_ledger.md`, `docs/near_methodology/finishing_runbook.md`, `docs/near_methodology/README.md`). Git keeps them: `git log --all -- <file>` finds the last version.

---

## Where the study stands

**Data collection closed 24 Aug 2026**, by Angad's decision. Both clusters were destroyed after every byte of data was pulled into this repository.

**Spend: about $124 of a $300 budget**, estimated from machine-hours (Google gives no exact figure without a billing export). The rest of the credit expires 6 Nov 2026.

**Nothing is billing in the NEAR project** (`project-c4c87dcb-da41-4caf-922`). Its nine 13 Aug disk snapshots were deleted on 25 Oct 2026, after the one unique file on them, the validator health log, was copied out (`data/near_supplementary/rescued_generator_13aug/`). The private chains themselves are gone; the per-payment records and the health log remain. The Polygon project (`remittances-benchmarking`) still needs a check in the console under the account that owns it: [docs/snapshot_retirement.md](docs/snapshot_retirement.md) step 6.

**Left open at closure** (`ANALYSIS_PLAN.md` §13, amendment 17):

| Question | Status |
|---|---|
| Does NEAR's collapse at 200/sec belong to NEAR or to our program that watches each payment? | **Open.** The 47.5/sec, 76.3%-failed result is always quoted with that condition. The 150/sec result is unaffected. |
| Does a faster block timer change NEAR's waiting-time verdict? (2 s blocks: median 12.20 s; 1.2 s: 7.18 s) | **Preliminary only.** One or two tests survived, below the five-repeat minimum. |
| Does the original token contract behave like the rebuilt one? | Not run. The original is committed in `data/reference/contracts/`. |
| Polygon's limit on full-size machines | Not run. The corrected limit (320–340/sec) is a floor argued from smaller machines. |

---

## Running Phase 1

Phase 1 proves the machinery records reality accurately. **It produces no data for the paper** — its runs are automatically excluded from all results.

### Before you start

```bash
brew install opentofu jq
python3.12 -m venv .venv && .venv/bin/pip install web3 py-solc-x pandas pyarrow
gcloud auth login && gcloud auth application-default login
```

### 1. Bring up the cluster

```bash
cd terraform/phase1
cp terraform.tfvars.example terraform.tfvars   # fill in project ID and your IP
tofu init && tofu apply
```

Roughly **$0.60–0.80 per hour** while running. Zero when destroyed.

### 2. Start the blockchain

```bash
./scripts/bootstrap_cluster.sh
```

Collects each validator's identity, writes the shared startup file, starts every node, and confirms blocks are actually being produced. A cluster that starts but never reaches agreement looks fine from the outside — only a rising block number proves it works.

### 3. Deploy the test dollar and prepare wallets

```bash
.venv/bin/python -m scripts.deploy_and_fund \
  --rpc-url <from bootstrap output> --chain-id 100100 \
  --funder-key $(sed -n 1p keys/funder.txt) --senders 46
```

### 4. Run the validation test

```bash
.venv/bin/python -m harness.cli run \
  --config config/phase1.json --tps 5 --window 300 --amount 200
```

Deliberately slow. The goal is confirming the pipeline records reality, not producing a number.

### 5. Export the data

```bash
.venv/bin/python -m analysis.export
```

### 6. Shut it down

```bash
cd terraform/phase1 && tofu destroy
```

**Do not skip this.** The automatic timers stop the machines but do not delete their disks, which keep billing.

---

## Cost controls

Google's budget alerts send email. **They do not stop spending**, and a paid account has no hard cap. Three things actually protect the budget:

1. **A hard shutdown timer** armed at boot on every machine, using the kernel's own scheduler — fires even if every other script crashes
2. **An idle watcher** that shuts down after 30 minutes with no benchmark running
3. **`tofu destroy`**, which is the only thing that removes the disks

The realistic way to waste money here is not an expensive experiment — it is a debugging session that ends at 2am with the cluster still up. A 7-node cluster is about $1.15/hour, so a forgotten weekend is roughly $80 against a $300–450 total budget.

---

## Checking the harness before trusting a result

```bash
.venv/bin/python -m harness.cli capacity
```

Runs the full load ramp against a backend that does nothing. Any ceiling that appears is **ours**, not a blockchain's.

This matters more than it sounds. If throughput flattens at 200 payments per second, that might be the blockchain hitting its limit — or our own program unable to send faster. Identical-looking result, opposite meaning: one is a finding, the other is a bug we published.

Measured 7 Aug 2026 on an 8-core laptop: **sustained 300/second at 1.1ms scheduling lag**, with ~600 settlements tracked concurrently. No planned load level comes close to the harness's limit.

---

## Data

| File | Contents |
|---|---|
| `data/raw/all_runs_raw.parquet` | Every payment from every run. Nothing removed. |
| `data/clean/all_runs_clean.parquet` | The dataset results are built from. |
| `data/clean/exclusions.log` | Every exclusion, with the rule that caused it. |
| `data/web/results.json` | Small per-test summary for the RemitBridge website, built by `analysis/build_web_summary.py`, which refuses to write it unless the published figures reproduce. |

Per-payment records, never pre-computed summaries — a question thought of later can be answered by querying rather than re-running, which matters because cloud time is the scarcest resource here.

**Nothing is ever deleted.** Excluded runs stay in the raw file, flagged, so the two files can be compared and verified against each other.

---

## Layout

```
harness/          measurement program — identical across all three architectures
  core/           arrival timing, concurrent sending, storage
  adapters/       per-architecture send/confirm logic
analysis/         cleaning and export
contracts/        the test dollar
scripts/          cluster bootstrap, token deployment, wallet funding
terraform/        infrastructure, including the shutdown guards
```

The measurement core is shared deliberately. Everything that produces a number — timing, arrival pattern, concurrency, storage — is byte-identical for all three architectures, so the cross-architecture comparison is genuinely like-for-like. That is why Hyperledger Caliper was dropped: it only supports one of the three, and using it there would have put two different measuring instruments inside a three-way comparison.

---

## Cloud traps

Mistakes from running the machines, each of which cost real time or money. Comments in `scripts/` and `terraform/` refer to them by number.

0. **A resumed sweep restarts from the bottom of the load ladder**, not where it stopped. After two preemptions this silently produced 22 duplicate runs with identical random seeds. `analysis/export.py` now drops re-executions; check repeat counts after any resumed sweep.
1. **A spot machine being reclaimed wipes the sending program's Python environment and database.** The chain survives. Spot was still the right call: rebuilding costs ~15 minutes, while on-demand machines cost 4.5 times as much.
2. **Startup scripts re-run on every boot**, not just creation. This reset folder ownership and made validator key setup fail on reboot. Every setup script now checks whether its work is already done.
3. **The hard shutdown timer re-arms from each boot**, so a reboot silently extends the deadline.
4. **SSH is allowed only from one home IP address**, set in the `terraform.tfvars` files. It changes every few weeks; if SSH hangs, compare `curl -s https://ifconfig.me` with the file.
5. **Never nest quotes through `gcloud compute ssh --command`.** Three shell layers mangle them silently. Copy a script over and run it.
6. **Starting a background job through SSH holds the session open forever.** Use `setsid nohup ... < /dev/null &` inside a script on the remote machine.
7. **macOS `pgrep` has no `-c` flag**; the usage error looks like "zero processes". Use `pgrep -f X | wc -l`.
8. **`pkill -f <pattern>` can match your own SSH command** and kill the connection.
9. **Copying a live SQLite database needs `VACUUM INTO`**; a plain copy comes out corrupted.
10. **Data files exceed GitHub's 100 MB limit** and live in large-file storage (Git LFS): 10 GB storage and 10 GB/month download included on Free and Pro.
11. **Long commands hit a 10-minute timeout.** Run them detached and check back.
12. **Quota increases: roughly 50% steps were approved, doubling was denied.** The limit ended at 96 processors.
13. **`claude.md` is lowercase**, and the Mac's filesystem ignores case, so edits to `CLAUDE.md` land in the same file.
14. **Zero-padded hours crash bash arithmetic** (`08` reads as invalid octal); use `10#` everywhere.
15. **Never attach a copy of a boot disk to a machine while it boots.** The duplicate disk label threw the next boot into emergency mode (25 minutes lost on 24 Aug).
16. **`/opt/benchmark` on the machines is owned by root**, so the sending program runs under sudo.
