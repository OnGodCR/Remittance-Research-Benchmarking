#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Realism technique #6 for NEAR: intermittent validator outages.
#
# Takes validators offline during the adversarial arm and records exactly when
# and which, so the performance difference can be attributed to specific
# failures rather than guessed at.
#
# WHY NEAR NEEDS ITS OWN, AND WHY THE ARM IS SHAPED DIFFERENTLY
#
# On Polygon Edge a stopped validator rejoins IBFT consensus the moment it
# restarts, so each of the 15 runs met the same 4-validator network. On NEAR a
# validator that misses its scheduled blocks falls below the 90% kickout
# threshold and the protocol EXPELS it -- for two further epochs, four hours
# here. Outages therefore do not just perturb the run they occur in; they
# permanently shrink the network for everything after.
#
# THE PROPERTY THAT MAKES THE ARM POSSIBLE AT ALL
#
# Expulsion is decided at the end of the epoch in which a validator
# underperformed and applied TWO epochs later. Starting the arm near the
# beginning of an epoch therefore guarantees at least two hours -- and up to
# four -- during which the validator set stays nominally whole, however badly a
# node behaves. The arm takes about 80 minutes. So it fits inside the window,
# and the expulsions land afterwards, when the cluster is being shut down
# anyway.
#
# The script checks that window before starting rather than assuming it.
#
# TWO HARD LIMITS, BOTH ENFORCED RATHER THAN TRUSTED
#
#   1. NEVER validator-0. It is the boot node and the only RPC endpoint; taking
#      it down measures our loss of connectivity, not the network's tolerance of
#      a missing validator.
#   2. AT MOST ONE validator down at a time. With 8 validators over 4 shards
#      there are exactly 2 per shard -- the protocol minimum -- so two
#      simultaneous outages can leave a shard with no producer at all, which
#      measures nothing except that we broke it.
#
# Outage and gap distributions are IDENTICAL to phase 2's (15-45s down, 20-60s
# between), because the difference between the arms is supposed to be the
# architecture, not the fault schedule.
#
# USAGE
#   ./scripts/near_adversarial_nodes.sh --duration 5400 --events /tmp/near_events.tsv
#   ./scripts/near_adversarial_nodes.sh --restore
# ---------------------------------------------------------------------------
set -uo pipefail

PROJECT="project-c4c87dcb-da41-4caf-922"
DURATION=5400
EVENTS="/tmp/near_node_events.tsv"
ACTION="run"
OUTAGE_MIN=15; OUTAGE_MAX=45
GAP_MIN=20;    GAP_MAX=60

while [ $# -gt 0 ]; do
  case "$1" in
    --duration) DURATION="$2"; shift 2 ;;
    --events)   EVENTS="$2"; shift 2 ;;
    --restore)  ACTION="restore"; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

NAMES=(near-validator-0 near-validator-1 near-validator-2 near-validator-3
       near-validator-4 near-validator-5 near-validator-6 near-validator-7)
ZONES=(us-east4-c us-east4-c asia-south1-a asia-south1-a
       asia-southeast1-a asia-southeast1-a europe-west2-b europe-west2-b)
COUNT=${#NAMES[@]}

log()   { printf '\033[0;36m==>\033[0m %s\n' "$*"; }
stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }

on_node() {  # index, command
  gcloud compute ssh "${NAMES[$1]}" --zone "${ZONES[$1]}" --project "$PROJECT" \
    --command "$2" < /dev/null 2>&1 | grep -v "^Warning:"
}

if [ "$ACTION" = "restore" ]; then
  log "Restoring every validator"
  # Written out individually: a loop wrapping gcloud ssh silently fails to take
  # effect on the remote host (PHASE4_HANDOFF S2.2).
  on_node 1 "sudo systemctl start neard" >/dev/null; echo "  validator-1 started"
  on_node 2 "sudo systemctl start neard" >/dev/null; echo "  validator-2 started"
  on_node 3 "sudo systemctl start neard" >/dev/null; echo "  validator-3 started"
  on_node 4 "sudo systemctl start neard" >/dev/null; echo "  validator-4 started"
  on_node 5 "sudo systemctl start neard" >/dev/null; echo "  validator-5 started"
  on_node 6 "sudo systemctl start neard" >/dev/null; echo "  validator-6 started"
  on_node 7 "sudo systemctl start neard" >/dev/null; echo "  validator-7 started"
  exit 0
fi

