"""Build a Lightning channel topology matching the real network's shape.

REALISM TECHNIQUE #5 (claude.md S5). This is the module that decides whether
the Lightning results mean anything.

WHY THIS EXISTS
---------------
A test network with evenly-funded channels is not Lightning. It is a much
easier network to route through, and it would understate exactly the routing
failures this study exists to measure. The real network's defining property is
extreme concentration of liquidity: from 1ML on 9 Aug 2026 (see
`data/reference/calibration_2026-08-09.md`), average node capacity is **142x
the median** -- a handful of very well-funded hubs, and thousands of thin
leaves that can barely forward anything.

Waugh & Holz (2020) found payment success falling from ~72% to ~15% as payment
size rises. That gradient is a *consequence* of this shape: a large payment
needs every hop on some path to hold enough liquidity in the right direction,
and in a concentrated network few paths qualify. Flatten the topology and the
gradient disappears -- we would measure ~100% success at every size, conclude
Lightning is more reliable than the literature says, and be wrong because of
our own test fixture.

WHAT IS PRESERVED, AND WHAT IS NOT
----------------------------------
We preserve the *concentration*, not the absolute capacities. A private
regtest network needs no real capital, and matching mainnet's 2,645 BTC would
be meaningless. What must match is the ratio structure:

    mean/median node capacity   ~= 142x
    channels per node (mean)    ~= 6.54

`verify()` checks the generated plan against those targets, because a topology
that silently comes out flat would invalidate the headline Lightning result
without any error being raised.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field, asdict
from statistics import mean, median
from typing import Any

# --- Observed mainnet structure, 1ML, 9 Aug 2026 -----------------------------
# Recorded here as constants so the generated topology and the paper's
# justification cannot drift apart. Source and caveats live in
# data/reference/calibration_2026-08-09.md; that file is the citation.
OBSERVED_NODES = 6_010
OBSERVED_CHANNELS = 19_644
OBSERVED_AVG_CHANNELS_PER_NODE = 6.54
OBSERVED_MEAN_NODE_CAPACITY_BTC = 0.440
OBSERVED_MEDIAN_NODE_CAPACITY_BTC = 0.003107
OBSERVED_MEAN_CHANNEL_CAPACITY_BTC = 0.134
OBSERVED_MEDIAN_CHANNEL_CAPACITY_BTC = 0.020256
OBSERVED_CAPACITY_SKEW = OBSERVED_MEAN_NODE_CAPACITY_BTC / OBSERVED_MEDIAN_NODE_CAPACITY_BTC  # ~142x

SATS_PER_BTC = 100_000_000

# --- Why capacities are sampled, not assigned ---------------------------------
# The first version of this module split capacity into fixed tier shares
# (55/30/15) and divided evenly inside each tier. `verify()` rejected it: the
# result was 6.3x skew against mainnet's 142x -- flat enough to route almost
# anything, which would have manufactured a Lightning reliability result that
# contradicted the literature for a reason entirely of our own making.
#
# The fix is to stop inventing the distribution and fit the observed one. 1ML
# reports two moments of channel capacity -- mean 0.134 BTC, median 0.020256
# BTC. A lognormal is the standard heavy-tailed fit and is determined exactly
# by those two numbers:
#
#     median = exp(mu)                  -> mu    = ln(0.020256) = -3.8993
#     mean   = exp(mu + sigma^2 / 2)    -> sigma = 1.9439
#
# Sampling from that gives a realistic spread rather than a few sizes we chose:
# most channels thin, a few very large. Both the node-level 142x skew and the
# payment-size failure gradient then emerge from the distribution instead of
# being imposed by hand.
LOGNORMAL_MU = -3.8993
LOGNORMAL_SIGMA = 1.9439

# --- Our deployment ----------------------------------------------------------
# 20 nodes in three tiers. Small enough to run on four cheap instances, large
# enough that a payment can need 3-4 hops and so actually fail for want of
# liquidity.
MAJOR_HUBS = 2
SECONDARY_HUBS = 4
LEAF_NODES = 14

#: Upstream connections per leaf. Averages ~3, which with the hub backbone puts
#: channels-per-node near the observed 6.54.
LEAF_UPSTREAM_MIN = 2
LEAF_UPSTREAM_MAX = 4

#: Absolute capacities are kept at real mainnet scale rather than scaled down.
#: Regtest coins are free, so there is no reason to shrink them -- and shrinking
#: would break the one relationship that decides every routing outcome: how a
#: $10-$500 payment compares to the capacity of the channels it must cross.
#: At the pinned BTC rate a $200 remittance is 15% of a median channel and 99%
#: of a median *node's entire capacity*. That is the structural reason payment
#: size drives success on Lightning, and it only survives at true scale.

#: Sats the channel opener pushes to the far side at open. Real channels start
#: one-sided: the opener holds everything and can only send. Some inbound
#: liquidity is needed or leaves could never receive at all.
LEAF_INBOUND_PUSH_FRACTION = 0.20


@dataclass
class Node:
    """One LND node in the plan."""

    node_id: str
    tier: str                       # major_hub | secondary_hub | leaf
    host_index: int                 # which instance it lives on
    role: str                       # sender | recipient | router

    def __str__(self) -> str:       # pragma: no cover - debugging aid
        return f"{self.node_id}({self.tier})"


@dataclass
class Channel:
    """One funded channel. Direction matters: `source` opens and funds it."""

    source: str
    target: str
    capacity_sat: int
    push_sat: int                   # moved to target at open -> target's inbound

    @property
    def source_balance_sat(self) -> int:
        return self.capacity_sat - self.push_sat


@dataclass
class Topology:
    nodes: list[Node] = field(default_factory=list)
    channels: list[Channel] = field(default_factory=list)

    def capacity_by_node(self) -> dict[str, int]:
        """Total capacity each node participates in, both sides counted.

        This mirrors how 1ML reports node capacity, so our verification
        compares like with like.
        """
        totals = {n.node_id: 0 for n in self.nodes}
        for c in self.channels:
            totals[c.source] += c.capacity_sat
            totals[c.target] += c.capacity_sat
        return totals

    def channel_count_by_node(self) -> dict[str, int]:
        counts = {n.node_id: 0 for n in self.nodes}
        for c in self.channels:
            counts[c.source] += 1
            counts[c.target] += 1
        return counts

    def senders(self) -> list[Node]:
        return [n for n in self.nodes if n.role == "sender"]

    def recipients(self) -> list[Node]:
        return [n for n in self.nodes if n.role == "recipient"]


def build(seed: int = 20260809) -> Topology:
    """Generate the channel plan.

    Seeded and deterministic: the same topology must come back on every
    deployment, or repeats of a configuration would be measuring different
    networks and the confidence intervals would be meaningless.
    """
    rng = random.Random(seed)
    topo = Topology()

    majors = [f"hub-major-{i}" for i in range(MAJOR_HUBS)]
    secondaries = [f"hub-secondary-{i}" for i in range(SECONDARY_HUBS)]
    leaves = [f"leaf-{i:02d}" for i in range(LEAF_NODES)]

    # --- Placement: senders and recipients sit in real corridor regions ------
    #
    # An earlier version put every leaf on one host. That balanced badly (14
    # nodes on one machine) but the real fault was worse: with payer and payee
    # in the same region, every payment would have been settled inside one
    # datacentre and the arm would have measured almost no internet latency at
    # all. Realism technique #1 would have been present in the deployment and
    # absent from the measurement.
    #
    # Placement now follows the corridors the regions were chosen for, so
    # every measured payment crosses an ocean the way a real remittance does:
    #
    #   host 0  us-east4        Virginia   sending   -- major hub + senders
    #   host 1  asia-south1     Mumbai     receiving -- major hub + recipients
    #   host 2  asia-southeast1 Singapore  receiving -- secondaries + recipients
    #   host 3  europe-west2    London     sending   -- secondaries + senders
    #
    # Five nodes per host, matching terraform/phase3 `nodes_per_host`.
    senders = leaves[: LEAF_NODES // 2]
    recipients = leaves[LEAF_NODES // 2:]

    topo.nodes.append(Node(majors[0], "major_hub", host_index=0, role="router"))
    topo.nodes.append(Node(majors[1], "major_hub", host_index=1, role="router"))
    for nid in secondaries[:2]:
        topo.nodes.append(Node(nid, "secondary_hub", host_index=3, role="router"))
    for nid in secondaries[2:]:
        topo.nodes.append(Node(nid, "secondary_hub", host_index=2, role="router"))

    # Senders split across the two sending regions, recipients across the two
    # receiving regions. A node paying itself tests nothing, so the roles are
    # disjoint.
    for i, nid in enumerate(senders):
        topo.nodes.append(Node(nid, "leaf", host_index=0 if i < 4 else 3, role="sender"))
    for i, nid in enumerate(recipients):
        topo.nodes.append(Node(nid, "leaf", host_index=1 if i < 4 else 2, role="recipient"))

    # --- Structure first: who connects to whom -------------------------------
    #
    # 1. Hub backbone. Every major connects to every other major and to every
    #    secondary. This is the well-connected core that makes multi-hop
    #    routing possible at all.
    backbone: list[tuple[str, str]] = []
    for i, a in enumerate(majors):
        for b in majors[i + 1:]:
            backbone.append((a, b))
        for b in secondaries:
            backbone.append((a, b))

    # 2. Secondary mesh -- partial, not complete. Real mid-tier nodes are not
    #    all connected to each other, and leaving gaps means some routes
    #    genuinely do not exist, which is the point.
    sec_pairs = [(a, b) for i, a in enumerate(secondaries) for b in secondaries[i + 1:]]
    rng.shuffle(sec_pairs)
    mesh = sec_pairs[: max(1, (len(sec_pairs) * 2) // 3)]

    # 3. Leaves attach upstream. Most nodes on the real network are exactly
    #    this: a few channels into better-connected peers, and little else.
    #
    #    WHICH SIDE OPENS THE CHANNEL DECIDES WHO CAN BE PAID.
    #    A channel's opener holds the balance, so it can send but cannot
    #    receive. That is the well-known inbound-liquidity problem, and it
    #    splits our two leaf roles:
    #      - senders open their own channels, so they hold outbound balance
    #      - recipients have channels opened *to* them by a hub
    #    The second is not a convenience; it is how real Lightning payment
    #    services work. A provider opens a funded channel to the user precisely
    #    so the user can receive. Had every leaf opened its own channel, no
    #    recipient could have been paid at all and the arm would have measured
    #    100% failure caused entirely by our own fixture.
    leaf_links: list[tuple[str, str]] = []
    for leaf in leaves:
        role = "sender" if leaf in {n.node_id for n in topo.nodes if n.role == "sender"} else "recipient"
        k = rng.randint(LEAF_UPSTREAM_MIN, LEAF_UPSTREAM_MAX)
        for up in rng.sample(secondaries + majors, k):
            # (source, target): source funds the channel.
            leaf_links.append((leaf, up) if role == "sender" else (up, leaf))

    # --- Capacities second: sample, sort, assign by structural importance -----
    #
    # Every channel's capacity is drawn from the fitted lognormal, so the
    # marginal distribution matches 1ML's by construction. Sorting and giving
    # the largest to the backbone reproduces the real network's arrangement --
    # big channels between well-connected nodes, thin ones at the edge --
    # without distorting the distribution we just fitted.
    total_channels = len(backbone) + len(mesh) + len(leaf_links)
    caps = sorted(
        (max(int(rng.lognormvariate(LOGNORMAL_MU, LOGNORMAL_SIGMA) * SATS_PER_BTC), 20_000)
         for _ in range(total_channels)),
        reverse=True,
    )

    # Hubs take the largest channels -- on the real network they genuinely do.
    # The remainder is SHUFFLED rather than left sorted, so leaves get a
    # realistic spread (a few well-funded, most thin) instead of being handed
    # the smallest channel every time, which would have made the size gradient
    # an artifact of the sort order rather than of the distribution.
    hub_count = len(backbone) + len(mesh)
    leaf_caps = caps[hub_count:]
    rng.shuffle(leaf_caps)
    caps = caps[:hub_count] + leaf_caps

    i = 0
    for a, b in backbone:
        # Backbone channels start near-balanced: real hub-to-hub channels are
        # actively rebalanced, and a one-sided backbone would fail routing for
        # a reason that has nothing to do with payment size.
        topo.channels.append(Channel(a, b, caps[i], push_sat=caps[i] // 2))
        i += 1
    for a, b in mesh:
        topo.channels.append(Channel(a, b, caps[i], push_sat=caps[i] // 2))
        i += 1
    for leaf, up in leaf_links:
        # A leaf opens and funds its own channel, so it starts holding almost
        # all the balance -- able to send, but with little inbound. That
        # asymmetry is why receiving is harder than sending on real Lightning,
        # and it is why our recipient leaves are the binding constraint.
        topo.channels.append(
            Channel(leaf, up, caps[i], push_sat=int(caps[i] * LEAF_INBOUND_PUSH_FRACTION))
        )
        i += 1

    return topo


def verify(topo: Topology) -> dict[str, Any]:
    """Check the generated plan reproduces the observed concentration.

    Returns a report rather than raising: the deployment script decides what to
    do, and the numbers belong in the methodology log either way.
    """
    caps = list(topo.capacity_by_node().values())
    counts = list(topo.channel_count_by_node().values())
    ch_caps = [c.capacity_sat for c in topo.channels]

    cap_mean, cap_median = mean(caps), median(caps)
    skew = cap_mean / cap_median if cap_median else float("inf")
    channels_per_node = mean(counts)

    # Tolerances are wide on purpose. With 20 nodes we cannot land exactly on a
    # 6,010-node network's statistics, and pretending otherwise would be false
    # precision. What matters is being concentrated at all -- a flat topology
    # scores near 1.0 and must be caught.
    return {
        "nodes": len(topo.nodes),
        "channels": len(topo.channels),
        "capacity_skew": round(skew, 1),
        "capacity_skew_target": round(OBSERVED_CAPACITY_SKEW, 1),
        "skew_ok": skew >= 10.0,
        "channels_per_node": round(channels_per_node, 2),
        "channels_per_node_target": OBSERVED_AVG_CHANNELS_PER_NODE,
        "channels_per_node_ok": 3.0 <= channels_per_node <= 12.0,
        "channel_capacity_mean_btc": round(mean(ch_caps) / SATS_PER_BTC, 4),
        "channel_capacity_median_btc": round(median(ch_caps) / SATS_PER_BTC, 6),
        "channel_capacity_mean_target": OBSERVED_MEAN_CHANNEL_CAPACITY_BTC,
        "channel_capacity_median_target": OBSERVED_MEDIAN_CHANNEL_CAPACITY_BTC,
        "total_capacity_sat": sum(ch_caps),
        "senders": len(topo.senders()),
        "recipients": len(topo.recipients()),
        "nodes_per_host": {h: sum(1 for n in topo.nodes if n.host_index == h)
                           for h in sorted({n.host_index for n in topo.nodes})},
        "cross_region_payment_paths": all(
            s.host_index != r.host_index
            for s in topo.senders() for r in topo.recipients()),
    }


def to_json(topo: Topology) -> str:
    return json.dumps(
        {
            "nodes": [asdict(n) for n in topo.nodes],
            "channels": [asdict(c) for c in topo.channels],
            "verification": verify(topo),
        },
        indent=2,
    )


if __name__ == "__main__":  # pragma: no cover
    t = build()
    report = verify(t)
    print(f"nodes {report['nodes']}  channels {report['channels']}")
    print(f"capacity skew   {report['capacity_skew']}x "
          f"(mainnet {report['capacity_skew_target']}x)  "
          f"{'OK' if report['skew_ok'] else 'TOO FLAT -- would understate routing failure'}")
    print(f"channels/node   {report['channels_per_node']} "
          f"(mainnet {report['channels_per_node_target']})  "
          f"{'OK' if report['channels_per_node_ok'] else 'OUT OF RANGE'}")
    print(f"channel capacity  mean {report['channel_capacity_mean_btc']} BTC "
          f"(mainnet {report['channel_capacity_mean_target']}), "
          f"median {report['channel_capacity_median_btc']} BTC "
          f"(mainnet {report['channel_capacity_median_target']})")
    print(f"senders {report['senders']}  recipients {report['recipients']}")
    print(f"nodes per host  {report['nodes_per_host']}  "
          f"every payment crosses regions: {report['cross_region_payment_paths']}")
    print()
    print("Can a recipient leaf actually receive each test amount?")
    print("  (inbound liquidity = what the upstream side of its channels holds)")
    btc_usd = 65163.0
    # Channel(source=A, target=B, capacity, push): A holds capacity-push,
    # B holds push. So A can RECEIVE at most `push` (what sits on B's side),
    # and B can receive at most `capacity - push`.
    inbound = {n.node_id: 0 for n in t.nodes}
    for ch in t.channels:
        inbound[ch.source] += ch.push_sat
        inbound[ch.target] += ch.capacity_sat - ch.push_sat
    for usd in (10, 50, 200, 500):
        sat = usd / btc_usd * 1e8
        able = sum(1 for n in t.recipients() if inbound.get(n.node_id, 0) >= sat)
        print(f"  ${usd:>3}: {able}/{len(t.recipients())} recipients have the inbound liquidity")
