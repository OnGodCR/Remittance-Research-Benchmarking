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
| [PHASE1.md](PHASE1.md) | **Start here.** Plain-language walkthrough of the first phase |
| [claude.md](claude.md) | Full scope — what is being done |
| [DECISIONS.md](DECISIONS.md) | Every technical decision, with the alternatives that were rejected |
| [ANALYSIS_PLAN.md](ANALYSIS_PLAN.md) | The locked pre-registered analysis plan |
| [HANDOFF.md](HANDOFF.md) | Everything needed to write the paper, self-contained |

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
