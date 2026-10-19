# Shard Scaling — how a 4-shard measurement answers an 8-shard question

**Written:** 11 August 2026
**Use this when:** writing the NEAR results and the Limitations section, and whenever a reader asks why a 4-shard testbed can say anything about a 10-shard mainnet.

> **Corrected 12 Aug 2026.** This document said mainnet ran "8–9 shards", carried over from planning. Queried directly (`EXPERIMENTAL_protocol_config` on `rpc.mainnet.near.org`, 12 Aug 2026, protocol version 86, shard layout **V3**): mainnet runs **10 shards** with **422 validators, 10 per shard**. Every figure below is updated. The correction makes the cross-shard blend *larger*, so the conservative direction of our bias is unchanged — see §2.

> ## ⚠️ THE PRODUCT OF THIS DOCUMENT IS WITHDRAWN — 14 Aug 2026 (ANALYSIS_PLAN §13, amendment 12.2)
>
> The method below is still readable as method, and the 4-vs-10 shard gap it
> describes is still a real caveat that must travel with every NEAR number.
> **But the projection it was built to produce — scaling NEAR's measured
> throughput up to a 10-shard mainnet, and the ~372/sec figure that came out of
> it — is withdrawn and must not be quoted.**
>
> Why: the method assumes capacity grows with shard count because work spreads
> across shards. It does not, for the workload we measured. **Every NEP-141
> transfer executed on the single shard holding the token contract.** Sharding
> distributed *inclusion* and never distributed *execution*, so adding shards
> adds no capacity to a single-contract stablecoin workload at any shard count.
> That replacement finding is the one to cite.
>
> Amendment 12.2 also discredits `route_hops` as a measure of execution
> placement, which several calculations below rely on.
>
> Nothing here is deleted, because the reasoning is what a reader needs in order
> to understand why the projection failed.

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

> **Clarified 12 Aug 2026 — the correction here must use GAS.**
>
> The section above says $c(S)$ "applies unchanged to settlement latency, gas burnt, and cost in dollars", and that is true of $c(S)$ itself. It is **not** true of the ratio $c(4)/c(S)$ used here. Throughput is limited by how much *work* a shard can execute per block, so the correction is a gas ratio. Substituting the latency ratio would fold a queueing property into a capacity calculation and give a different, wrong answer — the two ratios have no reason to be equal. `analysis/shard_scaling.py` uses gas and says so in its output.

> **Precondition, added 12 Aug 2026 — $T_{\text{shard}}$ must be a measured ceiling.**
>
> This formula presumes $T_{\text{shard}}$ is the point at which a shard runs out of capacity. If the chain meets every offered load across the whole 10–300/sec ramp, then the largest throughput we observed is simply **the largest load we asked for**, and multiplying it by $S$ projects our own test plan rather than NEAR's capacity — a number that would look like a finding and contain none.
>
> `analysis/shard_scaling.py` therefore checks for saturation (achieved below 90% of offered at some step) **before** projecting, and refuses to extrapolate when none occurred. If NEAR clears 300/sec cleanly, the honest options are to report throughput as "at least 300/sec, ceiling not reached" or to add exploratory load steps above the pre-registered ramp — the route Polygon took with its 500 and 1000/sec levels (`ANALYSIS_PLAN.md` §13, amendment 3). **Do not scale an unsaturated measurement.**

---

## 4. Why this is stronger than running 8 shards would have been

Running at 8 shards would have produced **one number, at one shard count**. Measuring the two regimes separately produces **a function of shard count**, which:

- answers the mainnet question today (10 shards) and tomorrow's (NEAR has been increasing shard count: 4 → 6 → 8 → 10)
- makes the underlying mechanism explicit rather than buried in an average
- lets a reader check the reasoning against their own assumptions about $S$

**State the limitation honestly anyway:** the two regimes are measured on a 4-shard chain with 2 validators per shard. If cross-shard cost itself varies with shard count — for example through congestion control behaving differently at 9 shards — this method would not capture it. Nothing in our data can rule that out.

---

## 4b. The implementation

`analysis/shard_scaling.py` computes all of the above from
`data/clean/all_runs_clean.parquet`:

- $c_{\text{same}}$ and $c_{\text{cross}}$ for latency and gas, each with a
  bootstrap 95% interval taken **over runs** (the unit of replication), matching
  `analysis/results.py`
- $c(S)$ for every shard count up to mainnet's 10, and the 4 → 10 correction factor
- dollar cost, priced from `docs/mainnet_pricing.json`
- the §6 sanity check on the observed mix, run automatically
- the throughput projection, gated on saturation as described above

`--self-test` verifies the projection against hand-computed values and checks
that $c(S)$ rises monotonically in $S$ and is bounded above by $c_{\text{cross}}$.
That check exists because this projection is the one part of the NEAR analysis
with **no observable ground truth**: if the formula were implemented wrongly,
every projected figure would be wrong together and wrong consistently, which is
precisely the kind of error that survives review.

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
