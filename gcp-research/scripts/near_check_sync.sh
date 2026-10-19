#!/usr/bin/env bash
# Every validator's own view of the tip. HEAD is the MAXIMUM across all nodes,
# not validator-0's view -- when validator-0 is restarting, trusting it produced
# "0 validators behind" while two were 200 blocks back.
#
# Addresses come from /opt/benchmark/peer_rpcs.json (written by the
# orchestrator from the infrastructure state). The old hardcoded list belonged
# to the 11 Aug cluster and would have called seven healthy machines
# UNREACHABLE -- an invitation to "fix" a cluster with nothing wrong with it.
IPS=$(python3 -c "import json;print(' '.join(json.load(open('/opt/benchmark/peer_rpcs.json')).values()))" 2>/dev/null)
if [ -z "$IPS" ]; then
  echo "error: /opt/benchmark/peer_rpcs.json missing -- run the orchestrator (or write the map) first" >&2
  exit 1
fi
declare -A H
MAX=0
for ip in $IPS; do
  r=$(curl -s -m 6 -X POST http://$ip:3030 -H 'Content-Type: application/json' \
      -d '{"jsonrpc":"2.0","id":1,"method":"status","params":[]}' 2>/dev/null \
      | python3 -c 'import sys,json;d=json.load(sys.stdin)["result"]["sync_info"];print(d["latest_block_height"],d["syncing"])' 2>/dev/null)
  H[$ip]="$r"
  h=$(echo "$r" | cut -d" " -f1)
  [ -n "$h" ] && [ "$h" -gt "$MAX" ] && MAX=$h
done
echo "chain head (max across nodes): $MAX"
BEHIND=0
for ip in "${!H[@]}"; do :; done
for ip in $IPS; do
  r="${H[$ip]}"; h=$(echo "$r" | cut -d" " -f1); s=$(echo "$r" | cut -d" " -f2)
  if [ -z "$h" ]; then echo "  $ip  UNREACHABLE"; BEHIND=$((BEHIND+1)); continue; fi
  d=$((MAX - h)); flag=""
  { [ "$d" -gt 30 ] || [ "$s" = "True" ]; } && { flag="  <== NOT AT TIP"; BEHIND=$((BEHIND+1)); }
  echo "  $ip  height $h  behind $d  syncing=$s$flag"
done
echo "NOT_AT_TIP=$BEHIND"
