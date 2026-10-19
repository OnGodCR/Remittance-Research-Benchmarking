#!/usr/bin/env bash

# A PROCESS CHECK THAT FINDS ITSELF
#
# `pgrep -f foo` and `pkill -f foo` search whole command lines, so the shell
# running the check has "foo" in its own -- the check matches itself. It
# reports RUNNING when nothing is, and `pkill` kills its own wrapper. This
# cost hours on 22 Aug 2026 and, in one case, killed a sweep on its first
# instruction. The brackets fix it: the regex [f]oo still matches the text
# "foo" in a real process, but this line's own text reads "[f]oo", which the
# regex does not match. Repo convention -- see RESUME_HERE.md S5 trap 8.
# ---------------------------------------------------------------------------
# The adversarial arm: 3 load levels x $200 x 5 repeats, with validators
# dropping offline throughout.
#
# WHAT THIS MEASURES
#
# Not "how fast is the chain" -- we have that from the clean baseline. This
# measures the DIFFERENCE between the two arms at identical load. That
# difference is the finding, and it only exists because a clean comparison
# was measured first.
#
# LOAD LEVELS
#
# 100/sec (comfortable), 200/sec (the measured sustainable ceiling) and
# 300/sec (past the knee). The locked analysis plan requires 100/sec; the
# other two are additional data, reported as secondary. Running more than
# was pre-registered is not a violation -- omitting what was pre-registered
# would be.
#
# Testing only the comfortable level would miss the question that matters:
# whether losing a validator hurts more when the system is already stressed.
#
# Node outages run CONTINUOUSLY across all 15 runs rather than being started
# and stopped per run, so outages fall at unpredictable points within each
# run rather than at the same offset every time -- which would let the
# workload synchronise with the failures.
# ---------------------------------------------------------------------------
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ZONE=us-east4-c
PROJECT=remittances-benchmarking
GEN=bench-p2-generator

# 15 runs x ~320s, plus setup slack.
TOTAL_SECONDS=6000

log() { printf '\033[0;36m==>\033[0m %s\n' "$*"; }

log "Starting background traffic and the 15 measured runs on the generator"
gcloud compute ssh "$GEN" --zone "$ZONE" --project "$PROJECT" --no-tunnel-through-iap \
  --command "cd /opt/benchmark && rm -f ADV_DONE adv.log noise.log && \
    setsid nohup ./.venv/bin/python -m harness.noise --config config/phase1.json \
      --duration ${TOTAL_SECONDS} --keys keys/noise_senders.json > noise.log 2>&1 < /dev/null & \
    sleep 8 && \
    setsid nohup bash -c '
      for tps in 100 200 300; do
        for r in 0 1 2 3 4; do
          ./.venv/bin/python -m harness.cli run --config config/phase1.json \
            --tps \$tps --window 300 --amount 200 --workers 8 \
            --repeat \$r --phase phase-2-adversarial --arm adversarial \
            2>&1 | grep -vE \"block watcher|t=[0-9]+s\" | tail -2
        done
      done
      echo \$? > ADV_DONE
    ' > adv.log 2>&1 < /dev/null & \
    sleep 15 && (pgrep -f '[h]harness.cli run' >/dev/null && echo 'runs RUNNING' || echo 'FAILED to start') && \
    (pgrep -f '[h]harness.noise' >/dev/null && echo 'background traffic RUNNING' || echo 'noise FAILED')" \
  -- -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=60 2>&1 | tail -3

log "Starting node outages (runs for the whole arm, from this machine)"
nohup "$REPO/scripts/adversarial_nodes.sh" --phase phase2 --duration "$TOTAL_SECONDS" \
  > /tmp/adversarial.log 2>&1 < /dev/null &
sleep 20
if pgrep -f "[a]adversarial_nodes.sh" >/dev/null; then
  log "Node outages active -- at most one validator down at a time"
  grep -E "DOWN|back up" /tmp/adversarial.log | tail -2 || true
else
  echo "WARNING: outage script did not start; the arm would measure a clean baseline"
  tail -5 /tmp/adversarial.log 2>/dev/null || true
  exit 1
fi
