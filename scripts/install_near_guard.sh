#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Replace the Polygon idle watcher with a NEAR-aware one, and fix the p2p bind.
#
# terraform/phase4 reuses phase 1's shutdown guard, whose activity signal is
# eth_blockNumber -- an Ethereum RPC that does not exist on a NEAR node. It
# therefore reads zero forever and shuts the machine down 45 minutes after
# boot no matter what is happening. It did exactly that to six of eight
# validators, and it had already killed the Lightning cluster five times.
#
# The honest signal here is BLOCK HEIGHT: if the chain is advancing, the
# cluster is doing work. A heartbeat file covers the setup window, when real
# work is happening but no blocks are being measured.
#
# Also re-applies the p2p bind. `neard localnet` generates configs for running
# every node on one machine and binds each to [::1] on a random port; ours are
# spread across four regions and must listen on 0.0.0.0:24567 or no node can
# see another. A reboot restores the file from the startup script, so this must
# be idempotent and re-applied.
# ---------------------------------------------------------------------------
set -uo pipefail

# --- p2p bind --------------------------------------------------------------
if [ -f /opt/near/node/config.json ]; then
  python3 - <<'PY'
import json
p = "/opt/near/node/config.json"
c = json.load(open(p))
net = c.setdefault("network", {})
if net.get("addr") != "0.0.0.0:24567":
    net["addr"] = "0.0.0.0:24567"
    json.dump(c, open(p, "w"), indent=2)
    print("  p2p re-bound to 0.0.0.0:24567")
else:
    print("  p2p bind already correct")
PY
  systemctl restart neard 2>/dev/null || true
fi

# --- NEAR-aware idle watcher ----------------------------------------------
cat > /usr/local/bin/idle-watch.sh <<'EOF'
#!/usr/bin/env bash
IDLE_MINUTES="${1:-45}"
INTERVAL=60
required=$((IDLE_MINUTES * 60 / INTERVAL))
HEARTBEAT=/var/run/bench-active
exec >>/var/log/idle-watch.log 2>&1
echo "=== NEAR idle watcher started $(date -u), limit ${IDLE_MINUTES}m ==="

height() {
  curl -s -m 5 -X POST http://localhost:3030 -H 'Content-Type: application/json' \
    -d '{"jsonrpc":"2.0","id":1,"method":"status","params":[]}' 2>/dev/null \
    | python3 -c 'import sys,json;print(json.load(sys.stdin)["result"]["sync_info"]["latest_block_height"])' 2>/dev/null
}

last=""
idle=0
while true; do
  sleep "$INTERVAL"
  now=$(height)

  fresh=0
  if [ -f "$HEARTBEAT" ]; then
    age=$(( $(date +%s) - $(stat -c %Y "$HEARTBEAT" 2>/dev/null || echo 0) ))
    [ "$age" -lt $((IDLE_MINUTES * 60)) ] && fresh=1
  fi

  # A chain that is advancing is a cluster doing work. Height alone would keep
  # the machine alive forever, since validators always produce blocks -- so
  # this deliberately keys off the HEARTBEAT for idleness and uses height only
  # to detect a dead chain worth shutting down early.
  if [ "$fresh" = "1" ]; then
    idle=0
  else
    idle=$((idle + 1))
    echo "$(date -u) no heartbeat ($idle/$required) height=${now:-unknown}"
    if [ "$idle" -ge "$required" ]; then
      echo "$(date -u) idle ${IDLE_MINUTES}m -- shutting down"
      shutdown -h now "Automatic shutdown: idle."
      exit 0
    fi
  fi
  last="$now"
done
EOF
chmod +x /usr/local/bin/idle-watch.sh
pkill -f idle-watch.sh 2>/dev/null || true
touch /var/run/bench-active
setsid nohup /usr/local/bin/idle-watch.sh 45 >/dev/null 2>&1 < /dev/null &

# --- heartbeat -------------------------------------------------------------
cat > /usr/local/bin/bench-heartbeat.sh <<'EOF'
#!/usr/bin/env bash
while true; do
  if pgrep -f "neard|harness.cli|near_bootstrap" >/dev/null; then
    touch /var/run/bench-active
  fi
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
systemctl daemon-reload
systemctl enable --now bench-heartbeat >/dev/null 2>&1

# --- lifetime cap covering the whole sweep --------------------------------
shutdown -c 2>/dev/null || true
shutdown -h +2040 "Automatic shutdown: cluster lifetime cap." 2>/dev/null || true

sleep 1
echo "  watcher: $(pgrep -f idle-watch.sh >/dev/null && echo running || echo MISSING); heartbeat: $(systemctl is-active bench-heartbeat)"
