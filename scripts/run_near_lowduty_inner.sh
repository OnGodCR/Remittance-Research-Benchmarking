#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# EXPLORATORY duty-cycle block: 150/sec x $200 x 5 repeats = 5 runs.
#
# NOT part of the pre-registered adversarial arm. Recorded under its own phase,
# `phase-4-adversarial-lowduty`, so it can never be pooled with the 15 runs of
# `phase-4-adversarial`.
#
# WHAT IT IS FOR
#
# The pre-registered arm measures one point: one validator down, ~43% of the
# time, in a shard that has only 2 producers. NEAR mainnet differs on three
# axes at once -- 422 validators not 8, 10 producers per shard not 2, and ~0.1%
# downtime not 43%. One measurement cannot be extrapolated across three
# simultaneous differences, and scaling the failure rate down by the ratio of
# any one of them would be arithmetic dressed up as evidence.
#
# Two of those axes are fixed by our quota: we cannot add validators, and 2 per
# shard is the protocol minimum. **Downtime fraction is the one axis that can
# be varied**, so this block varies it and nothing else:
#
#     pre-registered arm : 15-45s down, 20-60s gap   -> ~43% downtime
#     this block         :  5s down,   115s gap      -> ~4% downtime
#
# Same load (150/sec, NEAR's knee), same amount, same background traffic, same
# impairment, same everything else. Two points on the downtime axis show
# whether failure scales roughly linearly with how often things break. If it
# does, arguing toward mainnet's 0.1% becomes a defensible extrapolation with a
# stated assumption rather than a guess.
#
# **This is exploratory and must be labelled as such** (`ANALYSIS_PLAN.md` S4):
# it was designed after seeing the arm's results, so it cannot support a
# headline claim, and it is a single load level with no second architecture to
# compare against.
# ---------------------------------------------------------------------------
set -uo pipefail
cd /opt/benchmark

PHASE="${1:-phase-4-adversarial-lowduty}"

for r in 0 1 2 3 4; do
  done_already=$(./.venv/bin/python - "$r" "$PHASE" <<'PYEOF'
import sqlite3, sys
r, phase = int(sys.argv[1]), sys.argv[2]
c = sqlite3.connect('data/working/runs.sqlite')
n = c.execute(
    "SELECT COUNT(*) FROM runs WHERE phase=? AND architecture='near' "
    "AND tx_size_usd=200.0 AND target_tps=150.0 AND repeat_index=? "
    "AND invalidated=0 AND ended_wall IS NOT NULL", (phase, r)).fetchone()[0]
print(n)
PYEOF
)
  if [ "${done_already:-0}" -gt 0 ]; then
    echo "### low-duty repeat $r -- already complete, skipping"
    continue
  fi

  echo "### LOW-DUTY \$200 @ 150/sec repeat $r ### $(date -u +%H:%M:%S)"
  ./.venv/bin/python -u -m harness.cli run --config config/phase4.json \
    --tps 150 --window 300 --amount 200 --repeat "$r" \
    --phase "$PHASE" --arm adversarial 2>&1 | tail -3

  sleep 20
done

echo "### LOW-DUTY BLOCK FINISHED $(date -u +%FT%TZ)"
