#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# THE WAITING-ROOM EXPERIMENT
#
# Does Polygon's measured ceiling move if the waiting room gets bigger?
#
# THE QUESTION, IN PLAIN WORDS
#
# Every single failure in the 140 clean Polygon runs was a payment being
# turned away at the door with the message "txpool is full" -- the waiting
# room where transactions sit before a validator packs them into a block. Not
# one accepted payment failed to settle. So our headline "Polygon sustains
# about 270 payments/second, with 10% failures at 300 offered" is really two
# separate claims stuck together:
#
#   1. the chain committed about 270 payments/second        <- about the chain
#   2. about 10% were turned away at the door               <- about a setting
#
# We never changed that setting. An auditor's objection is that if the waiting
# room were simply bigger, claim 1 might rise too -- in which case the ceiling
# we published is partly an artefact of a default we left alone, and the
# paper's headline number is wrong.
#
# HOW THIS SETTLES IT
#
# Run the identical cluster twice, changing only the size of the waiting room,
# and compare the payments-per-second actually committed:
#
#   * If committed throughput stays flat while the turn-away rate falls, then
#     the queue only controlled WHO GOT TURNED AWAY, and the ceiling belongs
#     to the chain. Claim 1 survives, claim 2 gets a caveat. This is the
#     result we expect and the one that defends the paper.
#
#   * If committed throughput rises with the bigger waiting room, the
#     published ceiling was partly our own configuration and must be
#     re-measured on hardware-matched machines before publication.
#
# Either answer is worth having. The second one is worth having BEFORE a
# reviewer finds it rather than after.
#
# WHAT THIS TEST CANNOT DO, STATED UP FRONT
#
# This cluster runs 4-processor validators, because a brand new Google account
# caps the whole project at 32 processors. The published runs used
# 8-processor validators. So the ABSOLUTE ceiling measured here will be lower
# than 270/sec and must never be quoted as a replacement for it.
#
# That does not damage the experiment, because the experiment is a
# comparison, not a measurement. Both arms run on the same machines within
# minutes of each other, so the hardware cancels out. What transfers to the
# paper is the direction of the effect, not the number.
#
# "THE WAITING ROOM" IS TWO SETTINGS, NOT ONE
#
# Polygon Edge limits the room in two ways at once: how many transactions it
# holds in total (4,096) and how many any ONE sender may have waiting in it
# (128). We send from 46 wallets, so 46 x 128 = 5,888 -- more than 4,096, and
# the total is what actually bites.
#
# Raise only the total to 32,768 and the per-sender limit becomes the real
# ceiling at 5,888: we would think we had opened the room eight times wider
# when we had opened it 1.4 times wider. If throughput then failed to move we
# would publish a confident negative result that was simply false.
#
# So both scale by eight together, preserving the ratio the software ships
# with. The total stays the binding limit in both arms. One real thing
# changes -- how much room there is -- and nothing shifts underneath it.
#
# THREE THINGS THIS DESIGN DOES TO AVOID FOOLING ITSELF
#
#   1. The two arms ALTERNATE (A,B then B,A then A,B ...) instead of running
#      all of A and then all of B. A chain that gradually slows as it grows
#      would otherwise make whichever arm ran second look worse, and we would
#      not be able to tell that apart from a real effect.
#
#   2. The three load levels run in a DIFFERENT ORDER in every repeat. In the
#      published sweep they always ran low-to-high, which an auditor flagged:
#      a fixed order lets slow-building effects line up with load.
#
#   3. Validators are restarted between arms, never during a run, and the
#      chain is checked to be producing blocks before any measuring starts.
#      A restart briefly shrinks the validator set, which is the exact thing
#      the adversarial arm measures -- letting one land inside a measured run
#      would mix the two experiments together.
#
# COST AND TIME
#
# 30 measured runs of 300 seconds, plus 10 waiting-room changes.
# About 3 hours, roughly $4 of machine time at on-demand prices.
#
# USAGE
#   caffeinate -i ./scripts/run_txpool_ab.sh            # keeps the Mac awake
#   ./scripts/run_txpool_ab.sh --dry-run                # print the plan only
# ---------------------------------------------------------------------------
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ZONE=us-east4-c
PROJECT=remittances-benchmarking
GEN=bench-p2-generator

