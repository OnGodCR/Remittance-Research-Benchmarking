#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Drive the NEAR endpoint experiment from account setup to a stopped cluster.
#
# Everything after the accounts are funded, in one unattended run:
#
#   1. wait for account setup to finish
#   2. put a hard shutdown time on all nine machines
#   3. apply the network impairment the published runs were measured under
#   4. check the chain is whole -- 8 validators, blocks advancing
#   5. run the endpoint A/B
#   6. pull the results back and export them
#   7. STOP EVERY MACHINE, whatever happened above
#
# STEP 7 RUNS EVEN IF SOMETHING FAILS. That is the point of the trap: the way
# this project wastes real money is not a long experiment, it is a cluster left
# running after a short one died at 3am. Nine machines cost about $4.50 an hour.
#
# THE HARD SHUTDOWN TIME IS NOT A SCRIPT
#
# `shutdown -h` is armed inside each machine's own operating system. If this
# orchestrator dies, if the laptop closes, if the network drops -- the machines
# still stop. Nothing here can revoke it except an explicit cancel.
#
# WHY THE GUARD SCRIPT IS NOT INSTALLED
#
# scripts/install_near_guard.sh restarts the node software on all 8 validators
# to re-apply a network binding. The chain is already healthy and already bound
# correctly, so that restart is pure risk for no gain. Its other job -- a
# lifetime cap -- is done here directly, and at a much tighter deadline than
# its own 34 hours.
#
# USAGE
#   nohup caffeinate -i ./scripts/near_ab_orchestrate.sh > ~/near_ab.log 2>&1 &
#
# The log goes to the home directory, NOT /tmp -- macOS clears /tmp on restart
# and the first attempt's log was lost exactly that way.
# ---------------------------------------------------------------------------
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
PROJECT="$(grep -E '^project_id' terraform/phase4/terraform.tfvars | cut -d'"' -f2)"
GEN=near-generator
GZONE=us-east4-c
HARD_STOP_UTC="${HARD_STOP_UTC:-11:15}"

NAMES=(0 1 2 3 4 5 6 7)
ZONES=(us-east4-c us-east4-c asia-south1-a asia-south1-a asia-southeast1-a asia-southeast1-a europe-west2-b europe-west2-b)

log()  { printf '\033[0;36m==>\033[0m %s  %s\n' "$(date -u +%H:%M:%SZ)" "$*"; }
note() { printf '    %s\n' "$*"; }

SSH_OPTS=(-o StrictHostKeyChecking=no -o LogLevel=ERROR -o ConnectTimeout=60)
gssh() {  # host zone command
  gcloud compute ssh "$1" --zone "$2" --project "$PROJECT" --no-tunnel-through-iap \
    --command "$3" < /dev/null -- "${SSH_OPTS[@]}" 2>&1 | grep -v "^Warning:"
}
ggen() { gssh "$GEN" "$GZONE" "$1"; }

stop_everything() {
  log "STOPPING ALL NINE MACHINES"
  gcloud compute instances stop "$GEN" --zone "$GZONE" --project "$PROJECT" --async --quiet >/dev/null 2>&1
  gcloud compute instances stop near-validator-0 near-validator-1 --zone us-east4-c        --project "$PROJECT" --async --quiet >/dev/null 2>&1
  gcloud compute instances stop near-validator-2 near-validator-3 --zone asia-south1-a     --project "$PROJECT" --async --quiet >/dev/null 2>&1
  gcloud compute instances stop near-validator-4 near-validator-5 --zone asia-southeast1-a --project "$PROJECT" --async --quiet >/dev/null 2>&1
  gcloud compute instances stop near-validator-6 near-validator-7 --zone europe-west2-b    --project "$PROJECT" --async --quiet >/dev/null 2>&1
  note "stop requested for all nine; disks and chain state survive"
}
trap stop_everything EXIT

# --- 1. wait for account setup -------------------------------------------
log "Waiting for account setup to finish"
waited=0
while [ "$waited" -lt 5400 ]; do
  state=$(ggen "systemctl is-active near-bootstrap" | tail -1)
  [ "$state" = "active" ] || break
  sleep 60; waited=$((waited + 60))
  [ $((waited % 300)) -eq 0 ] && note "still setting up accounts (${waited}s): $(ggen 'tail -1 /opt/benchmark/bootstrap.log' | tail -1)"
done
ok=$(ggen "test -f /opt/benchmark/config/phase4.json && echo yes || echo no" | tail -1)
if [ "$ok" != "yes" ]; then
  log "ACCOUNT SETUP DID NOT PRODUCE A CONFIG -- stopping here"
  ggen "tail -20 /opt/benchmark/bootstrap.log"
  exit 1
fi
note "config written; accounts ready"

