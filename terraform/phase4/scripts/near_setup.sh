#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Startup script for one NEAR validator. Installs nearcore and prepares the
# node directory. It does NOT generate genesis or start the chain -- see below.
#
# IDEMPOTENT BY REQUIREMENT.
#
# GCP re-runs startup scripts on EVERY boot, not just at creation
# (README.md cloud trap 2). On Polygon that reset ownership and made
# `secrets init` refuse to overwrite validator keys, so four validators exited
# 1 after a reboot. On Lightning, re-running wallet creation would have
# destroyed channel state. Here the equivalent hazard is regenerating a
# validator key or genesis: a node that comes back with a different key is no
# longer part of the validator set, and a node with different genesis forks.
#
# So every step checks before acting, and anything that creates identity lives
# in scripts/deploy_near.sh, invoked once, explicitly.
#
# WHY GENESIS IS NOT BUILT HERE
#
# Every validator must share a byte-identical genesis that lists all 8 as
# validators and pins the shard layout to 4. That is inherently a whole-cluster
# operation -- no node can construct it alone -- so it is built once on the
# boot node and distributed.
# ---------------------------------------------------------------------------
set -euo pipefail

VALIDATOR_INDEX="${validator_index}"
NUM_VALIDATORS="${num_validators}"
NUM_SHARDS="${num_shards}"
NEAR_VERSION="${near_version}"
BOOT_NODE_IP="${boot_node_ip}"

BASE=/opt/near
mkdir -p "$BASE"

# apt can be held by unattended-upgrades on a fresh boot. Bounded wait rather
# than immediate failure -- phase 2 hit this.
wait_for_apt() {
  local waited=0
  while fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1; do
    sleep 5; waited=$((waited + 5))
    [ "$waited" -ge 300 ] && { echo "apt lock still held after 300s"; return 1; }
  done
}

if [ ! -f "$BASE/.packages-done" ]; then
  wait_for_apt
  apt-get update -y
  apt-get install -y curl jq tar ca-certificates
  touch "$BASE/.packages-done"
fi

# --- nearcore binary -------------------------------------------------------
if [ ! -x /usr/local/bin/neard ]; then
  # Official release artifact for the pinned version. Retried: a transient 503
  # must not leave a validator without a binary.
  URL="https://s3-us-west-1.amazonaws.com/build.nearprotocol.com/nearcore/Linux/$NEAR_VERSION/neard"
  attempt=1
  until curl -fsSL --retry 5 --retry-delay 5 -o /tmp/neard "$URL"; do
    attempt=$((attempt + 1))
    [ "$attempt" -gt 5 ] && { echo "could not fetch neard $NEAR_VERSION"; exit 1; }
    sleep 10
  done
  install -m 0755 /tmp/neard /usr/local/bin/neard
fi

/usr/local/bin/neard --version || true

# --- node directory --------------------------------------------------------
# Created but NOT initialised. `neard init` writes validator_key.json and a
# genesis; doing that here would give each node its own genesis and its own
# idea of the validator set, and the cluster would never form a single chain.
NODE_DIR="$BASE/node"
mkdir -p "$NODE_DIR"

cat > "$BASE/node-info.json" <<INFO
{
  "validator_index": $VALIDATOR_INDEX,
  "num_validators": $NUM_VALIDATORS,
  "num_shards": $NUM_SHARDS,
  "boot_node_ip": "$BOOT_NODE_IP",
  "near_version": "$NEAR_VERSION"
}
INFO

# systemd unit is written now and enabled, but NOT started: there is no genesis
# yet. deploy_near.sh distributes genesis and then starts the service, so a
# reboot before deployment does not leave a node crash-looping on missing
# config.
cat > /etc/systemd/system/neard.service <<UNIT
[Unit]
Description=NEAR validator $VALIDATOR_INDEX
After=network-online.target

[Service]
ExecStart=/usr/local/bin/neard --home $NODE_DIR run
Restart=always
RestartSec=10
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable neard >/dev/null 2>&1 || true

# Ownership last, and tolerant of files that do not exist yet. Phase 2's reboot
# breakage came from resetting ownership unconditionally.
chown -R ubuntu:ubuntu "$BASE" 2>/dev/null || true

echo "near validator $VALIDATOR_INDEX ready: binary installed, awaiting genesis"
