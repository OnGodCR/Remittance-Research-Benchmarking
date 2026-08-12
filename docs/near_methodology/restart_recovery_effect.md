# The first run after a chain restart fails more — observed, not corrected

**Written:** 12 August 2026
**Use this when:** interpreting NEAR's failure rates, writing Limitations, and
comparing NEAR's adversarial arm against Polygon's.

---

## 1. What was observed

Failure rates across the first four completed cells of the NEAR matrix, by
repeat index:

| Cell | r0 | r1 | r2 | r3 | r4 | Preceded by |
|---|---|---|---|---|---|---|
| $10 @ 10/sec | **0.95%** | 0.73% | 0.66% | 0.44% | 0.54% | sweep start (cold) |
| $10 @ 25/sec | 0.19% | 0.51% | **2.11%** | 0.40% | 1.55% | continuous running |
| $10 @ 50/sec | 0.15% | 0.08% | **0.45%** | 0.10% | 0.20% | continuous running |
| $200 @ 10/sec | **2.93%** | 1.68% | 1.50% | 0.41% | 0.69% | a 248-minute gap |

**The pattern is not "repeat 0 is worse".** It is "**the first run after the
chain restarts** is worse":

- In the two cells that followed a restart, r0 was the **highest** failure rate in
  its cell — 2 of 2.
- In the two cells measured mid-sweep, r0 was the **lowest or near-lowest** — 0 of
  2 elevated.

The 248-minute gap was the four-hour validator expulsion window (see
`adversarial_arm.md` §3). The sweep restarted at 16:05 UTC, roughly one minute
after the validator set became whole again.

## 2. Size of the effect

| Cell | Mean including r0 | Mean excluding r0 | Difference |
|---|---|---|---|
| $10 @ 10/sec | 0.664% | 0.593% | +0.07pp |
| $200 @ 10/sec | 1.442% | 1.070% | **+0.37pp** |

At these load levels the effect is far too small to touch the pre-registered
5% sustainability bar (`ANALYSIS_PLAN.md` §2). **It should be re-checked at
200 and 300/sec**, where NEAR's failure rate may approach that bar and a
0.4-point shift could matter.

## 3. What the failures actually are

Every failure in the worst run carries the same error: `not FINAL within 60s |
last: InternalError: Transaction <hash> doesn't exist`. These are **submission
rejections** — the payment was never accepted by the network, so nothing was
charged and a real system would retry. This was established earlier by querying
three separate validators for the missing hashes. It is not settlement failure,
and the paper should not describe it as one.

## 4. Why nothing was changed to compensate

Two options were considered.

**Add a settling delay** after the validator set becomes whole before the sweep
resumes. Rejected: the cells already collected did not have one, so adding it
mid-sweep would make early and late cells incomparable. **A consistent method
with a documented artefact is worth more than an improved method applied to half
the matrix.**

**Exclude the affected runs.** Rejected: no pre-registered rule covers it
(`ANALYSIS_PLAN.md` §7), and inventing one after seeing which runs it would
remove is precisely the practice the pre-registration exists to prevent. The
five repeats average the effect in, and the bootstrap intervals resample runs,
so the extra variability appears honestly as a **wider interval** rather than
being hidden.

## 5. It is probably a real property, not only an artefact

A network that has just readmitted two validators genuinely is in a worse state
for a few minutes: connections are being re-established and routing tables
re-formed. For an architecture proposed to carry payment traffic, **how it
behaves in the minutes after recovery is a legitimate thing to measure**, not
noise to be scrubbed out. This is the same argument that makes the four-hour
expulsion window a finding rather than an inconvenience.

## 6. Limits of this observation

- **Two restarts, not a designed experiment.** The effect is *suggestive*, not
  established. A cell's five repeats vary by more than this on their own — $10 @
  25/sec ranges 0.19% to 2.11% with no restart involved at all.
- **Restart timing is confounded with clock time and chain age.** The 16:05
  restart also happened on a chain four hours older than the morning runs.
- **No causal mechanism was measured.** No attempt was made to instrument peer
  reconnection or routing convergence during the affected runs.

State it as an observation with a plausible mechanism, and do not build a claim
on it.

## 7. How to find the affected runs in the data

Restarts are visible as gaps between consecutive `t0_wall` values. Any gap far
above the normal ~6 minutes marks a restart, and the run immediately after it is
the affected one.

```sql
-- runs that began more than 20 minutes after the previous run ended
SELECT run_id, tx_size_usd, target_tps, repeat_index,
       ROUND((t0_wall - LAG(ended_wall) OVER (ORDER BY t0_wall))/60.0, 1) AS gap_min
FROM runs
WHERE phase = 'phase-4-full-stack' AND invalidated = 0 AND ended_wall IS NOT NULL
ORDER BY t0_wall;
```

This makes a **sensitivity check** cheap: recompute any headline NEAR figure with
the post-restart runs dropped and report whether it moves. That is the honest
way to handle an effect noticed after the fact — quantify its influence rather
than either ignoring it or quietly removing it.
