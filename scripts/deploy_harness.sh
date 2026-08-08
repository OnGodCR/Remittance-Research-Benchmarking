#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Put the measurement program on the generator machine and prepare it to run.
#
# WHY THIS EXISTS
#
# Phase 1 was run from the laptop, across the public internet to the cloud.
# The harness reported itself saturated at 5 payments per second, with 204ms
# of scheduling lag -- against 300 per second at 1.1ms when tested locally.
# Nothing was wrong with the harness. Every submission was simply paying an
# intercontinental round trip.
#
# That distinction matters enormously. A saturated generator means the
# measured ceiling belongs to our tooling rather than to the blockchain, and
# any throughput number produced that way is worthless. So the harness runs
# on a machine inside the same region as the validators, where a round trip
# is under a millisecond.
#
# The generator is a separate machine from the validators on purpose: sharing
# would let the load generator compete with consensus for processor time, and
# a slowdown could then be either the chain saturating or our own tool
# starving it -- with no way to tell which.
#
# USAGE
#   ./scripts/deploy_harness.sh
#
# Requires: cluster already built (`tofu apply`) and started
# (`bootstrap_cluster.sh`).
# ---------------------------------------------------------------------------
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PHASE="phase1"
while [ $# -gt 0 ]; do
  case "$1" in
    --phase) PHASE="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 1 ;;
  esac
done

TF_DIR="$REPO/terraform/$PHASE"
GENERATOR="bench-p1-generator"
[ "$PHASE" = "phase2" ] && GENERATOR="bench-p2-generator"
REMOTE_DIR="/opt/benchmark"

