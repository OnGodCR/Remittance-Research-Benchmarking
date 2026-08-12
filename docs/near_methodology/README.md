# NEAR methodology notes

Reference material for writing up the NEAR (sharding) arm. Each file states what is measured, what is derived, and which limitations must appear in the paper.

| File | Covers |
|---|---|
| [`shard_scaling.md`](shard_scaling.md) | How a 4-shard measurement answers a 10-shard question. The $c(S)$ formula and why a naive average cannot be scaled. |
| [`cost_per_transaction.md`](cost_per_transaction.md) | Gas summed across receipts, priced with mainnet rates. RQ3. |
| [`settlement_definition.md`](settlement_definition.md) | Why settlement means `FINAL` and what accepting `EXECUTED_OPTIMISTIC` would have done to the comparison. |

---

## The three numbers this arm exists to produce

1. **Throughput** — per-shard, and scaled to mainnet shard count.
2. **Cost per transaction** — flat with amount if NEAR behaves like Polygon; the pre-registered expectation.
3. **Same-shard versus cross-shard overhead** — the property unique to sharding, and the reason the other two need a shard-count correction.

---

## Constraints that shaped the deployment

**8 validators, 4 shards — set by quota, not preference.** NEAR needs ≥2 validators per shard. Matching mainnet's **10 shards** (measured 12 Aug 2026) needs 20 validators, which at NEAR's published 8 vCPU minimum is 160 vCPU against a project ceiling of 96. Requests for 144, 120 and 136 were each denied. 4 shards with 2 validators each is what fits.

**No margin on validators per shard.** With exactly 2 per shard, losing one node drops a shard to a single validator. **NEAR's adversarial arm is therefore harsher than Polygon's**, where losing one of four validators still left three. Say so when comparing them — a worse NEAR result under node failure is partly a consequence of the quota, not purely a property of sharding.

**Hardware matched to spec, deliberately.** `n2-standard-8` (8 vCPU / 32 GB), the same instance used for Polygon's validators. Running 16 validators at 4 vCPU would have fitted 8 shards inside the quota, but it would have put a hardware confound directly inside the cross-architecture comparison this project exists to make.

---

## What must be stated in the paper

1. **Results describe one sharding implementation**, NEAR's Nightshade — not sharding as a general architectural concept.
2. **4 shards measured, 10 on mainnet** (measured 12 Aug 2026, protocol 86, layout V3). The scaling method and its assumption are in `shard_scaling.md`; the bias is conservative. Mainnet also runs **422 validators, 10 per shard**, against our 2 — the protocol minimum.
3. **2 validators per shard is the protocol minimum**, so the adversarial arm is harsher than Polygon's equivalent.
4. **Cost is priced with mainnet gas and token prices** pulled on one stated date, not with our own chain's gas price, which we set ourselves.
5. **Settlement means `FINAL`.** See `settlement_definition.md` — accepting the optimistic status would have understated latency and flattered NEAR against Polygon.

---

## The adversarial arm — why NEAR's is not Polygon's, 12 August 2026

**Design:** identical fault schedule to phase 2 — one validator offline at a
time, 15–45s down, 20–60s between, continuous across all 15 runs (3 loads ×
$200 × 5 repeats). The difference between the arms must be the architecture, not
the fault pattern.

**The complication, and the property that resolves it.** On Polygon Edge a
restarted validator rejoins consensus immediately, so every run met the same
4-validator network. On NEAR a validator that misses its scheduled blocks falls
below the **90% kickout threshold** and is **expelled for two further epochs** —
four hours here. Outages therefore do not merely perturb the run they occur in;
they permanently shrink the network for everything after, and the arm would
measure a progressively smaller cluster rather than the effect of node failure.

What makes the arm possible is that **expulsion is decided at the end of the
epoch and applied two epochs later**. Starting near an epoch boundary buys at
least two hours, and up to four, in which the validator set stays nominally
whole however badly a node behaves. The arm takes about 80 minutes.
`scripts/near_adversarial_nodes.sh` checks that window before starting and
refuses if it is too short — an expulsion landing mid-arm would make the later
runs incomparable to the earlier ones.

**Two limits enforced in the script, not trusted to the operator:**
- **Never validator-0** — it is the boot node and sole RPC endpoint, so taking it
  down measures our loss of connectivity, not the network's tolerance of a
  missing validator.
- **At most one validator down at a time** — 8 validators over 4 shards is
  exactly 2 per shard, the protocol minimum, so two simultaneous outages can
  leave a shard with no producer at all.

**Events go into the database, not a log file.** `analysis/backfill.py` records
that phase 2's outages "went to a text file, never the database", and
`analysis/export.py` keys two exclusion rules on `node_events` — an empty table
means those rules silently never fire. `scripts/near_import_events.py` attributes
each event to the run it fell in, refuses to import twice, and reports any run
that carries no outage at all.

### Three asymmetries to state when the two arms are compared

1. **Fraction of the network removed.** Polygon lost 1 of 4 (25%); NEAR loses 1
   of 8 (12.5%). NEAR's arm is *gentler* on this axis.
2. **Redundancy remaining in the affected shard.** Polygon kept 3 of 4
   validators; NEAR drops the affected shard from 2 producers to 1, its
   protocol minimum. NEAR's arm is *harsher* on this axis.
3. **The recovery cost itself, which Polygon does not have.** A NEAR validator
   interrupted beyond ~10% of an epoch is locked out for four hours. This was
   observed twice, unintentionally and with timestamps, on 11–12 Aug. It is a
   real architectural cost of proof-of-stake sharding that the Polygon arm
   cannot produce, and it needs no extra runs to report.

Points 1 and 2 pull in opposite directions. The paper should give both rather
than the flattering one.
