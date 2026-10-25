#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Cost guard for a NEAR node. Replaces the phase 1 guard, which must NOT be
# reused here.
#
# WHY THE PHASE 1 GUARD WAS REMOVED
#
# Its idle signal is `eth_blockNumber` -- an Ethereum JSON-RPC method. That
# exists on Polygon Edge and on nothing else. Reused unchanged it reads zero
# forever, concludes the cluster is idle, and shuts the machine down:
#
#   - it killed the Lightning cluster FIVE times, twice mid-deployment
#   - it then killed six of eight NEAR validators within an hour of boot
#
# Both times the fault was invisible until instances started disappearing,
# because a guard that shuts things down "correctly" logs nothing alarming.
#
# THE SIGNAL USED INSTEAD
#
# A heartbeat file touched by anything doing real work -- neard itself, a
# benchmark run, the bootstrap script. That covers the setup window, when a
# great deal is happening but no measured transactions exist yet, which is
# exactly when the old guard did its damage.
#
# Both protections remain: a hard lifetime cap armed at boot, and idle
# shutdown. Only the definition of "idle" changed.
# ---------------------------------------------------------------------------
set -uo pipefail

MAX_LIFETIME_MINUTES=${max_lifetime_minutes}
IDLE_MINUTES=${idle_shutdown_minutes}

exec >>/var/log/shutdown-guard.log 2>&1
echo "=== shutdown guard starting at $(date -u) ==="

# Guard 1: hard cap, armed from boot.
# NOTE: this re-arms on EVERY boot, not from creation, so a reboot silently
# extends the deadline (README.md cloud trap 3).
shutdown -c 2>/dev/null || true
shutdown -h "+$MAX_LIFETIME_MINUTES" \
  "Automatic shutdown: cluster reached its $MAX_LIFETIME_MINUTES-minute lifetime cap."
echo "hard shutdown armed for +$MAX_LIFETIME_MINUTES minutes"

# Guard 2: DISABLED.
#
# The idle watcher stopped clusters SEVEN times across three phases, every one
# a false positive. It polled an Ethereum RPC on a Lightning host and on a NEAR
# host; it keyed off process names that did not match; it killed a generator
# mid-deployment twice. It has never once saved money the hard cap above would
# not also have saved, and each false positive cost far more in cluster hours
# than it ever protected.
#
# The hard lifetime cap is the protection that works: an absolute deadline
# armed at boot, immune to whatever the machine believes it is doing.
cat >/usr/local/bin/bench-heartbeat.sh <<'EOF'
#!/usr/bin/env bash
while true; do
  if pgrep -f "neard|harness.cli|near_bootstrap" >/dev/null; then
    touch /var/run/bench-active
  fi
  sleep 120
done
EOF
chmod +x /usr/local/bin/bench-heartbeat.sh
cat >/etc/systemd/system/bench-heartbeat.service <<'EOF'
[Unit]
Description=Benchmark activity heartbeat
[Service]
ExecStart=/usr/local/bin/bench-heartbeat.sh
Restart=always
[Install]
WantedBy=multi-user.target
EOF

cat >/usr/local/bin/idle-watch.sh <<'EOF'
#!/usr/bin/env bash
IDLE_MINUTES="$${1:-45}"
INTERVAL=60
required=$((IDLE_MINUTES * 60 / INTERVAL))
HEARTBEAT=/var/run/bench-active
exec >>/var/log/idle-watch.log 2>&1
echo "=== idle watcher started $(date -u), limit $${IDLE_MINUTES}m ==="
idle=0
while true; do
  sleep "$INTERVAL"
  fresh=0
  if [ -f "$HEARTBEAT" ]; then
    age=$(( $(date +%s) - $(stat -c %Y "$HEARTBEAT" 2>/dev/null || echo 0) ))
    [ "$age" -lt $((IDLE_MINUTES * 60)) ] && fresh=1
  fi
  if [ "$fresh" = "1" ]; then
    idle=0
  else
    idle=$((idle + 1))
    echo "$(date -u) no heartbeat ($idle/$required)"
    if [ "$idle" -ge "$required" ]; then
      echo "$(date -u) idle $${IDLE_MINUTES}m -- shutting down to stop billing"
      shutdown -h now "Automatic shutdown: idle for $${IDLE_MINUTES} minutes."
      exit 0
    fi
  fi
done
EOF
chmod +x /usr/local/bin/idle-watch.sh

touch /var/run/bench-active
systemctl daemon-reload
systemctl enable --now bench-heartbeat >/dev/null 2>&1 || true
pkill -f idle-watch.sh 2>/dev/null || true
setsid nohup /usr/local/bin/idle-watch.sh "$IDLE_MINUTES" >/dev/null 2>&1 < /dev/null &
echo "idle watcher started (heartbeat based, $${IDLE_MINUTES}m)"
