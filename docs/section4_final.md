**4. Execution and Results**

Data collection ran from 8 to 23 August 2026, and the cloud machines were deleted on 24 August. Unless stated otherwise, every self-measured result below follows the pre-registered rules. Each run uses a 300-second measurement window. Payments scheduled in the first 10 seconds are discarded. A payment counts as successful only if it reaches finality within 60 seconds. Each configuration was repeated 5 times, and intervals are 95% bootstrap intervals across runs (10,000 resamples). A load is "sustainable" if achieved throughput is at least 90% of the offered rate and fewer than 5% of payments fail.

**4.1 Lightning: evidence from published literature**

*4.1.1 Why a private Lightning network was not used*

Lightning was first deployed as a private regtest network with 20 nodes and 51 channels. During the period measured by Waugh and Holz [16] (3 to 25 November 2019), the live Lightning Network had between 4,826 and 4,950 nodes and between 31,400 and 31,800 channels. The private network therefore had about 240 to 250 times fewer nodes and about 620 times fewer channels than the network it was meant to represent (Table 4.1). This gap matters more for Lightning than for the other architectures. A Lightning payment succeeds only if a route exists in which every channel holds enough funds to forward it, so the number of routes and the liquidity along them directly determine the success rate. A network with a small fraction of the real network's channels cannot reproduce that behavior, and no amount of hardware within this study's budget would have closed a gap of this size. Lightning's reliability is therefore evaluated from published measurements of the live network. This decision was recorded in the Amendment Log on 10 August 2026, the day the testbed was run, before any Lightning results were reported.

**Table 4.1.** Scale of the private Lightning testbed compared with the live network

| | Nodes | Channels |
|---|---|---|
| Private regtest testbed | 20 | 51 |
| Live network, Waugh and Holz [16] (3–25 Nov 2019) | 4,826–4,950 | 31,400–31,800 |
| Ratio | ~241–248× | ~620× |

**[FIGURE 4.1]** *Private testbed vs. live Lightning Network.* Side-by-side bars on a log scale for nodes and channels, using Table 4.1.

*4.1.2 Reliability by payment size*

Waugh and Holz [16] measured payment success on the live network by sending payments of increasing size (Table 4.2). Success fell from 71.92% at $0.01 to 17.30% at $100, meaning 82.70% of $100 payments failed. The largest single cause of failure was insufficient channel liquidity, reported as a temporary channel failure, which accounted for 31.6% of all attempts. Several limits apply to these figures. $100 was the largest amount Waugh and Holz tested, and we found no published measurement at a larger size, so Lightning's failure rate at the $200 benchmark is unmeasured and any figure at that size would be extrapolation. Only two attempts were allowed per payment, so these success rates are lower bounds on what a user retrying more often might see. We found no confidence intervals for any published Lightning success figure. Finally, the measurements are from 2019. By August 2026, total public channel capacity was about 4.7 times its 2019 level on only about 6% more channels, so average capital per channel was about 4.4 times deeper [41]. Lightning has also since adopted multi-path payments, which split one payment across several routes [43]. The absolute success rates are therefore probably pessimistic today, but the pattern of failure rising with payment size is likely to hold. In current terms, a $200 payment is about 15% of the median public channel's capacity (18 August 2026 [41]), and it has to fit within the available balance at every hop along its route. Waugh and Holz also measured how many of the 4,626 destination nodes they targeted received at least one successful payment. This stayed near one third from $0.01 to $10 (with a dip to 25.66% at $5), then fell to 9.22% at $50 and 4.82% at $100.

**Table 4.2.** Lightning payment success by size, live network (Waugh and Holz [16])

| Amount | Payment success | Failure | Destination nodes reached |
|---|---|---|---|
| $0.01 | 71.92% | 28.08% | 35.24% |
| $1 | 57.82% | 42.18% | 35.19% |
| $5 | 44.06% | 55.94% | 25.66% |
| $10 | 44.15% | 55.85% | 33.72% |
| $50 | 30.93% | 69.07% | 9.22% |
| $100 | 17.30% | 82.70% | 4.82% |
| $200 | Not measured | Not measured | Not measured |

**[FIGURE 4.2]** *Lightning payment success by size.* Success rate from $0.01 to $100 using the success column of Table 4.2, a horizontal line at 95% success (the inverse of the 5% failure threshold), and $200 marked "no data." This shows that Lightning falls far below the threshold well before the benchmark size.

*4.1.3 Throughput and routing*

Sivaraman et al. [24] studied whether better routing could reduce Lightning's liquidity problem. Their protocol, Spider, splits each payment into smaller units and sends them across multiple paths over time, instead of requiring a single route to carry the full amount at once. In their simulations, Spider routed over 95% of transactions using less than 25% of the funds required by existing approaches on balanced demand, moved about four times more transactions onto the payment channel network under imbalanced demand, and, on a credit-card transaction dataset, completed 1.3 to 1.8 times more of the largest 25% of transactions. Two limits apply here. These results come from a packet-level simulator supported by a small prototype, not from the live network, and Spider itself has not been adopted by Lightning, although a simpler form of splitting payments across routes was adopted in 2020 [43]. The results are also relative improvements over other routing methods rather than absolute transactions per second. We found no published sustainable throughput figure for Lightning that can be placed beside the Polygon Edge and NEAR results.

