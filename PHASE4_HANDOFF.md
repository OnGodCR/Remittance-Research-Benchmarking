# Phase 4 (NEAR) — Handoff, 11 August 2026

**Written at an agent switch. Read this before touching anything in Phase 4.**

This document is deliberately blunt about what is broken and what was gotten wrong. Its
purpose is that you do not rediscover four bugs the hard way.

**Read order:** this file → `RESUME_HERE.md` → `METHODOLOGY_LOG.md` → `ANALYSIS_PLAN.md`.
For paper-writing context, `HANDOFF.md`. For NEAR-specific formulas, `docs/near_methodology/`.

---

## 1. The one-line status

> **Updated 12 Aug 2026, 01:00 UTC.** The four bugs below are all fixed and the race fix is
> **verified working against the live chain** — 382 of 400 payments confirmed, against 0 on
> every previous attempt. Collection is automated and gated; it starts by itself once the
> validator set is whole. Read §2 for the current state; §3's bug histories are kept because
> the failure modes are instructive, not because they are open.

**Phase 4 has produced 0 of 140 valid runs so far**, but the instrument now works and the
cluster is self-healing. What blocks collection is validator churn, not code: two validators
were expelled by the protocol after spot preemptions and are being re-admitted.

Phases 1–3 are complete and unaffected.

---

## 2. What is running right now

| | |
|---|---|
| Instances | **9 RUNNING** — `near-validator-0..7` + `near-generator`, project `project-c4c87dcb-da41-4caf-922` |
| Regions | us-east4-c (v0, v1, generator), asia-south1-a (v2, v3), asia-southeast1-a (v4, v5), europe-west2-b (v6, v7) |
| Chain | nearcore **2.13.3**, protocol **86**, **4 shards**, healthy |
| Validator set | ⚠️ **7 of 8** — `node0` expelled, re-admitted at block 36002; `node1` expelled next epoch, re-admitted ~39602. Shard 3 has one producer until then. |
| RPC endpoint | `http://10.40.0.10:3030` — **validator-0**, reachable only from inside the VPC and from the operator IP |
| Machine type | `n2-standard-8` everywhere (8 vCPU / 32 GB), 100 GB pd-balanced |
| Provisioning | **STANDARD (on-demand) on all nine** as of 12 Aug — see §2.1 |
| Cost | **~$3.50/hr**, ~$80 of the $300 credit spent — verify, do not quote from here |
| Sweep | **not running; starts automatically** when the validator set is whole |
| Idle watchers | **disabled on every node** (they were killing the cluster) — keep it that way |
| Shutdown | **dead-man's switch armed on all nine**, six hours out, renewed by the operator every 30 min — see §2.2 |

### 2.1 Spot was abandoned — preemption causes EXPULSION, not a restart

**This is the most important operational finding of the phase.** A reclaimed validator does
not cost a restart. It misses scheduled blocks and chunks, its epoch score falls below the
**90%** kickout threshold, and the protocol **expels** it. Re-admission needs a fresh
`StakeAction` and takes effect two epochs later — **four hours** at `epoch_length` 3600 and
2s blocks. The harness health check refuses to run below 8 validators, so **one preemption
costs four hours of collection**.

Observed: `node0` reclaimed 11:31 UTC 11 Aug, scored 19%, expelled. `node1` reclaimed 00:04
UTC 12 Aug, back to 100% production within minutes, still expelled on a 63% score.

All nine were converted in place — stop, `set-scheduling`, start. **The flag that makes this
work is `--clear-instance-termination-action`**; without it GCP rejects SPOT→STANDARD, which
is why an earlier attempt concluded it was impossible. Disks, chain state, validator keys and
the static internal IP all survive; genesis was verified byte-identical by SHA-256.

### 2.2 Shutdown protection — a renewed dead-man's switch, not a fixed timer

Every machine halts itself at an absolute epoch timestamp in `/etc/hardcap_deadline`,
checked by `/etc/cron.d/hardcap` every 5 minutes. This survives reboots, unlike the old `at`
job (`at` is not installed on these images) and unlike `shutdown -h +N`, which re-arms from
each boot and so is silently extended by a reboot.

**The window is six hours and is renewed by the operator every 30 minutes**
(`scripts/near_cluster_control.sh renew`). If the operator side stops renewing, the whole
cluster halts within six hours rather than billing for days. Halting is cheap and safe:
disks, chain state and the database persist, and the sweep is resumable.

The terraform guard's `shutdown -h +2040` is cancelled on each machine so there is exactly
one deadline in one place.

**If you are redeploying, put the deadline file in the OpenTofu startup script** so every
node is armed at boot.

### 2.3 What now runs by itself

| Component | Where | Does what |
|---|---|---|
| `scripts/near_liveness_watch.py` | generator, systemd `near-liveness` | samples the chain every 10s; records validator count, per-shard producer counts, peers, sync state |
| `scripts/near_supervisor.py` | generator, cron every 5 min | gates the sweep on a whole validator set, restarts a dead sweep, **re-stakes expelled validators automatically**, writes `supervisor_status.json` |
| `scripts/run_near_sweep_inner.sh` | generator | the 140-run matrix, foreground, resumable; the supervisor owns detaching and the PID file |
| `analysis/apply_validator_liveness.py` | operator | invalidates any run overlapping a degraded sample, **and any run whose window is not densely covered** |
| `scripts/near_cluster_control.sh` | operator | `status` / `renew` / `stop` |

`supervisor_status.json` on the generator is the single place to read what is happening.
**The generator has no service account**, so it cannot call the Compute API — cluster-wide
shutdown must come from the operator side.

### 2.2 `gcloud` misbehaves in this environment — read before scripting against it

Three behaviours cost about forty minutes and produced a string of misleading "FAILED"
results against machines that were actually fine:

1. **Any `for` loop wrapping `gcloud compute scp` / `ssh` silently fails.** Not an error —
   the command simply does not take effect on the remote host. Redirecting stdin
   (`< /dev/null`) does not help. **Write the calls out individually.**
2. **Multi-file `scp` transfers only one file.** `gcloud compute scp a b c host:/tmp/`
   silently delivers a subset. **Copy one file per invocation.**
3. **Remote stdout arrives on stderr.** A command ending in `2>/dev/null` therefore prints
   nothing and looks like a failure. Use `2>&1` and filter out the `Warning:` lines.

A corollary, and the reason this matters beyond convenience: **several nodes reported
"FAILED" when the install had genuinely not run, and others reported nothing when it had
succeeded.** Always verify the end state on the host itself (`cat /etc/hardcap_deadline`)
rather than trusting the exit status or captured output of the loop that supposedly did it.

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

### Step 2 — finish arming the hard cap (do not skip)

Seven of nine machines have **no automatic shutdown of any kind** — the idle watchers are
deliberately disabled *and* they have no lifetime cap. See §2.1 for the mechanism and §2.2
for why looping over `gcloud` to install it will appear to work and will not.

If redeploying, move this into the OpenTofu startup script instead of retrofitting it.

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
- **Do not loop over `gcloud`, do not multi-file `scp`, do not discard stderr.** See §2.2 —
  all three fail silently and produce confident, wrong status output.
- **`at` is not installed on these images.** The lifetime cap uses a deadline file plus
  cron so it survives reboots and preemption restarts (§2.1).
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
