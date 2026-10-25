#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# DOES NEAR REALLY COLLAPSE AT 200 PAYMENTS/SEC, OR DID WE MEASURE OUR OWN
# QUESTION-ASKING?
#
# WHAT WE PUBLISHED
#
# NEAR sustains 150 payments/sec and does not merely plateau above that -- it
# collapses: 47.5/sec achieved against 200 offered, 76% failing. That is the
# single most striking claim in the NEAR chapter, and the comparison with
# Polygon's graceful decline rests on it.
#
# WHY IT IS NOW IN DOUBT
#
# The identical experiment on Polygon found that its published ceiling was not
# the chain's. Polygon's "270.5/sec with 9.97% failures" at 300 offered became
# 300.4/sec with ZERO failures once the harness stopped asking one machine
# every question. The number measured one node's ability to answer, not the
# network's ability to settle.
#
# NEAR's failure signature says the same thing even more plainly. The failures
# are "reached EXECUTED, not FINAL": the payment was accepted, executed, and
# then we failed to OBSERVE it finalising inside 60 seconds. That is a
# reporting failure, not a settlement failure -- and reporting is exactly what
# one endpoint does badly. At 200/sec with roughly 20 seconds to finality
# there are about 4,000 payments in flight at any moment, every one of them
# being asked after repeatedly. All of those questions went to one machine.
#
# So the pre-registered prediction, written before the runs: the four-endpoint
# arm will settle materially more than 47.5/sec at 200 offered. If it does
# not, the collapse is real and NEAR's chapter stands as written -- which is
# also a result worth having, because it would then be a property of the
# architecture rather than an artifact we failed to notice.
#
# WHAT IS AND IS NOT BEING CHANGED
#
# Only WHERE THE HARNESS LOOKS FOR ANSWERS. Submission still goes to one node
# in both arms. That restriction is deliberate and was learned the hard way on
# Polygon: sending from several continents at once made things ten times
# WORSE, because a sender holds its account's counter locked for the whole
# round trip and a slow intercontinental hop holds it longer. NEAR orders
# transactions per access key by nonce, so it has the same weakness. Spreading
# the ASKING is safe; spreading the SENDING is not.
#
# Hardware, block interval, network impairment, background traffic, the
# 60-second deadline and the sender pool are all identical between arms and
# identical to the published runs. This cluster is at the FULL published spec
# -- 8-processor validators, not the half-spec the 64-processor plan called
# for -- so if the ceiling moves, the new figure replaces the old one rather
# than sitting beside it with a caveat.
#
# WAITING BETWEEN RUNS
#
# The published sweep waited 20 seconds between runs. A run that leaves
# payments unsettled hands them to the next run, which then measures a chain
# that is still busy with the previous one. On Polygon that turned a clean
# 199/sec control into 171/sec with 9,452 timeouts -- and because the arms
# alternate, whichever arm followed the heavy run looked worse. Here the wait
# is 120 seconds, comfortably past the 60-second deadline, plus a check that
# the chain is still producing blocks before anything is timed.
#
# ARM ORDER ALTERNATES, AND THERE ARE SIX REPEATS NOT FIVE
#
# Whichever arm runs second inherits the other's leftovers, so a fixed order
# would hand one arm a permanent advantage. Six repeats split the favourable
# position exactly 3/3; five cannot. The pre-registered plan sets five as a
# MINIMUM, so six satisfies it rather than departing from it.
#
# USAGE
#   nohup caffeinate -i ./scripts/run_near_endpoint_ab.sh > near_ab.log 2>&1 &
#   ./scripts/run_near_endpoint_ab.sh --dry-run
#   ./scripts/run_near_endpoint_ab.sh --from-repeat 3
#   ./scripts/run_near_endpoint_ab.sh --loads "250 300" --arms four   # stage 2
#
# Do NOT add setsid -- macOS does not have it and the run dies instantly.
# ---------------------------------------------------------------------------
set -uo pipefail

# A PROCESS CHECK THAT FINDS ITSELF
#
# `pgrep -f foo` searches whole command lines, and when this runs on the
# generator the shell wrapping it HAS "foo" in its own command line -- so the
# check matches itself and always says yes. Observed 05:0x on 22 Aug: a status
# check reported the sweep RUNNING while it had never been started.
#
# Two ways that ruins the night. The "is one already going?" test never fires,
# so the sweep is never launched and the watcher waits on nothing until the
# machines hit their shutdown time. Worse, `pkill -f 'harness.cli run'` at the
# top of the sweep MATCHES ITS OWN WRAPPER and kills the sweep on its first
# instruction.
#
# The brackets fix it: the regex [h]arness still matches the text "harness" in
# a real process, but this line's own text now reads "[h]arness", which the
# regex does not match. Same trap as README.md cloud trap 8.

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="$(grep -E '^project_id' "$REPO/terraform/phase4/terraform.tfvars" | cut -d'"' -f2)"
GEN=near-generator
ZONE=us-east4-c

