#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Startup script for one Lightning host. Installs bitcoind (host 0 only) and
# LND, then starts `nodes_per_host` LND daemons on offset ports.
#
# IDEMPOTENT BY REQUIREMENT, NOT BY STYLE.
#
# Phase 2 trap (README.md cloud trap 2): GCP re-runs startup scripts on EVERY
# boot, not just at creation. On Polygon that reset directory ownership and
# made `secrets init` refuse to overwrite existing validator keys, so all four
# validators' startup scripts exited 1 after a reboot. Here the stakes are
# higher: re-initialising an LND wallet would destroy channel state, and the
# whole funded topology with it. Every step below therefore checks before
# acting, and a reboot must leave existing wallets untouched.
#
# Ports, per node index i on this host:
#   p2p   9735 + i      REST  8080 + i      gRPC  10009 + i
# ---------------------------------------------------------------------------
set -euo pipefail

HOST_INDEX="${host_index}"
RUN_BITCOIND="${run_bitcoind}"
BITCOIND_VERSION="${bitcoind_version}"
LND_VERSION="${lnd_version}"
NODES_PER_HOST="${nodes_per_host}"
BITCOIND_HOST="${bitcoind_host}"

BASE=/opt/lightning
mkdir -p "$BASE"

# apt can be held by unattended-upgrades on a fresh boot. Phase 2 hit this and
# the fix is a bounded wait rather than an immediate failure.
wait_for_apt() {
  local waited=0
  while fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1; do
    sleep 5; waited=$((waited + 5))
    [ "$waited" -ge 300 ] && { echo "apt lock still held after 300s"; return 1; }
  done
}

fetch() {  # url dest -- retried; a transient 503 must not kill the host
  local url="$1" dest="$2" attempt=1
  until curl -fsSL --retry 5 --retry-delay 5 -o "$dest" "$url"; do
    attempt=$((attempt + 1))
    [ "$attempt" -gt 5 ] && return 1
    sleep 10
  done
}

# --- packages --------------------------------------------------------------
if [ ! -f "$BASE/.packages-done" ]; then
  wait_for_apt
  apt-get update -y
  apt-get install -y curl jq tar
  touch "$BASE/.packages-done"
fi

# --- bitcoind, host 0 only -------------------------------------------------
if [ "$RUN_BITCOIND" = "yes" ] && [ ! -x /usr/local/bin/bitcoind ]; then
  fetch "https://bitcoincore.org/bin/bitcoin-core-$BITCOIND_VERSION/bitcoin-$BITCOIND_VERSION-x86_64-linux-gnu.tar.gz" \
        /tmp/bitcoin.tar.gz
  tar -xzf /tmp/bitcoin.tar.gz -C /tmp
  install -m 0755 "/tmp/bitcoin-$BITCOIND_VERSION/bin/bitcoind" /usr/local/bin/bitcoind
  install -m 0755 "/tmp/bitcoin-$BITCOIND_VERSION/bin/bitcoin-cli" /usr/local/bin/bitcoin-cli
fi

if [ "$RUN_BITCOIND" = "yes" ]; then
  mkdir -p "$BASE/bitcoind"
  # Credentials are fixed and in the clear ON PURPOSE. This is a private
  # regtest chain whose coins are mined by us and worth nothing, reachable
  # only from inside the VPC, and every node needs the same values. Generating
  # secrets here would add a distribution problem with no security benefit.
  # These must never be reused anywhere real.
  if [ ! -f "$BASE/bitcoind/bitcoin.conf" ]; then
    cat > "$BASE/bitcoind/bitcoin.conf" <<'CONF'
# Network-specific options MUST sit under [regtest]. Bitcoin Core refuses to
# start otherwise -- "Config setting for -rpcbind only applied on regtest
# network when in [regtest] section" -- and systemd then restart-loops the
# service forever, which surfaces as every LND node stuck LOCKED rather than
# as an obvious bitcoind failure.
regtest=1
server=1
txindex=1
# Load the funding wallet at startup. bitcoind does not auto-load wallets, so
# after any restart of this host every RPC against it failed with "Requested
# wallet does not exist or is not loaded" -- which reads as a missing wallet
# rather than an unloaded one.
wallet=bench
rpcuser=bench
rpcpassword=bench