*4.1.4 Latency*

Waugh and Holz [16] did not measure latency. Two other mainnet studies give timing evidence, but both used probe payments, which are built to fail at the recipient. They measure the time taken to reach the destination, not completed settlement. In November 2019, a probe of every reachable node using Blockstream's c-lightning probe plugin made 7,659 payment attempts. The median time to completion was 13.12 seconds; 40% completed in under 10 seconds on a single attempt, and 10% needed more than four attempts and took over 30 seconds [33]. Tikhomirov et al. measured a median of 3.36 seconds across 8,256 probes that returned an error, with a 10-second cutoff (3.93 seconds excluding timed-out and erring probes) [34]. Nisslmueller et al. found in a local test network that settlement time did not depend on payment amount, and on Bitcoin's public testnet that it rose from about 0.9–2.0 seconds over one hop to about 2.0–2.7 seconds over two hops [35]. We found no published 95th or 99th percentile latency for Lightning. For illustration only, the private testbed recorded a median of 1.510 seconds, a 95th percentile of 3.555 seconds, and a 99th percentile of 3.997 seconds for $200 payments at 10 per second, across two 60-second runs and 924 payments, of which 1.19% failed. These figures come from a network far smaller than the real one, from runs shorter than the 300-second window, and from fewer than the 5 required repeats, so they are labeled small-scale and illustrative, and are not used in the comparison.

*4.1.5 Cost*

Lightning routing fees were estimated by combining the route lengths measured on the testbed with the median fee policy published by 1ML [36] on 10 August 2026: a base fee of 0.449584 satoshis per hop and a proportional rate of 165 parts per million. Bitcoin was priced at $64,803.00 (CoinGecko, 10 August 2026 [37]). The first hop on a route charges no fee, so only the remaining hops were priced. The resulting fees are shown in Table 4.3. A $200 payment costs about $0.0523 in routing fees, or 0.026% of the amount sent. These estimates have two important limits. First, they exclude the cost of opening a channel, which this study did not calculate; Béres, Seres, and Benczúr [38] also give no estimate of it. River estimated that between January 2020 and February 2022, about 53 Lightning payments were made for every on-chain transaction that opened or closed a channel [42], which spreads the opening cost thinly but does not remove it. Second, they exclude the cost of the capital locked in channels. Using February–March 2019 network data, Béres, Seres, and Benczúr estimated that the two largest routing nodes, LNBIG.com and ACINQ, would need fees about 1,240 and 1,680 times higher to earn a 5% annual return on the capital locked in their channels, with the multiple varying widely across the 25 nodes they analysed [38]. This suggests Lightning's fees appear close to zero largely because routing capital is not being compensated. The $200 and $500 figures also rest on 3 and 2 short runs respectively, below the 5-repeat minimum, and no $50 run was made. The proportional rate in current fee policy is lower than the one used here (a median of 101 parts per million across all public channels on 18 August 2026 [41]), and we found no published measurement of fees actually paid.

**Table 4.3.** Estimated Lightning routing fees (routing only; excludes channel opening and locked capital)

| Amount | Mean route length (hops) | Fee-charging hops | Fee | Fee as % of amount | Runs |
|---|---|---|---|---|---|
| $10 | 2.603 | 1.603 | $0.0031 | 0.031% | 28 |
| $200 | 2.571 | 1.571 | $0.0523 | 0.026% | 3 |
| $500 | 2.772 | 1.772 | $0.1467 | 0.029% | 2 |

**Table 4.4.** Lightning evidence mapped to the pre-registered metrics

| Metric | Lightning value | Source | Evidence type |
|---|---|---|---|
| Sustainable throughput at $200 | No published figure found | — | Absent |
| Failure by payment size | 28.08% at $0.01, rising to 82.70% at $100; $200 unmeasured | Waugh and Holz [16] | Literature-derived |
| Destination node reachability | 35.24% at $0.01, falling to 4.82% at $100 | Waugh and Holz [16] | Literature-derived |
| Latency | Median 3.36–13.12 s from probe payments; no published p95 or p99 | [33], [34] | Literature-derived |
| Cost per $200 transfer | $0.0523 (routing only) | Measured route length × 1ML fee policy | Estimated |

**4.2 Polygon Edge: what was built and what it showed**

*4.2.1 Deployment*

Polygon Edge was deployed with the configuration in Table 4.5. Version 1.3.2 is the final release of Polygon Edge, and its repository was archived in December 2024. This means the software is no longer maintained, a limitation discussed in Section 6. The network used four validators, the smallest set that can tolerate one failure, placed in four regions that correspond to major remittance corridors: Virginia, Mumbai, Singapore, and London. Polygon Edge's IBFT consensus gives deterministic finality, so a payment is final once its block is committed. Each test payment was a stablecoin (ERC-20) transfer.