# The shipped default, and eight times it. Eight times is chosen so that a
# null result is convincing: if eight times the room changes nothing, a
# reviewer cannot argue we simply did not open it wide enough.
SLOTS_DEFAULT=4096
SLOTS_LARGE=32768

AMOUNT=200
WINDOW=300
WORKERS=8
DRY_RUN=0

[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

log()  { printf '\033[0;36m==>\033[0m %s\n' "$*"; }
die()  { printf '\033[0;31merror:\033[0m %s\n' "$*" >&2; exit 1; }
note() { printf '    %s\n' "$*"; }

# Load order per repeat. Fixed rather than random so the run is reproducible,
# but rotated so no load level always sits in the same position.
ORDERS=("100 200 300" "300 100 200" "200 300 100" "100 300 200" "300 200 100")
# Which arm goes first in each repeat, so arm order is not confounded either.
FIRST=("default" "enlarged" "default" "enlarged" "default")

if [ "$DRY_RUN" = "1" ]; then
  log "Plan (nothing will be run)"
  for r in 0 1 2 3 4; do
    order="${ORDERS[$r]}"
    if [ "${FIRST[$r]}" = "default" ]; then arms="default enlarged"; else arms="enlarged default"; fi
    for arm in $arms; do
      echo "  repeat $r  arm=$arm  loads: $order"
    done
  done
  echo
  echo "  30 measured runs, 10 waiting-room changes, about 3 hours."
  exit 0
fi

run_block() {  # arm, slots, repeat, load order
  local arm="$1" slots="$2" r="$3" order="$4"

  log "repeat $r / arm $arm -- setting the waiting room to $slots"
  "$REPO/scripts/set_txpool_size.sh" --slots "$slots" || die "could not set the waiting room"

  # Let the validators settle after the restart. A restart briefly shrinks the
  # validator set; measuring inside that window would mix this experiment with
  # the node-failure experiment.
  note "settling for 60s so no restart lands inside a measured run"
  sleep 60

  local tps
  for tps in $order; do
    log "repeat $r / arm $arm / $tps payments per second"
    gcloud compute ssh "$GEN" --zone "$ZONE" --project "$PROJECT" --no-tunnel-through-iap \
      --command "cd /opt/benchmark && ./.venv/bin/python -m harness.cli run \
        --config config/phase1.json --tps $tps --window $WINDOW --amount $AMOUNT \
        --workers $WORKERS --repeat $r --phase phase-6-txpool-$arm --arm baseline \
        2>&1 | grep -vE 'block watcher|t=[0-9]+s' | tail -3" \
      < /dev/null -- -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=60 2>&1 \
      | grep -v "^Warning:" | tail -3
  done
}

log "Starting background traffic on the generator for the whole experiment"
# ~3 hours of runs plus changeovers; the noise generator exits on its own.
gcloud compute ssh "$GEN" --zone "$ZONE" --project "$PROJECT" --no-tunnel-through-iap \
  --command "cd /opt/benchmark && rm -f noise.log && \
    setsid nohup ./.venv/bin/python -m harness.noise --config config/phase1.json \
      --duration 12000 --keys keys/noise_senders.json > noise.log 2>&1 < /dev/null & \
    sleep 8 && (pgrep -f 'harness.noise' >/dev/null && echo 'background traffic RUNNING' \
      || echo 'BACKGROUND TRAFFIC FAILED')" \
  < /dev/null -- -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=60 2>&1 | tail -2

for r in 0 1 2 3 4; do
  order="${ORDERS[$r]}"
  if [ "${FIRST[$r]}" = "default" ]; then
    run_block default  "$SLOTS_DEFAULT" "$r" "$order"
    run_block enlarged "$SLOTS_LARGE"   "$r" "$order"
  else
    run_block enlarged "$SLOTS_LARGE"   "$r" "$order"
    run_block default  "$SLOTS_DEFAULT" "$r" "$order"
  fi
done

# Leave the cluster in the shipped configuration, so anything run later
# matches the published study rather than this experiment.
log "Putting the waiting room back to the shipped default"
"$REPO/scripts/set_txpool_size.sh" --slots "$SLOTS_DEFAULT"

log "All 30 runs finished."
note "Pull the data with the usual merge step, then compare the two phases:"
note "  phase-6-txpool-default  vs  phase-6-txpool-enlarged"
note "The number that decides it is committed payments per second, NOT the"
note "failure rate -- the failure rate is expected to fall in the enlarged"
note "arm whether or not the ceiling moves."
