#!/usr/bin/env bash
# Every validator's own view of the tip. HEAD is the MAXIMUM across all nodes,
# not validator-0's view -- when validator-0 is restarting, trusting it produced
# "0 validators behind" while two were 200 blocks back.
declare -A H
MAX=0
for ip in 10.40.0.10 10.40.0.2 10.40.1.2 10.40.1.3 10.40.2.3 10.40.2.2 10.40.3.3 10.40.3.2; do
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
for ip in 10.40.0.10 10.40.0.2 10.40.1.2 10.40.1.3 10.40.2.3 10.40.2.2 10.40.3.3 10.40.3.2; do
  r="${H[$ip]}"; h=$(echo "$r" | cut -d" " -f1); s=$(echo "$r" | cut -d" " -f2)
  if [ -z "$h" ]; then echo "  $ip  UNREACHABLE"; BEHIND=$((BEHIND+1)); continue; fi
  d=$((MAX - h)); flag=""
  { [ "$d" -gt 30 ] || [ "$s" = "True" ]; } && { flag="  <== NOT AT TIP"; BEHIND=$((BEHIND+1)); }
  echo "  $ip  height $h  behind $d  syncing=$s$flag"
done
echo "NOT_AT_TIP=$BEHIND"
