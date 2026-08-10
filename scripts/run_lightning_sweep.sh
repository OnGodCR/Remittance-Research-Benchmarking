#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Runs ON THE GENERATOR. The full Lightning matrix, detached and RESUMABLE.
#
# 4 amounts x 7 load steps x 5 repeats = 140 runs at 300s each.
#
# WHY A REBALANCE BETWEEN RUNS
#
# Every measured run pushes liquidity one way, because a remittance corridor is
# one-directional by nature. Without recycling, run N+1 would start on an
# emptier network than run N and the five repeats would not be repeats at all --
# they would be a slow drain dressed up as replication. The rebalancer pays in
# the opposite direction between runs, so each starts from the same state.
#
# WHY RESUMABLE
#
# Spot preemption took the Polygon cluster twice, and this one has already been
# preempted once. Without resume, a reclaim means either repeating finished
# work or hand-picking what to re-run -- and hand-picking is how configurations
# get silently skipped. The database is the source of truth.
# ---------------------------------------------------------------------------
set -uo pipefail
cd /opt/benchmark

PHASE="${1:-phase-3-full-stack}"
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
    # ended_wall IS NOT NULL is essential, not decoration. Without it an
    # INTERRUPTED run counts as complete: the sweep skips that configuration
    # on resume and the matrix quietly ends up with a hole nobody notices
    # until the analysis finds 139 cells instead of 140.
    \"SELECT COUNT(*) FROM runs WHERE phase=? AND architecture='lightning' \"
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
        ./.venv/bin/python -m harness.cli run --config config/phase3.json \\
          --tps \$tps --window 300 --amount \$amount --repeat \$r \\
          --phase ${PHASE} --arm baseline 2>&1 | tail -2

        # Recycle liquidity, sized to the run just completed.
        #
        # A flat 45-second gap cannot restore what a heavy run drains: 300/sec
        # for 290s at \$500 moves 671 BTC one way, and recycling it means
        # moving 671 BTC back. Reverse payments cost the same as forward ones,
        # so the gap has to run at the same rate for a comparable time --
        # there is no cheaper way round it, and that IS the capital-recycling
        # cost this arm exists to quantify.
        #
        # Light configurations still get a short gap; heavy ones get a long
        # one. Without this the network runs progressively dry and the later
        # runs measure our fixture emptying rather than Lightning.
        case \$tps in
          10|25|50)   rb_dur=60  ;;
          100|150)    rb_dur=200 ;;
          *)          rb_dur=330 ;;
        esac
        ./.venv/bin/python -m harness.rebalance --config config/phase3.json \\
          --mode reset --amount \$amount --duration \$rb_dur --tps \$tps 2>&1 | tail -1
      done
    done
  done
  echo \$? > SWEEP_DONE
" > sweep.log 2>&1 < /dev/null &

sleep 20
if pgrep -f "harness.cli run" > /dev/null || grep -q "###" sweep.log 2>/dev/null; then
  echo "sweep RUNNING"
  grep -E "^###" sweep.log | tail -2
else
  echo "ERROR: sweep did not start"
  tail -10 sweep.log 2>/dev/null
  exit 1
fi
