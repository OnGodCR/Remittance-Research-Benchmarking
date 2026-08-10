#!/usr/bin/env python3
"""Map topology node ids onto real host:port endpoints and their macaroons.

The topology is abstract -- it says `hub-major-0` connects to `leaf-03`. The
deployment is concrete -- five LND daemons per host on consecutive ports. This
turns one into the other, and the mapping must be DETERMINISTIC: if node ids
were assigned to ports differently on a re-deploy, the funded channel topology
would no longer match the plan that was verified against 1ML, and the arm's
central claim to realism would quietly stop being true.

Nodes on a host are therefore sorted by node id and assigned local index 0..4,
matching ports 8080..8084 exactly as the startup script created them.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import topology as topo_mod  # noqa: E402

def host_ips() -> dict[int, str]:
    """Read the hosts' private IPs from GCP rather than assuming them.

    Only host 0 has a pinned address (bitcoind needs a stable one). The rest
    get whatever the subnet hands out, and that CHANGES when an instance is
    replaced -- a rebuild moved them from .2 to .3, which a hardcoded table
    would not have noticed. It would have produced connection failures that
    look exactly like Lightning nodes refusing payments.
    """
    import subprocess
    out = subprocess.run(
        ["gcloud", "compute", "instances", "list", "--filter=name~'^ln-host-'",
         "--format=value(name,networkInterfaces[0].networkIP)"],
        capture_output=True, text=True, check=True).stdout
    ips: dict[int, str] = {}
    for line in out.strip().splitlines():
        name, ip = line.split()
        ips[int(name.rsplit("-", 1)[1])] = ip
    return ips


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--macaroons", required=True,
                    help="lines of '<host_index> <local_index> <macaroon_hex>'")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    macaroons: dict[tuple[int, int], str] = {}
    for line in Path(args.macaroons).read_text().splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        host, local, mac = parts
        macaroons[(int(host), int(local))] = mac

    plan = topo_mod.build()
    HOST_IPS = host_ips()
    print(f"  host IPs (read live): {HOST_IPS}")

    endpoints: dict[str, dict[str, str]] = {}
    missing: list[str] = []
    for host_index in sorted({n.host_index for n in plan.nodes}):
        on_host = sorted((n for n in plan.nodes if n.host_index == host_index),
                         key=lambda n: n.node_id)
        for local_index, node in enumerate(on_host):
            mac = macaroons.get((host_index, local_index))
            if mac is None:
                missing.append(f"{node.node_id} (host {host_index}, node {local_index})")
                continue
            endpoints[node.node_id] = {
                "url": f"https://{HOST_IPS[host_index]}:{8080 + local_index}",
                "macaroon": mac,
                "host_index": host_index,
                "local_index": local_index,
                "tier": node.tier,
                "role": node.role,
            }

    if missing:
        print(f"ERROR: no macaroon for {len(missing)} node(s):")
        for m in missing[:10]:
            print(f"  {m}")
        return 1

    Path(args.out).write_text(json.dumps(endpoints, indent=2))
    by_role: dict[str, int] = {}
    for e in endpoints.values():
        by_role[e["role"]] = by_role.get(e["role"], 0) + 1
    print(f"  {len(endpoints)} endpoints -> {args.out}")
    print(f"  {by_role}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
