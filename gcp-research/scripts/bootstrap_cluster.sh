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

# Which deployment to bootstrap. Phase 1 is single-region; Phase 2 onward
# spreads validators across regions, which means each machine lives in a
# different zone and every remote command must name the right one.
PHASE="phase1"
while [ $# -gt 0 ]; do
  case "$1" in
    --phase) PHASE="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 1 ;;
  esac
done

TF_DIR="$REPO/terraform/$PHASE"
NODE_PREFIX="bench-p1"
[ "$PHASE" = "phase2" ] && NODE_PREFIX="bench-p2"
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

# Read the project from the deployment itself rather than relying on gcloud's
# global setting, which can be unset or pointed elsewhere.
PROJECT=$(grep -oE '"project": *"[^"]+"' terraform.tfstate | head -1 | cut -d'"' -f4)
[ -n "$PROJECT" ] || PROJECT=$(gcloud config get-value project 2>/dev/null)
[ -n "$PROJECT" ] || die "Could not determine the GCP project."
# Portable array read. `mapfile` would be cleaner but is bash 4+, and macOS
# still ships bash 3.2 -- this script has to run on the operator's laptop.
PRIVATE_IPS=()
while IFS= read -r ip; do
  [ -n "$ip" ] && PRIVATE_IPS+=("$ip")
