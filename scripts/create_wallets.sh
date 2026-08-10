#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Runs ON A LIGHTNING HOST. Creates a wallet for each LND node that lacks one,
# unlocks any that already exist, waits for every node to be serving, then
# prints each node's admin macaroon as hex.
#
# WHY THIS IS SEPARATE FROM THE STARTUP SCRIPT
#
# GCP re-runs startup scripts on EVERY boot (RESUME_HERE.md S5 trap 2). Running
# `initwallet` a second time would create a NEW wallet and abandon the channel
# state of the old one -- destroying the funded topology and doing it silently:
# the nodes would come back healthy with zero channels, which reads exactly
# like a catastrophic Lightning reliability result.
#
# WHY TWO PASSES
#
# The first version created and then waited for each node in turn, with a 180s
# budget each. Five LND nodes on one host all sync the chain and build their
# routing graph at the same time, and the later ones needed longer than that --
# so the script died on node 1 while node 1 was merely still starting. Creating
# every wallet first and then waiting on all of them together is both faster
# and immune to how the work happens to be spread across nodes.
#
# Usage:  create_wallets.sh <nodes_per_host>
# Output: one "<local_index> <macaroon_hex>" line per node, on stdout.
#         Progress goes to stderr so stdout stays machine-readable.
# ---------------------------------------------------------------------------
set -euo pipefail

NODES="${1:?usage: create_wallets.sh <nodes_per_host>}"
BASE=/opt/lightning

# Fixed password. A private regtest network whose coins are mined by us and
# worth nothing, reachable only inside the VPC. Per-node passwords would add a
# secret-distribution problem with no security benefit. Never reuse this.
PASSWORD_B64="$(printf 'benchmarkwallet' | base64)"

READY_TIMEOUT=900     # generous: 5 nodes syncing together, across regions
PORT_TIMEOUT=240

state_of() {
  curl -sk --max-time 4 "https://localhost:$1/v1/state" 2>/dev/null \
    | grep -o '"state":"[A-Z_]*"' | cut -d'"' -f4 || true
}

# --- pass 1: every node gets a wallet, no waiting ---------------------------
for i in $(seq 0 $((NODES - 1))); do
  REST=$((8080 + i))

  waited=0
  while [ -z "$(state_of "$REST")" ]; do
    sleep 3; waited=$((waited + 3))
    [ "$waited" -ge "$PORT_TIMEOUT" ] && { echo "ERROR node$i: REST $REST never answered" >&2; exit 1; }
  done

  case "$(state_of "$REST")" in
    NON_EXISTING)
      SEED="$(curl -sk --max-time 30 "https://localhost:$REST/v1/genseed")"
      MNEMONIC="$(echo "$SEED" | python3 -c 'import sys,json; print(json.dumps(json.load(sys.stdin)["cipher_seed_mnemonic"]))')"
      curl -sk --max-time 60 -X POST "https://localhost:$REST/v1/initwallet" \
        -d "{\"wallet_password\":\"$PASSWORD_B64\",\"cipher_seed_mnemonic\":$MNEMONIC}" >/dev/null
      echo "  node$i: wallet created" >&2
      ;;
    LOCKED)
      # Survives a reboot but starts locked. Unlock, NEVER re-init.
      curl -sk --max-time 60 -X POST "https://localhost:$REST/v1/unlockwallet" \
        -d "{\"wallet_password\":\"$PASSWORD_B64\"}" >/dev/null
      echo "  node$i: wallet unlocked" >&2
      ;;
    *)
      echo "  node$i: already up" >&2
      ;;
  esac
done

# --- pass 2: wait for all of them together ----------------------------------
waited=0
while true; do
  pending=""
  for i in $(seq 0 $((NODES - 1))); do
    # SERVER_ACTIVE or RPC_ACTIVE both mean the wallet is open and the node is
    # answering. LND can sit at RPC_ACTIVE while fully caught up to the chain
    # tip -- host 3's five nodes did exactly that, at the correct block height,
    # and gating strictly on SERVER_ACTIVE stalled the whole deployment for a
    # distinction that does not affect whether payments work. Chain agreement
    # is the condition that actually matters, and lightning_bootstrap.py checks
    # it properly by comparing block heights across every node.
    case "$(state_of $((8080 + i)))" in
      SERVER_ACTIVE|RPC_ACTIVE) ;;
      *) pending="$pending $i" ;;
    esac
  done
  [ -z "$pending" ] && break
  sleep 5; waited=$((waited + 5))
  if [ "$waited" -ge "$READY_TIMEOUT" ]; then
    echo "ERROR: nodes not serving after ${READY_TIMEOUT}s:$pending" >&2
    for i in $pending; do echo "  node$i state: $(state_of $((8080 + i)))" >&2; done
    exit 1
  fi
  [ $((waited % 60)) -eq 0 ] && echo "  waiting ${waited}s, pending:$pending" >&2
done

# --- emit macaroons ---------------------------------------------------------
for i in $(seq 0 $((NODES - 1))); do
  MAC="$BASE/node$i/data/chain/bitcoin/regtest/admin.macaroon"
  [ -f "$MAC" ] || { echo "ERROR node$i: no macaroon" >&2; exit 1; }
  echo "$i $(xxd -ps -u -c 1000 "$MAC")"
done
