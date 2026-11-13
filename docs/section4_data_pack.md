# Section 4 data pack

Every number for the Section 4 draft, recomputed from the committed data on 12 Nov 2026
(`analysis/results.py`, `analysis/calibration.py`, and direct queries on
`data/clean/all_runs_clean.parquet` and `data/working/runs.sqlite`). Where a source
document disagrees with the data, the data wins and the disagreement is noted.

**Corrected 13 Nov 2026.** A line-by-line fact-check of the draft built from this pack,
against the data, the project's records and the original papers, found errors in this
pack itself. Each is fixed in place below; section F lists them.

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
3. **Node reachability was not independent of payment size.** Waugh and Holz Table I
   gives the share of the 4,626 probed destination nodes reached at every amount:
   35.24% at $0.01, 35.19% at $1, 25.66% at $5, 33.72% at $10, **9.22% at $50, 4.82% at
   $100** (checked against the paper's full text, 13 Nov 2026; this pack previously said
   it was not reported above $5). Write "about one third of destination nodes up to $10,
   falling below 5% at $100", not "25% to 35% at any given time".
4. **Lightning failure at $200 is unmeasured, not "above 82.7%".** $100 is the largest
   amount Waugh and Holz tested, and we found no published measurement above it. 82.70% failure at $100 is the strongest measured point;
   anything at $200 is extrapolation and must be labelled so.
5. **The cross-shard / hot-shard test (4.3.4, Table 4.10, Figure 4.7) was never run,
   and its premise turned out not to apply.** These tests were never in the pre-registered
   plan (ANALYSIS_PLAN has none); they appeared only in the paper's Section 3.6. Every token transfer executed on the one
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
   (amendment 17). Collection began 8 Aug 2026 (first run 02:29 UTC); the last measured
   run was 23 Aug; the machines were deleted 24 Aug and the last disk snapshots 25 Oct.
   No further runs are needed for Section 4.

---

## B. Lightning (Section 4.1)

### B1. Scale (4.1.1, Figure 4.1)

| | Nodes | Channels |
|---|---|---|
| Private regtest testbed | 20 | 51 |
| Live network, Waugh and Holz (3–25 Nov 2019) | 4,826–4,950 | 31,400–31,800 |
| Ratio | ~241–248× | **~616–624× (≈620×)** |

Optional 2026 context (mempool.space, 18 Aug 2026): 16,442 nodes, 33,313 channels.
1ML reported 20,004 channels the same day — a 40% disagreement between explorers, and
1ML publishes no collection timestamp.

### B2. Reliability by payment size (4.1.2, Figure 4.2) — Waugh and Holz Table I

| Amount | Payment success | Failure (100 − success) | Nodes reached |
|---|---|---|---|
| $0.01 | 71.92% | 28.08% | 35.24% |
| $1 | 57.82% | 42.18% | 35.19% |
| $5 | 44.06% | 55.94% | 25.66% |
| $10 | 44.15% | 55.85% | 33.72% |
| $50 | 30.93% | 69.07% | 9.22% |
| $100 | 17.30% | 82.70% | 4.82% |

