#!/bin/bash
# ---------------------------------------------------------------------------
# Validator machine setup.
#
# Installs the blockchain software and generates this node's identity. It does
# NOT start the chain -- a Polygon Edge network needs every validator's public
# identity collected before the shared genesis file can be written, and a
# startup script running independently on each machine cannot coordinate that.
# The operator runs scripts/bootstrap_cluster.sh once all machines are up.
#
# Splitting it this way also means a failed bootstrap can be retried without
# rebuilding the machines.
# ---------------------------------------------------------------------------
set -euo pipefail

exec >>/var/log/validator-setup.log 2>&1
echo "=== validator setup starting at $(date -u) ==="

CHAIN_ID=${chain_id}

# Pinned to the FINAL Polygon Edge release, verified 7 Aug 2026 against the
# GitHub releases API: v1.3.2, published 24 January 2024. The repository was
# archived read-only on 4 December 2024, so this version is final and will not
# move. That is a reproducibility advantage, not a defect -- anyone repeating
# this study gets byte-identical software. The paper must cite this exact tag.
EDGE_VERSION="${edge_version}"

export DEBIAN_FRONTEND=noninteractive
# -o DPkg::Lock::Timeout=60: GCE's Ubuntu image runs its own apt-news/esm-cache
# services in the first seconds after boot, which can hold the dpkg lock. This
# script has no control over when it runs relative to those, so it waits for
# the lock instead of failing -- observed 9 Aug 2026: this and every step below
# used to fail outright on a REBOOT (not a fresh instance), because the
# metadata startup-script runs on every boot, not just the first.
apt-get -o DPkg::Lock::Timeout=60 update -qq
apt-get -o DPkg::Lock::Timeout=60 install -yqq curl jq tar iproute2 chrony

# Accurate clocks matter more than usual here. Settlement latency is measured
# by comparing timestamps, and although the harness uses a drift-immune timer
# for the measurement itself, correlating against node logs and block
# timestamps needs the machines to agree on the time.
systemctl enable --now chrony

useradd -r -m -s /bin/false edge 2>/dev/null || true
install -d -o edge -g edge /var/lib/edge /var/log/edge

ARCH="$(dpkg --print-architecture)"
case "$ARCH" in
  amd64) EDGE_ARCH="amd64" ;;
  arm64) EDGE_ARCH="arm64" ;;
  *) echo "FATAL: unsupported architecture $ARCH"; exit 1 ;;
esac

# IDEMPOTENCY, added 9 Aug 2026. This script runs again on every reboot, not
# just once at creation -- confirmed the hard way: after a stop/start cycle
# (switching the cluster from spot to on-demand mid-study), all four
# validators failed here with exit status 1 while already running fine,
# because `secrets init` refuses to overwrite a validator's existing key
# material. That refusal is correct behaviour from polygon-edge -- overwriting
# a live validator's identity mid-study would be a real bug -- so the fix
# belongs here: skip straight to "already provisioned" rather than trying to
# regenerate what's already on disk and already backing a running edge.service.
if [ -f /usr/local/bin/polygon-edge ] && [ -f /var/lib/edge/identity.json ]; then
  echo "polygon-edge already installed and this node's identity already exists -- nothing to do"
  echo "chain id: $CHAIN_ID"
  echo "=== validator setup complete at $(date -u) -- already provisioned, skipped ==="
  exit 0
fi

URL="https://github.com/0xPolygon/polygon-edge/releases/download/$${EDGE_VERSION}/polygon-edge_$${EDGE_VERSION#v}_linux_$${EDGE_ARCH}.tar.gz"
echo "downloading polygon-edge $${EDGE_VERSION} ($${EDGE_ARCH}) from $${URL}"

cd /tmp
# Retry a few times before giving up -- in the first seconds after boot, DNS
# and outbound routing are not always fully settled yet, and a single-shot
# curl turns a transient hiccup into a fatal deployment failure.
download_ok=0
for attempt in 1 2 3 4 5; do
  if curl -fsSL --connect-timeout 10 -o edge.tar.gz "$URL"; then
    download_ok=1
    break
  fi
  echo "download attempt $attempt failed, retrying in 5s..."
  sleep 5
done
if [ "$download_ok" -ne 1 ]; then
  echo "FATAL: download failed after 5 attempts. The release tag $${EDGE_VERSION} may not exist."
  echo "Polygon Edge was archived in Dec 2024; confirm the final release tag at"
  echo "https://github.com/0xPolygon/polygon-edge/releases"
  exit 1
fi

tar -xzf edge.tar.gz
install -m 0755 polygon-edge /usr/local/bin/polygon-edge
/usr/local/bin/polygon-edge version || true

# Generate this node's cryptographic identity. Written where the bootstrap
# script can collect it.
sudo -u edge /usr/local/bin/polygon-edge secrets init \
  --data-dir /var/lib/edge/data --insecure

sudo -u edge /usr/local/bin/polygon-edge secrets output \
  --data-dir /var/lib/edge/data --json > /var/lib/edge/identity.json
chmod 0644 /var/lib/edge/identity.json

echo "chain id: $CHAIN_ID"
echo "node identity written to /var/lib/edge/identity.json"
echo "=== validator setup complete at $(date -u) -- awaiting bootstrap ==="