Two problems were found and fixed before any data was kept. In the first single-region pilot run, every payment was recorded as failed, because the block headers produced by Polygon Edge's proof-of-authority mode broke the measuring program's method for detecting settlement. This was a defect in the measuring program, not the network, and the run was excluded. After the fix, the pilot ran at 5.0 payments per second with no failures and a median settlement time of 3.13 seconds. The second problem appeared when network impairment was first added, in the multi-region phase. The added delay was also applied to the load generator's own traffic, which pushed its scheduling lag from 10 milliseconds to 553 milliseconds at 100 payments per second. The impairment was reworked to apply only to traffic between validators. No pilot data is included in the results.

**Table 4.5.** Polygon Edge deployment configuration

| Parameter | Value |
|---|---|
| Software | Polygon Edge v1.3.2 (final release, January 2024; repository archived December 2024) |
| Consensus | IBFT, proof-of-authority |
| Validators | 4 (smallest set tolerating one failure) |
| Regions | Virginia (us-east4), Mumbai (asia-south1), Singapore (asia-southeast1), London (europe-west2); one validator each |
| Instance | n2-standard-8: 8 vCPU, 32 GB RAM, 100 GB disk (CPU and RAM matched to published validator specifications) |
| Block gas limit / block time | 30,000,000 / about 2 s (default). The gas limit was not a constraint at the loads tested; Polygon mainnet blocks carried 160,000,000 in August 2026 [44] |
| Finality rule | 1 confirmation (IBFT finality is deterministic) |
| Payment type | ERC-20 stablecoin transfer |
| Measurement tool | Custom harness written for this study (Poisson arrival, concurrent submission, per-payment logging) |
| Injected delay / jitter / packet loss | US +20 ms ±4 ms, 0.10%; India +45 ms ±12 ms, 0.40%; Singapore +40 ms ±10 ms, 0.30%; UK +25 ms ±6 ms, 0.15% (validator-to-validator traffic only) |
| Background traffic | Native transfers at 60–115 per second (mean about 88) from separate accounts, calibrated to Polygon mainnet activity (79.6 per second measured on 12 August 2026; Table 4.15) |
| Repeats | 5 per configuration (140 baseline runs and 15 node-failure runs) |

**[FIGURE 4.3, optional]** *Deployment map.* A world map of the four regions, showing Polygon Edge's one validator and NEAR's two validators per region, with the injected delay for each region labeled. This is useful but not essential. Cut it first if space is tight.

*4.2.2 Effect of each realism condition (exploratory)*

As conditions were added, short check runs confirmed that each one behaved as expected. These runs used 60-second windows and mostly a single run per step; the first step was run at all seven offered rates, and later steps only at 100 and 300 payments per second. Under the pre-registered rules they are excluded from the results and cannot give a sustainable throughput for each step. They are reported here as exploratory evidence of which conditions matter most (Table 4.6). At 100 payments per second, every step that was run at that rate (all except the node-failure step) delivered 99.3 payments per second with no failures and median settlement between 3.23 and 4.12 seconds, so the realism conditions had no visible effect at moderate load. At 300 payments per second, the effects were clear. Matching validator hardware to published specifications was the only condition that improved results, cutting median settlement by about 30% (from 5.33 to 3.76 seconds). Network impairment roughly doubled median settlement time without causing failures. Background traffic was the first condition to push failures above zero, and node failures had the largest effect, cutting achieved throughput by about a third. No single-region run at 300 payments per second exists, so the table begins with the multi-region configuration.

**Table 4.6.** Polygon Edge at 300 payments per second offered, as conditions were added (exploratory: one 60-second run per step)

| Step (cumulative) | Achieved (per s) | Failure rate | Median settlement (s) |
|---|---|---|---|
| Multi-region, 4-vCPU validators | 298.2 | 0.00% | 5.33 |
| + Hardware matched (8 vCPU) | 298.2 | 0.00% | 3.76 |
| + Injected delay, jitter, and packet loss | 298.2 | 0.00% | 8.04 |
| + Background traffic | 278.0 | 6.77% | 14.19 |
| + Node failures | 191.4 | 35.81% | 19.51 |

**[FIGURE 4.4]** *How each realism condition affected Polygon Edge at 300 per second.* Use either a waterfall of achieved throughput or a paired bar chart of failure rate and median settlement time across the five steps in Table 4.6. Label it "exploratory, one 60-second run per step." NEAR has no equivalent data, since it went straight to the full set of conditions.

*4.2.3 Throughput and latency under full realism*

With all conditions active except node failures, which are reported separately in Section 4.2.5, the offered rate was stepped from 10 to 300 payments per second (Table 4.7). Polygon Edge's sustainable throughput was 200 payments per second. At that rate, it achieved 200.9 per second with no failures, a median settlement time of 3.43 seconds, and a 99th percentile of 6.35 seconds. At 300 per second, it achieved 270.5 per second, which meets the 90% throughput bar, but 9.97% of payments failed, which does not meet the 5% failure bar.

