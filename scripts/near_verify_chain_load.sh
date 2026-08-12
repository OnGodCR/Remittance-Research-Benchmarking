#!/usr/bin/env bash
# Is the background traffic ACTUALLY landing in blocks?
#
# The generator reports "sent", which means the node accepted the broadcast.
# That is not the same as executed: the account top-up reported 1,187 successful
# sends while every one was silently dropped for a stale nonce. The only
# trustworthy evidence is transactions appearing in blocks.
/opt/benchmark/.venv/bin/python - <<'PY'
import json, urllib.request, time
RPC="http://10.40.0.10:3030"
def q(m,p):
    r=urllib.request.Request(RPC,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),
                             headers={"Content-Type":"application/json"})
    return json.load(urllib.request.urlopen(r,timeout=20))["result"]

head=q("block",{"finality":"final"})
h=head["header"]["height"]
print(f"sampling blocks below height {h}\n")
tot=0; blocks=0; first=None; last=None; gas_used=0; gas_limit=0
for i in range(10):
    try: b=q("block",{"block_id":h-i})
    except Exception: continue
    ts=b["header"]["timestamp"]
    first = ts if first is None else first
    last = ts
    n=0
    for ch in b["chunks"]:
        gas_used += ch.get("gas_used",0); gas_limit += ch.get("gas_limit",0)
        try: n+=len(q("chunk",{"chunk_id":ch["chunk_hash"]})["transactions"])
        except Exception: pass
    tot+=n; blocks+=1
span=(first-last)/1e9 if first and last else 1
print(f"  {blocks} blocks over {span:.1f}s, {tot} transactions")
print(f"  => chain is carrying {tot/span:.1f} transactions/sec")
print(f"  block utilisation: {100*gas_used/max(1,gas_limit):.2f}% of gas limit")
print()
print("  expected right now: ~88/sec background + the measured run's offered load")
print(f"  {'PLAUSIBLE -- background traffic is real' if tot/span > 50 else '*** TOO LOW -- background traffic may not be landing ***'}")
PY
