#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Full Lightning bring-up, from bare instances to a running sweep.
#
# Exists because the cluster has now been rebuilt three times: changing the
# startup script forces GCP to replace the instances, which takes the chain and
# the funded topology with them. Every fix learned along the way is baked into
# terraform/phase3/scripts/lightning_setup.sh, so this should now run clean:
#
#   bitcoin.conf network options under [regtest]   (bitcoind restart-looped)
#   ZMQ ports 28332-28333 open                     (remote nodes saw no blocks)
#   maxchansize raised                             (large opens refused by peer)
#   auto-unlock + heartbeat services               (spot locks, idle shutdowns)
#   funding by transfer, not mining                (subsidy halves to nothing)
# ---------------------------------------------------------------------------
set -uo pipefail
cd "$(dirname "$0")/.."
P=remittances-benchmarking
HOSTS=(ln-host-0 ln-host-1 ln-host-2 ln-host-3)
ZONES=(us-east4-c asia-south1-a asia-southeast1-a europe-west2-b)
SSH="gcloud compute ssh --strict-host-key-checking=no --project $P"
SCP="gcloud compute scp --strict-host-key-checking=no --quiet --project $P"

echo "[1/6] waiting for LND on every host"
for i in 0 1 2 3; do
  for a in $(seq 1 80); do
    $SSH "${HOSTS[$i]}" --zone "${ZONES[$i]}" --command "test -x /usr/local/bin/lnd" 2>/dev/null && break
    sleep 15
  done
  echo "  ${HOSTS[$i]} ready"
done

echo "[2/6] installing auto-unlock and heartbeat"
for i in 0 1 2 3; do
  $SCP scripts/install_autounlock.sh "${HOSTS[$i]}:/tmp/au.sh" --zone "${ZONES[$i]}" >/dev/null 2>&1
  $SSH "${HOSTS[$i]}" --zone "${ZONES[$i]}" --command "sudo bash /tmp/au.sh 5" 2>/dev/null | tail -1
done

echo "[3/6] creating wallets and endpoint map"
rm -f keys/lightning_endpoints.json
bash scripts/deploy_lightning.sh 5 2>&1 | tail -3

echo "[4/6] deploying harness to the generator"
bash scripts/deploy_lightning_generator.sh 2>&1 | tail -2
$SCP keys/lightning_endpoints.json ln-generator:/tmp/eps.json --zone us-east4-c >/dev/null 2>&1
$SSH ln-generator --zone us-east4-c --command "sudo cp /tmp/eps.json /opt/benchmark/keys/lightning_endpoints.json" 2>/dev/null

echo "[5/6] funding topology at the well-capitalised scale"
$SSH ln-generator --zone us-east4-c --command \
  "cd /opt/benchmark && ./.venv/bin/python scripts/lightning_bootstrap.py \
   --endpoints keys/lightning_endpoints.json --out config/phase3.json --scale 200 2>&1 \
   | grep -vE 'Deprecation|auth =|async with|path =' | tail -8" 2>/dev/null

echo "[6/6] verification run"
$SSH ln-generator --zone us-east4-c --command \
  "cd /opt/benchmark && ./.venv/bin/python -m harness.cli run --config config/phase3.json \
   --tps 10 --amount 200 --window 60 --phase phase-3-smoke 2>&1 | tail -2" 2>/dev/null

echo "DONE"
