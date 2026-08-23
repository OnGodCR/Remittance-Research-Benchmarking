#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# DOES NEAR'S SETTLEMENT TIME DEPEND ON HOW FAST WE TOLD IT TO MAKE BLOCKS?
#
# WHY THIS IS THE MOST CONSEQUENTIAL TEST LEFT
#
# The published NEAR runs made a block every 2 seconds. NEAR's own default is
# 600 milliseconds. We changed it because at the default the four-continent
# cluster could not agree on blocks at all -- it got stuck. 2 seconds was the
# fastest setting that held.
#
# That single line of configuration decides one of the paper's conclusions.
# A payment is final after a fixed NUMBER of blocks, so if blocks come more
# slowly, settlement takes proportionally longer. The decision rule disqualifies
# NEAR for taking longer than 10 seconds to settle -- and its measured 12.3-19.2s
# was recorded at the slow setting. ANALYSIS_PLAN.md amendment 12 works out that
# at 1.2s the same runs would land around 7.4-11.5s: straddling the bar rather
# than clearly failing it. The disqualification may be an artefact of a setting
# we chose for stability.
#
# So this is not a curiosity. It tests whether one of the study's verdicts
# survives.
#
# WHY 1.2 SECONDS AND NOT NEAR'S 600ms DEFAULT
#
# 600ms is already known to fail here -- that failure is why the setting was
# changed, and it is documented. Re-running a known failure proves nothing.
# 1.2s is the decision-relevant point: it is where the first-order estimate puts
# NEAR right at the 10-second bar. If it holds, 600ms can be tried afterwards.
#
# WHY A FRESH 2-SECOND CONTROL, RATHER THAN COMPARING TO THE PUBLISHED RUNS
#
# This cluster is a rebuild: new token contract, new accounts, new chain. If the
# 1.2s numbers were held against the published 2s numbers, any difference could
# be the cadence OR any of those other changes, and nothing could separate them.
# So both cadences are measured HERE, back to back, on one cluster. Same reason
# the endpoint experiment carries a control arm.
#
# The other delays scale with the main one. Leaving a 6-second ceiling under a
# 1.2-second target would change the shape of the timing, not just its speed.
#
# USAGE
#   ./scripts/run_near_blocktime.sh --dry-run
#   ./scripts/run_near_blocktime.sh --local --endpoints "http://a:3030,..."
# ---------------------------------------------------------------------------
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="$(grep -E '^project_id' "$REPO/terraform/phase4/terraform.tfvars" | cut -d'"' -f2)"
GEN=near-generator
ZONE=us-east4-c
CFG=/opt/near/node/config.json

AMOUNT=200
WINDOW=300
LOADS="100 150"
REPEATS=5
SETTLE=120
DRY_RUN=0
LOCAL=0
FROM_REPEAT=0
ENDPOINT_OVERRIDE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)   DRY_RUN=1; shift ;;
    --from-repeat) FROM_REPEAT="$2"; shift 2 ;;
    --loads)     LOADS="$2"; shift 2 ;;
    --repeats)   REPEATS="$2"; shift 2 ;;
    --local)     LOCAL=1; shift ;;
    --endpoints) ENDPOINT_OVERRIDE="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

