# Section 4 data pack

Every number for the Section 4 draft, recomputed from the committed data on 12 Nov 2026
(`analysis/results.py`, `analysis/calibration.py`, and direct queries on
`data/clean/all_runs_clean.parquet` and `data/working/runs.sqlite`). Where a source
document disagrees with the data, the data wins and the disagreement is noted.

Rules behind every table: 300 s windows; the first 10 s of scheduled payments are
discarded; a payment succeeds only if it settles within 60 s; 5 repeats per
configuration; intervals are 95% bootstrap intervals over runs (10,000 resamples,
seed 20260812); "sustainable" = achieved ≥ 90% of offered AND failures < 5%.

---

## A. Corrections the draft needs before any numbers go in

These are factual errors in the draft, not style points.

1. **Caliper was never used.** Hyperledger Caliper was dropped before Phase 1. Every
   architecture was measured by one custom harness written for this study (Poisson
   arrival, concurrent submission, per-payment logging, one adapter per chain), so
   that the three-way comparison uses one instrument (METHODOLOGY_LOG §3.1).
   Remove "Hyperledger Caliper [32]" from Table 4.2, "Caliper load generation" from
   4.2.1, and **delete the whole claim in 4.3.1 that the NEAR scripts were checked
   against Caliper and "agreed within X%"**. That check never happened and cannot be
   filled in.
2. **The 6,010 nodes / 19,644 channels / 385× figures are not in Waugh and Holz.**
   Zero occurrences in the paper. They most likely came from 1ML. The paper states
   **4,826–4,950 nodes and 31.4k–31.8k channels** (3–25 Nov 2019). Against the
   testbed's 51 channels that is **~620× fewer channels**, not 385×.
3. **Node reachability was not independent of payment size.** Waugh and Holz report
   35.24% at $0.01, 35.19% at $1, 25.66% at $5, and do not report it above $5.
   Write "about one third of destination nodes at the smallest sizes, falling to about
   one quarter at $5", not "25% to 35% at any given time".
4. **Lightning failure at $200 is unmeasured, not "above 82.7%".** $100 is the largest
   amount anyone has tested. 82.70% failure at $100 is the strongest measured point;
   anything at $200 is extrapolation and must be labelled so.
5. **The cross-shard / hot-shard test (4.3.4, Table 4.10, Figure 4.7) was never run,
   and its premise turned out not to apply.** Every token transfer executed on the one
   shard holding the token contract (ANALYSIS_PLAN §13, amendment 12.2). The whole
   NEAR workload was a single "hot shard" by construction. Sharding spread *inclusion*
   of transactions across shards but never spread *execution*. Replace 4.3.4 with that
   finding. Do not use the cross-shard column in `results.py` (~0.74); it is built on
   a route field amendment 12.2 discredits.
6. **There is no NEAR step-by-step realism table (Table 4.8).** NEAR went straight to
   the full realism stack. Only Polygon has per-step data, and it is exploratory (see C2).
7. **"Recovery time after nodes return (s)" was not measured** as a metric on either
   chain. What is known is qualitative and asymmetric (see C5 and D5).
8. **Draft note 5 (credit expiry) is obsolete.** Data collection closed 24 Aug 2026
   (amendment 17). No further runs are needed for Section 4; all cloud resources are
   deleted.

---

## B. Lightning (Section 4.1)

### B1. Scale (4.1.1, Figure 4.1)

| | Nodes | Channels |
|---|---|---|
| Private regtest testbed | 20 | 51 |
| Live network, Waugh and Holz (3–25 Nov 2019) | 4,826–4,950 | 31,400–31,800 |
| Ratio | ~240× | **~620×** |

Optional 2026 context (mempool.space, 18 Aug 2026): 16,442 nodes, 33,313 channels.
1ML reported 20,004 channels the same day — a 40% disagreement between explorers, and
1ML publishes no collection timestamp.

### B2. Reliability by payment size (4.1.2, Figure 4.2) — Waugh and Holz Table I

| Amount | Payment success | Failure (100 − success) | Nodes reached |
|---|---|---|---|
| $0.01 | 71.92% | 28.08% | 35.24% |
| $1 | 57.82% | 42.18% | 35.19% |
| $5 | 44.06% | 55.94% | 25.66% |
| $10 | 44.15% | 55.85% | — |
| $50 | 30.93% | 69.07% | — |
| $100 | 17.30% | 82.70% | — |

