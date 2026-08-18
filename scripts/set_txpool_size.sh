#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Resize the waiting room that transactions sit in before a validator puts
# them in a block, then restart the validators so the new size takes effect.
#
# WHY THIS SCRIPT EXISTS
#
# Every failure in all 140 clean Polygon runs was the same thing: the node
# refused the payment at the door with "txpool is full". It never got a
# transaction number, never used any gas, never entered the chain. So the
# 9.97% failure rate at 300/sec is a measure of how many payments could not
# get INTO the waiting room -- not of anything the chain did wrong.
#
# That raises an obvious and fair objection, and an auditor raised it: if the
# waiting room were simply bigger, would the chain get through more payments?
# If yes, the "~270 payments/sec ceiling" we published is partly a property of
# a setting we never touched, not of the architecture. That would be a
# serious problem, because the ceiling is one of the paper's headline numbers.
#
# This script is half of the experiment that answers it. It changes ONE thing
# -- the size of the waiting room -- so the same cluster can be measured twice
# and the two curves compared.
#
# WHAT THE DEFAULT IS AND WHY WE NEVER SET IT
#
# Polygon Edge ships with a default and we deliberately left every runtime
# setting alone, so the published numbers describe the software as it comes
# rather than as we tuned it. That was the right call for the main study. It
# is also exactly why this follow-up is needed.
#
# The script does not assume what the flag is called. It asks the binary
# first, and refuses to run if the flag is not there, because a flag that
# silently does not exist would produce two "different" arms that were
# actually identical -- the worst possible outcome, since it would look like
# a clean negative result.
#
# RESTARTS ARE ONE AT A TIME, ON PURPOSE
#
# Restarting all four validators together would stop the chain until enough
# of them came back. Restarting them one at a time keeps three running, which
# is enough to keep producing blocks, so the chain never actually halts.
#
# USAGE
#   ./scripts/set_txpool_size.sh --slots 4096      # the shipped default
#   ./scripts/set_txpool_size.sh --slots 32768     # eight times bigger
#   ./scripts/set_txpool_size.sh --show            # report what is set now
# ---------------------------------------------------------------------------
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_DIR="$REPO/terraform/phase2"
NODE_PREFIX="bench-p2"
SLOTS=""
ACTION="set"

while [ $# -gt 0 ]; do
  case "$1" in
    --slots) SLOTS="$2"; shift 2 ;;
    --show)  ACTION="show"; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

log() { printf '\033[0;36m==>\033[0m %s\n' "$*"; }
die() { printf '\033[0;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

cd "$TF_DIR" || die "no terraform directory at $TF_DIR"
[ -f terraform.tfstate ] || die "No cluster found. Run 'tofu apply' first."

PROJECT=$(grep -oE '"project": *"[^"]+"' terraform.tfstate | head -1 | cut -d'"' -f4)
[ -n "$PROJECT" ] || PROJECT=$(gcloud config get-value project 2>/dev/null)

ZONES=()
while IFS= read -r z; do [ -n "$z" ] && ZONES+=("$z"); done \
  < <(tofu output -json validator_zones 2>/dev/null | jq -r '.[]' 2>/dev/null || true)
COUNT=${#ZONES[@]}
[ "$COUNT" -gt 0 ] || die "could not read the validator list from terraform"

ssh_node() {
  gcloud compute ssh "${NODE_PREFIX}-validator-$1" --zone "${ZONES[$1]}" \
    --project "$PROJECT" --no-tunnel-through-iap \
    --command "$2" < /dev/null -- -o StrictHostKeyChecking=no -o LogLevel=ERROR \
    -o ConnectTimeout=60 2>/dev/null
}

# --- report mode ----------------------------------------------------------
if [ "$ACTION" = "show" ]; then
  log "Waiting-room size currently configured on each validator"
  for ((i = 0; i < COUNT; i++)); do
    line=$(ssh_node "$i" "grep -o -- '--max-slots [0-9]*' /etc/systemd/system/edge.service || echo '--max-slots UNSET(default)'")
    printf '  validator-%d  %s\n' "$i" "$line"
  done
  exit 0
fi

[ -n "$SLOTS" ] || die "give a size: --slots 4096"
case "$SLOTS" in (*[!0-9]*) die "--slots must be a whole number, got '$SLOTS'" ;; esac

# --- the flag must actually exist -----------------------------------------
#
# If it does not, the systemd unit will fail to start and the cluster goes
# down. Worse, if the binary silently ignored an unknown flag we would run
# two arms that were secretly identical and report a false negative.
log "Checking that this build of Polygon Edge has the flag at all"
HELP=$(ssh_node 0 "/usr/local/bin/polygon-edge server --help 2>&1 | grep -c -- '--max-slots' || echo 0")
HELP=$(echo "$HELP" | tr -dc '0-9')
if [ "${HELP:-0}" -lt 1 ]; then
  die "this Polygon Edge build has no --max-slots flag. The experiment cannot
  run as designed -- do NOT fall back to leaving it unset, because that would
  produce two identical arms that look like a clean negative result."
fi
echo "  present"

# --- rewrite the unit and restart, one validator at a time ----------------
log "Setting the waiting room to $SLOTS on $COUNT validators, one at a time"
for ((i = 0; i < COUNT; i++)); do
  ssh_node "$i" "sudo tee /etc/systemd/system/edge.service >/dev/null <<'UNIT'
[Unit]
Description=Polygon Edge validator
After=network-online.target

[Service]
Type=simple
User=edge
ExecStart=/usr/local/bin/polygon-edge server \
  --data-dir /var/lib/edge/data \
  --chain /var/lib/edge/genesis.json \
  --grpc-address 0.0.0.0:9632 \
  --libp2p 0.0.0.0:1478 \
  --jsonrpc 0.0.0.0:8545 \
  --max-slots $SLOTS \
  --seal
Restart=on-failure
RestartSec=5
LimitNOFILE=65535
StandardOutput=append:/var/log/edge/node.log
StandardError=append:/var/log/edge/node.log

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload && sudo systemctl restart edge.service" >/dev/null

  # Confirm this one is actually running before touching the next, so a bad
  # setting takes down one validator rather than all four.
  state=$(ssh_node "$i" "systemctl is-active edge.service")
  printf '  validator-%d  %s\n' "$i" "$state"
  if [ "$state" != "active" ]; then
    die "validator-$i did not come back up. Stopping here so the other
  validators stay running. Check: sudo journalctl -u edge -n 40"
  fi
done

# --- the chain must still be moving ---------------------------------------
#
# Four validators that are each "active" can still fail to agree with each
# other. The only real proof is the block number going up.
log "Confirming the chain is still producing blocks"
read_height() {
  ssh_node 0 "curl -s -X POST -H 'Content-Type: application/json' \
    --data '{\"jsonrpc\":\"2.0\",\"method\":\"eth_blockNumber\",\"params\":[],\"id\":1}' \
    http://localhost:8545 | sed -n 's/.*\"result\":\"\\([^\"]*\\)\".*/\\1/p'"
}
h1=$(read_height)
sleep 20
h2=$(read_height)
d1=$((h1)); d2=$((h2))
echo "  block $d1 -> $d2 over 20 seconds"
if [ "$d2" -le "$d1" ]; then
  die "the chain stopped producing blocks after the change. Put the default
  back with: ./scripts/set_txpool_size.sh --slots 4096"
fi

log "Waiting room is now $SLOTS on every validator, chain healthy"
