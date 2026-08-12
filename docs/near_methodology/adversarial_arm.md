# The NEAR Adversarial Arm — what it measures, and what it cannot

**Written:** 12 August 2026
**Use this when:** writing the adversarial results, the cross-architecture
comparison, and Limitations. Every figure here is either measured or derived
from a stated source, and the claims that are *not* supported are marked as
such.

---

## 1. The design in one paragraph

Three load levels (100, 200, 300/sec) × **$200** × 5 repeats = **15 runs**, with
validators dropping offline throughout. The fault schedule is **identical to
Polygon's**: one validator offline at a time, 15–45s down, 20–60s between
outages, running continuously across all 15 runs rather than restarting per run
so outages fall at unpredictable points inside each run. The difference between
the two arms is supposed to be the architecture, not the fault pattern.

The finding is **the difference between the arms at the same load**, which only
exists because a clean baseline was measured first.

---

## 2. The three asymmetries against Polygon — state all three

These do not all point the same way. Reporting only the flattering one, in
either direction, would be a choice the data does not support.

| | Polygon | NEAR | Which arm is harsher |
|---|---|---|---|
| **Share of the network removed** | 1 of 4 = **25%** | 1 of 8 = **12.5%** | **Polygon** — NEAR's arm is gentler here |
| **Redundancy left in the affected shard** | 3 of 4 validators remain | affected shard drops **2 → 1** producer, its protocol minimum | **NEAR** — the affected shard loses half its producers |
| **Cost of the interruption itself** | validator rejoins consensus on restart, **immediately** | validator is **expelled for two further epochs ≈ 4 hours** | **NEAR** — a cost Polygon has no equivalent of |

**Rows 1 and 2 pull in opposite directions**, and both are consequences of the
same constraint: the 96 vCPU quota forced 8 validators over 4 shards, which is
exactly 2 per shard. A larger cluster would have given NEAR both a smaller
network fraction *and* spare producers per shard.

**Row 3 is the one that is genuinely about the architecture** rather than about
our cluster size, and it is the one Polygon's arm structurally cannot produce.

---

## 3. The expulsion mechanic, and the evidence for it

### The rule

- NEAR scores every validator each epoch against
  `block_producer_kickout_threshold` and `chunk_producer_kickout_threshold`,
  **both 90%** on this chain (read from `EXPERIMENTAL_protocol_config`).
- Below either threshold the protocol **expels** the validator.
- Re-admission requires a fresh `StakeAction`, which takes effect **two epochs
  later**. At `epoch_length` 3600 and 2s blocks that is **~4 hours**.
- The deficit is arithmetic and cannot be recovered inside the epoch.

### Observed twice, unintentionally, with timestamps

Both were spot-instance reclamations during Phase 4 setup, not deliberate
injections — which is what makes them clean evidence rather than a demonstration
of our own script.

| | `node0` | `node1` |
|---|---|---|
| Interrupted | 11:31 UTC, 11 Aug | 00:04 UTC, 12 Aug |
| Downtime | minutes | minutes |
| Epoch score on return | **91 of 467 blocks = 19%** | recovered to **100% production within minutes**, but the epoch score was already **63%** |
| Outcome | expelled | expelled |
| Back in the validator set | block 36002, ~03:07 UTC 12 Aug | block 39602, ~05:07 UTC 12 Aug |

**`node1` is the more instructive case.** It was healthy and producing perfectly
within minutes of returning, and was still expelled, because the epoch score is
cumulative and the deficit could not be made up before the epoch closed. A brief
interruption is punished for hours regardless of how quickly the operator
recovers.

### Why this belongs in the paper, not just in ops notes

It is a real operational property of proof-of-stake sharding with a liveness
requirement, and it has a direct remittance consequence: **a validator
interruption of a few minutes removes that validator's capacity for four hours**.
For an architecture being proposed to carry payment traffic, the recovery
characteristic is as relevant as the failure characteristic.

Polygon Edge's IBFT validators rejoin on restart, so the Polygon arm measures
only the *outage*. The NEAR arm measures the outage; the four-hour lockout has to
be reported alongside it and cannot be measured *within* the arm, because the
arm is deliberately shorter than the window in which expulsions take effect
(§4).

