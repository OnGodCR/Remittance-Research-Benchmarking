#!/usr/bin/env bash
# Runs ON THE GENERATOR. Unpacks the harness and builds its environment.
set -uo pipefail
mkdir -p /opt/benchmark
tar -xzf /tmp/harness.tar.gz -C /opt/benchmark
waited=0
while fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1; do
  sleep 5; waited=$((waited+5)); [ "$waited" -ge 300 ] && break
done
apt-get update -y >/dev/null 2>&1 || true
apt-get install -y python3-venv python3-pip >/dev/null 2>&1 || true
cd /opt/benchmark
[ -d .venv ] || python3 -m venv .venv
./.venv/bin/pip install -q --upgrade pip >/dev/null 2>&1 || true
# py-near for NEAR, base58/pynacl for account key generation. web3 and pandas
# are Polygon and analysis concerns and are not needed here.
./.venv/bin/pip install -q py-near base58 PyNaCl >/dev/null 2>&1
chown -R $(logname 2>/dev/null || echo ubuntu):$(logname 2>/dev/null || echo ubuntu) /opt/benchmark 2>/dev/null || true
echo "  harness installed"
./.venv/bin/python -c "import py_near, base58, nacl; print('  py-near ready')"