"Nodes reached" = share of the 4,626 destination nodes probed that received at least one
successful payment of that size (Table I's own column, "% nodes").

Limits that must travel with this table: $100 is the largest amount tested; only two
attempts were allowed per payment (so these are lower bounds on what a user sees); we found
no confidence intervals for any published Lightning success figure; the
dominant failure class was insufficient channel liquidity (31.6% of all attempts).
Absolute values are probably pessimistic for 2026 (total public capacity ~4.7× the 2019
level on ~6% more channels, so ~4.4× more capital per channel — not 4.7×) but the direction should still hold. A $200 payment is ~15% of the
current median public channel (2,042,100 sat at BTC $64,186; mempool.space, 18 Aug 2026), and must
clear that at every hop.

Do not set River's "99.7% success" against this table — it is one well-connected
commercial node. If a modern figure is used at all, River's own routed-payment
failure rate of 2.63% is the more representative one (River Lightning Report 2023,
August 2023 data; still one company's node).

### B3. Spider (4.1.3)

Checked 13 Nov 2026 against arXiv 1809.05088 (NSDI 2020): the abstract's figures are
correct. "1.3–1.8× more of the largest 25%" comes from their simulations on a credit-card
transaction dataset (their modified-LND prototype, 10 nodes / 25 channels, showed 5–30%
more). Lightning never adopted Spider, but it did adopt a simpler form of splitting a
payment over several routes (multi-path payments, LND v0.10, 30 Apr 2020), after the
2019 measurements; worth one sentence.

### B4. Latency (Table 4.1 row)

Waugh and Holz contains **no latency measurement**. What exists:

| Figure | Method | Source |
|---|---|---|
| median 13.12 s "with just one attempt"; 40% under 10 s on a single attempt; 10% needed more than four attempts and over 30 s | 7,659 probe attempts on mainnet (test payments built to fail at the recipient, not real payments) | C. Decker, "c-lightning Plugins 05: Probe Plugin Results", Blockstream blog, 20 Nov 2019 |
| median 3.36 s over 8,256 probe messages that returned an error (3.93 s excluding timed-out and erring ones); 10 s cutoff | mainnet probing, not payments | S. Tikhomirov, R. Pickhardt, A. Biryukov, M. Nowostawski, "Probing Channel Balances in the Lightning Network", arXiv 2004.00333, 2020 — NOT the Tikhomirov/Moreno-Sanchez/Maffei paper |
| rises per hop (testnet: 0.86–1.97 s at 1 hop, 1.99–2.68 s at 2 hops; no 3+ hop route possible); unaffected by amount — found in a local lab network, not testnet | testnet + lab | U. Nisslmueller, K.-T. Foerster, S. Schmid, C. Decker, arXiv 2003.00003 (preliminary version at ICISSP 2020) |

**We found no published p95 or p99**, and both mainnet medians come from probe messages,
not real payments. Fill the row as "p50 only, 3.36–13.12 s from probe studies; no
published p95/p99 found". The testbed's own illustrative figure ($200 at 10/sec, two
60-second shake-out runs, with the 10 s warm-up cut): 924 payments, 1.19% failure, p50
1.510 s, p95 3.555 s, p99 3.997 s — label "small-scale, illustrative, 2 runs". (This pack
previously gave 1,111 / 1.501 / 3.501 / 3.975, which skipped the warm-up cut.)

### B5. Cost (4.1.4)

Routing fee, computed from **measured route length** on the testbed priced at **1ML's
median fee policy** (pulled 10 Aug 2026): base 0.449584 sat per hop, rate 165 ppm.
BTC/USD pinned at **$64,803.00** (CoinGecko, observed 10 Aug 2026 00:45 UTC; Coinbase
cross-check $64,817.29, 0.022% apart).

| Amount | Sats | Mean route (hops) | Fee-charging hops | Fee | % of value |
|---|---|---|---|---|---|
| $10 | 15,431 | 2.603 | 1.603 | $0.0031 | 0.031% |
| $200 | 308,628 | 2.571 | 1.571 | **$0.0523** | 0.026% |
| $500 | 771,569 | 2.772 | 1.772 | $0.1467 | 0.029% |

$10 rests on 28 valid runs (this pack previously gave 2.651 hops / $0.0032, which
included 17 invalidated runs). $50 was never run on Lightning. $200 rests on 3 runs and
$500 on 2, below the 5-repeat minimum, and all five were short shake-out runs (60–120 s
windows), not 300 s runs.

**Channel-opening cost was not computed.** The draft's "[number] vbytes at [rate]
sat/vB" inputs do not exist in the study. Do not invent them. What can be said, with
sources:
- Network-wide compression is ~53 Lightning payments per on-chain transaction (use 53,
  not River's 252). Source: River Lightning Report 2023 (updated Feb 2024), dividing
  Arcane Research's 11.43M payments (Jan 2020–Feb 2022) by the 214,656 channel open/close
  transactions in the same period. It is a 2020–22 estimate, not a current rate.
- Béres, Seres and Benczúr (arXiv 1911.09432) state they "give no estimate on the cost
  of opening the channels". One paper does not make the omission standard; do not
  write that it is.
- They do price the larger omission, for 25 named routing nodes in Feb–Mar 2019 data:
  to earn a 5% annual return on locked capital, the two largest, LNBIG.com (52% of
  capacity) and ACINQ, would need fees about **1,240× and 1,680×** higher. Across all 25
  the multiple runs from 1.4× to 4,461× (their Table 1), so 1,240–1,680 is not a range
  for routers in general. Lightning's fees look near-zero
  because routing capital is uncompensated. This is the strongest cost point available.
- Current fee *policy* (mempool.space, 18 Aug 2026, all channels): median 101 ppm, base
  500 msat — a lower rate than the 165 ppm used above, but a higher base fee than the
  449.584 msat. We found no published measurement of fees actually paid.

Label: "Estimated — routing fees only, excluding channel opening and the cost of locked
capital."

### B6. Table 4.1 corrected rows

| Metric | Lightning value | Source | Evidence type |
|---|---|---|---|
| Sustainable throughput at $200 | No figure found in any source | — | Absent |
| Failure by size | 28.08% at $0.01 → 82.70% at $100; $200 unmeasured | Waugh and Holz | Literature |
| Node reachability | 35.24% at $0.01 → 4.82% at $100 | Waugh and Holz | Literature |
| Latency | p50 3.36–13.12 s, from probe messages, not payments; no published p95/p99 found | Decker 2019; Tikhomirov, Pickhardt et al. 2020 | Literature |
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
| Block gas limit / block time | 30,000,000 — **not** mainnet's: Polygon PoS blocks carried a 160,000,000 limit on 12 Aug 2026 (block 91,888,638). Not a limiting factor here: 30M gas per 2 s block leaves room for ~460 payments/sec after background traffic, above the 340–360 knee / ~2 s (Edge default) |
| Finality rule | **1 confirmation** — IBFT gives deterministic finality; a committed block is final |
| Payment type | ERC-20 stablecoin transfer, Solidity 0.8.24 targeting "london" |
| Benchmarking tool | Custom harness (Caliper rejected), Poisson arrival, concurrent submission |
| Injected delay / jitter / loss | +20/45/40/25 ms; ±4/12/10/6 ms (normal distribution); 0.10/0.40/0.30/0.15% — US/India/Singapore/UK, applied to validator-to-validator traffic only |
| Background traffic | Native transfers (21,000 gas), 60–115/sec, mean ~88, two overlaid sine waves, separate accounts; calibrated to mainnet's ~87/sec (a secondary-source figure; cite it, or cite our own on-chain reading of 79.6/sec on 12 Aug) |
| Repeats | 5 per configuration (140 baseline + 15 node-failure runs) |

**Pilot (4.2.1).** The first Phase 1 run (single region, 5/sec) recorded 100% failure
because proof-of-authority block headers broke settlement detection (METHODOLOGY_LOG
§7.4) — a client defect, invalidated and excluded. After the fix, Phase 1 ran clean at
5.0/sec, 0.00% failure, p50 3.13 s. Separately — in Phase 2 (multi-region, evening of 8 Aug), not
the single-region pilot — the first impairment attempt delayed the load generator's own traffic (lag 10 ms → 553 ms at 100/sec) and was reworked to impair
only validator-to-validator traffic. Pilot data is excluded from results.

### C2. Effect of each realism condition (Table 4.3, Figure 4.4)

**Important framing:** these runs were shake-out checks — **60 s windows. The first step
(multi-region, 4 vCPU) covered all seven rates; later steps ran only 100/sec and 300/sec,
mostly one run each** (the impairment step ran twice per rate; its first attempt was the
faulty one in C1). They are excluded from results by the
pre-registered rules. They cannot give a *sustainable throughput* per step. The honest
version of Table 4.3 reports what happened at 300/sec offered, labelled exploratory:

| Step (cumulative) | Achieved at 300/sec | Failure | p50 settlement |
|---|---|---|---|
| Multi-region, 4-vCPU validators | 298.2 | 0.00% | 5.33 s |
| + hardware matched (8 vCPU) | 298.2 | 0.00% | 3.76 s |
| + injected delay, jitter, loss | 298.2 | 0.00% | 8.04 s |
| + background traffic | 278.0 | 6.77% | 14.19 s |
| + node failures | 191.4 | 35.81% | 19.51 s |

At 100/sec every step that was run there delivered 99.3/sec with 0.00% failure, p50
3.23–4.12 s, so the realism conditions only bite under load. (The node-failure step has
no 100/sec run. This pack previously gave 3.23–4.38 s; the 4.38 s run was the faulty
first impairment attempt.) The order of steps differs from the draft:
hardware matching came before impairment. Matching hardware is the one condition that
made results *better* (−29.5%, 5.33 → 3.76 s at 300/sec). No single-region run at 300/sec
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
failure measured one node, not the chain: validator-0 received every payment *and*
answered every settlement question (84% CPU). The fix spread only the settlement questions
across four nodes. The same chain then committed **300.4/sec with 0.00% failures** (runs
ranged 298.3–302.2; that is a range, not a confidence interval). By the study's own rule
the limit is **340/sec** (337.9/sec, 0.70% mean failures, worst run 2.61%), breaking
between 340 and 360 (360 → 286.2/sec, 20.44%, runs 242.5–351.4). 320/sec was the highest
load with zero failures (320.5/sec, runs 319.0–322.3). Those re-measurements
used 4-vCPU validators, so they are a floor, not a replacement. Do not write "Polygon
degrades gracefully, NEAR collapses" — amendment 14.2 withdrew it; past its own knee
Polygon also falls, to 37% of peak at 600/sec offered.

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
validator 0 never targeted (it hosts the submission endpoint). About 60 outages (121
on/off events) across the 15 runs. With 4 validators one outage removes **25%** of the
network; over the full arm a validator was offline **49.7% of the time** (~12.4% of
capacity missing on average). The 51% / 13% in METHODOLOGY_LOG come from an early
43-minute check of 33 outages, not the full arm. This is roughly **130× more
hostile than real Polygon** — the arm measures sensitivity to validator loss, not expected
mainnet behaviour.

| Offered | Clean | With node failures | Throughput lost |
|---|---|---|---|
| 100 | 100.1/s, 0.00% | 99.4/s [98.9, 99.8], 0.76% | 0.7% |
| 200 | 200.9/s, 0.00% | 148.4/s [129.4, 167.5], 26.11% | 26.1% |
| 300 | 270.5/s, 9.97% | 156.2/s [117.3, 192.7], 48.03% | 42.3% |

p95 with failures: 17.51 s / 43.62 s / 51.31 s. Sustainable throughput with failures:
**100/sec** (down from 200). Range at 300/sec was 93–203/sec across identical runs.
Recovery: a returning validator was not removed from the validator set and resumed
taking part. How quickly was not measured, so do not write "immediately".

### C6. Cost (4.2.6)

Recomputed from the clean data: **28,613 gas** mean per successful payment (median
27,465). Source documents carry 28,538, computed before the final dataset; the dollar
figure is the same.

28,613 gas × **270.927 Gwei** (PolygonScan Standard, 9 Aug 2026 19:42 UTC) × **POL
$0.0774** (PolygonScan's own price display in the same snapshot — cite PolygonScan, not
CoinGecko) = **$0.000600 → $0.0006 per payment**.

**Do not call 270 Gwei high or the figure conservative.** Nothing in the study supports a
typical 30–50 Gwei: both snapshots gave ~271–274 Gwei, and a mainnet block on 12 Aug 2026
had a base fee of 248.6 Gwei. At 30–50 Gwei Polygon would undercut NEAR, so the claim
would contradict RQ3. Re-priced on the 12 Aug snapshot (273.5 Gwei, POL $0.075258, the same
pull as NEAR's price) it is $0.000589 — still $0.0006; use this for the same-day
comparison with NEAR. ANALYSIS_PLAN §6.3 asks for one pricing date for the whole paper;
this pack uses 9 Aug (Polygon), 10 Aug (BTC, 1ML) and 12 Aug (NEAR, Polygon re-price).
Say so in the paper.

---

## D. NEAR (Section 4.3)

### D1. Deployment (Table 4.7)

| Parameter | Value |
|---|---|
| Software | nearcore **2.13.3**, protocol 86 (same protocol version as mainnet) |
| Validators / shards | **8 / 4** — exactly 2 per shard, the minimum *this study's sizing rule* allowed (claude.md §4). NEAR's own protocol minimum is 1 (mainnet `minimum_validators_per_shard` = 1). The 96 vCPU quota ruled out 12 validators (104 vCPU with the generator); 8 is the largest count that splits evenly over 4 shards and 4 regions. Mainnet: 10 shards, 422 validators (12 Aug 2026) |
| Regions | Same four as Polygon, 2 validators per region |
| Instance | n2-standard-8 (8 vCPU / 32 GB) |
| Block time | **2 s** — nearcore's default 600 ms could not hold consensus across four continents |
| Finality rule | **FINAL**, not the earlier optimistic stage |
| Payment type | NEP-141 fungible-token transfer |
| Benchmarking tool | **Same custom harness as Polygon**, NEAR adapter |
| Sender accounts | 836 (900 created, 836 verified usable; NEAR orders each sender's transactions one after another) |
| Impairment / background traffic | Same settings as Polygon. Background traffic spreads over 4 shards, so the token's shard competes with only ~22/sec of it, against ~88/sec on Polygon's single chain |
| Repeats | 5 per configuration: 140 baseline runs over 28 configurations (118 measured runs + 22 rule-excluded runs shown as sensitivity data), 15 node-failure runs, plus 5 exploratory low-duty node-failure runs |

### D2. Full-realism results by load (Table 4.9) — $200, 5 runs each

| Offered | Achieved [95% CI] | Achieved / offered | Failure | p50 | p95 | p99 | Meets? |
|---|---|---|---|---|---|---|---|
| 10 | 9.8 [9.6, 9.9] | 98% | 1.37% | 11.33 | 12.76 | 15.38 | Y |
| 25 | 24.8 [24.6, 24.9] | 99% | 0.88% | 11.20 | 12.33 | 14.27 | Y |
| 50 | 49.8 [49.5, 50.1] | 100% | 0.41% | 11.29 | 12.43 | 14.08 | Y |
| 100 | 100.0 [99.3, 100.7] | 100% | 0.16% | 11.68 | 13.18 | 15.37 | Y |
| **150** | **150.1 [149.6, 150.6]** | 100% | **0.15%** | 12.43 | 19.20 | 23.25 | **Y** |
| 200 | 47.5 [26.3, 68.7] (n=4) | 24% | 76.30% | 35.48 | 57.85 | 59.56 | N |
| 300† | 9.9 [8.0, 11.6] | 3% | 96.69% | 44.85 | 58.45 | 59.50 | N |

**Sustainable throughput: 150/sec.**

† The 300/sec cell is excluded from the clean dataset by the pre-registered rule (the
sending program's lag *grew* 57–83 ms across each run, against a 50 ms growth limit; the
rule tests growth, not size) and is reported from the raw
data as sensitivity data.

Three conditions that must travel with the 200 and 300 rows:
1. **Whether the 200/sec drop belongs to NEAR or partly to the measuring program is
   open** (amendments 15–17). NEAR's adapter checks every waiting payment individually
   over the network; under load that checking grows until the program itself falls behind.
   In the 23 Aug re-test (impairment verified applied), the stored data hold 37 runs, of
   which 25 were excluded, every one for the program falling behind (p95 lag 0.32–0.74 s
   against the 50 ms rule). Amendment 16's "24 exclusions across all 44 runs" does not
   match the stored runs; use 25 of 37. No run was excluded for a validator problem —
   which says nothing about the chain either way. The 150/sec *throughput* stands
   (rule-clean with margin). Its latency may include delay from the program's own
   checking, and 150/sec was never re-run (only 100/sec was reproduced, at 99.9/sec).
2. 200/sec failures, by the furthest stage reached: 33.8% in a final block but not
   finished, 26.3% finalised but after 60 s, 24.5% executed but not final, 15.1% node
   errors, 0.2% included only, 0.1% never sent. About 85% were accepted and still in
   progress at the deadline; 15% were refused with an error. Do not write "mostly executed".
3. Every NEAR latency depends on the 2 s block setting. A preliminary re-test (surviving runs: 3 at
   2 s blocks, 2 at 1.2 s, 1–2 per load; below the 5-repeat minimum) gave p50 12.20 s /
   p95 15.07 s at 2 s blocks and **p50 7.18 s / p95 8.20 s at 1.2 s blocks**. That p95
   would pass the decision rule's 10 s bar. Cite only as preliminary sensitivity.

### D3. Cross-shard (4.3.4) — replace with this finding

Every NEP-141 transfer executes on the shard holding the token contract. Processing could not
be spread across shards, so a single-contract stablecoin is capped at what one shard can
process, however many shards the network has (more shards can only move other traffic off
the token's shard). About three quarters of payments did cross shards, from the sender's
shard to the token's (amendment 12.2), but all were processed on one. The earlier 10-shard projection (~372/sec) is withdrawn.

### D4. Failure by payment size (Table 4.11)

| Size | Failure at 100/sec | Failure at 150/sec | Mean gas |
|---|---|---|---|
| $10 | 0.20% | 0.17% | 2.2154 × 10¹² |
| $50 | 0.21% | 0.19% | 2.2147 × 10¹² |
| $200 | 0.16% | 0.15% | 2.2159 × 10¹² |
| $500 | 0.20% | 2.99% | 2.2152 × 10¹² |

Flat at 100/sec. The $500 figure at 150/sec (2.99%, achieved 145.2/sec) comes from **one
run** out of five (14.39% failures, 127.3/sec); the other four ran at 149.3–150.0/sec with
0.05–0.35% failures. Gas is within 0.06% across sizes, so the processing work does not
depend on amount. RQ2 must mention this run rather than say "flat everywhere".

### D5. Node failures (Table 4.12)

Same outage rules as Polygon (15–45 s outages, 20–60 s gaps), but actual downtime was
lower: a validator was offline ~41% of the time, against ~50% on Polygon. Two asymmetries make NEAR's arm harsher, and both must be
stated: one outage drops a shard from 2 validators to 1 (Polygon keeps 3 of 4); and a
NEAR validator that goes offline is **expelled for ~4 hours**, so the network shrinks
across the arm (not within each run), where a Polygon validator is never removed.

| Offered | Clean | With node failures | Throughput lost |
|---|---|---|---|
| 100 | 100.0/s, 0.16% | 68.4/s [39.1, 95.3], 31.72% | 31.6% |
| 150 | 150.1/s, 0.15% | 35.4/s [3.8, 69.3], 76.36% | 76.4% |
| 200 | 47.5/s, 76.30% | 0.1/s [0.0, 0.3], 99.95% | ~100% |

p95 with failures: 55.53 s / 57.42 s / 59.75 s. Exploratory low-duty block at 150/sec,
five runs with validators offline ~12% of the time: 47.9/s [0.6, 107.0], 67.99% failure;
runs delivered 0.0, 0.0, 2.7, 87.4 and 149.3/sec. **The one equal-load comparison:** at 100/sec,
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
| Recovery | Not removed; speed not measured | Expelled ~4 h | Not measured |
| Main weakness observed | Measuring single node limited the 300/sec figure; tight headroom under node loss | Single-contract shard bottleneck; node loss | Liquidity at larger sizes |
| Security assumption | Permissioned IBFT validator set (no bridge tested) | Validator assignment per shard; 2 per shard here (protocol minimum is 1) | Counterparties and routing nodes; locked funds |

### E2. Research questions

- **RQ1 throughput:** Polygon Edge 200/sec vs NEAR 150/sec at $200. Lightning has no
  measurable figure.
- **RQ2 reliability by size:** flat on Polygon at every size up to 200/sec; flat on NEAR up
  to 100/sec, and at 150/sec except one $500 run (see D4). Gas does not depend on amount.
  Lightning's failure, as measured by Waugh and Holz, rises with size, 28.08% → 82.70%
  (do not write that it "matches" Waugh and Holz — it is their data).
- **Decision rule (ANALYSIS_PLAN §10), which the draft must state:** highest sustainable
  throughput at $200 among architectures with p95 < 10 s and cost < $0.10. Polygon
  qualifies (200/sec, p95 4.77 s, $0.0006). NEAR fails the latency bar at every load
  (lowest p95 12.33 s) at 2 s blocks; that is conditional on the block setting (preliminary
  1.2 s blocks: p95 8.20 s). Lightning cannot be ranked (no throughput figure).
- **RQ3 cost:** NEAR lowest at $0.000366, Polygon $0.0006 ($0.000589 on the same 12 Aug
  pull as NEAR), Lightning $0.0523 routing only
  (~87× Polygon). Lightning's proportional fee passes the $0.10 threshold at $500
  ($0.1467).
- **RQ4 gap to production (Table 4.14):**

| Network | Private sustainable | Mainnet observed | Demand ratio | Capability gap |
|---|---|---|---|---|
| Polygon | 200.9/sec | 79.6 tx/sec (25 blocks, 12 Aug 2026) | **2.52×** | **0.719×** (mainnet capacity ~279 tx/sec at 28.5% block use) |
| NEAR | 150.1/sec | 4.8 tx/sec (8 blocks across 10 shards, 12 Aug 2026) | **31.3×** | Not derivable (blocks 0.04% full) |

Demand ratio is about how busy mainnet was, not what it can do; the capability gap is the
ratio against mainnet's estimated capacity. NEAR's mainnet sample is
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

---

## F. Corrections made 13 Nov 2026

Found by fact-checking the Section 4 draft line by line. Earlier versions of this pack:

1. Said Waugh and Holz did not report node reachability above $5. They do: 33.72% at
   $10, 9.22% at $50, 4.82% at $100 (A3, B2, B6). LIGHTNING_EVIDENCE.md §4 had the same error.
2. Gave the $10 Lightning route as 2.651 hops / $0.0032, including 17 invalidated runs
   (valid: 2.603 / $0.0031, 28 runs), and the testbed latency without the 10 s warm-up cut.
3. Called capital per channel 4.7× deeper; that is total capacity (per channel ~4.4×).
4. Cited arXiv 2004.00333 as the Tikhomirov/Moreno-Sanchez/Maffei paper. It is "Probing
   Channel Balances in the Lightning Network" (Tikhomirov, Pickhardt, Biryukov,
   Nowostawski). Both latency medians come from probe messages, not real payments.
5. Gave Béres et al.'s 1,240–1,680× as a general range (it is two routers), and called
   the channel-opening omission "standard".
6. Said Polygon Edge's 30M block gas limit matched mainnet (mainnet: 160M in Aug 2026),
   and that 270 Gwei was high for Polygon (unsupported; it contradicted RQ3).
7. Gave 119 outages and 51% downtime for the Polygon node-failure arm (about 60 outages,
   49.7%), and said returning validators rejoined "immediately" (not measured).
8. Put Polygon's knee at 320–340 and presented a run range as a confidence interval.
   By the study's rule the limit is 340.
9. Called 2 validators per shard NEAR's protocol minimum (it is 1), called background
   traffic identical on both chains, and counted runs as "cells".
10. Gave the 300/sec NEAR interval as [8.0, 11.7] (11.6), the 23 Aug re-test as 24 of 44
    (stored data: 25 of 37), and the block-cadence survivors as n=1–2 (3 and 2).
11. Said the 150/sec NEAR figure was "unaffected" (throughput yes; latency not shown) and
    that 200/sec failures had "mostly executed" (about a quarter had).
12. Explained the NEAR $500 rise as edge-of-ceiling behaviour (it is one run) and omitted
    the §10 decision-rule outcome.
13. Gave the 100/sec realism-step range as 3.23–4.38 s (4.38 was a faulty run) and said
    every step ran only at 100 and 300/sec (the first step ran all seven rates).