# --- precondition: enough epoch left that no expulsion lands mid-arm ---------
read -r HEIGHT EPOCH_START <<<"$(gcloud compute ssh near-generator --zone us-east4-c \
  --project "$PROJECT" --command '
curl -s -m 10 -X POST http://10.40.0.10:3030 -H "Content-Type: application/json" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"validators\",\"params\":[null]}" \
  | python3 -c "import sys,json;d=json.load(sys.stdin)[\"result\"];print(d[\"epoch_start_height\"])" > /tmp/es
curl -s -m 10 -X POST http://10.40.0.10:3030 -H "Content-Type: application/json" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"status\",\"params\":[]}" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)[\"result\"][\"sync_info\"][\"latest_block_height\"])" > /tmp/h
echo "$(cat /tmp/h) $(cat /tmp/es)"' < /dev/null 2>/dev/null | tail -1)"

if [ -z "${HEIGHT:-}" ]; then
  echo "could not read chain height; refusing to start" >&2; exit 1
fi
# Expulsions decided this epoch apply two epochs out, so the set is safe until
# then. epoch_length is 3600 blocks at ~2s.
SAFE_UNTIL=$(( EPOCH_START + 2 * 3600 ))
SAFE_SECONDS=$(( (SAFE_UNTIL - HEIGHT) * 2 ))
log "height $HEIGHT, epoch started $EPOCH_START"
echo "  validator set stays whole for another ${SAFE_SECONDS}s (until block $SAFE_UNTIL)"
echo "  arm needs ${DURATION}s"
if [ "$SAFE_SECONDS" -lt "$((DURATION + 600))" ]; then
  echo "REFUSING: not enough of the expulsion window left. Wait for the next" >&2
  echo "epoch boundary and start again -- an expulsion landing mid-arm would" >&2
  echo "shrink the network permanently and make later runs incomparable." >&2
  exit 1
fi

mkdir -p "$(dirname "$EVENTS")"
: > "$EVENTS"
log "Adversarial outages for ${DURATION}s -> $EVENTS"
echo "  one validator at a time, never validator-0, ${OUTAGE_MIN}-${OUTAGE_MAX}s down"
echo

start=$(date +%s)
while true; do
  now=$(date +%s); elapsed=$(( now - start ))
  [ "$elapsed" -ge "$DURATION" ] && break

  # 1..7 only. validator-0 hosts the RPC the harness submits through.
  target=$(( (RANDOM % (COUNT - 1)) + 1 ))
  outage=$(( OUTAGE_MIN + RANDOM % (OUTAGE_MAX - OUTAGE_MIN + 1) ))
  remaining=$(( DURATION - elapsed ))
  [ "$outage" -gt "$remaining" ] && outage=$remaining
  [ "$outage" -lt 5 ] && break

  printf '%s\tvalidator-%d\toffline\tadversarial\n' "$(stamp)" "$target" >> "$EVENTS"
  on_node "$target" "sudo systemctl stop neard" >/dev/null
  printf '  [t=%04ds] validator-%d DOWN %ds\n' "$elapsed" "$target" "$outage"
  sleep "$outage"

  on_node "$target" "sudo systemctl start neard" >/dev/null
  printf '%s\tvalidator-%d\tonline\tadversarial\n' "$(stamp)" "$target" >> "$EVENTS"
  printf '  [t=%04ds] validator-%d back\n' "$(( $(date +%s) - start ))" "$target"

  gap=$(( GAP_MIN + RANDOM % (GAP_MAX - GAP_MIN + 1) ))
  remaining=$(( DURATION - ($(date +%s) - start) ))
  [ "$gap" -gt "$remaining" ] && gap=$remaining
  [ "$gap" -gt 0 ] && sleep "$gap"
done

log "Outages finished; restoring every validator"
on_node 1 "sudo systemctl start neard" >/dev/null
on_node 2 "sudo systemctl start neard" >/dev/null
on_node 3 "sudo systemctl start neard" >/dev/null
on_node 4 "sudo systemctl start neard" >/dev/null
on_node 5 "sudo systemctl start neard" >/dev/null
on_node 6 "sudo systemctl start neard" >/dev/null
on_node 7 "sudo systemctl start neard" >/dev/null
echo
log "$(wc -l < "$EVENTS") events recorded in $EVENTS"
echo "    Import them with scripts/near_import_events.py -- outage events that"
echo "    live only in a text file are events the dataset does not have, which"
echo "    is exactly what happened to phase 2 (see analysis/backfill.py)."
