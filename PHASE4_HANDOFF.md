# Phase 4 (NEAR) — Handoff, 11 August 2026

**Written at an agent switch. Read this before touching anything in Phase 4.**

This document is deliberately blunt about what is broken and what was gotten wrong. Its
purpose is that you do not rediscover four bugs the hard way.

**Read order:** this file → `RESUME_HERE.md` → `METHODOLOGY_LOG.md` → `ANALYSIS_PLAN.md`.
For paper-writing context, `HANDOFF.md`. For NEAR-specific formulas, `docs/near_methodology/`.

---

## 1. The one-line status

**Phase 4 has produced ZERO valid runs. A 9-instance cluster has been billing since
10 August. Every full-rate test has failed 100%.** The cause is now identified and a fix
is written but **untested**.

Phases 1–3 are complete and unaffected. Nothing in this document threatens the Polygon or
Lightning results.

---

## 2. What is running right now

| | |
|---|---|
| Instances | **9 RUNNING** — `near-validator-0..7` + `near-generator`, project `project-c4c87dcb-da41-4caf-922` |
| Regions | us-east4-c (v0, v1, generator), asia-south1-a (v2, v3), asia-southeast1-a (v4, v5), europe-west2-b (v6, v7) |
| Chain | nearcore **2.13.3**, protocol **86**, 8 validators, **4 shards**, healthy, block height ~27,500 |
| RPC endpoint | `http://10.40.0.10:3030` — this is **validator-0**, reachable only from inside the VPC and from the operator IP |
| Machine type | `n2-standard-8` everywhere (8 vCPU / 32 GB), 100 GB pd-balanced |
| Provisioning | validators **SPOT**, generator **STANDARD** (on-demand) |
| Spend | **roughly $75–85 of the $300 credit** — verify, do not quote this from here |
| Sweep | **NOT running** |
| Idle watchers | **disabled on every node** (they were killing the cluster) |
| Hard cap | **`atq` on the generator is EMPTY — the cap is GONE.** The generator rebooted at 04:08 on 11 Aug and the `at` job did not survive. **Re-arm it or the cluster runs until the credit is gone.** |

### Two validators were preempted today
`near-validator-0` at 11:31 UTC, and `near-validator-1` shortly after. Both were restarted
manually. **Validator-0 being spot is a standing risk: it is both the boot node and the
only RPC endpoint, so losing it stops everything.**

I tried to convert it to on-demand and **could not**. GCP rejects `setScheduling`
SPOT→STANDARD on an existing instance because it will not clear the stored
`instanceTerminationAction`, both via `gcloud` and via the raw API:

```
Invalid value for field 'resource.instanceTerminationAction':
'INSTANCE_TERMINATION_ACTION_UNSPECIFIED'. You cannot specify a termination action for a
VM instance that has the standard provisioning model.
```

The only route is **recreating the instance** via OpenTofu with `use_spot = false`, which
loses that node's chain data (it would re-sync from peers). Angad has given **explicit
standing permission to move to on-demand if necessary** — but this costs ~$0.27/hr per
machine, so it is a spend decision and should be confirmed.

---

## 3. The bugs — four of them, each hiding the next

This is the important section.

### Bug 1 — 64 sender keys did not match the chain ✅ FIXED

The 900-account bootstrap reused account names (`aase000.node0` …) that **already existed**
from the earlier 64-account pool. `CreateAccount` failed for those, but the bootstrap
**wrote the newly generated keys to the keys file anyway**. Result: 64 accounts whose
private keys did not correspond to any on-chain access key.

Symptom: `ValueError: access key ed25519:… does not exist while viewing`.

Fixed by dropping those 64. **The active keys file now has 836 verified senders**, all
funded, all registered with the token contract, spread **209 / 209 / 209 / 209** across the
four shards.

- Active: `/opt/benchmark/keys/near_senders.json` (836)
- Backup of the broken 900: `…/near_senders.json.bak-900`

**`scripts/near_bootstrap.py` is still unfixed** — it will do this again. It must verify
that each created account's on-chain public key matches the key it is about to write, and
fail loudly on mismatch. There is an uncommitted local edit to this file; review it.