AMOUNT=200
WINDOW=300
LOADS="100 200"
ARMS="both"
REPEATS=6
SETTLE=120
DRY_RUN=0
FROM_REPEAT=0

# --- surviving a laptop restart ------------------------------------------
# Normally this script sits on the Mac and reaches the generator over ssh for
# every single run. That makes the Mac a single point of failure for a
# four-hour job: it restarted at 04:20 on 22 Aug and took the whole sweep with
# it. With --local the script is copied ONTO the generator and run there, so
# the only thing the Mac does is watch. Closing the laptop then costs nothing.
#
# --endpoints is needed because the generator has no copy of the infrastructure
# definitions to look the node addresses up from, so they are passed in.
LOCAL=0
ENDPOINT_OVERRIDE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)     DRY_RUN=1; shift ;;
    --from-repeat) FROM_REPEAT="$2"; shift 2 ;;
    --loads)       LOADS="$2"; shift 2 ;;
    --arms)        ARMS="$2"; shift 2 ;;
    --repeats)     REPEATS="$2"; shift 2 ;;
    --local)       LOCAL=1; shift ;;
    --endpoints)   ENDPOINT_OVERRIDE="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

log()  { printf '\033[0;36m==>\033[0m %s\n' "$*"; }
die()  { printf '\033[0;31merror:\033[0m %s\n' "$*" >&2; exit 1; }
note() { printf '    %s\n' "$*"; }

SSH_OPTS=(-o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=60)
gssh() {
  # In --local mode this IS the generator, so there is nothing to ssh into.
  if [ "$LOCAL" = "1" ]; then
    bash -c "$1" 2>&1
  else
    gcloud compute ssh "$GEN" --zone "$ZONE" --project "$PROJECT" --no-tunnel-through-iap \
      --command "$1" < /dev/null -- "${SSH_OPTS[@]}" 2>&1 | grep -v "^Warning:"
  fi
}

# One endpoint per REGION, so the asking is spread across continents rather
# than across two machines sitting in the same datacentre. Validators are laid
# out two per region, so indices 0, 2, 4 and 6 are one from each.
if [ -n "$ENDPOINT_OVERRIDE" ]; then
  ENDPOINTS="$ENDPOINT_OVERRIDE"
