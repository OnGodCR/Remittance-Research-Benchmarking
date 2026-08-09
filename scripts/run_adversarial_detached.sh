#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Runs ON THE GENERATOR. Starts background traffic and the 15 adversarial-arm
# measurements, fully detached.
#
# A script file rather than an inline `gcloud ssh --command`: backgrounding
# through SSH held the session open indefinitely, so the caller never reached
# the step that starts the node outages -- and the runs executed against a
# healthy cluster while being labelled adversarial. Those runs were discarded.
#
# Writes ADV_DONE with the exit code when finished.
# ---------------------------------------------------------------------------
set -euo pipefail
cd /opt/benchmark

NOISE_SECONDS="${1:-6000}"

rm -f ADV_DONE adv.log noise.log

setsid nohup ./.venv/bin/python -m harness.noise \
  --config config/phase1.json \
  --duration "${NOISE_SECONDS}" \
  --keys keys/noise_senders.json > noise.log 2>&1 < /dev/null &

sleep 8
if ! pgrep -f "harness.noise" > /dev/null; then
  echo "ERROR: background traffic did not start"
  tail -5 noise.log 2>/dev/null || true
  exit 1
fi
echo "background traffic RUNNING"

# 3 load levels x 5 repeats at the $200 benchmark size.
setsid nohup bash -c '
  for tps in 100 200 300; do
    for r in 0 1 2 3 4; do
      echo "### ${tps}/sec repeat ${r} ###"
      ./.venv/bin/python -m harness.cli run --config config/phase1.json \
        --tps ${tps} --window 300 --amount 200 --workers 8 \
        --repeat ${r} --phase phase-2-adversarial --arm adversarial \
        2>&1 | grep -vE "block watcher|t=[0-9]+s" | tail -2
    done
  done
  echo $? > ADV_DONE
' > adv.log 2>&1 < /dev/null &

sleep 15
if pgrep -f "harness.cli run" > /dev/null; then
  echo "measurements RUNNING (15 runs, ~80 minutes)"
  head -2 adv.log 2>/dev/null || true
else
  echo "ERROR: measurements did not start"
  tail -10 adv.log 2>/dev/null || true
  exit 1
fi
