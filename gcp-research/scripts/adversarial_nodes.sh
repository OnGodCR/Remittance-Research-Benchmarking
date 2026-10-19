#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Realism technique #6: adversarial / unreliable nodes.
#
# Takes validators offline intermittently during a run and logs exactly when
# and which, so performance dips can be correlated against specific failures.
#
# WHY THIS RUNS AS A SEPARATE ARM, NOT FOLDED INTO EVERY TEST
#
# If node failures were injected into every configuration, we could never
# separate "degrades under load" from "degrades under node failure". The clean
# baseline is what makes the adversarial data interpretable at all -- the
# finding is the DIFFERENCE between the two arms at the same load, and that
# difference does not exist without a clean comparison. Scoped to 3 load
# levels x $200 x 5 repeats per architecture (claude.md S5 #6).
#
# WHY THE FAILURE RATE IS CAPPED
#
# Byzantine fault tolerance survives fewer than a third of nodes failing. With
# four validators that means AT MOST ONE may be down at a time -- two and the
# chain halts entirely, which measures nothing except that we broke it.
# The script enforces this rather than trusting the percentage.
#
# CRITICALLY: every event is timestamped and logged. A node outage looks
# identical to a cloud provider reclaiming a spot instance, and conflating the
# two would corrupt exactly the comparison this arm exists to make.
#
# USAGE
#   ./scripts/adversarial_nodes.sh --phase phase2 --duration 300
#   ./scripts/adversarial_nodes.sh --phase phase2 --restore
# ---------------------------------------------------------------------------
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PHASE="phase2"
DURATION=300
ACTION="run"
OUTAGE_MIN=15      # shortest outage, seconds
OUTAGE_MAX=45      # longest outage, seconds
GAP_MIN=20         # shortest gap between outages
GAP_MAX=60

while [ $# -gt 0 ]; do
  case "$1" in
    --phase)    PHASE="$2"; shift 2 ;;
    --duration) DURATION="$2"; shift 2 ;;
    --restore)  ACTION="restore"; shift ;;
    *) echo "unknown argument: $1" >&2; exit 1 ;;
  esac
done

TF_DIR="$REPO/terraform/$PHASE"
NODE_PREFIX="bench-p2"
[ "$PHASE" = "phase1" ] && NODE_PREFIX="bench-p1"
EVENT_LOG="$REPO/data/working/node_events_$(date -u +%Y%m%dT%H%M%SZ).log"

log() { printf '\033[0;36m==>\033[0m %s\n' "$*"; }
die() { printf '\033[0;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

cd "$TF_DIR"
[ -f terraform.tfstate ] || die "No cluster found. Run 'tofu apply' first."

PROJECT=$(grep -oE '"project": *"[^"]+"' terraform.tfstate | head -1 | cut -d'"' -f4)
[ -n "$PROJECT" ] || PROJECT=$(gcloud config get-value project 2>/dev/null)

ZONES=()
while IFS= read -r z; do [ -n "$z" ] && ZONES+=("$z"); done \
  < <(tofu output -json validator_zones 2>/dev/null | jq -r '.[]' 2>/dev/null || true)
if [ ${#ZONES[@]} -eq 0 ]; then
  single=$(tofu output -raw zone)
  n=$(tofu output -json validator_private_ips | jq 'length')
  for ((i = 0; i < n; i++)); do ZONES+=("$single"); done
fi
COUNT=${#ZONES[@]}

# Byzantine tolerance: strictly fewer than a third may be down. Four
# validators tolerate one. Enforced rather than assumed.
MAX_DOWN=$(( (COUNT - 1) / 3 ))
[ "$MAX_DOWN" -lt 1 ] && MAX_DOWN=1

ssh_node() {
  gcloud compute ssh "${NODE_PREFIX}-validator-$1" --zone "${ZONES[$1]}" \
    --project "$PROJECT" --no-tunnel-through-iap \
    --command "$2" -- -o StrictHostKeyChecking=no -o LogLevel=ERROR 2>/dev/null
}

# Second precision, no fractional part. `%3N` is a GNU extension that the
# remote `date` does not implement, and it silently emitted the literal
# characters "3N" instead -- producing timestamps no parser accepts. Outages
# last 15-45 seconds, so seconds are ample.
stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }

record() {
  # node_id, event, source -- matching the node_events table so this merges
  # straight into the dataset alongside the payment records.
  printf '%s\t%s\t%s\t%s\n' "$(stamp)" "$1" "$2" "adversarial" | tee -a "$EVENT_LOG"
}

if [ "$ACTION" = "restore" ]; then
  log "Restoring all validators"
  for ((i = 0; i < COUNT; i++)); do
    ssh_node "$i" "sudo systemctl start edge" || true
    printf '  validator-%d started\n' "$i"
  done
  exit 0
fi

mkdir -p "$(dirname "$EVENT_LOG")"
log "Adversarial arm: $COUNT validators, at most $MAX_DOWN down at once, ${DURATION}s"
echo "  events -> $EVENT_LOG"
echo

start=$(date +%s)
while true; do
  now=$(date +%s)
  elapsed=$(( now - start ))
  [ "$elapsed" -ge "$DURATION" ] && break

  # Never validator 0: it hosts the endpoint the harness submits through, so
  # taking it down would measure our loss of connectivity rather than the
  # network's tolerance of a missing validator.
  target=$(( (RANDOM % (COUNT - 1)) + 1 ))
  outage=$(( OUTAGE_MIN + RANDOM % (OUTAGE_MAX - OUTAGE_MIN + 1) ))
  remaining=$(( DURATION - elapsed ))
  [ "$outage" -gt "$remaining" ] && outage=$remaining
  [ "$outage" -lt 5 ] && break

  record "validator-$target" "offline"
  ssh_node "$target" "sudo systemctl stop edge" || true
  printf '  [t=%03ds] validator-%d DOWN for %ds\n' "$elapsed" "$target" "$outage"

  sleep "$outage"

  ssh_node "$target" "sudo systemctl start edge" || true
  record "validator-$target" "online"
  printf '  [t=%03ds] validator-%d back up\n' "$(( $(date +%s) - start ))" "$target"

  gap=$(( GAP_MIN + RANDOM % (GAP_MAX - GAP_MIN + 1) ))
  now=$(date +%s)
  remaining=$(( DURATION - (now - start) ))
  [ "$gap" -gt "$remaining" ] && gap=$remaining
  [ "$gap" -gt 0 ] && sleep "$gap"
done

log "Adversarial arm complete. Restoring any stopped validators."
for ((i = 0; i < COUNT; i++)); do
  ssh_node "$i" "sudo systemctl start edge" >/dev/null 2>&1 || true
done

echo
log "Event log: $EVENT_LOG"
echo "    Import alongside the payment data so dips can be attributed to"
echo "    specific outages rather than guessed at."
