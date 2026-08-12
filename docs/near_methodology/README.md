# NEAR methodology notes

Reference material for writing up the NEAR (sharding) arm. Each file states what is measured, what is derived, and which limitations must appear in the paper.

| File | Covers |
|---|---|
| [`shard_scaling.md`](shard_scaling.md) | How a 4-shard measurement answers a 10-shard question. The $c(S)$ formula and why a naive average cannot be scaled. |
| [`cost_per_transaction.md`](cost_per_transaction.md) | Gas summed across receipts, priced with mainnet rates. RQ3. |
| [`settlement_definition.md`](settlement_definition.md) | Why settlement means `FINAL` and what accepting `EXECUTED_OPTIMISTIC` would have done to the comparison. |

---

## The three numbers this arm exists to produce

1. **Throughput** — per-shard, and scaled to mainnet shard count.
2. **Cost per transaction** — flat with amount if NEAR behaves like Polygon; the pre-registered expectation.
3. **Same-shard versus cross-shard overhead** — the property unique to sharding, and the reason the other two need a shard-count correction.

---

## Constraints that shaped the deployment

**8 validators, 4 shards — set by quota, not preference.** NEAR needs ≥2 validators per shard. Matching mainnet's **10 shards** (measured 12 Aug 2026) needs 20 validators, which at NEAR's published 8 vCPU minimum is 160 vCPU against a project ceiling of 96. Requests for 144, 120 and 136 were each denied. 4 shards with 2 validators each is what fits.

**No margin on validators per shard.** With exactly 2 per shard, losing one node drops a shard to a single validator. **NEAR's adversarial arm is therefore harsher than Polygon's**, where losing one of four validators still left three. Say so when comparing them — a worse NEAR result under node failure is partly a consequence of the quota, not purely a property of sharding.

**Hardware matched to spec, deliberately.** `n2-standard-8` (8 vCPU / 32 GB), the same instance used for Polygon's validators. Running 16 validators at 4 vCPU would have fitted 8 shards inside the quota, but it would have put a hardware confound directly inside the cross-architecture comparison this project exists to make.

---

## What must be stated in the paper

1. **Results describe one sharding implementation**, NEAR's Nightshade — not sharding as a general architectural concept.
2. **4 shards measured, 10 on mainnet** (measured 12 Aug 2026, protocol 86, layout V3). The scaling method and its assumption are in `shard_scaling.md`; the bias is conservative. Mainnet also runs **422 validators, 10 per shard**, against our 2 — the protocol minimum.
3. **2 validators per shard is the protocol minimum**, so the adversarial arm is harsher than Polygon's equivalent.
4. **Cost is priced with mainnet gas and token prices** pulled on one stated date, not with our own chain's gas price, which we set ourselves.
5. **Settlement means `FINAL`.** See `settlement_definition.md` — accepting the optimistic status would have understated latency and flattered NEAR against Polygon.
