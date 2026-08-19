#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# RE-MEASURE THE 300/SEC RUNS ON A GENERATOR THAT CAN ACTUALLY DRIVE THEM
#
# WHY THIS EXISTS
#
# The first attempt at the waiting-room experiment lost the load level the
# whole question lives at. Seven of ten runs at 300 payments/sec auto-
# invalidated because the SENDING PROGRAM, not the chain, fell behind -- by
# 132 to 657 milliseconds against a 50 ms limit. The three that survived had
# large scheduling lag that happened to be shrinking rather than growing, so
# they slipped past a rule that only tests growth. None of them measure what
# they claim to.
#
# The 100/sec and 200/sec runs were clean, but both settings pass those loads
# with zero failures, so they say nothing about the queue.
#
# WHAT CHANGED, AND WHAT DELIBERATELY DID NOT
#
# The generator went from 8 processors to 16. Nothing else. That is a change
# to the measuring instrument, not to the system being measured, so what the
# chain does is unaffected -- but it must be recorded rather than smoothed
# over, which is why these runs carry their own phase names ending in "-g16".
# Nobody can then pool them with the 8-processor runs by accident.
#
# The validators are untouched at 4 processors each. Network impairment is
# re-applied before this runs -- traffic-control rules do NOT survive a
# machine restart, and re-measuring without them would compare an impaired
# arm against a clean one.
#
# SIX REPEATS, NOT FIVE
#
# Five repeats cannot split the favourable running position evenly between
# two settings: one gets it three times, the other twice, which biases a
# naive average. Six splits 3/3 exactly. The pre-registered plan sets five as
# a MINIMUM, so six satisfies it rather than departing from it.
#
# WHAT DECIDES THE QUESTION
#
# Committed payments per second, compared between settings. NOT the failure
# rate -- a bigger queue is expected to turn away fewer payments whether or
# not the ceiling moves, so the failure rate cannot distinguish the two
# explanations. It is still worth recording, because the KIND of failure
# (refused at the door vs accepted and then stuck) is a finding in itself.
#
# USAGE
#   nohup caffeinate -i ./scripts/run_txpool_300_rerun.sh > rerun.log 2>&1 &
#   ./scripts/run_txpool_300_rerun.sh --dry-run
#   ./scripts/run_txpool_300_rerun.sh --from-repeat 3
#
# Do NOT add setsid -- macOS does not have it and the run dies instantly.
# ---------------------------------------------------------------------------
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ZONE=us-east4-c
PROJECT=remittances-benchmarking
GEN=bench-p2-generator

SLOTS_DEFAULT=4096
SLOTS_LARGE=32768

AMOUNT=200
WINDOW=300
WORKERS=8
TPS=300
DRY_RUN=0
FROM_REPEAT=0

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)     DRY_RUN=1; shift ;;
    --from-repeat) FROM_REPEAT="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

log()  { printf '\033[0;36m==>\033[0m %s\n' "$*"; }
die()  { printf '\033[0;31merror:\033[0m %s\n' "$*" >&2; exit 1; }
note() { printf '    %s\n' "$*"; }

# 3 repeats lead with each setting, so running order is balanced exactly.
FIRST=("default" "enlarged" "default" "enlarged" "default" "enlarged")

if [ "$DRY_RUN" = "1" ]; then
  log "Plan (nothing will be run)"
  for r in 0 1 2 3 4 5; do
    if [ "${FIRST[$r]}" = "default" ]; then arms="default enlarged"; else arms="enlarged default"; fi
    echo "  repeat $r: $arms  (300/sec, \$200, 300s each)"
  done
  echo
  echo "  12 measured runs, 12 waiting-room changes, about 75 minutes."
  echo "  Each setting leads 3 times -- running order fully balanced."
  exit 0
fi

run_one() {  # arm, slots, repeat
  local arm="$1" slots="$2" r="$3"

  log "repeat $r / arm $arm -- setting the waiting room to $slots"
  "$REPO/scripts/set_txpool_size.sh" --slots "$slots" || die "could not set the waiting room"

  note "settling for 60s so no restart lands inside a measured run"
  sleep 60

  log "repeat $r / arm $arm / $TPS payments per second"
  gcloud compute ssh "$GEN" --zone "$ZONE" --project "$PROJECT" --no-tunnel-through-iap \
    --command "cd /opt/benchmark && ./.venv/bin/python -m harness.cli run \
      --config config/phase1.json --tps $TPS --window $WINDOW --amount $AMOUNT \
      --workers $WORKERS --repeat $r --phase phase-6-txpool-$arm-g16 --arm baseline \
      2>&1 | grep -vE 'block watcher|t=[0-9]+s' | tail -3" \
    < /dev/null -- -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=60 2>&1 \
    | grep -v "^Warning:" | tail -3
}

log "Starting background traffic for the whole re-run"
gcloud compute ssh "$GEN" --zone "$ZONE" --project "$PROJECT" --no-tunnel-through-iap \
  --command "cd /opt/benchmark && rm -f noise.log && \
    setsid nohup ./.venv/bin/python -m harness.noise --config config/phase1.json \
      --duration 6000 --keys keys/noise_senders.json > noise.log 2>&1 < /dev/null & \
    sleep 8 && (pgrep -f 'harness.noise' >/dev/null && echo 'background traffic RUNNING' \
      || echo 'BACKGROUND TRAFFIC FAILED')" \
  < /dev/null -- -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=60 2>&1 | tail -2

for r in 0 1 2 3 4 5; do
  [ "$r" -lt "$FROM_REPEAT" ] && { note "repeat $r already done, skipping"; continue; }
  if [ "${FIRST[$r]}" = "default" ]; then
    run_one default  "$SLOTS_DEFAULT" "$r"
    run_one enlarged "$SLOTS_LARGE"   "$r"
  else
    run_one enlarged "$SLOTS_LARGE"   "$r"
    run_one default  "$SLOTS_DEFAULT" "$r"
  fi
done

log "Putting the waiting room back to the shipped default"
"$REPO/scripts/set_txpool_size.sh" --slots "$SLOTS_DEFAULT"

log "All 12 runs finished."
note "Check FIRST that none auto-invalidated for scheduling lag -- that was"
note "the failure that cost the first attempt. Then compare committed"
note "payments per second between phase-6-txpool-default-g16 and"
note "phase-6-txpool-enlarged-g16."
