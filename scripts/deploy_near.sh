#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Build ONE genesis for the whole cluster, distribute it, and start the chain.
#
# WHY GENESIS IS BUILT CENTRALLY
#
# Every validator must share a byte-identical genesis that lists all 8 as
# validators and pins the shard layout. `neard init` run per node would give
# each its own genesis and its own idea of the validator set, and the nodes
# would never form a single chain -- they would each sit at height 0 believing
# they were the only validator. `neard localnet` exists precisely to generate a
# consistent multi-node set, so it is run once on the boot node and the
# per-node directories are shipped out.
#
# WHY THE STARTUP SCRIPT DOES NOT DO THIS
#
# GCP re-runs startup scripts on every boot. Regenerating genesis or a
# validator key there would fork the chain or silently drop a node from the
# validator set (RESUME_HERE.md S5 trap 2). Identity creation lives here, runs
# once, explicitly.
#
# NEVER nest quotes through `gcloud compute ssh --command` (trap 5): three
# shell layers mangle escapes. And never `pkill -f <pattern>` inline (trap 8):
# it matches the ssh command line itself and kills the connection.
# ---------------------------------------------------------------------------
set -uo pipefail
cd "$(dirname "$0")/.."

PROJECT="$(grep -E '^project_id' terraform/phase4/terraform.tfvars | cut -d'"' -f2)"
NUM_SHARDS="${1:-4}"
SSH="gcloud compute ssh --strict-host-key-checking=no --project $PROJECT"
SCP="gcloud compute scp --strict-host-key-checking=no --quiet --project $PROJECT"

mapfile -t VALIDATORS < <(tofu -chdir=terraform/phase4 output -json validators \
  | .venv/bin/python -c "import sys,json; [print(v['name'], v['zone'], v['private_ip']) for v in json.load(sys.stdin)]")
