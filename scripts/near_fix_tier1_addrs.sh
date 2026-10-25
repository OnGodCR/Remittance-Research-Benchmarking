#!/usr/bin/env bash
# Point this validator's TIER1 advertisement at its real address.
#
# THE BUG
# `network.public_addrs` held "<node_key>@[::1]:<random port>" -- IPv6 localhost.
# TIER1 is NEAR's direct validator-to-validator layer, used to propagate blocks
# and chunks among validators without going through general gossip. Every
# validator was telling the others to reach it at THEIR OWN localhost, so no
# TIER1 connection could ever be established and all validator traffic fell back
# to the slower TIER2 path.
#
# That was survivable at 50/sec and fatal at 100/sec: the asia-south1 pair fell
# ~460 blocks behind, stopped producing chunks, and because NEAR finality needs
# chunks from every shard, settlement stalled network-wide -- eleven consecutive
# runs recorded ZERO settled payments.
#
# PHASE4_HANDOFF.md (in git history) S6 lists "P2P must not bind [::1] -- this broke the chain
# twice". It is now three times. The fix is written into the node config rather
# than applied by hand so a restart cannot undo it.
set -uo pipefail
IP=$(hostname -I | awk '{print $1}')
sudo python3 - "$IP" <<'PY'
import json, sys
ip = sys.argv[1]
p = "/opt/near/node/config.json"
c = json.load(open(p))
key = json.load(open("/opt/near/node/node_key.json"))["public_key"]
old = (c.get("network") or {}).get("public_addrs")
c.setdefault("network", {})["public_addrs"] = [f"{key}@{ip}:24567"]
json.dump(c, open(p, "w"), indent=2)
print(f"  {old} -> {c['network']['public_addrs']}")
PY
sudo systemctl restart neard
sleep 8
echo "  neard: $(systemctl is-active neard)"