log()  { printf '\033[0;36m==>\033[0m %s\n' "$*"; }
die()  { printf '\033[0;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

command -v gcloud >/dev/null || die "gcloud not found."
command -v jq     >/dev/null || die "jq not found."

cd "$TF_DIR"
[ -f terraform.tfstate ] || die "No cluster found. Run 'tofu apply' first."

# The generator has its own zone output from Phase 2 onward; in Phase 1 it
# shares the single cluster zone.
ZONE=$(tofu output -raw generator_zone 2>/dev/null || tofu output -raw zone)
CHAIN_ID=$(tofu output -raw chain_id)
PROJECT=$(grep -oE '"project": *"[^"]+"' terraform.tfstate | head -1 | cut -d'"' -f4)
[ -n "$PROJECT" ] || PROJECT=$(gcloud config get-value project 2>/dev/null)
[ -n "$PROJECT" ] || die "Could not determine the GCP project."

# The PRIVATE address, deliberately. This is the entire point of the exercise:
# traffic stays inside the cloud network instead of crossing the internet.
#
# From Phase 2 the deployment names which validator the generator should talk
# to -- the one in its own region. Submission cost then stays constant across
# runs while *consensus* pays the cross-region price, so the measured
# degradation is attributable to consensus rather than to how far the client
# happened to be from its entry point.
RPC_URL=$(tofu output -raw rpc_url 2>/dev/null || echo "")
if [ -z "$RPC_URL" ]; then
  RPC_URL="http://$(tofu output -json validator_private_ips | jq -r '.[0]'):8545"
fi
VALIDATOR_IP=$(echo "$RPC_URL" | sed -E 's#^http://([^:]+):.*#\1#')

cd "$REPO"

ssh_gen() {
  gcloud compute ssh "$GENERATOR" --zone "$ZONE" --project "$PROJECT" \
    --no-tunnel-through-iap \
    --command "$1" -- -o StrictHostKeyChecking=no -o LogLevel=ERROR 2>/dev/null
}

log "Waiting for the generator machine to finish its own setup..."
for attempt in $(seq 1 40); do
  if ssh_gen "test -d $REMOTE_DIR" 2>/dev/null; then
    printf '  ready\n'; break
  fi
  [ "$attempt" -eq 40 ] && die "Generator never finished setup. Check /var/log/generator-setup.log on it."
  sleep 15
done

# --- copy the code --------------------------------------------------------
log "Copying the harness to $GENERATOR..."
TARBALL="$(mktemp -d)/harness.tar.gz"
# Ship only what a benchmark run needs. Notably NOT keys/ -- those are
# generated fresh on the generator, so private keys never travel over the
# wire or sit in two places.
tar -czf "$TARBALL" \
  --exclude='__pycache__' --exclude='*.pyc' \
  harness analysis contracts scripts requirements.txt

gcloud compute scp "$TARBALL" "$GENERATOR:/tmp/harness.tar.gz" \
  --zone "$ZONE" --project "$PROJECT" --quiet >/dev/null 2>&1 \
  || die "Could not copy the harness to the generator."

# Ownership goes to whoever gcloud actually logs in as, which is the local
# username, NOT 'ubuntu'. Hardcoding 'ubuntu' leaves the directory unwritable
# by the SSH user, and the venv step then fails with a bare permission error
# that says nothing about ownership.
ssh_gen "sudo tar -xzf /tmp/harness.tar.gz -C $REMOTE_DIR && \
         sudo chown -R \$(id -un):\$(id -gn) $REMOTE_DIR && rm -f /tmp/harness.tar.gz" \
  || die "Could not unpack the harness on the generator."
log "  code in place"

# --- build the environment ------------------------------------------------
log "Building the Python environment (this takes a couple of minutes)..."
ssh_gen "cd $REMOTE_DIR && \
  python3.11 -m venv .venv 2>/dev/null || python3 -m venv .venv; \
  ./.venv/bin/pip install --quiet --upgrade pip && \
  ./.venv/bin/pip install --quiet -r requirements.txt" \
  || die "Dependency install failed on the generator."

installed=$(ssh_gen "cd $REMOTE_DIR && ./.venv/bin/python -c 'import web3; print(web3.__version__)'")
[ -n "$installed" ] || die "web3 did not install on the generator."
log "  web3 $installed installed"

# --- prove it works before trusting it ------------------------------------
# The harness's own self-checks: arrival timing, latency accuracy, failure
# accounting. If these fail on the generator, every number it later produces
# is suspect -- better to find out now than after a 39-hour sweep.
log "Running the harness self-checks on the generator..."
ssh_gen "cd $REMOTE_DIR && ./.venv/bin/python -m harness.smoke_test 2>&1 | tail -4" \
  || die "Harness self-checks failed on the generator."

# --- measure the network path ---------------------------------------------
# The reason this machine exists. Recorded so the Methodology section can
# state the generator's own contribution to measured latency.
log "Measuring the generator-to-validator round trip..."
rtt=$(ssh_gen "ping -c 10 -q $VALIDATOR_IP 2>/dev/null | tail -1")
printf '  %s\n' "$rtt"

cat <<EOF

$(log "Generator is ready.")

  Machine   : $GENERATOR
  Code      : $REMOTE_DIR
  Chain     : $RPC_URL (private address -- traffic stays in-region)

Run everything from the generator now, NOT from the laptop:

  1. Deploy the test dollar and fund the wallets:

       gcloud compute ssh $GENERATOR --zone $ZONE --project $PROJECT --command \\
         "cd $REMOTE_DIR && ./.venv/bin/python -m scripts.deploy_and_fund \\
            --rpc-url $RPC_URL --chain-id $CHAIN_ID \\
            --funder-key <from keys/funder.txt> --senders 46"

  2. Run the Phase 1 validation:

       gcloud compute ssh $GENERATOR --zone $ZONE --project $PROJECT --command \\
         "cd $REMOTE_DIR && ./.venv/bin/python -m harness.cli run \\
            --config config/phase1.json --tps 5 --window 300 --amount 200"

  Check the reported scheduling lag. It should be under a millisecond. If it
  is still hundreds of milliseconds, something is wrong with the in-region
  path and no throughput number can be trusted yet.
EOF