log()  { printf '\033[0;36m==>\033[0m %s %s\n' "$(date -u +%H:%M:%SZ)" "$*"; }
note() { printf '    %s\n' "$*"; }
die()  { printf '\033[0;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

SSH_OPTS=(-o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=60)
NAMES=(0 1 2 3 4 5 6 7)
ZONES=(us-east4-c us-east4-c asia-south1-a asia-south1-a asia-southeast1-a asia-southeast1-a europe-west2-b europe-west2-b)

gssh() {
  gcloud compute ssh "$1" --zone "$2" --project "$PROJECT" --no-tunnel-through-iap \
    --command "$3" < /dev/null -- "${SSH_OPTS[@]}" 2>&1 | grep -v "^Warning:"
}
ggen() {
  if [ "$LOCAL" = "1" ]; then bash -c "$1" 2>&1; else gssh "$GEN" "$ZONE" "$1"; fi
}

if [ -n "$ENDPOINT_OVERRIDE" ]; then
  ENDPOINTS="$ENDPOINT_OVERRIDE"
else
  ENDPOINTS=$(cd "$REPO/terraform/phase4" && tofu output -json validators 2>/dev/null | python3 -c "
import sys, json
v = json.load(sys.stdin)
print(','.join('http://%s:3030' % v[i]['private_ip'] for i in (0, 2, 4, 6)))
")
fi
[ -n "$ENDPOINTS" ] || die "could not work out the node addresses"
SINGLE=$(echo "$ENDPOINTS" | cut -d, -f1)

# Cadences in milliseconds. 2000 is what every published NEAR figure was
# measured at; 1200 is the one under test. Order alternates by repeat so a
# slow drift in the cluster cannot masquerade as a cadence effect.
FIRST=("2000" "1200" "2000" "1200" "2000")

if [ "$DRY_RUN" = "1" ]; then
  log "Plan (nothing will be run)"
  echo "  project   $PROJECT"
  echo "  loads     $LOADS   amount \$$AMOUNT   window ${WINDOW}s   repeats $REPEATS"
  echo "  cadences  2000ms (control, as published)  vs  1200ms (under test)"
  n=0
  for r in $(seq 0 $((REPEATS - 1))); do
    if [ "${FIRST[$r]}" = "2000" ]; then o="2000 1200"; else o="1200 2000"; fi
    echo "  repeat $r: $o"
    for _l in $LOADS; do for _c in $o; do n=$((n + 1)); done; done
  done
  echo
  echo "  $n measured runs, about $(( n * (WINDOW + SETTLE) / 60 )) minutes plus restarts."
  exit 0
fi

# --- change the cadence on all eight, then prove the chain still works -----
set_cadence() {  # milliseconds
  local ms="$1" secs nanos maxs waits
  secs=$((ms / 1000)); nanos=$(((ms % 1000) * 1000000))
  maxs=$((ms * 3 / 1000)); waits=$((ms * 6 / 1000))
  log "Setting block cadence to ${ms}ms on all eight computers"
  local py="import json;p='$CFG';d=json.load(open(p));c=d['consensus'];\
c['min_block_production_delay']={'secs':$secs,'nanos':$nanos};\
c['max_block_production_delay']={'secs':$maxs,'nanos':0};\
c['max_block_wait_delay']={'secs':$waits,'nanos':0};\
open(p,'w').write(json.dumps(d,indent=2))"
  # Every machine must confirm, and a failure retries once then STOPS the
  # leg: one machine left at the old speed is a mixed-cadence cluster that
  # can still pass the block-production check, and 20 runs would be measured
  # on a configuration that matches nothing.
  for i in 0 1 2 3 4 5 6 7; do
    r=$(gssh "near-validator-${NAMES[$i]}" "${ZONES[$i]}" \
      "sudo python3 -c \"$py\" && sudo systemctl restart neard && echo ok" | tail -1)
    if [ "$r" != "ok" ]; then
      note "validator-${NAMES[$i]}: no confirmation (${r:0:60}) -- retrying once"
      sleep 8
      r=$(gssh "near-validator-${NAMES[$i]}" "${ZONES[$i]}" \
        "sudo python3 -c \"$py\" && sudo systemctl restart neard && echo ok" | tail -1)
    fi
    case "$r" in
      ok) note "validator-${NAMES[$i]}: ok" ;;
      *)  die "cadence change failed on validator-${NAMES[$i]} -- refusing to measure a mixed-speed cluster" ;;
    esac
  done
  note "waiting 90s for the cluster to settle after the restart"
  sleep 90
}

chain_height() {
  gssh near-validator-0 us-east4-c \
    "curl -s -m 10 -X POST -H 'Content-Type: application/json' --data '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"status\",\"params\":[]}' http://localhost:3030 | python3 -c 'import sys,json;d=json.load(sys.stdin)[\"result\"];print(d[\"sync_info\"][\"latest_block_height\"], len(d[\"validators\"]))'" \
    2>/dev/null | tail -1
}

