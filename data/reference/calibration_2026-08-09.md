# External Calibration Data — pulled 9 August 2026

**This is the single pricing and topology reference for the entire paper.** `ANALYSIS_PLAN.md` §6.3 requires external figures to be pulled on one stated date and cited once, never re-pulled later if a number becomes inconvenient. These are those figures.

Anything in the paper that converts our measured resource consumption into dollars, or configures Lightning channel liquidity, uses these values and cites this date.

---

## 1. Polygon mainnet — pricing

**Source:** [PolygonScan Gas Tracker](https://polygonscan.com/gastracker)
**Pulled:** 9 August 2026, 19:42:27 UTC

| Figure | Value |
|---|---|
| Gas price — Standard | **270.927 Gwei** |
| Gas price — Fast | 270.927 Gwei |
| Gas price — Rapid | 279.494 Gwei |
| POL token price | **$0.0774 USD** |

**Which figure to use:** *Standard* (270.927 Gwei). It is the rate an ordinary transaction pays without bidding for priority, which is what a remittance would do. Fast and Rapid represent congestion premiums that a routine payment has no reason to pay.

⚠️ **Caveat that must appear in the paper.** 270 Gwei is high by Polygon's historical standards — the network has spent long periods in the 30-50 Gwei range. A single-day snapshot captures whatever conditions prevailed that day. This makes our cost figures **conservative** (higher than a long-run average would give), which is the safer direction to err, but the limitation should be stated rather than left implicit.

---

## 2. Derived cost per transaction — Polygon

Our measured gas consumption is real and architecture-determined. The dollar conversion uses the figures above.

```
measured gas per stablecoin transfer   =  28,467 gas  (mean, results data)
gas price (Standard)                   =  270.927 Gwei
                                       =  270.927 × 10⁻⁹ POL

  28,467 × 270.927 × 10⁻⁹             =  0.0077125 POL
  0.0077125 POL × $0.0774              =  $0.000597
```

### **Cost per remittance transaction: $0.0006**

> ⚠️ **Corrected 9 Aug 2026.** The earlier $0.00075 was computed from **Phase 1**, which the pre-registered rules exclude from results. Phase 1 was a small run with all storage slots cold, showing a uniform 35,865 gas — a value occurring in only 3.6% of the actual results data. Using it overstated cost by 26%.

Against the pre-registered architecture-selection threshold of **$0.10 per transaction** (`ANALYSIS_PLAN.md` §10), Polygon clears it by a factor of roughly **168×**.

For context against the UN SDG 10.c target of total remittance cost under 3% of value — $6.00 on a $200 transfer — the settlement layer consumes **0.01%** of that budget. The fiat conversion at each end, which this study does not measure, dominates the real cost entirely.

**What is real and what is derived:** the 28,467 gas figure is measured on our own network and would be identical on Polygon mainnet, because gas consumption is a deterministic function of the operations performed. The dollar figure is that real quantity priced at one moment in time.

---

## 3. Lightning Network — topology reference

**Source:** [1ML Lightning Network Statistics](https://1ml.com/statistics)
**Pulled:** 9 August 2026

| Figure | Value |
|---|---|
| Nodes | **6,010** (−3.95% over 30 days) |
| Channels | **19,644** (−7.3% over 30 days) |
| Network capacity | **2,645.64 BTC** (≈ $172.4M) |
| Average channel capacity | **0.134 BTC** |
| Median channel capacity | **0.020256 BTC** |
| Average node capacity | **0.440 BTC** |
| Median node capacity | **0.003107 BTC** |
| Average channels per node | **6.54** |

**Implied BTC price:** ≈ $65,163 (derived from $172.4M ÷ 2,645.64 BTC). Derived, not quoted — if the paper needs a BTC price it should cite a price source directly rather than infer one.

### The number that matters for realism technique #5

**Average node capacity is 142× the median** (0.440 BTC vs 0.003107 BTC). Channel capacity shows the same shape at 6.6× (0.134 vs 0.020256 BTC).

That extreme skew *is* the Lightning Network's structure: a small number of very well-funded hubs carrying most of the liquidity, and thousands of thin leaf nodes. A test network with evenly-funded channels would not be Lightning — it would be a much easier network to route through, and it would understate exactly the routing failures this study exists to measure.

### Derived configuration for our ~20-node deployment

Preserving the observed concentration rather than the absolute values (a private regtest network needs no real capital):

| Role | Nodes | Share of capacity | Rationale |
|---|---|---|---|
| Major hubs | 2 | ~55% | Reproduces the handful of dominant routing nodes |
| Secondary hubs | 4 | ~30% | The mid-tier that carries regional traffic |
| Leaf nodes | 14 | ~15% | The long tail — most nodes, little liquidity |

Target average ≈ **6.5 channels per node**, matching the observed 6.54, with hubs far above that and leaves at 1-2.

**To verify once built:** the mean-to-median node capacity ratio should land near 142×. If our synthetic topology comes out far flatter, the routing failures will be unrealistically rare and the Waugh & Holz comparison becomes meaningless.

---

## 4. Still outstanding

- **NEAR mainnet gas prices and NEAR token price** — pull at Phase 4, and record here with its own date rather than assuming this one still holds.
- **Mainnet throughput figures for the calibration gap** (`ANALYSIS_PLAN.md` §11) — both the demand ratio and the capability gap need observed and peak mainnet throughput. Polygon's ~87 tx/sec average is already recorded in `METHODOLOGY_LOG.md` §4 (technique #3); the observed *peak* still needs pulling.