Limits that must travel with this table: $100 is the maximum ever tested; only two
attempts were allowed per payment (so these are lower bounds on what a user sees); no
confidence intervals exist for any Lightning success figure from any source; the
dominant failure class was insufficient channel liquidity (31.6% of all attempts).
Absolute values are probably pessimistic for 2026 (capital per channel ~4.7× deeper
than 2019) but the direction should still hold. A $200 payment is ~15% of the
current median public channel (2,042,100 sat at BTC $64,186, 18 Aug 2026), and must
clear that at every hop.

Do not set River's "99.7% success" against this table — it is one well-connected
commercial node. If a modern figure is used at all, River's own routed-payment
failure rate of 2.63% is the more representative one.

### B3. Spider (4.1.3)

The draft's Spider figures are consistent with the repo's notes and were confirmed by
the other session against the paper. No change.

### B4. Latency (Table 4.1 row)

Waugh and Holz contains **no latency measurement**. What exists:

| Figure | Method | Source |
|---|---|---|
| median 13.12 s; 40% under 10 s; 10% over 30 s | 7,659 probes, mainnet | Blockstream c-lightning probe plugin, Nov 2019 |
| median 3.36 s (3.93 s excluding errors) | 8,256 onions, mainnet | Tikhomirov et al., arXiv 2004.00333 |
| adds per hop, independent of amount | testnet, n=25 per cell | Nisslmueller et al., ICISSP 2020 |

**No p95 or p99 exists anywhere.** Fill the row as "p50 only, 3.36–13.12 s
(literature); p95/p99 not available in any published source". The testbed's own
illustrative figure ($200 at 10/sec, 2 runs, 1,111 payments, 1.0% failure): p50
1.501 s, p95 3.501 s, p99 3.975 s — label "small-scale, illustrative, 2 runs".

### B5. Cost (4.1.4)

Routing fee, computed from **measured route length** on the testbed priced at **1ML's
median fee policy** (pulled 10 Aug 2026): base 0.449584 sat per hop, rate 165 ppm.
BTC/USD pinned at **$64,803.00** (CoinGecko, observed 10 Aug 2026 00:45 UTC; Coinbase
cross-check $64,817.29, 0.022% apart).

| Amount | Sats | Mean route (hops) | Fee-charging hops | Fee | % of value |
|---|---|---|---|---|---|
| $10 | 15,431 | 2.651 | 1.651 | $0.0032 | 0.032% |
| $200 | 308,628 | 2.571 | 1.571 | **$0.0523** | 0.026% |
| $500 | 771,569 | 2.772 | 1.772 | $0.1467 | 0.029% |

$50 was never run on Lightning. $200 rests on 3 runs and $500 on 2, below the
5-repeat minimum.

