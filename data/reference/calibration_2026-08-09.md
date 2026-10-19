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
measured gas per stablecoin transfer   =  28,538 gas  (mean, results data)
gas price (Standard)                   =  270.927 Gwei
                                       =  270.927 × 10⁻⁹ POL

  28,538 × 270.927 × 10⁻⁹             =  0.0077317 POL
  0.0077317 POL × $0.0774              =  $0.000598
```

### **Cost per remittance transaction: $0.0006**

> ⚠️ **Corrected 9 Aug 2026.** The earlier $0.00075 was computed from **Phase 1**, which the pre-registered rules exclude from results. Phase 1 was a small run with all storage slots cold, showing a uniform 35,865 gas — a value occurring in only 5.6% of the actual results data. Using it overstated cost by 26%. The mean was refined from 28,467 to 28,538 on 9 Aug after 22 duplicate runs were excluded (`ANALYSIS_PLAN.md` §13 amendment 4); the cost is unchanged at $0.0006.

Against the pre-registered architecture-selection threshold of **$0.10 per transaction** (`ANALYSIS_PLAN.md` §10), Polygon clears it by a factor of roughly **167×**.

For context against the UN SDG 10.c target of total remittance cost under 3% of value — $6.00 on a $200 transfer — the settlement layer consumes **0.01%** of that budget. The fiat conversion at each end, which this study does not measure, dominates the real cost entirely.

**What is real and what is derived:** the 28,538 gas figure is measured on our own network and would be identical on Polygon mainnet, because gas consumption is a deterministic function of the operations performed. The dollar figure is that real quantity priced at one moment in time.

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

**Implied BTC price:** ≈ $65,163 (derived from $172.4M ÷ 2,645.64 BTC). **Derived, not quoted — do not cite this figure.** The rate the study actually uses is quoted from a price source in §4 below.

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

## 4. Bitcoin price — the study's pinned exchange rate

**Source:** [CoinGecko `simple/price` API](https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd)
**Observed:** 2026-08-10 00:45:20 UTC (the API returns its own observation timestamp, recorded here rather than the time we happened to read it)

| Figure | Value |
|---|---|
| **BTC/USD — the pinned rate** | **$64,803.00** |
| Cross-check: Coinbase spot, same session | $64,817.29 |
| Agreement between the two | **0.022%** |

**Why a cross-check.** A single API can be stale or wrong, and this one number multiplies into every Lightning cost and success figure in the paper. Two independent sources agreeing to 0.022% makes a bad quote unlikely. CoinGecko is the citation; Coinbase is the check.

**One rate, held constant across every run** (`claude.md` §6). Lightning is the only architecture that needs an exchange rate at all — the stablecoin chains make $200 exactly 200 tokens, which is a second independent reason the ERC-20 / NEP-141 choice was right. The rate lives as a single constant, `harness.topology.BTC_USD_PINNED`, which the adapter and the funding script both import so they cannot drift apart.

> ⚠️ **Superseded value.** Lightning code initially used **$65,163**, inferred from 1ML's own capacity figures rather than quoted from a price source. It was only 0.55% out — the $200 test payment moves from 306,923 to 308,628 satoshis — but an inferred rate is not citable, and this figure appears throughout the Lightning results. Replaced before any Lightning run was measured, so no result was ever computed from it.

**Note on dates.** The PolygonScan and 1ML figures above were pulled 9 Aug 2026 19:42 UTC; this quote is roughly five hours later and therefore falls on 10 Aug in UTC. Recorded honestly rather than rounded into the same calendar day. All three are from one calibration session and are cited together.

### What this rate means for the Lightning arm

At $64,803, the test amounts sit in this relationship to real network capacity:

| Amount | Satoshis | Share of a median channel | Share of a median **node's entire capacity** |
|---|---|---|---|
| $10 | 15,431 | 0.8% | 5.0% |
| $50 | 77,157 | 3.8% | 24.8% |
| $200 | 308,628 | 15.2% | **99.3%** |
| $500 | 771,569 | 38.1% | **248.3%** |

**The median Lightning node's entire capacity is almost exactly one $200 remittance.** This is the structural reason payment size drives success on Lightning and not on Polygon, and it is the mechanism behind the Waugh & Holz gradient the study sets out to replicate. It is also why `harness/topology.py` keeps channel capacities at true mainnet scale instead of scaling them down: shrink the network and this relationship — the one that decides every routing outcome — is destroyed.

---

## 5. Lightning fee policy — the cost basis for Phase 3

**Source:** [1ML Lightning Network Statistics](https://1ml.com/statistics)
**Pulled:** 10 August 2026 (a day after §3; see the drift note below)

| Figure | Value |
|---|---|
| **Median base fee** | **0.449584 sat** (449.584 msat) per hop |
| **Median fee rate** | **0.000165 sat/sat** = **165 ppm** |
| Average channel capacity | 0.133 BTC |
| Average node capacity | 0.439 BTC |

**Why these and not our own fees.** Our LND nodes ran the stock policy — 1,000 msat base plus 1 ppm. At the 2.53-hop routes we measured that produces ~2,016 msat, and observation confirmed it: the "measured" fee was almost entirely our own base-fee setting. Reporting it would repeat exactly the error `ANALYSIS_PLAN.md` §6.3 warns about for Polygon's gas price — pricing a number we chose ourselves. What is genuinely measured is **route length**; the price comes from the real network.

### Cost per remittance

Fees on Lightning are charged by *forwarding* nodes, so a route of N hops has N−1 chargers. Our measured mean route was **2.53 hops → 1.53 fee-charging hops**.

```
per hop  =  base_fee + (fee_rate x amount)
         =  0.449584 sat + 0.000165 x amount_sat
