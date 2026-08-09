#!/bin/bash
# ---------------------------------------------------------------------------
# Load generator setup.
#
# This machine runs the measurement program. It is deliberately separate from
# the validators so the load generator never competes with consensus for CPU --
# if they shared a machine, a throughput ceiling could be either the chain
# saturating or our own tool starving the chain of processor time, and there
# would be no way to tell which.
#
# It sits in the same region as the validators for Phase 1. In later phases it
# stays in ONE fixed region for every test, because consistency matters more
# than proximity: a generator that moves between runs would add a varying
# network delay to every measurement.
# ---------------------------------------------------------------------------
set -euo pipefail

exec >>/var/log/generator-setup.log 2>&1
echo "=== generator setup starting at $(date -u) ==="

# -o DPkg::Lock::Timeout=60: waits for the dpkg lock instead of failing if
# GCE's own apt-news/esm-cache services are holding it in the first seconds
# after boot. See validator_setup.sh for the reboot failure this was found
# alongside (9 Aug 2026) -- this script runs on every boot too, and was one
# lucky race away from the same failure.
export DEBIAN_FRONTEND=noninteractive
apt-get -o DPkg::Lock::Timeout=60 update -qq
apt-get -o DPkg::Lock::Timeout=60 install -yqq python3.11 python3.11-venv python3-pip git curl jq \
  iproute2 chrony build-essential

systemctl enable --now chrony

# Raise the open-file limit. At 300 payments/second with a 60-second timeout,
# up to 18,000 payments are in flight simultaneously, each holding a network
# connection. Linux defaults to 1024 open files, so the generator would fail
# with confusing connection errors long before the blockchain was stressed --
# and that failure would look like the chain refusing traffic.
cat >>/etc/security/limits.conf <<'LIMITS'
*    soft nofile 65535
*    hard nofile 65535
root soft nofile 65535
root hard nofile 65535
LIMITS

mkdir -p /etc/systemd/system.conf.d
cat >/etc/systemd/system.conf.d/limits.conf <<'SYSTEMD'
[Manager]
DefaultLimitNOFILE=65535
SYSTEMD

# Widen the local port range and shorten connection cleanup, for the same
# reason: tens of thousands of short-lived connections per run.
cat >/etc/sysctl.d/99-benchmark.conf <<'SYSCTL'
net.ipv4.ip_local_port_range = 10000 65535
net.ipv4.tcp_fin_timeout = 15
net.core.somaxconn = 4096
SYSCTL
sysctl -p /etc/sysctl.d/99-benchmark.conf

install -d -o ubuntu -g ubuntu /opt/benchmark
echo "=== generator setup complete at $(date -u) ==="
echo "Next: copy the harness to /opt/benchmark and create its virtualenv."
