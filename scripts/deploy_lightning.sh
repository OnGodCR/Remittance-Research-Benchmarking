#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Creates every LND wallet and writes the endpoint map the funding script and
# the harness both read.
#
# Runs from the laptop. Talks to each host over `gcloud compute ssh`, because
# the LND REST ports are firewalled to the operator IP and the macaroons live
# on the hosts' disks.
#
# NEVER nest quotes through `gcloud compute ssh --command` (RESUME_HERE.md S5
# trap 5): three shell layers mangle escapes silently. The wallet logic is a
# file, copied over and executed.
#
# Output: keys/lightning_endpoints.json  {node_id: {url, macaroon}}
#         gitignored -- macaroons are credentials.
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/.."

PROJECT="$(grep -E '^project_id' terraform/phase3/terraform.tfvars | cut -d'"' -f2)"
NODES_PER_HOST="${1:-5}"

HOSTS=(ln-host-0 ln-host-1 ln-host-2 ln-host-3)
ZONES=(us-east4-c asia-south1-a asia-southeast1-a europe-west2-b)

mkdir -p keys

echo "waiting for startup scripts to install bitcoind and LND..."
for i in "${!HOSTS[@]}"; do
  for attempt in $(seq 1 60); do
    if gcloud compute ssh "${HOSTS[$i]}" --zone "${ZONES[$i]}" --project "$PROJECT" \
         --command "test -x /usr/local/bin/lnd" 2>/dev/null; then
      echo "  ${HOSTS[$i]}: LND installed"
      break
    fi
    [ "$attempt" -eq 60 ] && { echo "  ${HOSTS[$i]}: LND never appeared"; exit 1; }
    sleep 15
  done
done

# --- initial blocks, BEFORE any wallet is created -------------------------
#
# A fresh regtest chain holds only the genesis block, and LND will not reach
# SERVER_ACTIVE against a chain it considers unsynced -- it sits at RPC_ACTIVE
# indefinitely. That reads as "the node is broken" when the node is fine and
# the chain is simply empty. Mining past coinbase maturity first also means the
# funding step has spendable coins waiting.
echo
echo "mining initial blocks..."
gcloud compute ssh "${HOSTS[0]}" --zone "${ZONES[0]}" --project "$PROJECT" --command '
CLI="sudo /usr/local/bin/bitcoin-cli -datadir=/opt/lightning/bitcoind -conf=/opt/lightning/bitcoind/bitcoin.conf"
$CLI createwallet bench 2>/dev/null || $CLI loadwallet bench 2>/dev/null || true
# 320 blocks, not 101. A coinbase output needs 100 confirmations before it can
# be spent, so at height 101 exactly one block has matured -- 50 BTC, against
# the ~1,500 BTC the well-capitalised topology needs. Mining to 320 leaves the
# first 220 blocks mature, which at the early 50 BTC subsidy is ample.
if [ "$($CLI getblockcount)" -lt 320 ]; then
  $CLI generatetoaddress 320 "$($CLI getnewaddress)" >/dev/null
fi
echo "  block height: $($CLI getblockcount)"' 2>/dev/null

echo
echo "creating wallets..."
: > /tmp/ln_macaroons.txt
for i in "${!HOSTS[@]}"; do
  gcloud compute scp scripts/create_wallets.sh "${HOSTS[$i]}:/tmp/create_wallets.sh" \
    --zone "${ZONES[$i]}" --project "$PROJECT" >/dev/null
  echo "  ${HOSTS[$i]} ..."
  gcloud compute ssh "${HOSTS[$i]}" --zone "${ZONES[$i]}" --project "$PROJECT" \
    --command "chmod +x /tmp/create_wallets.sh && sudo /tmp/create_wallets.sh $NODES_PER_HOST" \
    2>/dev/null | sed "s/^/$i /" >> /tmp/ln_macaroons.txt
done

echo
echo "assembling endpoint map..."
.venv/bin/python scripts/build_endpoints.py \
  --macaroons /tmp/ln_macaroons.txt \
  --out keys/lightning_endpoints.json
rm -f /tmp/ln_macaroons.txt

echo
echo "next: .venv/bin/python scripts/lightning_bootstrap.py \\"
echo "        --endpoints keys/lightning_endpoints.json"