**Channel-opening cost was not computed.** The draft's "[number] vbytes at [rate]
sat/vB" inputs do not exist in the study. Do not invent them. What can be said, with
sources:
- Network-wide compression is ~53 Lightning payments per on-chain transaction (use 53,
  not River's 252).
- Béres, Seres and Benczúr (arXiv 1911.09432) explicitly give no channel-opening cost
  either — the omission is standard in the literature.
- They do price the larger omission: for routers to earn a 5% annual return on locked
  capital, fees would need to rise **1,240× to 1,680×**. Lightning's fees look near-zero
  because routing capital is uncompensated. This is the strongest cost point available.
- Current fee *policy* (18 Aug 2026, all channels): median 101 ppm, base 500 msat —
  lower than the 165 ppm used above. No measurement of fees actually paid exists.

Label: "Estimated — routing fees only, excluding channel opening and the cost of locked
capital."

### B6. Table 4.1 corrected rows

| Metric | Lightning value | Source | Evidence type |
|---|---|---|---|
| Sustainable throughput at $200 | No figure exists from any source | — | Absent |
| Failure by size | 28.08% at $0.01 → 82.70% at $100; $200 unmeasured | Waugh and Holz | Literature |
| Node reachability | 35.24% at $0.01, 25.66% at $5 | Waugh and Holz | Literature |
| Latency | p50 3.36–13.12 s; no p95/p99 anywhere | Blockstream 2019; Tikhomirov 2020 | Literature |
| Cost per $200 | $0.0523, routing only | measured hops × 1ML policy | Estimated |

---

## C. Polygon Edge (Section 4.2)

### C1. Deployment (Table 4.2)

| Parameter | Value |
|---|---|
| Software | Polygon Edge **v1.3.2** (final release, 24 Jan 2024; repository archived 4 Dec 2024) |
| Consensus | IBFT, proof-of-authority (chosen over PolyBFT) |
| Validators | **4** (smallest set that tolerates one failure) |
| Regions | us-east4 (Virginia), asia-south1 (Mumbai), asia-southeast1 (Singapore), europe-west2 (London) — one validator each, mapped to remittance corridors |
| Instance | n2-standard-8: 8 vCPU / 32 GB / 100 GB disk (CPU and RAM matched to published validator specs; disk deliberately not) |
| Block gas limit / block time | 30,000,000 (matches mainnet) / ~2 s (Edge default) |
| Finality rule | **1 confirmation** — IBFT gives deterministic finality; a committed block is final |
| Payment type | ERC-20 stablecoin transfer, Solidity 0.8.24 targeting "london" |
| Benchmarking tool | Custom harness (Caliper rejected), Poisson arrival, concurrent submission |
| Injected delay / jitter / loss | +20/45/40/25 ms; ±4/12/10/6 ms (normal distribution); 0.10/0.40/0.30/0.15% — US/India/Singapore/UK, applied to validator-to-validator traffic only |
| Background traffic | Native transfers (21,000 gas), 60–115/sec, mean ~88, two overlaid sine waves, separate accounts; calibrated to mainnet's ~87/sec |
| Repeats | 5 per configuration (140 baseline + 15 node-failure runs) |

**Pilot (4.2.1).** The first Phase 1 run (single region, 5/sec) recorded 100% failure
because proof-of-authority block headers broke settlement detection (METHODOLOGY_LOG
§7.4) — a client defect, invalidated and excluded. After the fix, Phase 1 ran clean at
5.0/sec, 0.00% failure, p50 3.13 s. Separately, the first impairment attempt delayed the
load generator's own traffic (lag 10 ms → 553 ms at 100/sec) and was reworked to impair
only validator-to-validator traffic. Pilot data is excluded from results.

### C2. Effect of each realism condition (Table 4.3, Figure 4.4)

**Important framing:** these runs were shake-out checks — **60 s windows, one repeat,
and only 100/sec and 300/sec offered**. They are excluded from results by the
pre-registered rules. They cannot give a *sustainable throughput* per step. The honest
version of Table 4.3 reports what happened at 300/sec offered, labelled exploratory:

| Step (cumulative) | Achieved at 300/sec | Failure | p50 settlement |
|---|---|---|---|
| Multi-region, 4-vCPU validators | 298.2 | 0.00% | 5.33 s |
| + hardware matched (8 vCPU) | 298.2 | 0.00% | 3.76 s |
| + injected delay, jitter, loss | 298.2 | 0.00% | 8.04 s |
| + background traffic | 278.0 | 6.77% | 14.19 s |
| + node failures | 191.4 | 35.81% | 19.51 s |

At 100/sec every step delivered 99.3/sec with 0.00% failure (p50 3.23–4.38 s), so the
realism conditions only bite under load. The order of steps differs from the draft:
hardware matching came before impairment. Matching hardware is the one condition that
made results *better* (−29% settlement at 300/sec). No single-region run at 300/sec
exists. Figure 4.4 works for Polygon if drawn on this table and labelled "exploratory,
one 60-second run per step".

### C3. Full-realism results by load (Table 4.4, Figure 4.5) — $200, 5 runs each

| Offered | Achieved [95% CI] | Achieved / offered | Failure | p50 | p95 | p99 | Meets? |
|---|---|---|---|---|---|---|---|
| 10 | 9.9 [9.8, 10.1] | 99% | 0.00% | 3.19 | 4.16 | 4.40 | Y |
| 25 | 25.0 [24.9, 25.1] | 100% | 0.00% | 3.19 | 4.17 | 4.39 | Y |
| 50 | 50.0 [49.7, 50.2] | 100% | 0.00% | 3.20 | 4.22 | 4.46 | Y |
| 100 | 100.1 [99.6, 100.8] | 100% | 0.00% | 3.23 | 4.25 | 4.52 | Y |
| 150 | 150.3 [149.7, 150.9] | 100% | 0.00% | 3.31 | 4.38 | 4.70 | Y |
| **200** | **200.9 [199.7, 201.9]** | 100% | **0.00%** | 3.43 | 4.77 | 6.35 | **Y** |
| 300 | 270.5 [265.3, 274.6] | 90.2% | 9.97% | 10.61 | 24.26 | 30.49 | N |

Latency in seconds, pooled over the 5 runs. Intervals were computed for throughput only;
the latency columns have no intervals. **Sustainable throughput: 200/sec.** At 300/sec
the throughput bar is met (90.2%) but the failure bar is not.

**Required conditioning on the 300/sec row (amendment 14.1).** The 270.5/sec at 9.97%
failure measured the single node the harness asked about settlement, not the chain.
Spreading those questions across four nodes, the same chain committed **300.4/sec
[298.3–302.2] with 0.00% failures**, and its real knee sits near **320–340/sec**
(320 → 320.5/sec, 0.00%; 340 → 337.9, 0.70%; 360 → 286.2, 20.4%). Those re-measurements
used 4-vCPU validators, so they are a floor, not a replacement. Do not write "Polygon
degrades gracefully, NEAR collapses" — amendment 14.2 withdrew it; past its own knee
Polygon also falls to about a third of peak.

### C4. Failure by payment size (Table 4.5)

| Size | Failure at 200/sec | Failure at 300/sec | Mean gas |
|---|---|---|---|
| $10 | 0.00% | 9.79% | 28,610 |
| $50 | 0.00% | 8.51% | 28,617 |
| $200 | 0.00% | 9.97% | 28,606 |
| $500 | 0.00% | 12.85% | 28,618 |

At every load up to the sustainable ceiling, failure is 0.00% at every size. Gas is flat
across sizes (variation 0.04%), as expected: moving a larger number is not more work. The
spread at 300/sec is overload noise, not a size effect.

### C5. Node failures (Table 4.6, Figure 4.6)

Design: one validator offline at a time (enforced), outages 15–45 s, gaps 20–60 s,
validator 0 never targeted (it hosts the submission endpoint). 119 outage events logged.
With 4 validators one outage removes **25%** of the network; a validator was offline
**51% of the time** (~13% of capacity missing on average). This is roughly **130× more
hostile than real Polygon** — the arm measures sensitivity to validator loss, not expected
mainnet behaviour.

| Offered | Clean | With node failures | Throughput lost |
|---|---|---|---|
| 100 | 100.1/s, 0.00% | 99.4/s [98.9, 99.8], 0.76% | 0.7% |
| 200 | 200.9/s, 0.00% | 148.4/s [129.4, 167.5], 26.11% | 26.1% |
| 300 | 270.5/s, 9.97% | 156.2/s [117.3, 192.7], 48.03% | 42.3% |

p95 with failures: 17.51 s / 43.62 s / 51.31 s. Sustainable throughput with failures:
**100/sec** (down from 200). Range at 300/sec was 93–203/sec across identical runs.
Recovery: a returning validator rejoined consensus immediately on restart; recovery time
in seconds was not measured.

### C6. Cost (4.2.6)

Recomputed from the clean data: **28,613 gas** mean per successful payment (median
27,465). Source documents carry 28,538, computed before the final dataset; the dollar
figure is the same.

28,613 gas × **270.927 Gwei** (PolygonScan Standard, 9 Aug 2026 19:42 UTC) × **POL
$0.0774** = **$0.000600 → $0.0006 per payment**.

Caveat to state: 270 Gwei is high by Polygon's standards (long periods at 30–50 Gwei),
so this is conservative. Re-priced on the 12 Aug snapshot (273.5 Gwei, POL $0.075258)
it is $0.000589 — still $0.0006.

---

## D. NEAR (Section 4.3)

### D1. Deployment (Table 4.7)

| Parameter | Value |
|---|---|
| Software | nearcore **2.13.3**, protocol 86 (same protocol version as mainnet) |
| Validators / shards | **8 / 4** — exactly 2 per shard, the protocol minimum (limited by the 96 vCPU quota; mainnet runs 10 shards, 422 validators) |
| Regions | Same four as Polygon, 2 validators per region |
| Instance | n2-standard-8 (8 vCPU / 32 GB) |
| Block time | **2 s** — nearcore's default 600 ms could not hold consensus across four continents |
| Finality rule | **FINAL**, not the earlier optimistic stage |
| Payment type | NEP-141 fungible-token transfer |
| Benchmarking tool | **Same custom harness as Polygon**, NEAR adapter |
| Sender accounts | 836 funded (NEAR orders each sender's transactions one after another) |
| Impairment / background traffic | Identical values to Polygon |
| Repeats | 5 per configuration (118 measured cells + 22 sensitivity cells + 15 node-failure runs) |

### D2. Full-realism results by load (Table 4.9) — $200, 5 runs each

| Offered | Achieved [95% CI] | Achieved / offered | Failure | p50 | p95 | p99 | Meets? |
|---|---|---|---|---|---|---|---|
| 10 | 9.8 [9.6, 9.9] | 98% | 1.37% | 11.33 | 12.76 | 15.38 | Y |
| 25 | 24.8 [24.6, 24.9] | 99% | 0.88% | 11.20 | 12.33 | 14.27 | Y |
| 50 | 49.8 [49.5, 50.1] | 100% | 0.41% | 11.29 | 12.43 | 14.08 | Y |
| 100 | 100.0 [99.3, 100.7] | 100% | 0.16% | 11.68 | 13.18 | 15.37 | Y |
| **150** | **150.1 [149.6, 150.6]** | 100% | **0.15%** | 12.43 | 19.20 | 23.25 | **Y** |
| 200 | 47.5 [26.3, 68.7] (n=4) | 24% | 76.30% | 35.48 | 57.85 | 59.56 | N |
| 300† | 9.9 [8.0, 11.7] | 3% | 96.69% | 44.85 | 58.45 | 59.50 | N |

**Sustainable throughput: 150/sec.**

† The 300/sec cell is excluded from the clean dataset by the pre-registered rule (the
sending program's lag grew 57–83 ms against a 50 ms limit) and is reported from the raw
data as sensitivity data.

Three conditions that must travel with the 200 and 300 rows:
1. **Whether the 200/sec drop belongs to NEAR or partly to the measuring program is
   open** (amendments 15–17). NEAR's adapter checks every waiting payment individually
   over the network; under load that checking grows until the program itself falls behind.
   In the 23 Aug re-test under correct impairment, all 24 excluded runs were the program
   falling behind, none the chain. The 150/sec figure is unaffected.
2. 200/sec failures were mostly "executed but not seen to finalise in 60 s", not refusals.
3. Every NEAR latency depends on the 2 s block setting. A preliminary re-test (n=1–2, below
   the 5-repeat minimum) gave p50 12.20 s at 2 s blocks and **7.18 s at 1.2 s blocks** —
   cite only as preliminary sensitivity.

### D3. Cross-shard (4.3.4) — replace with this finding

Every NEP-141 transfer executes on the shard holding the token contract. The workload
could not be spread across shards, so adding shards adds no capacity to a single-contract
stablecoin at any shard count. The earlier 10-shard projection (~372/sec) is withdrawn.

### D4. Failure by payment size (Table 4.11)

| Size | Failure at 100/sec | Failure at 150/sec | Mean gas |
|---|---|---|---|
| $10 | 0.20% | 0.17% | 2.2154 × 10¹² |
| $50 | 0.21% | 0.19% | 2.2147 × 10¹² |
| $200 | 0.16% | 0.15% | 2.2159 × 10¹² |
| $500 | 0.20% | 2.99% | 2.2152 × 10¹² |

Flat at 100/sec. The $500 rise at 150/sec (achieved 145.2/sec, range 127.3–150.0) sits
at the edge of the ceiling; gas is identical across sizes, so the processing work does
not depend on amount.

### D5. Node failures (Table 4.12)

Same fault schedule as Polygon. Two asymmetries make NEAR's arm harsher, and both must be
stated: one outage drops a shard from 2 validators to 1 (Polygon keeps 3 of 4); and a
NEAR validator that goes offline is **expelled for ~4 hours**, so the network shrinks
through the arm, where a Polygon validator rejoins immediately.

| Offered | Clean | With node failures | Throughput lost |
|---|---|---|---|
| 100 | 100.0/s, 0.16% | 68.4/s [39.1, 95.3], 31.72% | 31.6% |
| 150 | 150.1/s, 0.15% | 35.4/s [3.8, 69.3], 76.36% | 76.4% |
| 200 | 47.5/s, 76.30% | 0.1/s [0.0, 0.3], 99.95% | ~100% |

p95 with failures: 55.53 s / 57.42 s / 59.75 s. Exploratory low-duty block at 150/sec:
47.9/s [0.6, 107.0], 67.99% failure. **The one equal-load comparison:** at 100/sec,
Polygon lost 0.7% and NEAR lost 31.6%.

### D6. Cost

Recomputed: **2.2153 × 10¹² gas** mean per payment (documents carry 2.214 × 10¹²).
× **100,000,000 yoctoNEAR per gas** (mainnet protocol floor, rpc.mainnet.near.org,
12 Aug 2026 01:37 UTC) × **NEAR $1.65** (CoinGecko, same pull)
= **$0.000366 per payment** (documents round to $0.000365).

Note: the recovered original token contract (148,137 bytes) is the one these runs used;
a later rebuild was a different build, which is why only the original campaign's gas is
quoted.

---

## E. Cross-architecture comparison (Section 4.4)

### E1. Table 4.13

| Metric | Polygon Edge | NEAR | Lightning |
|---|---|---|---|
| Sustainable throughput at $200 | **200/sec** (200.9 [199.7, 201.9]) | **150/sec** (150.1 [149.6, 150.6]) | No figure exists |
| p50 / p95 / p99 at that load | 3.43 / 4.77 / 6.35 s | 12.43 / 19.20 / 23.25 s (at 2 s blocks) | p50 3.36–13.12 s (lit.); no p95/p99 |
| Failure at $200 at that load | 0.00% | 0.15% | 82.70% at $100 (lit.); $200 unmeasured |
| Cost per $200 | $0.0006 | $0.000366 | $0.0523 routing only (est.) |
| Throughput lost to node failures, equal load (100/sec) | 0.7% | 31.6% (harsher design, see D5) | Not measured |
| Recovery | Rejoins immediately | Expelled ~4 h | Not measured |
| Main weakness observed | Measuring single node limited the 300/sec figure; tight headroom under node loss | Single-contract shard bottleneck; node loss | Liquidity at larger sizes |
| Security assumption | Permissioned IBFT validator set (no bridge tested) | Validator assignment per shard; 2 per shard here | Counterparties and routing nodes; locked funds |

### E2. Research questions

- **RQ1 throughput:** Polygon Edge 200/sec vs NEAR 150/sec at $200. Lightning has no
  measurable figure.
- **RQ2 reliability by size:** flat on both chains up to their ceilings, as expected
  (gas does not depend on amount). Lightning's failure rises with size, 28.08% → 82.70%,
  matching Waugh and Holz's direction.
- **RQ3 cost:** NEAR lowest at $0.000366, Polygon $0.0006, Lightning $0.0523 routing only
  (~87× Polygon). Lightning's proportional fee passes the $0.10 threshold at $500
  ($0.1467).
- **RQ4 gap to production (Table 4.14):**

| Network | Private sustainable | Mainnet observed | Demand ratio | Capability gap |
|---|---|---|---|---|
| Polygon | 200.9/sec | 79.6 tx/sec (25 blocks, 12 Aug 2026) | **2.52×** | **0.719×** (mainnet capacity ~279 tx/sec at 28.5% block use) |
| NEAR | 150.1/sec | 4.8 tx/sec (8 blocks across 10 shards, 12 Aug 2026) | **31.3×** | Not derivable (blocks 0.04% full) |

Demand ratio is about how busy mainnet is, not what it can do. NEAR's mainnet sample is
small; treat it as an order of magnitude.

### E3. Figure data at a glance

- **4.1:** B1 table.
- **4.2:** B2 success column, $0.01–$100; mark $200 as "no data".
- **4.4:** Polygon only, C2 table, labelled exploratory.
- **4.5:** C3 and D2 achieved columns against offered.
- **4.6:** needs a per-second time series from one node-failure run — query
  `data/raw` (Polygon adversarial, phase `phase-2-adversarial`) joined to the outage log.
- **4.7:** drop (see A5).
- **4.8:** C4 (200/sec), D4 (150/sec), B2 (Lightning, literature, dashed).