The 300 per second result needs one qualification. In the main runs, a single node received every payment and also answered every one of the measuring program's questions about whether a payment had settled. That node, not the chain, was what fell behind: it ran at 84% of its processing capacity while the other validators ran at 8.5–14%. When the settlement questions were spread across all four nodes, the chain committed 300.4 payments per second with no failures (individual runs ranged from 298.3 to 302.2). By the study's own rule, its sustainable limit was 340 per second, where it achieved 337.9 per second with 0.70% of payments failing (2.61% in the worst run). It broke down between 340 and 360 per second: at 360 it achieved 286.2 per second with 20.44% of payments failing, and individual runs ranged from 242.5 to 351.4. The highest rate with no failures at all was 320 per second (320.5 achieved). Those re-measurements were run on 4-vCPU validators, so they represent a minimum rather than a replacement for the main result. The pre-registered sustainable throughput of 200 per second is unchanged. Past its limit, Polygon Edge also lost throughput sharply, falling to 37% of its peak at 600 per second offered.

**Table 4.7.** Polygon Edge results by offered load (full realism, $200 transfers, 5 runs each)

| Offered (per s) | Achieved (per s) [95% CI] | Achieved / offered | Failure rate | p50 (s) | p95 (s) | p99 (s) | Sustainable? |
|---|---|---|---|---|---|---|---|
| 10 | 9.9 [9.8, 10.1] | 99% | 0.00% | 3.19 | 4.16 | 4.40 | Yes |
| 25 | 25.0 [24.9, 25.1] | 100% | 0.00% | 3.19 | 4.17 | 4.39 | Yes |
| 50 | 50.0 [49.7, 50.2] | 100% | 0.00% | 3.20 | 4.22 | 4.46 | Yes |
| 100 | 100.1 [99.6, 100.8] | 100% | 0.00% | 3.23 | 4.25 | 4.52 | Yes |
| 150 | 150.3 [149.7, 150.9] | 100% | 0.00% | 3.31 | 4.38 | 4.70 | Yes |
| 200 | 200.9 [199.7, 201.9] | 100% | 0.00% | 3.43 | 4.77 | 6.35 | Yes |
| 300* | 270.5 [265.3, 274.6] | 90.2% | 9.97% | 10.61 | 24.26 | 30.49 | No |

Latency is pooled across the 5 runs and has no intervals. *Limited by the single node that received payments and answered settlement checks (see text).

**[FIGURE 4.5]** *Offered vs. achieved throughput.* Offered rate on the x-axis and achieved rate on the y-axis, with one line for Polygon Edge (Table 4.7) and one for NEAR (Table 4.11), plus a dashed line at 90% of offered. Each network's sustainable throughput is the last point above the dashed line where failures are also below 5%. This is the main figure for the paper's primary metric.

*4.2.4 Failure rate by payment size*

At every load up to the sustainable throughput, no payment of any size failed (Table 4.8). The gas used per payment was also nearly identical across sizes, varying by only 0.04%, since moving a larger number does not require more processing. The differences between sizes at 300 per second reflect overload, not an effect of payment size.

**Table 4.8.** Polygon Edge failure rate by payment size

| Size | Failure at 200 per s | Failure at 300 per s | Mean gas |
|---|---|---|---|
| $10 | 0.00% | 9.79% | 28,610 |
| $50 | 0.00% | 8.51% | 28,617 |
| $200 | 0.00% | 9.97% | 28,606 |
| $500 | 0.00% | 12.85% | 28,618 |

*4.2.5 Node failures*

In the node-failure runs, one validator was taken offline at a time, for 15 to 45 seconds, with gaps of 20 to 60 seconds between outages. Validator 0 was never taken offline, since it hosted the endpoint that received payments. Across the 15 runs, about 60 outages were logged. With only four validators, each outage removed 25% of the network, and a validator was offline about half the time (49.7%), so on average about 12% of capacity was missing. This is roughly 130 times more hostile than real Polygon conditions, so this test measures how sensitive the network is to losing validators, not how it would behave on mainnet.

At 100 per second, node failures barely mattered, costing 0.7% of throughput (Table 4.9). At 200 per second, they cost 26.1% of throughput, and 26.11% of payments failed. Of the three loads tested, only 100 per second remained sustainable with node failures. Results also became less predictable. At 300 per second, achieved throughput across identical runs ranged from 93 to 203 per second. A validator that came back online was not removed from the validator set and resumed taking part, but how quickly it recovered was not measured.

**Table 4.9.** Polygon Edge with one validator offline at a time

| Offered (per s) | Clean | With node failures [95% CI] | Throughput lost | p95 with failures (s) |
|---|---|---|---|---|
| 100 | 100.1 per s, 0.00% failure | 99.4 per s [98.9, 99.8], 0.76% failure | 0.7% | 17.51 |
| 200 | 200.9 per s, 0.00% failure | 148.4 per s [129.4, 167.5], 26.11% failure | 26.1% | 43.62 |
| 300 | 270.5 per s, 9.97% failure | 156.2 per s [117.3, 192.7], 48.03% failure | 42.3% | 51.31 |

**[FIGURE 4.6]** *Throughput over time during a node-failure run.* Per-second throughput for one representative Polygon Edge run at 200 per second, with shaded bands marking when each validator was offline. This needs a new query on the raw node-failure data, joined to the outage log.

