"""Verify every sender key in the live keys file against the chain.

Bug 1 wrote 64 keys that matched no on-chain access key, and the fault surfaced
during a measured run as "access key does not exist while viewing" -- a chain
error for what was a setup fault. Those 64 were dropped by hand. This checks the
remaining 836 the same way the fixed bootstrap now does, BEFORE the sweep starts
rather than after it fails.

A NEAR ed25519 secret key is base58(seed || public), so the expected public key
is derivable locally; only the confirmation needs the chain.
"""
import asyncio, json, sys, urllib.request
import base58

RPC = "http://10.40.0.10:3030"
KEYS = "/opt/benchmark/keys/near_senders.json"
CONCURRENCY = 32


def pub_of(secret: str) -> str:
    raw = base58.b58decode(secret.split(":", 1)[1])
    return "ed25519:" + base58.b58encode(raw[32:]).decode()


def query(account_id: str):
    req = urllib.request.Request(RPC, data=json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "query",
        "params": {"request_type": "view_access_key_list",
                   "finality": "final", "account_id": account_id},
    }).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


async def main() -> int:
    keys = json.loads(open(KEYS).read())
    print(f"{len(keys)} sender keys on file")
    sem = asyncio.Semaphore(CONCURRENCY)
    loop = asyncio.get_running_loop()
    bad, missing = [], []

    async def check(k):
        async with sem:
            want = pub_of(k["private_key"])
            try:
                res = await loop.run_in_executor(None, query, k["account_id"])
            except Exception as e:                 # noqa: BLE001
                missing.append((k["account_id"], f"{type(e).__name__}"))
                return
            r = res.get("result")
            if not r:
                missing.append((k["account_id"], str(res.get("error"))[:60]))
                return
            if not any(x.get("public_key") == want for x in r.get("keys", [])):
                bad.append((k["account_id"], want))

    await asyncio.gather(*(check(k) for k in keys))

    print(f"\n  keys matching an on-chain access key : {len(keys)-len(bad)-len(missing)}")
    print(f"  keys with NO matching access key      : {len(bad)}")
    print(f"  accounts that could not be queried    : {len(missing)}")
    for a, w in bad[:5]:
        print(f"    MISMATCH {a} expected {w}")
    for a, e in missing[:5]:
        print(f"    UNQUERYABLE {a}: {e}")
    ok = not bad and not missing
    print(f"\n  VERDICT: {'all sender keys are usable' if ok else '*** SOME SENDERS CANNOT SIGN ***'}")
    return 0 if ok else 1


sys.exit(asyncio.run(main()))
