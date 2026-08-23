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
# Runs ON THE GENERATOR. Background traffic plus the adversarial-arm
# measurements, fully detached, and RESUMABLE.
#
# WHY RESUMABLE
#
# Spot preemption took the entire cluster twice on 9 Aug -- once mid-setup,
# once after 3 of 15 runs. Without resume, each preemption means either
# repeating finished work or hand-picking what to re-run, and hand-picking is
# how configurations get silently skipped. The database is the source of
# truth: a configuration with a valid completed run is not repeated.
#
# WHY A SCRIPT FILE RATHER THAN AN INLINE SSH COMMAND
#
# Backgrounding through `gcloud ssh --command` holds the session open
# indefinitely, so the caller never reaches whatever comes next. That failure
# left the first attempt measuring a healthy cluster while labelling the runs
# adversarial -- they were discarded.
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
if ! pgrep -f "[h]harness.noise" > /dev/null; then
  echo "ERROR: background traffic did not start"
  tail -5 noise.log 2>/dev/null || true
  exit 1
fi
echo "background traffic RUNNING"

setsid nohup bash -c '
  for tps in 100 200 300; do
    for r in 0 1 2 3 4; do
      # Skip configurations already completed and valid. Checked per run
      # rather than once at the start, so a preemption mid-arm resumes
      # exactly where it stopped.
      done_already=$(./.venv/bin/python - "$tps" "$r" <<PYEOF
import sqlite3, sys
tps, r = float(sys.argv[1]), int(sys.argv[2])
c = sqlite3.connect("data/working/runs.sqlite")
n = c.execute(
    "SELECT COUNT(*) FROM runs WHERE phase=? AND arm=? AND target_tps=? "
    "AND repeat_index=? AND tx_size_usd=200 AND invalidated=0",
    ("phase-2-adversarial", "adversarial", tps, r)).fetchone()[0]
print(n)
PYEOF
)
      if [ "$done_already" -gt 0 ]; then
        echo "### ${tps}/sec repeat ${r} -- already complete, skipping ###"
        continue
      fi
      echo "### ${tps}/sec repeat ${r} ###"
      ./.venv/bin/python -m harness.cli run --config config/phase1.json \
        --tps ${tps} --window 300 --amount 200 --workers 8 \
        --repeat ${r} --phase phase-2-adversarial --arm adversarial \
        2>&1 | grep -vE "block watcher|t=[0-9]+s" | tail -2
    done
  done
  echo $? > ADV_DONE
' > adv.log 2>&1 < /dev/null &

sleep 20
if pgrep -f "[h]harness.cli run" > /dev/null || grep -q "skipping" adv.log 2>/dev/null; then
  echo "measurements RUNNING"
  grep -E "^###" adv.log | tail -3 || true
else
  echo "ERROR: measurements did not start"
  tail -10 adv.log 2>/dev/null || true
  exit 1
fi
