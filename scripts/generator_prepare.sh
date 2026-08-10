#!/usr/bin/env bash
# Runs ON THE GENERATOR. Unpacks the harness and builds its environment.
set -euo pipefail

mkdir -p /opt/benchmark
tar -xzf /tmp/harness.tar.gz -C /opt/benchmark

# apt can be held by unattended-upgrades on a fresh boot (phase 2 trap).
waited=0
while fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1; do
  sleep 5; waited=$((waited + 5))
  [ "$waited" -ge 300 ] && break
done
apt-get update -y >/dev/null 2>&1 || true
apt-get install -y python3-venv python3-pip >/dev/null 2>&1 || true

cd /opt/benchmark
[ -d .venv ] || python3 -m venv .venv
# aiohttp is the only dependency the Lightning path needs; web3/pandas are
# Polygon and analysis concerns and would slow the install for nothing.
./.venv/bin/pip install -q --upgrade pip >/dev/null 2>&1 || true
./.venv/bin/pip install -q aiohttp >/dev/null 2>&1

chown -R $(logname 2>/dev/null || echo ubuntu):$(logname 2>/dev/null || echo ubuntu) /opt/benchmark 2>/dev/null || true
echo "  harness installed at /opt/benchmark"
./.venv/bin/python -c "import aiohttp; print('  aiohttp', aiohttp.__version__)"
