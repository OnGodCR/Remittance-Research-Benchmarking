#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Start the private blockchain.
#
# WHY THIS IS A SEPARATE STEP
#
# A Byzantine fault-tolerant network needs every validator to agree on who the
# validators are, before any of them starts. That list has to exist in a shared
# startup file, which means somebody must collect all the identities first.
# Machines booting independently cannot do that for each other, so this runs
# once from your laptop after the cluster is up.
#
# Splitting it out also means a failed start can be retried without paying to
# rebuild the machines.
#
# WHICH CONSENSUS, AND WHY
#
# This uses IBFT proof-of-authority rather than PolyBFT. PolyBFT requires a
# second "root" blockchain to anchor to, which would mean deploying and
# measuring a bridge as well as the sidechain -- and the study is about the
# sidechain's own settlement performance, not about bridge latency. IBFT
# isolates what we actually want to measure.
#
# It costs us nothing on the finality claim: IBFT is also deterministically
# final, so a committed block is settled, which is what ANALYSIS_PLAN.md S6.1
# fixes at one confirmation.
#
# USAGE
#   ./scripts/bootstrap_cluster.sh
#
# Requires: gcloud authenticated, cluster already created with `tofu apply`.
# ---------------------------------------------------------------------------
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_DIR="$REPO/terraform/phase1"
KEYS_DIR="$REPO/keys"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

BLOCK_GAS_LIMIT=30000000
PREMINE_BALANCE="1000000000000000000000000"   # 1,000,000 native coin

