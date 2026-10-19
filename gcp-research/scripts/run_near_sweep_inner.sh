#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# The NEAR matrix, in the FOREGROUND. Launched by scripts/near_supervisor.py,
# which detaches it and records its PID.
#
# WHY A SEPARATE SCRIPT FROM run_near_sweep.sh
#
# That one detaches itself with `setsid nohup ... &`, so the PID the caller
# sees belongs to a shell that exits immediately. There is then nothing to
# track, and liveness has to be guessed from process names -- which is exactly
# the check that reported "sweep RUNNING" for processes that did not exist
# (PHASE4_HANDOFF.md bug 4). Here the supervisor owns the detaching and the
# PID file, so "is the sweep alive" is answered by kill -0 on a known PID.
#
# 4 amounts x 7 load steps x 5 repeats = 140 runs at 300s each, ~13 hours.
#
# RESUMABLE. Spot preemption took the Polygon cluster twice and the Lightning
# one once. The database is the source of truth, and the check requires the run
# to have FINISHED, not merely to exist: an interrupted run counted as complete
# would leave a hole in the matrix that only surfaces at analysis time.
#
# NOTE ON RESUME AND REPEATS: the sweep restarts from the beginning of the
# ladder rather than from the point of interruption, which on Polygon silently
# produced 22 duplicate runs with identical arrival seeds. The skip check below
# is what prevents that, but audit repeat counts after any resumed sweep
# anyway (RESUME_HERE.md S5 trap 0).
# ---------------------------------------------------------------------------
set -uo pipefail
cd /opt/benchmark

PHASE="${1:-phase-4-full-stack}"

# $200 FIRST, deliberately.
#
# $200 is the World Bank's standard remittance size (claude.md S6) and the
# headline number of every comparison in the paper. In the original order --
# 10, 50, 200, 500 -- it is measured THIRD, landing seven to ten hours into a
# 13.5-hour sweep. Anything that cuts the sweep short therefore leaves the two
# least important sizes complete and the headline missing entirely.
#
# Order does not affect a result: each cell is five repeats under identical
# conditions, and amount is already known not to change gas or latency on an
# account-model chain. So this costs nothing and removes the failure mode where
# a stall at hour eight destroys the paper's central figure. Recorded in
# METHODOLOGY_LOG rather than done silently.
for amount in 200 10 50 500; do
  for tps in 10 25 50 100 150 200 300; do
    for r in 0 1 2 3 4; do

      done_already=$(./.venv/bin/python - "$amount" "$tps" "$r" "$PHASE" <<'PYEOF'
import sqlite3, sys
amount, tps, r, phase = float(sys.argv[1]), float(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
c = sqlite3.connect('data/working/runs.sqlite')
ok = c.execute(
    "SELECT COUNT(*) FROM runs WHERE phase=? AND architecture='near' "
    "AND tx_size_usd=? AND target_tps=? AND repeat_index=? AND invalidated=0 "
    "AND ended_wall IS NOT NULL",
    (phase, amount, tps, r)).fetchone()[0]

# RETRY CAP -- stops an unmeasurable cell from looping forever.
#
# The sweep walks the ladder once and exits; the supervisor then restarts it
# whenever fewer than 140 configurations are complete, and the fresh pass
# re-runs whatever is still missing. That is what repairs a run invalidated by
# a transient fault, and it is deliberate.
#
# It also means a cell that can NEVER complete is retried forever. On 12 Aug
# every 300/sec run was invalidated for generator saturation -- p95 scheduling
# lag ~1.2s, growth +67 to +77ms against the pre-registered 50ms threshold --
# and the cause is structural, not transient: NEAR's RPC answers slowly once
# the chain is congested, which holds up the send path. Retrying cannot fix
# that. Left alone, the supervisor would have spent the rest of the night
# re-running 20 doomed configurations at ~$3.50/hour, making no progress and
# reaching no end state.
#
# Three attempts is enough to ride out a transient fault (an epoch-boundary
# blip, one bad liveness sample) and few enough to bound the waste. A capped
# cell is reported as missing by the supervisor rather than silently forgotten.
attempts, saturated = c.execute(
    "SELECT COUNT(*), SUM(COALESCE(invalidation_reason,'') LIKE 'generator saturated%') "
    "FROM runs WHERE phase=? AND architecture='near' "
    "AND tx_size_usd=? AND target_tps=? AND repeat_index=? "
    "AND ended_wall IS NOT NULL",
    (phase, amount, tps, r)).fetchone()
saturated = saturated or 0

# A STRUCTURAL failure is not retried at all; a transient one gets 3 tries.
#
# The two failure modes need different treatment and the reason string
# distinguishes them without hard-coding a load level.
#
#   transient -- an epoch-boundary liveness blip (observed once in 5,604
#     samples), a validator briefly behind. Retrying fixes these, and the
#     second pass exists precisely to do that.
#
#   generator saturated -- the offered arrival pattern drifted from the
#     intended Poisson process. At 300/sec every one of the five $200 repeats
#     failed this way with p95 scheduling lag ~1.2s, and the cause does not
#     vary between attempts: NEAR's RPC answers slowly once the chain is
#     congested, which holds up the send path. A retry reproduces it exactly.
#
# Retrying the 20 doomed 300/sec cells three times each would burn about six
# hours and $21 of a budget with roughly $40 left, and end with the same 20
# holes. One attempt per cell still records the failure at every transaction
# size -- enough to show it is not specific to one amount -- and then stops.
if ok or attempts >= 3 or (attempts >= 1 and saturated == attempts):
    print(1)
else:
    print(0)
PYEOF
)
      if [ "${done_already:-0}" -gt 0 ]; then
        echo "### \$$amount @ $tps/sec repeat $r -- already complete, skipping"
        continue
      fi

      echo "### \$$amount @ $tps/sec repeat $r ### $(date -u +%H:%M:%S)"
      ./.venv/bin/python -u -m harness.cli run --config config/phase4.json \
        --tps "$tps" --window 300 --amount "$amount" --repeat "$r" \
        --phase "$PHASE" --arm baseline 2>&1 | tail -3

      # Let in-flight transactions finalise so they are not still settling when
      # the next run starts timing.
      sleep 20
    done
  done
done

echo "### SWEEP LOOP FINISHED $(date -u +%FT%TZ)"
