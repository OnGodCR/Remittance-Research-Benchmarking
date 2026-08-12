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
n = c.execute(
    "SELECT COUNT(*) FROM runs WHERE phase=? AND architecture='near' "
    "AND tx_size_usd=? AND target_tps=? AND repeat_index=? AND invalidated=0 "
    "AND ended_wall IS NOT NULL",
    (phase, amount, tps, r)).fetchone()[0]
print(n)
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
