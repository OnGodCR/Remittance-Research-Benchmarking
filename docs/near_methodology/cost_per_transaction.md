# NEAR — cost per transaction

**Written:** 11 August 2026
**Use this when:** writing the cost comparison, and RQ3 (reduce settlement cost).

This follows the same discipline as Polygon and Lightning: **measure the quantity the architecture determines, price it with real mainnet rates.** Never price with our own configuration — that number is one we chose, and reporting it would be circular.

---

## 1. What is measured and what is priced

| Quantity | Source | Why |
|---|---|---|
| **Gas burnt** per transfer | Measured on our chain | Deterministic. The same NEP-141 call burns the same gas on our network and on mainnet — it is a function of the operations executed. |
| **Gas price** | NEAR mainnet, pulled on one stated date | Set by network congestion. Ours is whatever our idle chain decides, which is meaningless. |
| **NEAR token price** | External source, same stated date | Needed to express the result in dollars. |

This mirrors `ANALYSIS_PLAN.md` §6.3 exactly, and is the same structure used for Polygon (gas consumed × PolygonScan gas price × POL price) and Lightning (route length × 1ML per-hop fee rates).

---

## 2. Gas is summed across receipts, not just the transaction

**This is the NEAR-specific trap.** A NEAR transfer is not one execution:

1. the transaction executes on the **sender's** shard, producing a receipt
2. the receipt executes on the **receiver's** shard, in a later block
3. a refund receipt may follow

Counting only `transaction_outcome.outcome.gas_burnt` reports a **fraction** of the real cost — and worse, it hides the difference between same-shard and cross-shard work, which is the property this arm exists to measure.

The adapter therefore sums:

$$G_{\text{total}} \;=\; G_{\text{transaction}} \;+\; \sum_{i} G_{\text{receipt}_i}$$

Implemented in `harness/adapters/near.py::_total_gas`. The same summation is applied to `tokens_burnt` for the native-currency figure.

---

## 3. The formula

$$\text{cost}_{\text{USD}} \;=\; G_{\text{total}} \times P_{\text{gas}} \times \frac{1}{10^{24}} \times P_{\text{NEAR}}$$

where

- $G_{\text{total}}$ — gas units burnt, summed across transaction and receipts
- $P_{\text{gas}}$ — mainnet gas price in **yoctoNEAR per gas unit** (NEAR's minimum is $10^{8}$, rising with congestion)
- $10^{24}$ — yoctoNEAR per NEAR
- $P_{\text{NEAR}}$ — NEAR token price in USD

### Applied per shard regime

Because cost differs between same-shard and cross-shard transfers (see `shard_scaling.md`), report **both**, then combine for a given shard count $S$:

$$\text{cost}(S) \;=\; \frac{1}{S}\,\text{cost}_{\text{same}} \;+\; \frac{S-1}{S}\,\text{cost}_{\text{cross}}$$

For mainnet, use $S = 8$ or $9$.

---

## 4. Comparison table to fill in

| | Polygon (measured) | Lightning (measured route × 1ML rates) | NEAR |
|---|---|---|---|
| Cost at $200 | **$0.0006** | **$0.0509** | *fill in* |
| Cost at $500 | $0.0006 (flat) | $0.1267 | *fill in* |
| Scales with amount? | No — 0.044% variation | **Yes** — 165 ppm | *expected: no* |
| Basis | 28,538 gas × 270.927 Gwei × $0.0774 | 1.53 fee-charging hops | $G_{\text{total}}$ × gas price × NEAR price |

**Expected result, stated in advance:** NEAR should be **flat with amount**, like Polygon and unlike Lightning, because NEAR charges for computational work and moving a larger number is not more work. This is the same pre-registered prediction that held on Polygon to within 0.044%. If NEAR's cost varies materially with amount, that is a finding worth investigating, not a rounding error.

---

## 5. Still outstanding

**Pull NEAR mainnet gas price and NEAR token price on one stated date**, and record them in `data/reference/` alongside the PolygonScan and 1ML figures. Per `ANALYSIS_PLAN.md` §6.3 these are pulled once, cited once, and never re-pulled because a number became inconvenient.

Note NEAR's gas price has a **protocol minimum** ($10^{8}$ yoctoNEAR) and rises only under congestion. If mainnet is at the floor on the pull date, say so — it means the figure is a lower bound on cost during busy periods, which is the same caveat attached to Polygon's 270 Gwei snapshot being high.

---

## 6. Query to reproduce

```sql
SELECT
  CASE t.route_hops WHEN 0 THEN 'same-shard' ELSE 'cross-shard' END AS regime,
  r.tx_size_usd,
  COUNT(*)                    AS payments,
  ROUND(AVG(t.gas_used), 0)   AS mean_gas,
  ROUND(AVG(CAST(t.fee_native AS REAL)), 0) AS mean_yocto_burnt
FROM transactions t
JOIN runs r ON t.run_id = r.run_id
WHERE r.architecture = 'near'
  AND r.invalidated = 0
  AND t.status = 'confirmed'
GROUP BY regime, r.tx_size_usd
ORDER BY r.tx_size_usd, regime;
```