### Bug 2 — `py-near`'s `nowait=True` does not mean "do not wait" ✅ FIXED

In **py-near 1.2.22**, `Account.sign_and_submit_tx` contains:

```python
included = included or nowait   # docstring: "nowait: LEGACY, now same as included"
```

and then calls `send_tx_included`, which **blocks server-side until block inclusion**
(~2s). The node's own RPC ceiling is 10s, so concurrent submissions queue behind each
other until they exceed it. A 20-way concurrent probe produced **1 success and 19
`TIMEOUT_ERROR`s**.

Fixed in `harness/adapters/near.py::_send_one` by signing locally and calling
`provider.send_tx` (which is `broadcast_tx_async` — returns the hash immediately, never
waits for execution). Nonce is primed once per account in `setup()` and incremented
locally; the per-sender lock keeps that counter correct.

**Verified working in isolation** — `send_tx` returns a hash in **0.00s**.

### Bug 3 — the future/`_hashes` race ⚠️ FIX WRITTEN, NEVER TESTED

**This is the one that caused the 100% failure rate, and it is the reason every error read
`never broadcast within 60s` with no exception attached.**

`submit()` created a future in `self._hashes[ref]`, then `asyncio.create_task(send())`.
But `create_task` **does not run the coroutine until the caller next awaits**, and the
harness calls `await_confirmation()` almost immediately — which does
`self._hashes.pop(tx_ref)`. So the pop routinely happened **first**. `_send_one` then did
`self._hashes.get(ref)`, got `None`, **broadcast the payment successfully, and discarded
the hash**.

**The transactions were settling on chain the entire time.** The harness simply had nothing
left to record them against. Every "failure" in the Phase 4 data so far is a measurement
artifact, not a chain result.

The fix holds the future as a **local variable** and passes it into `_send_one` by
reference rather than re-reading it from the dict. See the comment block at
`harness/adapters/near.py:316`.

**Status: uncommitted, syntax-checked only, NOT deployed to the generator, NOT tested.**

### Bug 4 — my own status checks were lying ✅ understand this before trusting any monitor

`pgrep -f near_bootstrap` run over SSH **matches the SSH command string itself**, because
that string contains the pattern. It reported "bootstrap RUNNING / sweep RUNNING" for
processes that **did not exist**, and I reported healthy progress to Angad on that basis.

**Never check liveness with `pgrep -f` over SSH.** Use the database as the source of truth:
a run is real only if it has a row in `runs` with `ended_wall IS NOT NULL` and
`invalidated = 0`.

Related: **Python buffers stdout when it is not a terminal**, so the detached bootstrap and
sweep logs read as empty while the processes ran fine. Use `python -u`.

---

## 4. What the data actually looks like

Database: `/opt/benchmark/data/working/runs.sqlite` on the generator.

| phase | runs | state |
|---|---|---|
| `phase-4-smoke` | 1 | fine, but a smoke test |
| `phase-4-full-stack` | 10 | **all invalidated** — 3 same-shard pairing, 3 generator-saturated, 4 superseded |
| `phase-4-lagtest` | 5 | diagnostics, 100% failure, not results |

**Valid `phase-4-full-stack` runs: 0 of 140.**

The 4 "superseded" runs were valid measurements collected with the **64-account** pool. I
invalidated them deliberately rather than mixing two sender-pool sizes inside one results
table — Angad's standing instruction is *"i want everything in paper to be standardized /
i dont want them to be able to point out things i switched halfway through."* Nothing was
deleted; the reason string is recorded in `invalidation_reason`.

**Why 836 senders and not 64.** NEAR orders transactions **per access key by nonce**, so a
single account cannot have two transactions in flight. The sender count *is* the
concurrency ceiling: at ~2s to inclusion, the ceiling is about **N/2 per second**. 64
senders capped throughput near 32/sec against a matrix whose top step is **300/sec**. 836
senders gives ~418/sec. This is a property of NEAR, not of our harness, and **it belongs in
the Methodology** — it is the sharding equivalent of Polygon's nonce-pool problem.