[regtest]
rpcbind=0.0.0.0
rpcport=18443
rpcallowip=10.30.0.0/16
zmqpubrawblock=tcp://0.0.0.0:28332
zmqpubrawtx=tcp://0.0.0.0:28333
fallbackfee=0.0001
CONF
  fi

  cat > /etc/systemd/system/bitcoind.service <<CONF
[Unit]
Description=bitcoind regtest
After=network-online.target

[Service]
ExecStart=/usr/local/bin/bitcoind -datadir=$BASE/bitcoind -conf=$BASE/bitcoind/bitcoin.conf
Restart=always
RestartSec=5
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
CONF
  systemctl daemon-reload
  systemctl enable --now bitcoind
fi

# --- LND -------------------------------------------------------------------
if [ ! -x /usr/local/bin/lnd ]; then
  fetch "https://github.com/lightningnetwork/lnd/releases/download/$LND_VERSION/lnd-linux-amd64-$LND_VERSION.tar.gz" \
        /tmp/lnd.tar.gz
  tar -xzf /tmp/lnd.tar.gz -C /tmp
  install -m 0755 "/tmp/lnd-linux-amd64-$LND_VERSION/lnd" /usr/local/bin/lnd
  install -m 0755 "/tmp/lnd-linux-amd64-$LND_VERSION/lncli" /usr/local/bin/lncli
fi

PRIVATE_IP="$(curl -s -H 'Metadata-Flavor: Google' \
  http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/ip)"

for i in $(seq 0 $((NODES_PER_HOST - 1))); do
  DIR="$BASE/node$i"
  mkdir -p "$DIR"

  cat > "$DIR/lnd.conf" <<CONF
[Application Options]
lnddir=$DIR
listen=0.0.0.0:$((9735 + i))
restlisten=0.0.0.0:$((8080 + i))
rpclisten=0.0.0.0:$((10009 + i))
externalip=$PRIVATE_IP:$((9735 + i))
alias=h$HOST_INDEX-n$i
accept-keysend=true
maxpendingchannels=25
# LND caps channel capacity even with wumbo enabled -- the default is around
# 10 BTC. The well-capitalised arm uses larger channels, and the cap must be
# lifted on BOTH ends: an over-sized request is refused by the receiver, and
# surfaces as "received funding error from <pubkey>" rather than as a local
# error, which points at the wrong node entirely.
maxchansize=500000000000
minchansize=20000
# Routing nodes on the real network do not sit idle waiting for perfect
# routes. These keep failed-payment behaviour realistic rather than letting
# LND retry indefinitely, which would turn routing failures into latency and
# hide the very effect this arm measures.
maxlogfiles=3
maxlogfilesize=50

[Bitcoin]
bitcoin.active=true
bitcoin.regtest=true
bitcoin.node=bitcoind

[Bitcoind]
bitcoind.rpchost=$BITCOIND_HOST:18443
bitcoind.rpcuser=bench
bitcoind.rpcpass=bench
bitcoind.zmqpubrawblock=tcp://$BITCOIND_HOST:28332
bitcoind.zmqpubrawtx=tcp://$BITCOIND_HOST:28333

[protocol]
protocol.wumbo-channels=true
CONF

  cat > "/etc/systemd/system/lnd-node$i.service" <<CONF
[Unit]
Description=LND node $i on host $HOST_INDEX
After=network-online.target

[Service]
ExecStart=/usr/local/bin/lnd --configfile=$DIR/lnd.conf
Restart=always
RestartSec=5
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
CONF

  systemctl enable "lnd-node$i"
  # Started but NOT unlocked: a fresh LND has no wallet until one is created.
  # Wallet creation is deliberately left to scripts/lightning_bootstrap.sh so
  # that a reboot re-running this script can never re-initialise a wallet that
  # already holds channel state.
  systemctl start "lnd-node$i" || true
done

# Ownership fixed last, and only for files that exist. Phase 2's reboot
# breakage came from resetting ownership unconditionally.
chown -R ubuntu:ubuntu "$BASE" 2>/dev/null || true

echo "lightning host $HOST_INDEX ready: $NODES_PER_HOST LND nodes, bitcoind=$RUN_BITCOIND"