else
ENDPOINTS=$(cd "$REPO/terraform/phase4" && tofu output -json validators 2>/dev/null | python3 -c "
import sys, json
v = json.load(sys.stdin)
print(','.join('http://%s:3030' % v[i]['private_ip'] for i in (0, 2, 4, 6)))
")
fi
[ -n "$ENDPOINTS" ] || die "could not read validator addresses from terraform"

SINGLE=$(echo "$ENDPOINTS" | cut -d, -f1)

# 3 repeats lead with each arm, so running order is balanced exactly.
FIRST=("one" "four" "one" "four" "one" "four")

if [ "$DRY_RUN" = "1" ]; then
  log "Plan (nothing will be run)"
  echo "  project    $PROJECT"
  echo "  one arm    $SINGLE"
  echo "  four arm   $ENDPOINTS"
  echo "  loads      $LOADS   amount \$$AMOUNT   window ${WINDOW}s   repeats $REPEATS"
  n=0
  for r in $(seq 0 $((REPEATS - 1))); do
    if [ "$ARMS" = "four" ]; then arms="four"; elif [ "${FIRST[$r]}" = "one" ]; then arms="one four"; else arms="four one"; fi
    echo "  repeat $r: $arms"
    for _t in $LOADS; do for _a in $arms; do n=$((n + 1)); done; done
  done
  mins=$(( n * (WINDOW + SETTLE) / 60 ))
  echo
  echo "  $n measured runs, about $mins minutes plus overhead."
  exit 0
fi

# ---------------------------------------------------------------------------
# IS THE CHAIN ACTUALLY ALIVE, AND HAS IT FINISHED THE LAST RUN?
#
# NEAR has no equivalent of Ethereum's "how many transactions are waiting"
# query, so the queue cannot be read directly. Two things are checked instead:
# that block height is still advancing (a stalled chain would otherwise be
# measured as a failed architecture), and that enough time has passed for
# anything still in flight to have hit the 60-second deadline one way or the
# other.
# ---------------------------------------------------------------------------
chain_height() {
  gssh "curl -s -m 10 -X POST -H 'Content-Type: application/json' --data '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"status\",\"params\":[]}' $SINGLE | python3 -c 'import sys,json;print(json.load(sys.stdin)[\"result\"][\"sync_info\"][\"latest_block_height\"])'" 2>/dev/null | tail -1
}

settle_and_check() {
  note "settling ${SETTLE}s so nothing from the last run is still in flight"
  sleep "$SETTLE"
  local h1 h2
  h1=$(chain_height); sleep 12; h2=$(chain_height)
  case "$h1$h2" in (*[!0-9]*|'') note "WARNING: could not read block height -- continuing"; return 0 ;; esac
  if [ "$h2" -le "$h1" ]; then
    note "WARNING: chain did not advance in 12s ($h1 -> $h2). Waiting 120s more."
    sleep 120
    h2=$(chain_height)
    [ "$h2" -le "$h1" ] && note "WARNING: chain still stalled at $h2 -- FLAG EVERY RUN AFTER THIS"
  else
    note "chain healthy: $h1 -> $h2 in 12s"
  fi
}

one_run() {  # arm(one|four), tps, repeat
  local arm="$1" tps="$2" r="$3" urls
  if [ "$arm" = "four" ]; then urls="$ENDPOINTS"; else urls="$SINGLE"; fi
  settle_and_check
  log "repeat $r / $arm endpoint(s) / $tps per second"
  # sudo: the results database belongs to root. Without it the harness exits
  # in seconds having recorded nothing, while every progress line looks
  # normal -- exactly what emptied the first block-cadence attempt.
  gssh "cd /opt/benchmark && sudo ./.venv/bin/python -u -m harness.cli run \
      --config config/phase4.json --tps $tps --window $WINDOW --amount $AMOUNT \
      --repeat $r --phase phase-6-near-endpoints-$arm --arm baseline \
      --rpc-urls '$urls' 2>&1 | grep -E 'achieved|lag growth|endpoint override' | tail -3" \
    | tail -3
}

# A LEFTOVER RUN WILL DESTROY THIS ONE.
#
# Killing the orchestrator on the Mac does NOT stop the run already executing
# on the generator -- the ssh session dies, the remote python does not. Start a
# fresh run while that one is still going and both draw from the same funded
# accounts, so their per-account counters collide and every payment is
# rejected. Observed on Polygon, 19 Aug 2026: a control run came back at 0.0
# payments/sec with all 23,959 failing. Nothing was wrong with the chain.
log "Clearing any leftover run on the generator"
gssh "sudo pkill -f '[h]arness.cli run' 2>/dev/null; sleep 2; \
  pgrep -f '[h]arness.cli run' >/dev/null && echo '  WARNING: a run is still active' || echo '  clear'" | tail -1

# BACKGROUND TRAFFIC MUST BE PRESENT, AND THERE MUST BE EXACTLY ONE OF IT.
#
# The supervisor on the generator starts the noise generator itself and keeps
# it alive. Starting a second one here would DOUBLE the background load and
# make these runs incomparable with the published ones -- the opposite of what
# this experiment is for. So: start one only if none is running.
log "Checking background traffic (exactly one generator must be running)"
gssh "cd /opt/benchmark && \
  if pgrep -f '[h]arness.noise_near' >/dev/null; then \
    echo \"background traffic already running (\$(pgrep -cf '[h]arness.noise_near') process(es))\"; \
  else \
    setsid nohup ./.venv/bin/python -u -m harness.noise_near \
      --config config/phase4.json --keys keys/near_noise_senders.json \
      --duration 30000 >> noise.log 2>&1 < /dev/null & \
    sleep 10; \
    pgrep -f '[h]arness.noise_near' >/dev/null && echo 'background traffic STARTED' \
      || echo 'BACKGROUND TRAFFIC FAILED -- check /opt/benchmark/noise.log'; \
  fi" | tail -2

log "Arms: one = $SINGLE"
note "four = $ENDPOINTS"

for r in $(seq 0 $((REPEATS - 1))); do
  [ "$r" -lt "$FROM_REPEAT" ] && { note "repeat $r already done, skipping"; continue; }
  if [ "$ARMS" = "four" ]; then arms="four"
  elif [ "${FIRST[$r]}" = "one" ]; then arms="one four"
  else arms="four one"; fi
  for tps in $LOADS; do
    for arm in $arms; do one_run "$arm" "$tps" "$r"; done
  done
done

log "All runs finished."
note "Check FIRST that none auto-invalidated -- for scheduling lag, or for the"
note "validator set being incomplete (analysis/apply_validator_liveness.py)."
note "Then compare settled payments per second between"
note "phase-6-near-endpoints-one and phase-6-near-endpoints-four."