# --- 2. hard shutdown time on every machine ------------------------------
log "Arming the hard shutdown for ${HARD_STOP_UTC} UTC on all nine machines"
CAP="sudo shutdown -c 2>/dev/null; sudo shutdown -h ${HARD_STOP_UTC} 'Hard cap.' 2>/dev/null; echo armed"
ggen "$CAP" | tail -1 | sed 's/^/    generator: /'
for i in 0 1 2 3 4 5 6 7; do
  ( r=$(gssh "near-validator-${NAMES[$i]}" "${ZONES[$i]}" "$CAP" | tail -1)
    printf "    validator-%s: %s\n" "${NAMES[$i]}" "$r" ) &
done
wait

# --- 3. network impairment ------------------------------------------------
log "Applying the network impairment the published runs were measured under"
./scripts/inject_impairment_near.sh 2>&1 | tail -6

# --- 4. is the chain whole? ----------------------------------------------
log "Checking the chain"
CHK="curl -s -m 10 -X POST -H 'Content-Type: application/json' --data '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"status\",\"params\":[]}' http://localhost:3030 | python3 -c 'import sys,json;d=json.load(sys.stdin)[\"result\"];print(d[\"sync_info\"][\"latest_block_height\"], len(d[\"validators\"]))'"
read -r H1 V1 <<< "$(gssh near-validator-0 us-east4-c "$CHK" | tail -1)"
sleep 20
read -r H2 V2 <<< "$(gssh near-validator-0 us-east4-c "$CHK" | tail -1)"
note "height $H1 -> $H2 in 20s, ${V2:-?} validators"
case "${V2:-0}" in
  8) : ;;
  *) log "VALIDATOR SET IS NOT WHOLE (${V2:-unknown} of 8) -- refusing to measure"; exit 1 ;;
esac
if [ "${H2:-0}" -le "${H1:-0}" ]; then
  log "CHAIN IS NOT ADVANCING -- refusing to measure"; exit 1
fi

# --- 5. the experiment, RUN ON THE GENERATOR ------------------------------
#
# The sweep is copied onto the generator and started there rather than driven
# over ssh from the Mac. The Mac restarted at 04:20 on 22 Aug and killed the
# first attempt; nothing on the laptop should be able to do that again. From
# here the Mac only watches, and closing it costs nothing.
log "Sending the experiment to the generator"
ENDPOINTS=$(cd "$REPO/terraform/phase4" && tofu output -json validators 2>/dev/null | python3 -c "
import sys, json
v = json.load(sys.stdin)
print(','.join('http://%s:3030' % v[i]['private_ip'] for i in (0, 2, 4, 6)))
")
[ -n "$ENDPOINTS" ] || { log "could not read node addresses"; exit 1; }
note "endpoints: $ENDPOINTS"

if ggen "pgrep -f run_near_endpoint_ab >/dev/null && echo yes || echo no" | tail -1 | grep -q yes; then
  note "a sweep is ALREADY running on the generator -- watching that one instead"
else
  gcloud compute scp --strict-host-key-checking=no --quiet --project "$PROJECT" \
    scripts/run_near_endpoint_ab.sh "$GEN:/opt/benchmark/run_ab.sh" --zone "$GZONE" >/dev/null 2>&1 \
    || { log "could not copy the experiment across"; exit 1; }
  ggen "chmod +x /opt/benchmark/run_ab.sh; cd /opt/benchmark && rm -f ab.log && \
    setsid nohup ./run_ab.sh --local --endpoints '$ENDPOINTS' > ab.log 2>&1 < /dev/null & \
    sleep 6; pgrep -f run_ab.sh >/dev/null && echo STARTED || echo FAILED_TO_START" | tail -1 | sed 's/^/    /'
fi

log "Watching. 24 runs, about 3 hours."
last=""
while ggen "pgrep -f run_ab.sh >/dev/null && echo yes || echo no" | tail -1 | grep -q yes; do
  sleep 300
  cur=$(ggen "grep -cE 'achieved' /opt/benchmark/ab.log 2>/dev/null || echo 0" | tail -1)
  line=$(ggen "tail -1 /opt/benchmark/ab.log" | tail -1)
  [ "$cur" != "$last" ] && { note "$(date -u +%H:%MZ)  runs finished: ${cur:-?}/24   $line"; last="$cur"; }
done
log "The sweep has stopped. Last 25 lines:"
ggen "tail -25 /opt/benchmark/ab.log"

# --- 6. bring the results home -------------------------------------------
log "Pulling the results database back"
gcloud compute scp --strict-host-key-checking=no --quiet --project "$PROJECT" \
  "$GEN:/opt/benchmark/bench.db" "data/near_ab_bench.db" --zone "$GZONE" >/dev/null 2>&1 \
  && note "saved to data/near_ab_bench.db" \
  || note "WARNING: could not copy the database back"

log "Done. The trap now stops every machine."