log()  { printf '\033[0;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[0;33mwarning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[0;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

command -v gcloud >/dev/null || die "gcloud not found."
command -v tofu   >/dev/null || die "tofu not found."
command -v jq     >/dev/null || die "jq not found. Install with: brew install jq"

# --- read the cluster layout ----------------------------------------------
cd "$TF_DIR"
[ -f terraform.tfstate ] || die "No cluster found. Run 'tofu apply' in $TF_DIR first."

ZONE=$(tofu output -raw zone 2>/dev/null || grep -oE '"zone": *"[^"]+"' terraform.tfstate | head -1 | cut -d'"' -f4)
CHAIN_ID=$(tofu output -raw chain_id)
mapfile -t PRIVATE_IPS < <(tofu output -json validator_private_ips | jq -r '.[]')
COUNT=${#PRIVATE_IPS[@]}
[ "$COUNT" -ge 4 ] || die "Need at least 4 validators for Byzantine fault tolerance, found $COUNT."

log "Cluster: $COUNT validators, chain id $CHAIN_ID, zone $ZONE"

names=()
for ((i = 0; i < COUNT; i++)); do names+=("bench-p1-validator-$i"); done

ssh_node() {
  gcloud compute ssh "$1" --zone "$ZONE" --tunnel-through-iap=false \
    --command "$2" -- -o StrictHostKeyChecking=no -o LogLevel=ERROR 2>/dev/null
}

# --- wait for setup to finish ---------------------------------------------
log "Waiting for validator setup to complete (installs the blockchain software)..."
for name in "${names[@]}"; do
  for attempt in $(seq 1 60); do
    if ssh_node "$name" "test -f /var/lib/edge/identity.json" 2>/dev/null; then
      printf '  %s ready\n' "$name"; break
    fi
    [ "$attempt" -eq 60 ] && die "$name never finished setup. Check /var/log/validator-setup.log on it."
    sleep 10
  done
done

# --- collect identities ---------------------------------------------------
log "Collecting validator identities..."
declare -a ADDRS NODE_IDS
for ((i = 0; i < COUNT; i++)); do
  identity=$(ssh_node "${names[$i]}" "cat /var/lib/edge/identity.json")
  ADDRS[i]=$(echo "$identity" | jq -r '.address')
  NODE_IDS[i]=$(echo "$identity" | jq -r '.node_id')
  [ -n "${ADDRS[$i]}" ] && [ "${ADDRS[$i]}" != "null" ] \
    || die "Could not read an address from ${names[$i]}."
  printf '  %s  %s\n' "${names[$i]}" "${ADDRS[$i]}"
done

# --- funder account -------------------------------------------------------
# Holds the entire premined supply and pays for deploying the token and
# funding the sender wallets. Generated once and reused, so a rebuilt cluster
# keeps the same funder.
mkdir -p "$KEYS_DIR"
FUNDER_KEY_FILE="$KEYS_DIR/funder.txt"
if [ ! -f "$FUNDER_KEY_FILE" ]; then
  log "Generating the funding account..."
  "$REPO/.venv/bin/python" - "$FUNDER_KEY_FILE" <<'PY'
import sys, secrets
from eth_account import Account
acct = Account.from_key(secrets.token_bytes(32))
open(sys.argv[1], "w").write(f"{acct.key.hex()}\n{acct.address}\n")
PY
  chmod 600 "$FUNDER_KEY_FILE"
fi
FUNDER_KEY=$(sed -n 1p "$FUNDER_KEY_FILE")
FUNDER_ADDR=$(sed -n 2p "$FUNDER_KEY_FILE")
log "Funding account: $FUNDER_ADDR"

# --- build the shared startup file ----------------------------------------
# Done on validator 0 because that machine already has the software.
log "Writing the shared genesis file..."

validator_flags=""
for addr in "${ADDRS[@]}"; do
  validator_flags+=" --ibft-validator ${addr}"
done

bootnode_flags=""
for ((i = 0; i < COUNT && i < 3; i++)); do
  bootnode_flags+=" --bootnode /ip4/${PRIVATE_IPS[$i]}/tcp/1478/p2p/${NODE_IDS[$i]}"
done

ssh_node "${names[0]}" "sudo -u edge /usr/local/bin/polygon-edge genesis \
  --dir /var/lib/edge/genesis.json \
  --consensus ibft \
  --chain-id ${CHAIN_ID} \
  --block-gas-limit ${BLOCK_GAS_LIMIT} \
  --premine ${FUNDER_ADDR}:${PREMINE_BALANCE} \
  ${validator_flags} ${bootnode_flags} --force" \
  || die "Genesis creation failed. Check /var/log/validator-setup.log on ${names[0]}."

log "Distributing genesis to the other validators..."
ssh_node "${names[0]}" "cat /var/lib/edge/genesis.json" > "$WORK/genesis.json"
[ -s "$WORK/genesis.json" ] || die "Genesis file came back empty."

for ((i = 1; i < COUNT; i++)); do
  gcloud compute scp "$WORK/genesis.json" "${names[$i]}:/tmp/genesis.json" \
    --zone "$ZONE" --quiet >/dev/null 2>&1 \
    || die "Could not copy genesis to ${names[$i]}."
  ssh_node "${names[$i]}" "sudo mv /tmp/genesis.json /var/lib/edge/genesis.json && \
    sudo chown edge:edge /var/lib/edge/genesis.json"
  printf '  %s\n' "${names[$i]}"
done

# --- start the validators -------------------------------------------------
log "Starting validators..."
for ((i = 0; i < COUNT; i++)); do
  ssh_node "${names[$i]}" "sudo tee /etc/systemd/system/edge.service >/dev/null <<'UNIT'
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
  --seal
Restart=on-failure
RestartSec=5
LimitNOFILE=65535
StandardOutput=append:/var/log/edge/node.log
StandardError=append:/var/log/edge/node.log

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload && sudo systemctl enable --now edge.service"
  printf '  %s started\n' "${names[$i]}"
done

# --- verify it is actually producing blocks -------------------------------
# A cluster that starts but never agrees on anything looks fine from the
# outside. The only real proof is the block number going up.
log "Waiting for the chain to produce blocks..."
RPC="http://${PRIVATE_IPS[0]}:8545"
first_block=""
for attempt in $(seq 1 30); do
  sleep 5
  height=$(ssh_node "${names[0]}" \
    "curl -s -X POST -H 'Content-Type: application/json' \
     --data '{\"jsonrpc\":\"2.0\",\"method\":\"eth_blockNumber\",\"params\":[],\"id\":1}' \
     http://localhost:8545" | jq -r '.result // empty' 2>/dev/null || echo "")

  if [ -n "$height" ]; then
    current=$((height))
    if [ -z "$first_block" ]; then
      first_block=$current
      printf '  chain is alive at block %d, confirming it advances...\n' "$current"
    elif [ "$current" -gt "$first_block" ]; then
      log "Chain is producing blocks (now at $current). Consensus is working."
      break
    fi
  fi
  [ "$attempt" -eq 30 ] && die "Chain never produced blocks. Check /var/log/edge/node.log on the validators."
done

cat <<EOF

$(log "Cluster is live.")

  RPC endpoint : $RPC
  Chain ID     : $CHAIN_ID
  Validators   : $COUNT
  Funder       : $FUNDER_ADDR (key in keys/funder.txt, never committed)

Next:

  1. Deploy the test dollar and prepare the wallets:

       .venv/bin/python -m scripts.deploy_and_fund \\
         --rpc-url $RPC --chain-id $CHAIN_ID \\
         --funder-key \$(sed -n 1p keys/funder.txt) --senders 46

  2. Run the Phase 1 validation test:

       .venv/bin/python -m harness.cli run \\
         --config config/phase1.json --tps 5 --window 300 --amount 200

REMINDER: run 'tofu destroy' when finished. The automatic shutdown stops the
machines but does not delete their disks, which keep billing.
EOF
