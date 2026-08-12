# Finishing Phase 4: the exact sequence, and the two traps in it

**Written:** 12 August 2026, with the matrix at 25/140 and ~13 hours left to run.
**Why it exists:** the steps after the matrix completes have ordering
dependencies that are not obvious, and at least one way to quietly destroy the
adversarial arm. Writing it down while there is time beats improvising it at
04:38 UTC.

---

## Trap 1 — the health audit must run DURING collection, not only after it

`analysis/apply_validator_liveness.py` invalidates any run measured while the
validator set was not whole. Run only at the end, the sequence goes:

> matrix reports 140/140 → audit invalidates some → the matrix is **no longer**
> 140/140 → the cluster has to stay up (or come back up) to refill the holes.

Run it **during** collection and the repair is free: the sweep's skip check
requires `invalidated = 0 AND ended_wall IS NOT NULL`, so an invalidated
configuration is automatically re-queued and re-measured while the cluster is
already running and already being paid for.

**Therefore: run it at every check-in.** It is idempotent, it only ever marks
rows invalid, and it writes nothing when there is nothing to mark.

```bash
cd /opt/benchmark && ./.venv/bin/python analysis/apply_validator_liveness.py \
  --db data/working/runs.sqlite \
  --liveness data/working/validator_liveness.jsonl \
  --phase phase-4-full-stack
```

Status at time of writing: **25 kept, 0 newly invalidated.** Every banked run is
provably healthy.

---

## Trap 2 — the supervisor will kill the adversarial arm's background traffic

`scripts/near_supervisor.py` runs from cron every 5 minutes. Once the matrix is
complete it takes this branch:

```python
if prog["complete"] >= MATRIX_TOTAL:
    state, action = "complete", "matrix finished; sweep stopped"
    if pid:  stop_sweep()
    if npid: stop_noise()      # <-- this one
```

`prog` is computed for `phase-4-full-stack` only. The adversarial arm runs under
`phase-4-adversarial`, so the supervisor keeps seeing "complete" and keeps
calling `stop_noise()` **every five minutes** — including on background traffic
started for the adversarial arm.

Losing it would not be loud. The arm would still produce 15 runs; they would
simply have been measured on a quieter chain than the baseline they are compared
against, and the whole point of the arm is that the *only* difference from the
baseline is validator outages.

**Two ways to avoid it, in order of preference:**

1. **Disable the supervisor cron before starting the arm** (below). Nothing else
   depends on it once the matrix is done — re-staking is only needed to keep the
   set whole for measurement, and the arm deliberately breaks the set anyway.
2. Start the arm's traffic *without* writing the noise pidfile, so `noise_pid()`
   returns None. Works, but relies on a side effect and leaves an unsupervised
   process with no recorded PID. Prefer option 1.

```bash
# option 1
sudo rm -f /etc/cron.d/near-supervisor
sudo systemctl restart cron
```

---

## The sequence

**Step 0 — confirm the matrix is genuinely done.** Not just 140 rows: 140
distinct configurations, none invalidated, each with an end timestamp. The
supervisor's own count already does this, so read it rather than counting by
hand.

```bash
bash scripts/near_cluster_control.sh status     # expect "state": "complete"
```

**Step 1 — final health audit**, per Trap 1. If it invalidates anything, the
matrix is not finished: leave the supervisor running, let the sweep refill the
holes, and come back to step 0.

**Step 2 — disable the supervisor cron**, per Trap 2.

**Step 3 — start background traffic for the arm.** The arm must meet the same
congestion the baseline did, or the comparison measures two changes at once.

**Step 4 — start the outage injector.** It runs **from the local machine**, not
the generator: it drives `gcloud compute ssh` against each validator.

```bash
./scripts/near_adversarial_nodes.sh --duration 5400 --events /tmp/near_events.tsv
```

It refuses to start unless the validator set is whole *and* enough of the
expulsion window remains (`adversarial_arm.md` §4). Both are checked, not
assumed. With 2-hour epochs the window check always passes; the whole-set check
is the one that matters.

**Step 5 — run the 15 adversarial runs** under `--phase phase-4-adversarial`,
3 loads × $200 × 5 repeats.

**Step 6 — import the outage events into the database.** Not optional, and the
single most forgettable step here.

```bash
cd /opt/benchmark && ./.venv/bin/python scripts/near_import_events.py \
  --events /tmp/near_events.tsv --phase phase-4-adversarial
```

`analysis/export.py` keys two exclusion rules on `node_events`. An empty table
means those rules **silently never fire** and the adversarial runs stop being
distinguishable from clean ones. This exact failure already happened once, in
phase 2, and had to be corrected afterwards by `analysis/backfill.py`.

**Step 7 — merge, export, verify.** Copy the cluster database down with
`VACUUM INTO` (never copy a live SQLite file), merge into the master, regenerate
both parquet files, and re-run the Polygon verification to prove nothing moved.

**Step 8 — stop the cluster and report the cost.**

```bash
bash scripts/near_cluster_control.sh stop
```

---

## What must be true before step 8, because it cannot be undone

Once the machines stop, **nothing can be re-measured** — the chain state and the
funded sender accounts go with them. Confirm all of these first:

- [ ] 140 distinct baseline configurations, none invalidated
- [ ] the health audit reports 0 newly invalidated on a final pass
- [ ] 15 adversarial runs recorded under `phase-4-adversarial`
- [ ] `node_events` contains the outage rows, attributed to runs
- [ ] the database has been copied off the generator and merged
- [ ] both parquet files regenerate, and the seven published Polygon load steps
      still reproduce exactly

The last one is the tripwire. If a Polygon figure moves after merging NEAR data,
something is wrong with the merge, not with Polygon.
