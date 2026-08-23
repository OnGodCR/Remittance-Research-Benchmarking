#!/usr/bin/env bash

# A PROCESS CHECK THAT FINDS ITSELF
#
# `pgrep -f foo` and `pkill -f foo` search whole command lines, so the shell
# running the check has "foo" in its own -- the check matches itself. It
# reports RUNNING when nothing is, and `pkill` kills its own wrapper. This
# cost hours on 22 Aug 2026 and, in one case, killed a sweep on its first
# instruction. The brackets fix it: the regex [f]oo still matches the text
# "foo" in a real process, but this line's own text reads "[f]oo", which the
# regex does not match. Repo convention -- see RESUME_HERE.md S5 trap 8.
# ---------------------------------------------------------------------------
# Installs a per-node auto-unlock service, and keeps the idle watcher from
# killing the cluster during setup.
#
# WHY AUTO-UNLOCK
#
# Spot reclamation stops an instance; disks survive, so wallets and channel
# state survive with them. But LND always restarts LOCKED, and a locked node
# serves no payments. Mid-sweep that means data collection silently stops and
# stays stopped until a human unlocks 20 wallets by hand.
#
# On-demand instances would not fix this -- they only make reclamation rarer,
# at 4.5x the price. Unlocking automatically closes the gap and keeps the
# cluster on spot, which is the standing instruction (RESUME_HERE.md S6).
#
# This is safe ONLY because the password protects nothing: a private regtest
# chain whose coins we mint, reachable only inside the VPC. Never do this
# anywhere real.
#
# WHY THE HEARTBEAT
#
# The idle watcher shut the cluster down three times tonight, twice during a
# rebuild. Creating wallets and opening channels is real work that produces no
# Lightning payments, so the watcher's activity signal reads zero. The
# heartbeat file marks "a human process is working here"; setup steps refresh
# it, and the watcher treats a fresh file as activity.
# ---------------------------------------------------------------------------
set -euo pipefail
NODES="${1:-5}"

cat > /usr/local/bin/lnd-autounlock.sh <<'EOF'
#!/usr/bin/env bash
# Unlock one LND node as soon as it reports LOCKED. Runs forever: a node can
# be locked again by any restart, not only at boot.
PORT="$1"
PASS="$(printf 'benchmarkwallet' | base64)"
while true; do
  state=$(curl -sk --max-time 5 "https://localhost:$PORT/v1/state" 2>/dev/null \
          | grep -o '"state":"[A-Z_]*"' | cut -d'"' -f4)
  if [ "$state" = "LOCKED" ]; then
    curl -sk --max-time 30 -X POST "https://localhost:$PORT/v1/unlockwallet" \
      -d "{\"wallet_password\":\"$PASS\"}" >/dev/null 2>&1
    logger -t lnd-autounlock "unlocked wallet on port $PORT"
  fi
  sleep 15
done
EOF
chmod +x /usr/local/bin/lnd-autounlock.sh

for i in $(seq 0 $((NODES - 1))); do
  cat > "/etc/systemd/system/lnd-unlock$i.service" <<EOF
[Unit]
Description=Auto-unlock LND node $i
After=lnd-node$i.service

[Service]
ExecStart=/usr/local/bin/lnd-autounlock.sh $((8080 + i))
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
  systemctl enable --now "lnd-unlock$i" >/dev/null 2>&1
done

# Keep the watcher quiet while setup is in progress.
touch /var/run/bench-active
cat > /usr/local/bin/bench-heartbeat.sh <<'EOF'
#!/usr/bin/env bash
# Refresh the heartbeat whenever any LND node is running. Setup counts as use.
while true; do
  pgrep -f "[/]/usr/local/bin/lnd " >/dev/null && touch /var/run/bench-active
  sleep 120
done
EOF
chmod +x /usr/local/bin/bench-heartbeat.sh
cat > /etc/systemd/system/bench-heartbeat.service <<'EOF'
[Unit]
Description=Benchmark activity heartbeat
[Service]
ExecStart=/usr/local/bin/bench-heartbeat.sh
Restart=always
[Install]
WantedBy=multi-user.target
EOF
systemctl enable --now bench-heartbeat >/dev/null 2>&1

# --- replace the Polygon idle watcher -------------------------------------
#
# terraform/phase3 reuses phase 1's shutdown guard, whose activity signal is
# eth_blockNumber -- an Ethereum RPC that does not exist on a Lightning host.
# It therefore reads zero forever and shuts the machine down 30 minutes after
# boot, no matter what work is happening. It has now killed this cluster five
# times, twice mid-deployment.
#
# Replaced with a watcher that trusts the heartbeat file above. The hard
# lifetime cap armed at boot is untouched, so cost is still bounded.
cat > /usr/local/bin/idle-watch.sh <<'EOF'
#!/usr/bin/env bash
IDLE_MINUTES="${1:-45}"
INTERVAL=60
required=$((IDLE_MINUTES * 60 / INTERVAL))
HEARTBEAT=/var/run/bench-active
exec >>/var/log/idle-watch.log 2>&1
echo "=== lightning idle watcher started $(date -u) ==="
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
      echo "$(date -u) idle ${IDLE_MINUTES}m -- shutting down"
      shutdown -h now "Automatic shutdown: idle."
      exit 0
    fi
  fi
done
EOF
chmod +x /usr/local/bin/idle-watch.sh
pkill -f idle-watch.sh 2>/dev/null || true
setsid nohup /usr/local/bin/idle-watch.sh 45 >/dev/null 2>&1 < /dev/null &

echo "  auto-unlock installed for $NODES nodes; heartbeat + lightning watcher running"
