# Shard Scaling — how a 4-shard measurement answers an 8-shard question

**Written:** 11 August 2026
**Use this when:** writing the NEAR results and the Limitations section, and whenever a reader asks why a 4-shard testbed can say anything about a 10-shard mainnet.

> **Corrected 12 Aug 2026.** This document said mainnet ran "8–9 shards", carried over from planning. Queried directly (`EXPERIMENTAL_protocol_config` on `rpc.mainnet.near.org`, 12 Aug 2026, protocol version 86, shard layout **V3**): mainnet runs **10 shards** with **422 validators, 10 per shard**. Every figure below is updated. The correction makes the cross-shard blend *larger*, so the conservative direction of our bias is unchanged — see §2.

---

## 1. The problem in one paragraph

NEAR mainnet runs **10 shards** (measured 12 Aug 2026, shard layout V3). Our testbed runs **4**, and that is forced by quota: NEAR needs at least 2 validators per shard for consensus, so 10 shards means 20 validators, which at NEAR's published 8 vCPU minimum is 160 vCPU against a 96 ceiling. Requests for 144, 120 and 136 were all denied. So the question is not "can we run 10 shards" — we cannot — but **"can a 4-shard measurement be honestly extended to 10?"**

A second gap, newly measured and worth stating beside the first: mainnet carries **10 validators per shard**; we carry **2**, the protocol minimum. Our shards therefore have no redundancy where mainnet's have nine spare producers each. That does not affect the throughput scaling below — capacity per shard is set by block gas limit and timing, not producer count — but it is why our adversarial arm is harsher than mainnet conditions and must not be read as a mainnet failure model.

The answer is yes, but **not by measuring an average and multiplying.** That was the first instinct and it is wrong.

---

## 2. Why the naive approach fails

Shard count changes two different things, and only one of them is linear.

**Capacity is linear.** Shards execute independently — that is the design intent of Nightshade — so total throughput is roughly the sum over shards. Doubling shards roughly doubles capacity.

**The mix of work is not.** NEAR routes a transaction to the shard that owns the **receiver's** account. So for a randomly-addressed transfer:

$$P(\text{cross-shard}) = \frac{S-1}{S}$$

| Shards $S$ | $P(\text{cross-shard})$ |
|---|---|
| 4 (ours) | 75.0% |
| 6 | 83.3% |
| 8 | 87.5% |
| 9 | 88.9% |
| **10 (mainnet, measured 12 Aug 2026)** | **90.0%** |

A cross-shard transfer costs more than a same-shard one: the transaction executes on the sender's shard, produces a receipt, and that receipt executes on the receiver's shard in a **later block**. It pays an extra block of latency and additional gas.

So as $S$ rises, a larger fraction of all transfers pays the higher cost. **Reporting our 4-shard average and scaling it would understate mainnet's per-transaction cost and latency**, because mainnet's blend is more cross-shard than ours.

---

## 3. The method actually used

Measure the two regimes **separately**, then recombine for whatever shard count is being discussed.

Every transaction is classified at submission time by comparing the sender's and receiver's shards, and the result is stored per payment (see §5). That gives two independent measurements rather than one blended one:

- $c_{\text{same}}$ — cost or latency of a same-shard transfer
- $c_{\text{cross}}$ — cost or latency of a cross-shard transfer

The expected value at any shard count is then:

$$\boxed{\;c(S) \;=\; \frac{1}{S}\,c_{\text{same}} \;+\; \frac{S-1}{S}\,c_{\text{cross}}\;}$$

This applies unchanged to **settlement latency**, **gas burnt**, and **cost in dollars**.

### Worked example (substitute your measured values)

Let $c_{\text{same}} = a$ and $c_{\text{cross}} = b$:

| $S$ | $c(S)$ | as a fraction of $b$ |
|---|---|---|
| 4 | $0.250a + 0.750b$ | — |
| 8 | $0.125a + 0.875b$ | — |
| 9 | $0.111a + 0.889b$ | — |

The **correction factor** from our measurement to mainnet is:

$$\frac{c(8)}{c(4)} \;=\; \frac{0.125a + 0.875b}{0.250a + 0.750b}$$

Note this is **always ≥ 1** whenever $b > a$, i.e. whenever cross-shard genuinely costs more. So our 4-shard figures are **conservative** — they understate mainnet cost and latency, never overstate them. That is the safe direction of bias, and it should be stated as such.

### Throughput scales the other way

For throughput the shard count multiplies capacity while the mix degrades per-transaction efficiency. If $T_{\text{shard}}$ is measured per-shard throughput:

$$T(S) \;\approx\; S \cdot T_{\text{shard}} \cdot \frac{c(4)}{c(S)}$$

The second factor is the correction for the worsening mix. It is a modest downward adjustment on an otherwise linear scaling — **not** a reason to expect sub-linear scaling in general.

---

## 4. Why this is stronger than running 8 shards would have been

Running at 8 shards would have produced **one number, at one shard count**. Measuring the two regimes separately produces **a function of shard count**, which:

- answers the mainnet question today (10 shards) and tomorrow's (NEAR has been increasing shard count: 4 → 6 → 8 → 10)
- makes the underlying mechanism explicit rather than buried in an average
- lets a reader check the reasoning against their own assumptions about $S$

**State the limitation honestly anyway:** the two regimes are measured on a 4-shard chain with 2 validators per shard. If cross-shard cost itself varies with shard count — for example through congestion control behaving differently at 9 shards — this method would not capture it. Nothing in our data can rule that out.

---

## 5. Where the data is

Every NEAR payment records which regime it was, in the `route_hops` column:

| Value | Meaning |
|---|---|
| `0` | same-shard transfer |
| `1` | cross-shard transfer |

The column is unused for NEAR otherwise, and "shard boundaries crossed" is a fair reading of the name. Classification happens in `harness/adapters/near.py::_shard_of`, which buckets an account name against the genesis `boundary_accounts` — the same rule NEAR itself uses to assign accounts to shards.

**A health check refuses to start a run if the boundaries could not be read.** Without them every transfer would be silently classified as same-shard, the cross-shard finding would vanish, and the data would look clean while being useless.

### Query to reproduce the two regimes

```sql
SELECT
  CASE t.route_hops WHEN 0 THEN 'same-shard' ELSE 'cross-shard' END AS regime,
  COUNT(*)                                          AS payments,
  ROUND(AVG(t.confirmed_offset - t.submitted_offset), 3) AS mean_latency_s,
  ROUND(AVG(t.gas_used), 0)                         AS mean_gas
FROM transactions t
JOIN runs r ON t.run_id = r.run_id
WHERE r.architecture = 'near'
  AND r.invalidated = 0
  AND t.status = 'confirmed'
GROUP BY regime;
```

---

## 6. Sanity check on the observed mix

With randomly-addressed transfers on a 4-shard chain, roughly **75%** of payments should come back as cross-shard. If the observed share is far from that, something is wrong with account placement rather than with NEAR:

- **Close to 0%** — all accounts landed on one shard. The arm is measuring a non-sharded chain. `scripts/near_bootstrap.py` refuses to write a config in this case, but check anyway.
- **Close to 100%** — senders and recipients are cleanly separated onto different shards, so the same-shard regime is unmeasured and $c_{\text{same}}$ has no data behind it.

Both are fixture faults, not findings.