verify_chain() {  # returns 1 if the cluster cannot hold consensus
  local h1 v1 h2 v2
  read -r h1 v1 <<< "$(chain_height)"; sleep 30; read -r h2 v2 <<< "$(chain_height)"
  case "${h1}${h2}" in (*[!0-9]*|'') note "could not read the chain"; return 1 ;; esac
  local made=$((h2 - h1))
  note "made $made blocks in 30s, ${v2:-?} of 8 computers taking part"
  [ "$made" -le 0 ] && return 1
  [ "${v2:-0}" -ne 8 ] && return 1
  return 0
}

one_run() {  # cadence_ms, tps, repeat
  local ms="$1" tps="$2" r="$3"
  note "settling ${SETTLE}s so nothing from the last run is still in flight"
  sleep "$SETTLE"
  log "repeat $r / ${ms}ms blocks / $tps per second"
  # sudo, because the results file belongs to root. Without it every run in
  # this leg exited in about four seconds and recorded NOTHING -- 20 runs of
  # apparent progress, an empty database, and no error anyone would notice
  # until the data was fetched. Third time the same ownership mismatch has
  # broken something today.
  ggen "cd /opt/benchmark && sudo ./.venv/bin/python -u -m harness.cli run \
      --config config/phase4.json --tps $tps --window $WINDOW --amount $AMOUNT \
      --repeat $r --phase phase-6-near-blocktime-${ms}ms --arm baseline \
      --rpc-urls '$ENDPOINTS' 2>&1 | grep -E 'achieved|lag growth|p95' | tail -3" | tail -3
}

# A LEFTOVER RUN WILL DESTROY THIS ONE -- same reasoning, same wording as the
# endpoint sweep: a run still executing on the generator shares the funded
# accounts with the new one, their per-account counters collide, and every
# payment is rejected (observed 19 Aug: 0.0/sec, 23,959 failures).
log "Clearing any leftover run on the generator"
ggen "sudo pkill -f '[h]arness.cli run' 2>/dev/null; sleep 2; \
  pgrep -f '[h]arness.cli run' >/dev/null && echo '  WARNING: a run is still active' || echo '  clear'" | tail -1

# Background traffic must be present and there must be exactly one of it --
# these runs are compared against runs that had it, and a silent dead noise
# generator would measure a quiet chain as if it were the same experiment.
log "Checking background traffic"
NOISE_N=$(ggen "pgrep -cf '[h]arness.noise_near' 2>/dev/null || echo 0" | tail -1)
case "$NOISE_N" in
  1) note "background traffic running (1 process)" ;;
  0) log "background traffic is NOT running -- starting it"
     ggen "cd /opt/benchmark && sudo rm -f noise.log && \
       sudo systemd-run --unit=near-noise --working-directory=/opt/benchmark \
         /opt/benchmark/.venv/bin/python -u -m harness.noise_near --config config/phase4.json >/dev/null 2>&1; \
       sleep 5; pgrep -cf '[h]arness.noise_near' || echo 0" | tail -1 | sed 's/^/    now running: /'
     ;;
  *) die "$NOISE_N background traffic generators running -- refusing to measure a doubled load" ;;
esac

CURRENT=""
for r in $(seq 0 $((REPEATS - 1))); do
  # Resumable: this leg is driven from the Mac because changing the cadence
  # needs to reach all eight computers, which the generator has no credentials
  # for. A laptop restart therefore still costs this sweep -- --from-repeat
  # lets it pick up rather than start over.
  [ "$r" -lt "$FROM_REPEAT" ] && { note "repeat $r already done, skipping"; continue; }
  if [ "${FIRST[$r]}" = "2000" ]; then order="2000 1200"; else order="1200 2000"; fi
  for ms in $order; do
    if [ "$ms" != "$CURRENT" ]; then
      set_cadence "$ms"
      if ! verify_chain; then
        log "THE CLUSTER CANNOT HOLD CONSENSUS AT ${ms}ms"
        note "that is itself the finding -- the same failure that forced 2s originally."
        note "putting the cadence back to 2000ms and stopping."
        set_cadence 2000; verify_chain
        exit 3
      fi
      CURRENT="$ms"
    fi
    for tps in $LOADS; do one_run "$ms" "$tps" "$r"; done
  done
done

log "Putting the block cadence back to 2000ms, as published"
set_cadence 2000
verify_chain
log "Block-cadence test complete."
