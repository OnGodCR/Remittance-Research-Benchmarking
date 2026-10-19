#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# The NEAR adversarial arm: 3 load levels x $200 x 5 repeats = 15 runs.
#
# Runs in the FOREGROUND on the generator. The outage injector
# (scripts/near_adversarial_nodes.sh) runs separately FROM THE OPERATOR'S
# MACHINE, because it drives `gcloud compute ssh` against each validator, and
# it runs continuously across all 15 runs rather than restarting per run -- so
# outages fall at unpredictable points inside each run rather than always at
# the same offset.
#
# WHY 100 / 150 / 200 AND NOT POLYGON'S 100 / 200 / 300
#
# Polygon's levels were below / at / past its knee, and its knee was 200/sec.
# NEAR's knee is 150/sec. Copying the absolute numbers would not copy the
# design: at 200/sec NEAR already fails 76% of payments with the network
# whole, and no valid run exists at 300/sec at all. The arm exists to separate
# degradation under load from degradation under node failure, so a level where
# the baseline has already collapsed measures nothing.
#
# 150/sec carries the finding, as the direct analogue of Polygon's 200.
# 200/sec is expected to be uninterpretable and is run anyway, so the paper can
# show rather than assert that losing a validator does not measurably worsen an
# already-collapsed network. See docs/near_methodology/adversarial_arm.md.
#
# NO --workers, unlike Polygon. The NEAR path is single-process by design, and
# the harness was validated to sustain 300/sec against a null backend at an
# equivalent in-flight load (docs/near_methodology/generator_is_not_the_ceiling.md).
#
# RESUMABLE on the same rule as the baseline sweep: a configuration counts only
# when it has FINISHED and is not invalidated.
# ---------------------------------------------------------------------------
set -uo pipefail
cd /opt/benchmark

PHASE="${1:-phase-4-adversarial}"

for tps in 100 150 200; do
  for r in 0 1 2 3 4; do

    done_already=$(./.venv/bin/python - "$tps" "$r" "$PHASE" <<'PYEOF'
import sqlite3, sys
tps, r, phase = float(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
c = sqlite3.connect('data/working/runs.sqlite')
n = c.execute(
    "SELECT COUNT(*) FROM runs WHERE phase=? AND architecture='near' "
    "AND tx_size_usd=200.0 AND target_tps=? AND repeat_index=? "
    "AND invalidated=0 AND ended_wall IS NOT NULL",
    (phase, tps, r)).fetchone()[0]
print(n)
PYEOF
)
    if [ "${done_already:-0}" -gt 0 ]; then
      echo "### $tps/sec repeat $r -- already complete, skipping"
      continue
    fi

    echo "### ADVERSARIAL \$200 @ $tps/sec repeat $r ### $(date -u +%H:%M:%S)"
    ./.venv/bin/python -u -m harness.cli run --config config/phase4.json \
      --tps "$tps" --window 300 --amount 200 --repeat "$r" \
      --phase "$PHASE" --arm adversarial 2>&1 | tail -3

    sleep 20
  done
done

echo "### ADVERSARIAL ARM FINISHED $(date -u +%FT%TZ)"