*4.2.6 Cost per transaction*

Each successful payment used a mean of 28,613 gas (median 27,465). Priced at the PolygonScan standard gas price of 270.927 Gwei and a POL price of $0.0774, both shown by PolygonScan on 9 August 2026 [39], this comes to about $0.0006 per payment. Re-pricing with a second snapshot from 12 August 2026 (273.5 Gwei, POL $0.075258 [37]) gives $0.000589, also about $0.0006, so the two snapshots three days apart agree. The pre-registered plan called for a single pricing date; prices were in fact recorded on 9, 10 and 12 August 2026, and moving Polygon Edge to the 12 August prices changes its cost by less than 2%.

**4.3 NEAR: what was built and what it showed**

*4.3.1 Deployment*

NEAR was deployed in the same four regions as Polygon Edge, using the same measuring program with a NEAR-specific adapter and the same network impairment and background traffic settings (Table 4.10). The node software ran the same protocol version as NEAR mainnet at the time. The 96 vCPU cloud quota ruled out the planned 12 validators, so the network used 8 validators across 4 shards: exactly 2 per shard, the minimum this study's design allowed (NEAR's own protocol minimum is one). For comparison, NEAR mainnet ran 10 shards and 422 validators on 12 August 2026 [40]. NEAR's default block time of 600 milliseconds could not keep consensus across four continents, so blocks were set to 2 seconds. Every NEAR latency figure depends on this setting. A payment counted as settled only at NEAR's FINAL stage, not at its earlier optimistic stage. Each test payment was a fungible token (NEP-141) transfer, the NEAR equivalent of a stablecoin transfer. NEAR processes each sender's transactions one after another, so 836 funded sender accounts were used to avoid creating an artificial bottleneck. Unlike Polygon Edge, NEAR went directly to the full set of realism conditions, so no step-by-step data exists.

**Table 4.10.** NEAR deployment configuration