NUM_VALIDATORS=${#VALIDATORS[@]}
BOOT_NAME=$(echo "${VALIDATORS[0]}" | cut -d' ' -f1)
BOOT_ZONE=$(echo "${VALIDATORS[0]}" | cut -d' ' -f2)
BOOT_IP=$(echo "${VALIDATORS[0]}" | cut -d' ' -f3)

echo "[1/5] waiting for neard on all $NUM_VALIDATORS validators"
for v in "${VALIDATORS[@]}"; do
  name=$(echo "$v" | cut -d' ' -f1); zone=$(echo "$v" | cut -d' ' -f2)
  for a in $(seq 1 60); do
    $SSH "$name" --zone "$zone" --command "test -x /usr/local/bin/neard" 2>/dev/null && break
    [ "$a" -eq 60 ] && { echo "  $name: neard never appeared"; exit 1; }
    sleep 15
  done
  echo "  $name ready"
done

echo
echo "[2/5] generating a single genesis on $BOOT_NAME ($NUM_VALIDATORS validators, $NUM_SHARDS shards)"
cat > /tmp/gen_genesis.sh <<EOF
#!/usr/bin/env bash
set -euo pipefail
BASE=/opt/near
# Idempotent: if the cluster config already exists, do not regenerate it.
# A second genesis would have different keys and every node would fork.
if [ -d "\$BASE/localnet/node0" ]; then
  echo "  genesis already generated, leaving it alone"
  exit 0
fi
rm -rf "\$BASE/localnet"
mkdir -p "\$BASE/localnet"
/usr/local/bin/neard --home "\$BASE/localnet" localnet \\
  --shards $NUM_SHARDS --validators $NUM_VALIDATORS --prefix node
echo "  generated:"
ls "\$BASE/localnet" | head -12
# Verify the shard count actually landed. A genesis with fewer shards than
# asked for would produce a chain that is not dividing work, and the arm would
# measure sharding that is not happening.
SHARDS=\$(python3 -c "
import json
g=json.load(open('\$BASE/localnet/node0/genesis.json'))
sl=g.get('shard_layout',{})
v=sl.get('V1') or sl.get('V2') or sl.get('V0') or {}
bounds=v.get('boundary_accounts')
print(len(bounds)+1 if bounds is not None else v.get('num_shards', 1))
")
echo "  genesis shard count: \$SHARDS"
[ "\$SHARDS" -ge "$NUM_SHARDS" ] || { echo "  ERROR: genesis has \$SHARDS shards, wanted $NUM_SHARDS"; exit 1; }
EOF
$SCP /tmp/gen_genesis.sh "$BOOT_NAME:/tmp/gen_genesis.sh" --zone "$BOOT_ZONE" >/dev/null 2>&1
$SSH "$BOOT_NAME" --zone "$BOOT_ZONE" --command "sudo bash /tmp/gen_genesis.sh" 2>/dev/null || exit 1

echo
echo "[3/5] collecting the boot node's peer id"
BOOT_KEY=$($SSH "$BOOT_NAME" --zone "$BOOT_ZONE" \
  --command "sudo cat /opt/near/localnet/node0/node_key.json | python3 -c 'import sys,json;print(json.load(sys.stdin)[\"public_key\"])'" 2>/dev/null)
BOOT_NODE="$BOOT_KEY@$BOOT_IP:24567"
echo "  boot node: $BOOT_NODE"

echo
echo "[4/5] distributing per-validator directories"
for i in "${!VALIDATORS[@]}"; do
  name=$(echo "${VALIDATORS[$i]}" | cut -d' ' -f1)
  zone=$(echo "${VALIDATORS[$i]}" | cut -d' ' -f2)

  # Pull node$i's directory off the boot node, push it to validator $i.
  $SSH "$BOOT_NAME" --zone "$BOOT_ZONE" \
    --command "sudo tar -czf /tmp/node$i.tar.gz -C /opt/near/localnet node$i && sudo chmod 644 /tmp/node$i.tar.gz" 2>/dev/null
  $SCP "$BOOT_NAME:/tmp/node$i.tar.gz" "/tmp/node$i.tar.gz" --zone "$BOOT_ZONE" >/dev/null 2>&1

  cat > /tmp/install_node.sh <<EOF
#!/usr/bin/env bash
set -euo pipefail
BASE=/opt/near
# Never overwrite a node that already holds chain data: it would rejoin with a
# different key and be dropped from the validator set.
if [ -f "\$BASE/node/validator_key.json" ]; then
  echo "  already configured, leaving it alone"
else
  rm -rf "\$BASE/node"
  tar -xzf /tmp/node$i.tar.gz -C /tmp
  mv /tmp/node$i "\$BASE/node"
fi
python3 - <<'PYEOF'
import json
p="/opt/near/node/config.json"
c=json.load(open(p))
c.setdefault("network",{})["boot_nodes"]="$BOOT_NODE"
# Bind RPC to all interfaces so the generator can reach it; the firewall, not
# the bind address, is what keeps it private.
c.setdefault("rpc",{})["addr"]="0.0.0.0:3030"
# Archival off: we keep hours of blocks, not years, and archival storage would
# be the single largest avoidable cost (claude.md S5 #4).
c["archive"]=False
json.dump(c, open(p,"w"), indent=2)
print("  config patched: boot node set, rpc bound, archive off")
PYEOF
chown -R ubuntu:ubuntu "\$BASE" 2>/dev/null || true
systemctl restart neard
sleep 3
systemctl is-active neard
EOF
  $SCP "/tmp/node$i.tar.gz" "/tmp/install_node.sh" "$name:/tmp/" --zone "$zone" >/dev/null 2>&1
  printf "  %s: " "$name"
  $SSH "$name" --zone "$zone" --command "sudo bash /tmp/install_node.sh" 2>/dev/null | tail -1
done

echo
echo "[5/5] waiting for the chain to produce blocks"
for a in $(seq 1 40); do
  H=$($SSH "$BOOT_NAME" --zone "$BOOT_ZONE" \
    --command "curl -s -m 5 -X POST http://localhost:3030 -H 'Content-Type: application/json' -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"status\",\"params\":[]}' | python3 -c 'import sys,json;print(json.load(sys.stdin)[\"result\"][\"sync_info\"][\"latest_block_height\"])'" 2>/dev/null)
  if [ -n "${H:-}" ] && [ "$H" -gt 2 ] 2>/dev/null; then
    echo "  chain live at height $H"
    break
  fi
  [ "$a" -eq 40 ] && { echo "  chain never produced blocks"; exit 1; }
  sleep 15
done

echo
echo "next: .venv/bin/python scripts/near_bootstrap.py"
echo "      (deploys the NEP-141 token, creates and funds accounts, writes config/phase4.json)"
