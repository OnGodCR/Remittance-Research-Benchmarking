# Spend ledger

**Why this file exists.** Google does not expose actual spend through its API
without a BigQuery billing export, which this project does not have. So spend
is tracked here from machine-hours: what ran, for how long, times the published
hourly rate. It is an ESTIMATE and is labelled as one. The authoritative
numbers are the budget alert emails at $50 / $100 / $200 and the billing
console.

**Budget: $300 total** (Angad, 23 Aug 2026). Credit on billing account
`01DAB3-71DAC1-49A233` was ~$274 as of 21 Aug.

## Rates

| Cluster | Machines | ~$/hr |
|---|---|---|
| NEAR | 8x n2-standard-8 + 1x n2-standard-16, four regions | 4.50 |
| Polygon | 4x n2-standard-8 + 1x n2-standard-16 | 2.60 |
| Single generator | 1x n2-standard-16 | 0.86 |

## Log

| Date (UTC) | What ran | Hours | Est. cost | Cumulative |
|---|---|---|---|---|
| to 21 Aug | Phases 1-4 and Phase 6 Polygon work, on the earlier accounts | — | ~26 | ~26 |
| 22 Aug 04:00-11:15 | NEAR rebuild, account setup, killed by the 11:15 shutdown | 7.2 | ~32 | ~58 |
| 22 Aug 19:12-00:44 | NEAR setup completed + endpoint A/B, 20 runs | 5.5 | ~25 | ~83 |
| 23 Aug 00:44-00:51 | generator alone, to recover the results database | 0.1 | ~0 | ~83 |
| 23 Aug 00:51-02:56 | Block-cadence attempt — **discarded**: collected without the network impairment (stale addresses; ops audit) | 2.1 | ~9 | ~92 |
| 23 Aug 03:30-10:18 | Corrected campaign, impairment verified: 24 endpoint runs + 13 block-cadence runs | 6.8 | ~31 | ~123 |

## Planned

| Work | Est. hours | Est. cost |
|---|---|---|
| Original-contract test | 0.8 | ~4 |
| Polygon at full spec | 4.0 | ~10 |
| **Projected total** | | **~$137** |

Leaves roughly $190 of the $300 unspent.