---

## 4. Why the arm can run at all, and the window it depends on

Expulsion is **decided** at the end of the epoch a validator underperformed in
and **applied two epochs later**. So from the start of an epoch there are at
least two hours — and up to four — in which the validator set stays nominally
whole however badly a node behaves.

**The arm takes ~80 minutes** (15 runs × ~320s), so it fits inside that window
with margin. `scripts/near_adversarial_nodes.sh` measures the remaining window
against the arm's duration before starting and **refuses** if it is too short.

**Why this matters for interpretation:** because the set stays whole,
- the harness health check (which requires 8 validators) does not abort the runs;
- every run in the arm meets the *same* nominal 8-validator network, so the runs
  are comparable with each other and with the baseline;
- the expulsions land *after* the arm, when the cluster is being shut down.

**What this means you cannot claim:** the arm does **not** measure NEAR operating
with a permanently reduced validator set. It measures a whole set with one member
intermittently unreachable. Those are different conditions and the paper should
say which one it tested.

---

## 5. How hostile the injection is relative to real NEAR

The same calibration Polygon's arm carries (`METHODOLOGY_LOG.md` §4 technique
#6), computed for NEAR against mainnet as measured on 12 Aug 2026 — **422
validators, 10 per shard, 10 shards**.

| | Our arm | NEAR mainnet | Ratio |
|---|---|---|---|
| Share of validators removed | 1 of 8 = 12.5% | 1 of 422 = 0.24% | **~53× more hostile** |
| Share of the affected shard's producers removed | 1 of 2 = 50% | 1 of 10 = 10% | **~5× more hostile** |
| Time offline | ~43% of the arm (15–45s down, 20–60s up) | 99.9% uptime target = 0.1% | **~430× more downtime** |

**This measures sensitivity to validator loss, not mainnet behaviour.** State it
exactly as the Polygon arm does. A reader who takes the adversarial failure rate
as a prediction of what NEAR would do in production has been misled, and the
paper is responsible for preventing that.

---

## 6. Constraints enforced by the script rather than left to the operator

- **Never `validator-0`.** It is the boot node and the only RPC endpoint. Taking
  it offline would measure our loss of connectivity, not the network's tolerance
  of a missing validator — the same error that, in phase 2, degraded the
  measurement instrument instead of the system under test.
- **At most one validator down at a time.** With 2 producers per shard, two
  simultaneous outages can leave a shard with **no** producer, which measures
  nothing except that we broke it. Polygon's script enforced the equivalent
  Byzantine limit for the same reason.

---

## 7. Where the data is

Outage events go into the `node_events` table with `source='adversarial'`, one
row per offline/online transition, with `offset` in seconds from the start of the
run they fell in — so an outage can be lined up against the per-second
throughput series.

They are written to the database by `scripts/near_import_events.py`, not left in
a log file. `analysis/backfill.py` records why: phase 2's outages "went to a text
file, never the database", and `analysis/export.py` keys two of its exclusion
rules on `node_events`, so an empty table means those rules **silently never
fire** and the adversarial runs stop being distinguishable from clean ones.

```sql
-- outages, and which run each fell in
SELECT r.target_tps, r.repeat_index, e.node_id, e.event, ROUND(e.offset,1) AS t
FROM node_events e JOIN runs r ON e.run_id = r.run_id
WHERE r.phase = 'phase-4-adversarial' AND e.source = 'adversarial'
ORDER BY r.t0_wall, e.offset;
```

---

## 8. The claims this arm supports, and the ones it does not

**Supported:**
- The throughput and failure-rate *difference* between the clean and adversarial
  arms at 100, 200 and 300/sec, with intervals over 5 repeats.
- That a NEAR validator interruption carries a multi-hour recovery cost, with
  two timestamped observations and the protocol rule that produces it.
- That the affected shard runs at half its producer redundancy during an outage,
  because 2 per shard is the protocol minimum at this cluster size.

**Not supported:**
- Any prediction of NEAR mainnet behaviour under failure. See §5.
- NEAR operating with a permanently reduced validator set. See §4.
- A like-for-like severity comparison with Polygon's arm in a single number —
  the two asymmetries in §2 point in opposite directions and must be reported
  separately.
