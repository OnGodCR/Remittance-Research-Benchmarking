#!/bin/bash
# ---------------------------------------------------------------------------
# Shutdown guard. Runs first on every machine, before anything else.
#
# WHY THIS IS THE MOST IMPORTANT FILE IN THE INFRASTRUCTURE
#
# Google's budget alerts send email. They do not stop spending. There is no
# hard spending cap available on a paid account, so nothing except this script
# stands between a forgotten cluster and a real bill.
#
# The realistic failure is not an expensive experiment -- it is a debugging
# session that ends at 2am with the cluster still running. A 7-node cluster is
# about $1.15/hour: one forgotten night is ~$14, a forgotten weekend is ~$80,
# against a total project budget of $300-450.
#
# TWO INDEPENDENT GUARDS, deliberately not sharing any machinery:
#
#   1. A hard timer armed at boot. Uses the kernel's own shutdown scheduler,
#      so it fires even if this script, the network, or the blockchain node
#      dies immediately afterward. This is the guarantee.
#
#   2. An idle watcher. Shuts down early when nothing is using the cluster,
#      which is the common case and saves far more money in practice.
#
# If guard 2 has a bug, guard 1 still fires. That redundancy is intentional:
# a single point of failure in the thing preventing runaway spend is not a
# sensible design.
# ---------------------------------------------------------------------------
set -euo pipefail

MAX_LIFETIME_MINUTES=${max_lifetime_minutes}
IDLE_MINUTES=${idle_shutdown_minutes}
RPC_PORT=8545

exec >>/var/log/shutdown-guard.log 2>&1
echo "=== shutdown guard starting at $(date -u) ==="

# --- Guard 1: hard lifetime cap -------------------------------------------
# Armed immediately. Nothing below this line can prevent it.
shutdown -h "+$MAX_LIFETIME_MINUTES" \
  "Automatic shutdown: cluster reached its $MAX_LIFETIME_MINUTES-minute lifetime cap."
echo "hard shutdown armed for +$MAX_LIFETIME_MINUTES minutes"

# --- Guard 2: idle watcher ------------------------------------------------
# Watches for connections on the node's RPC port -- the port only the
# measurement program talks to. Consensus traffic between validators uses
# different ports and continues regardless, so this distinguishes "nobody is
# benchmarking" from "the blockchain is alive", which a CPU-based check could
# not do (a validator's CPU is never idle).
cat >/usr/local/bin/idle-watch.sh <<'WATCHER'
#!/bin/bash
set -uo pipefail

IDLE_MINUTES=__IDLE_MINUTES__
RPC_PORT=__RPC_PORT__
CHECK_INTERVAL=60
idle_checks=0
required_checks=$((IDLE_MINUTES * 60 / CHECK_INTERVAL))

# Grace period. Without it, a cluster that takes a while to be configured
# could switch itself off before the operator ever connects to it.
sleep 600

while true; do
  # Established connections to or from the RPC port, in either direction, so
  # the same check works on validators (receiving) and the generator (sending).
  active=$(ss -tn state established \
    "( sport = :$RPC_PORT or dport = :$RPC_PORT )" 2>/dev/null | tail -n +2 | wc -l)

  if [ "$active" -gt 0 ]; then
    if [ "$idle_checks" -gt 0 ]; then
      echo "$(date -u) activity resumed ($active connections), idle counter reset"
    fi
    idle_checks=0
  else
    idle_checks=$((idle_checks + 1))
    echo "$(date -u) no benchmark activity ($idle_checks/$required_checks)"
    if [ "$idle_checks" -ge "$required_checks" ]; then
      echo "$(date -u) idle for $IDLE_MINUTES minutes -- shutting down to stop billing"
      shutdown -h now "Automatic shutdown: idle for $IDLE_MINUTES minutes."
      exit 0
    fi
  fi
  sleep "$CHECK_INTERVAL"
done
WATCHER

sed -i "s/__IDLE_MINUTES__/$IDLE_MINUTES/; s/__RPC_PORT__/$RPC_PORT/" \
  /usr/local/bin/idle-watch.sh
chmod +x /usr/local/bin/idle-watch.sh

cat >/etc/systemd/system/idle-watch.service <<'UNIT'
[Unit]
Description=Shut down the machine when no benchmark is running
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/idle-watch.sh
Restart=always
RestartSec=30
StandardOutput=append:/var/log/idle-watch.log
StandardError=append:/var/log/idle-watch.log

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now idle-watch.service
echo "idle watcher started (threshold: $IDLE_MINUTES minutes)"

# --- Spot reclamation notice ----------------------------------------------
# Google gives ~30 seconds' warning before taking a spot instance back. We
# record it so the analysis can tell a reclaimed run apart from a real node
# failure -- the adversarial arm deliberately kills nodes, and confusing the
# two would corrupt exactly the comparison that arm exists to make.
cat >/usr/local/bin/preempt-watch.sh <<'PREEMPT'
#!/bin/bash
set -uo pipefail
URL="http://metadata.google.internal/computeMetadata/v1/instance/preempted"
while true; do
  result=$(curl -s -H "Metadata-Flavor: Google" "$URL?wait_for_change=true&timeout_sec=300" || echo "")
  if [ "$result" = "TRUE" ]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%S.%NZ) PREEMPTED $(hostname)" \
      | tee -a /var/log/preemption.log
    exit 0
  fi
done
PREEMPT
chmod +x /usr/local/bin/preempt-watch.sh

cat >/etc/systemd/system/preempt-watch.service <<'UNIT'
[Unit]
Description=Record spot instance reclamation
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/preempt-watch.sh
Restart=always
RestartSec=10
StandardOutput=append:/var/log/preemption.log
StandardError=append:/var/log/preemption.log

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now preempt-watch.service
echo "=== shutdown guard ready at $(date -u) ==="
