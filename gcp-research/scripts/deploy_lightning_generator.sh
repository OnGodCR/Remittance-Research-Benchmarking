#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Put the harness on the generator and prepare it to run against Lightning.
#
# Separate from deploy_harness.sh, which is coupled to Polygon's chain outputs
# (chain_id, rpc_url) that have no Lightning equivalent.
#
# WHY THE HARNESS RUNS ON THE GENERATOR AT ALL
#
# Phase 1 ran it from the laptop and it reported saturation at 5 payments per
# second -- against 300 locally. Nothing was wrong with the harness; every
# submission was paying an intercontinental round trip. A saturated generator
# means the measured ceiling is our tooling rather than the network, so the
# harness must sit inside the VPC. The LND REST endpoints are on private
# addresses for the same reason: they are not reachable from outside.
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="$(pwd)"

PROJECT="$(grep -E '^project_id' terraform/phase3/terraform.tfvars | cut -d'"' -f2)"
GENERATOR="ln-generator"
ZONE="us-east4-c"

echo "packaging harness..."
TARBALL=/tmp/ln_harness.tar.gz
tar -czf "$TARBALL" harness scripts analysis config keys/lightning_endpoints.json requirements.txt 2>/dev/null

echo "waiting for the generator to finish booting..."
for attempt in $(seq 1 40); do
  gcloud compute ssh "$GENERATOR" --zone "$ZONE" --project "$PROJECT" \
    --command "test -d /opt/benchmark || sudo mkdir -p /opt/benchmark" 2>/dev/null && break
  [ "$attempt" -eq 40 ] && { echo "generator never became reachable"; exit 1; }
  sleep 15
done

echo "copying..."
gcloud compute scp "$TARBALL" "$GENERATOR:/tmp/harness.tar.gz" \
  --zone "$ZONE" --project "$PROJECT" --quiet >/dev/null

gcloud compute scp scripts/generator_prepare.sh "$GENERATOR:/tmp/prepare.sh" \
  --zone "$ZONE" --project "$PROJECT" --quiet >/dev/null

echo "installing..."
gcloud compute ssh "$GENERATOR" --zone "$ZONE" --project "$PROJECT" \
  --command "chmod +x /tmp/prepare.sh && sudo /tmp/prepare.sh" 2>/dev/null

echo
echo "harness ready on $GENERATOR"