---

## 5. Next steps, in order

### Step 1 — deploy and test the Bug 3 fix (~15 minutes, do this first)

```bash
gcloud compute scp harness/adapters/near.py near-generator:/tmp/near_adapter.py --zone us-east4-c --project project-c4c87dcb-da41-4caf-922
```

Then on the generator: `sudo cp /tmp/near_adapter.py /opt/benchmark/harness/adapters/near.py`
and run a single verification run:

```bash
cd /opt/benchmark && ./.venv/bin/python -m harness.cli run --config config/phase4.json --tps 100 --window 60 --amount 200 --repeat 0 --phase phase-4-lagtest --arm baseline
```

**Success looks like:** `ok=` climbing well above zero, achieved TPS near 100, and lag
`growth` small. **Failure looks like:** `ok=0` again, or a new error string in the
`transactions.error` column.

**If it fails again, stop and escalate to Angad rather than iterating on a billing
cluster.** He said explicitly he does not want budget spent on a benchmark that has not
recorded a single valid transaction.

### Step 2 — re-arm the hard cap (do not skip)

`atq` is empty. The cluster currently has **no automatic shutdown of any kind** — the idle
watchers are deliberately disabled *and* the lifetime cap is gone.

### Step 3 — launch the sweep

```bash
bash scripts/run_near_sweep.sh phase-4-full-stack
```

It is resumable and skips configurations that already have a finished, non-invalidated
run, so it will correctly redo the whole matrix. 140 runs × 300s + ~20s gaps ≈ **13 hours**.

### Step 4 — the adversarial arm

3 loads × $200 × 5 repeats = 15 runs. `scripts/run_adversarial_arm.sh`. **Note the
asymmetry that must be stated in the paper:** with only 2 validators per shard, killing one
node drops a shard to a single validator, so NEAR's adversarial arm is **harsher** than
Polygon's, where 3 of 4 survived. That is a quota artifact, not a property of sharding.

### Step 5 — still outstanding

- **NEAR mainnet gas price + token price**, pulled on one stated date, for
  `docs/near_methodology/cost_per_transaction.md`
- **Polygon calibration ratios** — observed mainnet *peak* throughput
- **Re-check Zilliqa x-shards** (claude.md §4 says to do this at Phase 4)
- **Fix `scripts/near_bootstrap.py`** so Bug 1 cannot recur
- Phase 5 (calibration + CIs), Phase 6 (cross-architecture comparison)

---

## 6. Traps specific to this cluster

- **Do not trust `pgrep -f` over SSH.** See Bug 4. Query the database.
- **Use `python -u`** for anything detached, or the logs will be empty.
- **`/opt/benchmark/keys/` is root-owned.** Write to `/tmp` and `sudo cp`.
- **The phase-1 idle watcher polls `eth_blockNumber`**, which does not exist on NEAR. It
  reads zero forever and shuts nodes down. It killed 6 of 8 validators within an hour of
  boot and the Lightning cluster five times. It is disabled — keep it that way.
- **`mapfile` is not available** in macOS bash 3.2 (local scripts).
- **P2P must not bind `[::1]`** — this broke the chain twice.
- **`epoch_length` is 3600**, raised from 60; short epochs caused constant validator churn.
- **Block delay is 2s**, raised from 600ms after `ShardStuck` errors.
- The **cross-shard mix must stay ~75%** ((S−1)/S at S=4). If it drifts, the arm is
  measuring a chain that is not dividing work, and the run is worthless — this failure is
  silent and looks healthy, so check it explicitly.

---

## 7. What I would tell Angad

The cluster has been up for about a day and has produced no usable data, because of a race
condition in code I wrote. The chain, the 964 accounts, the shard split and the token
contract are all verified healthy — the blockchain side of Phase 4 works. What failed was
the measurement harness, in a way that made a working chain look like a totally broken one.

The fix is small and the failing mechanism is now understood rather than guessed at. But it
is untested, and the honest position is that Phase 4 should be given **one clean attempt**
and then reassessed against the remaining credit rather than debugged indefinitely at
roughly $1.50/hr.
