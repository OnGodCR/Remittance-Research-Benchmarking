#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Launch the full sweep on the generator, detached from any SSH session.
#
# WHY A SCRIPT RATHER THAN AN INLINE COMMAND
#
# Launching this through `gcloud compute ssh --command` requires nesting quotes
# three deep -- shell, then ssh, then nohup -- and it silently failed once,
# starting the background traffic but not the sweep. A file has no quoting
# problem, and it can be inspected on the machine afterwards to see exactly
# what ran.
#
# `setsid` fully detaches the process group, so the sweep survives the SSH
# session ending, the operator's laptop sleeping, or the network dropping.
# A 12-hour run must not depend on a connection staying up.
#
# Writes SWEEP_DONE containing the exit code when finished, which is what the
# operator's machine polls for.
# ---------------------------------------------------------------------------
set -euo pipefail

cd /opt/benchmark

PHASE="${1:-phase-2-full-stack}"
WORKERS="${2:-8}"

rm -f SWEEP_DONE sweep.log

setsid nohup bash -c "
  ./.venv/bin/python -m harness.cli sweep \
    --config config/phase1.json \
    --phase ${PHASE} \
    --workers ${WORKERS} > sweep.log 2>&1
  echo \$? > SWEEP_DONE
" > /dev/null 2>&1 < /dev/null &

sleep 15

if pgrep -f "harness.cli sweep" > /dev/null; then
  echo "sweep RUNNING (phase=${PHASE}, workers=${WORKERS})"
  head -3 sweep.log 2>/dev/null || true
else
  echo "ERROR: sweep did not start"
  tail -20 sweep.log 2>/dev/null || echo "(no log written)"
  exit 1
fi