done < <(tofu output -json validator_private_ips | jq -r '.[]')
COUNT=${#PRIVATE_IPS[@]}
[ "$COUNT" -ge 4 ] || die "Need at least 4 validators for Byzantine fault tolerance, found $COUNT."

# Per-validator zones. Phase 1 has them all in one zone; from Phase 2 each
# validator sits in a different region. Naming the wrong zone makes gcloud
# report the machine as nonexistent, which this script would read as "not
# ready yet" and loop on until timeout -- so the mapping has to be exact.
ZONES=()
while IFS= read -r z; do
  [ -n "$z" ] && ZONES+=("$z")
done < <(tofu output -json validator_zones 2>/dev/null | jq -r '.[]' 2>/dev/null || true)
if [ ${#ZONES[@]} -ne "$COUNT" ]; then
  # Phase 1 has no validator_zones output; everything is in one zone.
  ZONES=()
  for ((i = 0; i < COUNT; i++)); do ZONES+=("$ZONE"); done
fi

log "Cluster: $COUNT validators, chain id $CHAIN_ID ($PHASE)"
for ((i = 0; i < COUNT; i++)); do
  printf '  validator-%d  %-20s %s\n' "$i" "${ZONES[$i]}" "${PRIVATE_IPS[$i]}"
done

names=()
for ((i = 0; i < COUNT; i++)); do names+=("${NODE_PREFIX}-validator-$i"); done

# Takes an INDEX, not a name, so the correct zone is always paired with the
# correct machine.
#
# NOTE: --tunnel-through-iap is a switch, not a key=value flag. Writing
# `--tunnel-through-iap=false` makes gcloud reject the whole command, and
# because failures here are swallowed the caller just sees "not ready yet"
# and loops until timeout -- ten minutes of billing for nothing.
ssh_node() {
  local idx="$1"
  gcloud compute ssh "${names[$idx]}" --zone "${ZONES[$idx]}" --project "$PROJECT" \
    --no-tunnel-through-iap \
    --command "$2" -- -o StrictHostKeyChecking=no -o LogLevel=ERROR 2>/dev/null
}

# --- wait for setup to finish ---------------------------------------------
log "Waiting for validator setup to complete (installs the blockchain software)..."
for ((i = 0; i < COUNT; i++)); do
  for attempt in $(seq 1 60); do
    if ssh_node "$i" "test -f /var/lib/edge/identity.json" 2>/dev/null; then
      printf '  %s ready\n' "${names[$i]}"; break
    fi
    [ "$attempt" -eq 60 ] && die "${names[$i]} never finished setup. Check /var/log/validator-setup.log on it."
    sleep 10
  done
done

# --- collect identities ---------------------------------------------------
log "Collecting validator identities..."
declare -a ADDRS NODE_IDS BLS_KEYS
for ((i = 0; i < COUNT; i++)); do
  identity=$(ssh_node "$i" "cat /var/lib/edge/identity.json")
  ADDRS[i]=$(echo "$identity" | jq -r '.address')
  NODE_IDS[i]=$(echo "$identity" | jq -r '.node_id')
  BLS_KEYS[i]=$(echo "$identity" | jq -r '.bls')
  [ -n "${ADDRS[$i]}" ] && [ "${ADDRS[$i]}" != "null" ] \
    || die "Could not read an address from ${names[$i]}."
  [ -n "${BLS_KEYS[$i]}" ] && [ "${BLS_KEYS[$i]}" != "null" ] \
    || die "Could not read a BLS key from ${names[$i]}."
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

# Flag names verified against polygon-edge v1.3.2 on 8 Aug 2026. Earlier
# documentation refers to `--ibft-validator`, which no longer exists; the flag
# is `--validators`, and with the default BLS validator type each entry is
# <ECDSA address>:<BLS public key>. There is no `--force` flag either.
validator_flags=""
for ((i = 0; i < COUNT; i++)); do
  validator_flags+=" --validators ${ADDRS[$i]}:${BLS_KEYS[$i]}"
done

bootnode_flags=""
for ((i = 0; i < COUNT && i < 3; i++)); do
  bootnode_flags+=" --bootnode /ip4/${PRIVATE_IPS[$i]}/tcp/1478/p2p/${NODE_IDS[$i]}"
done

# Must run from a directory the `edge` user can read: with no explicit
# validators path the command falls back to reading the working directory,
# and a permission error there is reported as a confusing "failed to read
# from prefix" rather than as a permissions problem.
ssh_node 0 "sudo rm -f /var/lib/edge/genesis.json; \
  sudo -u edge bash -c 'cd /var/lib/edge && /usr/local/bin/polygon-edge genesis \
  --dir /var/lib/edge/genesis.json \
  --consensus ibft \
  --chain-id ${CHAIN_ID} \
  --block-gas-limit ${BLOCK_GAS_LIMIT} \
  --premine ${FUNDER_ADDR}:${PREMINE_BALANCE} \
  ${validator_flags} ${bootnode_flags}'" \
  || die "Genesis creation failed. Check /var/log/validator-setup.log on ${names[0]}."

log "Distributing genesis to the other validators..."
# `sudo` is required: the genesis file is written 0660 owned by the edge user,
# so the SSH login account cannot read it. Without sudo this returns nothing
# and every validator starts against an empty chain definition.
ssh_node 0 "sudo cat /var/lib/edge/genesis.json" > "$WORK/genesis.json"
[ -s "$WORK/genesis.json" ] || die "Genesis file came back empty -- check permissions on ${names[0]}."
jq -e . "$WORK/genesis.json" >/dev/null 2>&1 || die "Genesis file is not valid JSON."
log "  genesis is $(wc -c < "$WORK/genesis.json" | tr -d ' ') bytes"

for ((i = 1; i < COUNT; i++)); do
  gcloud compute scp "$WORK/genesis.json" "${names[$i]}:/tmp/genesis.json" \
    --zone "${ZONES[$i]}" --project "$PROJECT" --quiet 2>&1 | tail -2
  ssh_node "$i" "sudo mv /tmp/genesis.json /var/lib/edge/genesis.json && \
    sudo chown edge:edge /var/lib/edge/genesis.json && \
    sudo chmod 0640 /var/lib/edge/genesis.json"
  size=$(ssh_node "$i" "sudo stat -c %s /var/lib/edge/genesis.json 2>/dev/null || echo 0")
  [ "$size" -gt 100 ] || die "Genesis did not arrive on ${names[$i]} (got $size bytes)."
  printf '  %s ok (%s bytes)\n' "${names[$i]}" "$size"
done

# --- start the validators -------------------------------------------------
log "Starting validators..."
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
  height=$(ssh_node 0 \
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
