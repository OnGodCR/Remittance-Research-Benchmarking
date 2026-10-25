#!/usr/bin/env bash

# A PROCESS CHECK THAT FINDS ITSELF
#
# `pgrep -f foo` and `pkill -f foo` search whole command lines, so the shell
# running the check has "foo" in its own -- the check matches itself. It
# reports RUNNING when nothing is, and `pkill` kills its own wrapper. This
# cost hours on 22 Aug 2026 and, in one case, killed a sweep on its first
# instruction. The brackets fix it: the regex [f]oo still matches the text
# "foo" in a real process, but this line's own text reads "[f]oo", which the
# regex does not match. Repo convention -- see README.md cloud trap 8.
# ---------------------------------------------------------------------------
# Runs ON THE GENERATOR. The full NEAR matrix, detached and RESUMABLE.
#
# 4 amounts x 7 load steps x 5 repeats = 140 runs at 300s each.
#
# NO REBALANCING BETWEEN RUNS, unlike Lightning. NEAR has no liquidity to
# recycle: a sender needs tokens, and every sender is funded with far more than
# the whole matrix consumes. The gap is therefore short -- just enough for
# in-flight transactions to finalise before the next run's timing starts.
#
# WHY RESUMABLE
#
# Spot preemption took the Polygon cluster twice and the Lightning one once.
# Without resume a reclaim means repeating finished work or hand-picking what
# to re-run, and hand-picking is how configurations get silently skipped. The
# database is the source of truth -- and the check requires the run to have
# FINISHED, not merely to exist: an interrupted run that counted as complete
# would leave a hole in the matrix that only surfaces at analysis time.
# ---------------------------------------------------------------------------
set -uo pipefail
cd /opt/benchmark

PHASE="${1:-phase-4-full-stack}"
rm -f SWEEP_DONE

setsid nohup bash -c "
  for amount in 10 50 200 500; do
    for tps in 10 25 50 100 150 200 300; do
      for r in 0 1 2 3 4; do
        done_already=\$(./.venv/bin/python - \"\$amount\" \"\$tps\" \"\$r\" <<'PYEOF'
import sqlite3, sys
amount, tps, r = float(sys.argv[1]), float(sys.argv[2]), int(sys.argv[3])
c = sqlite3.connect('data/working/runs.sqlite')
n = c.execute(
    \"SELECT COUNT(*) FROM runs WHERE phase=? AND architecture='near' \"
    \"AND tx_size_usd=? AND target_tps=? AND repeat_index=? AND invalidated=0 \"
    \"AND ended_wall IS NOT NULL\",
    ('${PHASE}', amount, tps, r)).fetchone()[0]
print(n)
PYEOF
)
        if [ \"\$done_already\" -gt 0 ]; then
          echo \"### \\\$\$amount @ \$tps/sec repeat \$r -- already complete, skipping\"
          continue
        fi
        echo \"### \\\$\$amount @ \$tps/sec repeat \$r ###\"
        ./.venv/bin/python -m harness.cli run --config config/phase4.json \\
          --tps \$tps --window 300 --amount \$amount --repeat \$r \\
          --phase ${PHASE} --arm baseline 2>&1 | tail -2
        # Let in-flight transactions finalise so they are not still settling
        # when the next run starts timing.
        sleep 20
      done
    done
  done
  echo \$? > SWEEP_DONE
" > sweep.log 2>&1 < /dev/null &

sleep 20
if pgrep -f "[h]harness.cli run" > /dev/null || grep -q "###" sweep.log 2>/dev/null; then
  echo "sweep RUNNING"
  grep -E "^###" sweep.log | tail -2
else
  echo "ERROR: sweep did not start"
  tail -10 sweep.log 2>/dev/null
  exit 1
fi
