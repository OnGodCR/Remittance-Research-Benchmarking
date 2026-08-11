#!/usr/bin/env bash
# Put the harness on the NEAR generator and prepare its environment.
set -uo pipefail
cd "$(dirname "$0")/.."
PROJECT="$(grep -E '^project_id' terraform/phase4/terraform.tfvars | cut -d'"' -f2)"
GEN=near-generator; ZONE=us-east4-c
SSH="gcloud compute ssh --strict-host-key-checking=no --project $PROJECT"
SCP="gcloud compute scp --strict-host-key-checking=no --quiet --project $PROJECT"

echo "packaging..."
tar -czf /tmp/near_harness.tar.gz harness scripts analysis config requirements.txt 2>/dev/null

for a in $(seq 1 40); do
  $SSH "$GEN" --zone "$ZONE" --command "sudo mkdir -p /opt/benchmark" 2>/dev/null && break
  sleep 15
done

$SCP /tmp/near_harness.tar.gz "$GEN:/tmp/harness.tar.gz" --zone "$ZONE" >/dev/null 2>&1
$SCP scripts/near_generator_prepare.sh "$GEN:/tmp/prepare.sh" --zone "$ZONE" >/dev/null 2>&1
$SSH "$GEN" --zone "$ZONE" --command "chmod +x /tmp/prepare.sh && sudo /tmp/prepare.sh" 2>/dev/null