fee      =  per_hop x 1.53
```

| Amount | Satoshis | Fee (sat) | **Fee (USD)** | % of value |
|---|---|---|---|---|
| $10 | 15,431 | 4.6 | **$0.0030** | 0.030% |
| $50 | 77,157 | 20.2 | **$0.0131** | 0.026% |
| **$200** | 308,628 | 78.6 | **$0.0509** | 0.025% |
| $500 | 771,569 | 195.5 | **$0.1267** | 0.025% |

### The comparison this enables

**Lightning routing costs $0.0509 to move $200; Polygon costs $0.0006 — a factor of 85.**

And the structure differs, not just the level. Polygon charges for computational work, so cost is **flat**: $500 costs the same as $10. Lightning charges 165 ppm of the amount, so cost is **proportional**: at $500 the fee reaches $0.1267, which alone **exceeds the $0.10 architecture-selection threshold** in `ANALYSIS_PLAN.md` §10.

That is the crossover predicted as a secondary objective in §12 — and it lands below $500, before the amortised channel-open cost or the cost of locked capital are counted, both of which push Lightning higher still.

> ⚠️ **Route length is topology-dependent.** 2.53 hops was measured on a 20-node network. A 6,010-node network generally needs longer paths, so this figure likely **understates** mainnet cost. The bias is conservative — it flatters Lightning, not its competitors — and must be stated.

> ⚠️ **Drift note.** §3 recorded average channel capacity 0.134 BTC and node capacity 0.440 BTC on 9 Aug; this pull a day later gives 0.133 and 0.439. A 0.2-0.7% change, consistent with ordinary network movement, and small enough not to affect the topology calibration built on the earlier figures.

---

## 6. Still outstanding

- **NEAR mainnet gas prices and NEAR token price** — pull at Phase 4, and record here with its own date rather than assuming this one still holds.
- **Mainnet throughput figures for the calibration gap** (`ANALYSIS_PLAN.md` §11) — both the demand ratio and the capability gap need observed and peak mainnet throughput. Polygon's ~87 tx/sec average is already recorded in `METHODOLOGY_LOG.md` §4 (technique #3); the observed *peak* still needs pulling.