| Parameter | Value |
|---|---|
| Software | nearcore 2.13.3, protocol version 86 (same as mainnet at the time) |
| Validators / shards | 8 / 4 (2 per shard, the minimum this study's design allowed; limited by the 96 vCPU quota) |
| Regions | Same four as Polygon Edge, 2 validators per region |
| Instance | n2-standard-8: 8 vCPU, 32 GB RAM |
| Block time | 2 s (the 600 ms default could not hold consensus across four continents) |
| Finality rule | FINAL stage |
| Payment type | NEP-141 fungible-token transfer |
| Measurement tool | Same custom harness as Polygon Edge, with a NEAR adapter |
| Sender accounts | 836 |
| Impairment / background traffic | Same settings as Polygon Edge (background traffic is spread over 4 shards, so the token's shard carried about a quarter of it) |
| Repeats | 5 per configuration: 140 baseline runs (118 measured, 22 excluded by rule and shown as sensitivity data), 15 node-failure runs, and 5 exploratory node-failure runs |

*4.3.2 Throughput and latency under full realism*

NEAR's sustainable throughput was 150 payments per second (Table 4.11). At that rate, it achieved 150.1 per second with 0.15% of payments failing, a median settlement time of 12.43 seconds, and a 99th percentile of 23.25 seconds. At 200 per second, achieved throughput dropped to 47.5 per second and 76.30% of payments failed. Most of these failures were payments the network had accepted but not finalised within 60 seconds: about a third had been included in a final block without finishing, a quarter had executed but were not yet final, and a quarter did finalise, but after the 60-second limit. About 15% were refused by the node with an error.

Whether the drop at 200 per second belongs to NEAR or partly to the measuring program remains open. NEAR's adapter checks each pending payment separately over the network, and under heavy load that checking can grow until the program itself falls behind. In a re-test on 23 August with the network impairment confirmed, 25 of 37 runs were excluded, every one because the measuring program fell behind its own schedule. None was excluded for a validator problem, so the re-test could not settle the question either way. The 150 per second throughput result does not depend on this question, since its runs passed the lag rule with a wide margin. Its latency figures could include some delay from the program's own checking, which was not measured separately, and the 150 per second cell was not re-run on the rebuilt network (the 100 per second cell was, and reproduced at 99.9 per second). One $200 run at 200 per second was excluded by the lag rule, leaving four. The 300 per second results were excluded from the clean dataset under the pre-registered rules, because the sending program's lag grew by 57 to 83 milliseconds over each run, more than the 50 milliseconds the rules allow. They are shown only as sensitivity data. A preliminary re-test of block time, with only two or three usable runs per setting and therefore below the 5-repeat minimum, gave a median settlement of 12.20 seconds (95th percentile 15.07 seconds) with 2-second blocks and 7.18 seconds (95th percentile 8.20 seconds) with 1.2-second blocks. This suggests NEAR's latency here is driven largely by the block time setting.

**Table 4.11.** NEAR results by offered load (full realism, $200 transfers, 5 runs each unless noted)

| Offered (per s) | Achieved (per s) [95% CI] | Achieved / offered | Failure rate | p50 (s) | p95 (s) | p99 (s) | Sustainable? |
|---|---|---|---|---|---|---|---|
| 10 | 9.8 [9.6, 9.9] | 98% | 1.37% | 11.33 | 12.76 | 15.38 | Yes |
| 25 | 24.8 [24.6, 24.9] | 99% | 0.88% | 11.20 | 12.33 | 14.27 | Yes |
| 50 | 49.8 [49.5, 50.1] | 100% | 0.41% | 11.29 | 12.43 | 14.08 | Yes |
| 100 | 100.0 [99.3, 100.7] | 100% | 0.16% | 11.68 | 13.18 | 15.37 | Yes |
| 150 | 150.1 [149.6, 150.6] | 100% | 0.15% | 12.43 | 19.20 | 23.25 | Yes |
| 200* | 47.5 [26.3, 68.7] (4 runs) | 24% | 76.30% | 35.48 | 57.85 | 59.56 | No |
| 300† | 9.9 [8.0, 11.6] | 3% | 96.69% | 44.85 | 58.45 | 59.50 | No |

All latencies use 2-second blocks. *Whether the measuring program contributed to this drop is unresolved (see text). †Excluded under the pre-registered rules; shown as sensitivity data only.

*4.3.3 Sharding did not spread the processing*

Separate tests for payments that cross shards and payments that stay on one shard were considered but not run, because the distinction turned out not to matter for processing. On NEAR, every token transfer executes on the one shard that holds the token's contract. About three quarters of payments did cross shards, from the sender's shard to the token's, but every one was processed on that single shard. Sharding spread the job of including transactions across shards, but never the job of executing them. This is recorded as an amendment to the analysis plan. It has a direct consequence for remittances: a stablecoin issued as a single contract is capped at what one shard can process, however many shards the network has, and additional shards can only move other traffic off that shard. An earlier projection of about 372 payments per second at mainnet's 10 shards was withdrawn for this reason. For a remittance system built on a single stablecoin contract, NEAR's sharding therefore offers little throughput advantage over a single-chain design, unless the stablecoin itself were split across multiple contracts.

*4.3.4 Failure rate by payment size*

As on Polygon Edge, failure rates were flat across payment sizes at moderate load, and gas use was nearly identical across sizes, varying by less than 0.06% (Table 4.12). The higher failure rate for $500 payments at 150 per second comes from a single run out of five, which achieved 127.3 per second with 14.39% of payments failing; the other four achieved 149.3 to 150.0 per second with 0.05% to 0.35% failing. Since the processing work does not depend on the amount, this most likely reflects a disturbance during that run rather than an effect of payment size.

**Table 4.12.** NEAR failure rate by payment size

| Size | Failure at 100 per s | Failure at 150 per s | Mean gas |
|---|---|---|---|
| $10 | 0.20% | 0.17% | 2.2154 × 10¹² |
| $50 | 0.21% | 0.19% | 2.2147 × 10¹² |
| $200 | 0.16% | 0.15% | 2.2159 × 10¹² |
| $500 | 0.20% | 2.99% | 2.2152 × 10¹² |

*4.3.5 Node failures*

NEAR used the same outage rules as Polygon Edge (15 to 45 second outages with 20 to 60 second gaps), and in practice its validators were offline less of the time (about 41%, against about 50% on Polygon Edge). Even so, two differences made the test harsher for NEAR, and both affect how the results should be read. First, each NEAR shard had only 2 validators, so one outage cut a shard to a single validator, while Polygon Edge kept 3 of its 4 validators. Second, a NEAR validator that misses too much of its work while offline is removed from the validator set, and at this testbed's settings it stays out for about 4 hours (two epochs). NEAR's validator set therefore shrank across the node-failure runs, while a Polygon Edge validator was never removed. Under these conditions, NEAR lost 31.6% of its throughput at 100 per second and 76.4% at 150 per second, and almost all payments failed at 200 per second (Table 4.13). A separate exploratory block of five runs at 150 per second, with validators offline only about 12% of the time, delivered 47.9 per second [0.6, 107.0] with 67.99% of payments failing; individual runs ranged from 0 to 149.3 per second.

**Table 4.13.** NEAR with one validator offline at a time

| Offered (per s) | Clean | With node failures [95% CI] | Throughput lost | p95 with failures (s) |
|---|---|---|---|---|
| 100 | 100.0 per s, 0.16% failure | 68.4 per s [39.1, 95.3], 31.72% failure | 31.6% | 55.53 |
| 150 | 150.1 per s, 0.15% failure | 35.4 per s [3.8, 69.3], 76.36% failure | 76.4% | 57.42 |
| 200 | 47.5 per s, 76.30% failure | 0.1 per s [0.0, 0.3], 99.95% failure | ~100% | 59.75 |

*4.3.6 Cost per transaction*

Each payment used a mean of 2.2153 × 10¹² gas. At NEAR's mainnet protocol floor of 100,000,000 yoctoNEAR per unit of gas, which was the price mainnet was actually charging that day [40], and a NEAR price of $1.65 [37], both recorded on 12 August 2026, this comes to about $0.000366 per payment.

**4.4 Cross-architecture comparison**

Table 4.14 places all three architectures side by side. Polygon Edge and NEAR were measured with the same instrument, in the same regions, under the same impairment and background traffic settings, so their figures are broadly comparable. Four differences remain and are noted where they matter: the measuring program checks settlement once per block on Polygon Edge but once per payment on NEAR; NEAR ran with a non-default 2-second block time; the networks had different numbers of validators (4 and 8); and background traffic competed with the token's shard on NEAR at about a quarter of the rate at which it competed with the whole Polygon Edge chain. Node failures also hit NEAR harder by design (Section 4.3.5). Lightning's figures come from different sources and methods and are shown for completeness, not as a head-to-head measurement.

**Table 4.14.** Summary of results on the pre-registered metrics

| Metric | Polygon Edge (sidechain) | NEAR (sharding) | Lightning (off-chain) |
|---|---|---|---|
| Sustainable throughput at $200 | 200 per s; 200.9 [199.7, 201.9] (self-measured) | 150 per s; 150.1 [149.6, 150.6] (self-measured) | No published figure found |
| p50 / p95 / p99 latency at that load | 3.43 / 4.77 / 6.35 s (self-measured) | 12.43 / 19.20 / 23.25 s at 2 s blocks (self-measured) | Median 3.36–13.12 s from probe payments; no published p95 or p99 (literature-derived) |
| Failure rate at $200 at that load | 0.00% (self-measured) | 0.15% (self-measured) | Unmeasured at $200; 82.70% at $100 (literature-derived) |
| Cost per $200 transfer | $0.0006 (self-measured gas, mainnet pricing) | $0.000366 (self-measured gas, mainnet pricing) | $0.0523, routing only (estimated) |
| Meets the pre-registered decision rule (p95 < 10 s, cost < $0.10) | Yes | No: p95 above 10 s at every load at 2 s blocks | Cannot be ranked |
| Throughput lost to node failures at 100 per s | 0.7% (self-measured) | 31.6% (self-measured; harsher test, see 4.3.5) | Not measured |
| Behavior after an outage | Validator not removed; recovery time not measured | Validator removed for about 4 hours | Not measured |
| Main weakness observed | Little headroom when validators are lost | All execution on one shard; sensitive to validator loss | Liquidity at larger payment sizes |
| Security assumption | Permissioned IBFT validator set (no bridge tested) | Random validator assignment per shard; 2 per shard here | Channel counterparties and routing nodes; funds locked in channels |

**[FIGURE 4.7]** *Failure rate by payment size, all three architectures.* A grouped bar or line chart with payment size on the x-axis. Use Polygon Edge at 200 per second (Table 4.8), NEAR at 150 per second (Table 4.12), and Lightning from Table 4.2, drawn as a dashed line or hatched bars and labeled literature-derived. This is the clearest single visual for why payment size matters to the recommendation.

*4.4.1 Answers to the pre-registered research questions*

RQ1 (throughput). At the $200 benchmark size, Polygon Edge sustained 200 payments per second and NEAR sustained 150. We found no published sustainable throughput figure for Lightning, and its published failure rates exceed the 5% threshold at every size tested, starting from $0.01.

RQ2 (reliability by size). On Polygon Edge, no payment of any size failed at any load up to its sustainable limit. On NEAR, failure rates were flat across sizes at 100 per second (0.16% to 0.21%), and at 150 per second they were flat except for $500 payments (2.99%), where a single run accounted for the rise (Section 4.3.4). This was expected, since gas use did not depend on the amount. In Waugh and Holz's measurements, Lightning's failure rate rose with payment size, from 28.08% at $0.01 to 82.70% at $100 [16].

RQ3 (cost). At mainnet prices on 12 August 2026, NEAR had the lowest cost per payment at $0.000366, followed by Polygon Edge at $0.000589 (about $0.0006 at the 9 August prices as well). This ranking depends on mainnet gas prices, which change over time: NEAR was charging its minimum price, while Polygon's price was about 270 Gwei on both dates, and Polygon Edge would become the cheaper of the two if its gas price fell below about 170 Gwei. Lightning's estimated routing fee of $0.0523 is about 87 to 89 times Polygon Edge's cost, even before channel-opening costs and the cost of locked capital are included. Because Lightning's fee scales with payment size, a $500 payment costs about $0.1467 in routing fees.

RQ4 (gap to production). Table 4.15 compares the private-network results with real mainnet activity on 12 August 2026. Polygon Edge's private network sustained about 2.5 times the transaction rate Polygon mainnet was actually carrying, and about 72% of mainnet's estimated capacity. NEAR's private network sustained about 31 times mainnet's observed rate, but NEAR mainnet blocks were only 0.04% full, so its capacity cannot be estimated from this sample. NEAR's mainnet sample was small (8 blocks) and should be read only as an order of magnitude. The first ratio describes how busy mainnet was, not the maximum it can handle, and the second compares against an estimate of that maximum, so both are plausibility checks rather than direct tests.

**Table 4.15.** Private-network results compared with mainnet activity (12 August 2026)

| Network | Private sustainable (per s) | Mainnet observed (per s) | Ratio to observed activity | Ratio to estimated mainnet capacity |
|---|---|---|---|---|
| Polygon | 200.9 | 79.6 (25 blocks) | 2.52× | 0.72× (mainnet capacity about 279 per s, at 28.5% block use) |
| NEAR | 150.1 | 4.8 (8 blocks across 10 shards) | 31.3× | Not derivable (blocks 0.04% full) |

*4.4.2 The pre-registered decision rule*

The analysis plan fixed in advance how the recommendation would be made: the architecture with the highest sustainable throughput at $200, among those whose 95th percentile latency is under 10 seconds and whose cost is under $0.10 per payment at that load. Polygon Edge meets both conditions (200 per second, 95th percentile 4.77 seconds, about $0.0006). NEAR does not, because its 95th percentile latency exceeded 10 seconds at every load tested (12.33 seconds at best). That disqualification depends on the 2-second block time: in the preliminary 1.2-second test, the 95th percentile was 8.20 seconds, which would pass. Lightning cannot be ranked, because no sustainable throughput figure exists for it. Under the pre-registered rule, Polygon Edge is therefore the recommended architecture.

*4.4.3 Summary*

Under the conditions tested, Polygon Edge offered the highest sustainable throughput at the $200 benchmark size, with no failures and a median settlement time under 3.5 seconds, and it is the only architecture that meets the pre-registered decision rule. NEAR was somewhat cheaper per payment at August 2026 prices, but it sustained lower throughput, settled about 9 seconds slower at the block time used, and gained no processing capacity from sharding, because a single stablecoin contract runs on a single shard. Both networks kept failure rates flat across payment sizes at moderate load, while Lightning's published failure rates rose steeply with size and exceeded the pre-registered threshold even for the smallest payments tested. These results point to Polygon Edge as the strongest candidate for the interoperability design in Section 5, with two qualifications carried forward: its throughput fell sharply when validators were lost, and the software is no longer maintained. Lightning's 2019 reliability data does not support routing even small remittances through it, although its reliability has likely improved since then.

**Figures at a glance**

| Figure | What it shows | Data | Priority |
|---|---|---|---|
| 4.1 | Private vs. live Lightning scale, log scale | Table 4.1 | Medium |
| 4.2 | Lightning success by payment size, $200 marked "no data" | Table 4.2 | High |
| 4.3 | Deployment map | Tables 4.5 and 4.10 | Optional |
| 4.4 | Polygon Edge realism steps at 300 per s, labeled exploratory | Table 4.6 | Medium |
| 4.5 | Offered vs. achieved throughput, both chains, 90% line | Tables 4.7 and 4.11 | High |
| 4.6 | Throughput over time during a node-failure run | New query on raw data | Medium |
| 4.7 | Failure by payment size, all three architectures | Tables 4.2, 4.8, and 4.12 | High |

If space is tight, keep 4.2, 4.5, and 4.7.

**New references**

[32] (unused; renumber at assembly)
[33] C. Decker, "c-lightning Plugins 05: Probe Plugin Results," Blockstream Blog, 20 Nov. 2019. [Online]. Available: https://blog.blockstream.com/c-lightning-plugins-05-probe-plugin-results/
[34] S. Tikhomirov, R. Pickhardt, A. Biryukov, and M. Nowostawski, "Probing channel balances in the Lightning Network," arXiv:2004.00333, 2020.
[35] U. Nisslmueller, K.-T. Foerster, S. Schmid, and C. Decker, "Toward active and passive confidentiality attacks on cryptocurrency off-chain networks," in Proc. 6th Int. Conf. Information Systems Security and Privacy (ICISSP), 2020. Extended version: arXiv:2003.00003.
[36] 1ML, "Lightning Network statistics." [Online]. Available: https://1ml.com/statistics (accessed 10 Aug. 2026)
[37] CoinGecko, price data for BTC (10 Aug. 2026) and for POL and NEAR (12 Aug. 2026). [Online]. Available: https://www.coingecko.com
[38] F. Béres, I. A. Seres, and A. A. Benczúr, "A cryptoeconomic traffic analysis of Bitcoin's Lightning Network," arXiv:1911.09432, 2019. Presented at Cryptoeconomic Systems (CES) 2020.
[39] PolygonScan, "Polygon gas tracker," gas price and POL price (accessed 9 Aug. 2026). [Online]. Available: https://polygonscan.com/gastracker
[40] NEAR Protocol mainnet RPC, rpc.mainnet.near.org (queried 12 Aug. 2026).
[41] mempool.space, "Lightning Network statistics" (accessed 18 Aug. 2026). [Online]. Available: https://mempool.space/lightning
[42] River Financial, "Lightning Report 2023" (updated Feb. 2024). [Online]. Available: https://river.com/learn/files/river-lightning-report-2023.pdf
[43] Lightning Labs, "lnd v0.10" release announcement, 30 Apr. 2020. [Online]. Available: https://lightning.engineering/posts/2020-04-30-lnd-v0.10
[44] Polygon PoS mainnet, block 91,888,638 (12 Aug. 2026), read through the public RPC endpoint polygon-bor-rpc.publicnode.com.
