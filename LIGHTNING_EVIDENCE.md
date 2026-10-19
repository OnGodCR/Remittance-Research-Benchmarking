# Lightning — What the Literature Actually Supports

**Built 18 August 2026** from a six-angle literature and network-data sweep. Every
citation below was opened and checked by a second agent; 25 confirmed, 9 corrected,
1 refuted, and **57 absences recorded**. Figures that could not be verified are
listed in §7 as things *not* to cite, including three that circulate widely and
one that appears to be fabricated.

---

## 1. The headline answer: Lightning cannot be ranked, and that is architectural

**No measured throughput ceiling for the Lightning Network exists in any
peer-reviewed venue, primary network-data source, or credible industry report.**
This was searched for directly from three separate angles and not found.

So the paper **cannot** produce a row like:

| | Sustainable throughput at $200 |
|---|---|
| Polygon Edge | 200/sec (measured) |
| NEAR | 150/sec (measured) |
| Lightning | **no such figure exists** |

**Why this is a property of the architecture, not a gap in effort.** Lightning has
no global state and no blocks. Capacity is the sum of what individual channels can
carry along whatever route a payment happens to take, and most channels are private
and invisible to any crawler. There is no observer position from which "the
network's transactions per second" is a measurable quantity. Polygon and NEAR both
have a block gas limit and a block interval; Lightning has neither.

**The two throughput-shaped numbers that do exist, and what each actually is:**

| Figure | What it really measures | Source |
|---|---|---|
| **~2.5 tx/sec** network-wide (Aug 2023) | **Demand.** What the network carried, not what it could carry. | River Lightning Report 2023 |
| **483 concurrent HTLCs per channel** | A **protocol constant** — a concurrency cap, not a rate. | BOLT #2 |
| 29.4/sec at 0 hops → 12.1/sec at 1 hop | A single unmaintained benchmark repo, **undated**, methodology unstated | dgarage/LightningBenchmarks |

The third is the most interesting and the least citable: it suggests throughput
falls by roughly 60% with a single intermediary hop. **A remittance is never a
0-hop payment**, so if that shape is real it matters — but with no date and no
stated method it cannot carry weight. Flag as suggestive only.

---

## 2. ⚠️ A citation error in our own documents

**The "6,010 nodes / 19,644 channels" figure this project attributes to Waugh &
Holz does not appear anywhere in that paper.** Zero occurrences of any of those
numbers in the full text.

**What the paper actually states:** between **4,826 and 4,950 nodes** and between
**31.4k and 31.8k non-stale channels**, measured 3–25 November 2019.

Every document in this repo that says "our testbed had 51 channels against the real
network's 19,644 — ~385× fewer" is citing a number that isn't in the source.

**The corrected comparison is stronger, not weaker:**

| | Channels |
|---|---|
| Our testbed | 51 |
| Waugh & Holz's network (Nov 2019) | ~31,600 |
| **Corrected ratio** | **~620× fewer**, not 385× |

**Where 19,644 probably came from:** 1ML.com, which this project designates as its
Lightning topology reference. On 18 Aug 2026, 1ML reported **20,004 channels** while
mempool.space reported **33,313** on the same day — a 40% disagreement between
explorers that no source reconciles. **1ML publishes no collection timestamp
anywhere on its statistics page**, which makes anything sourced from it undateable.

**Action:** correct the ratio to ~620×, cite the paper's own figures, and state the
explorer disagreement rather than picking a favourite.

---

## 3. The network in 2026 versus 2019 — the vintage problem, resolved

This determines whether citing a 2020 paper in 2026 is defensible. The answer is
more interesting than expected.

| | Nov 2019 (Waugh & Holz window) | 18 Aug 2026 | Change |
|---|---|---|---|
| Nodes | ~4,826–4,950 | 16,442 | ~3.4× |
| Channels | ~31,400–31,800 | 33,313 | **~+6%** |
| Public capacity | ~827 BTC | 3,852 BTC | **~4.7×** |
| Median channel | — | 2,042,100 sat | — |

**The finding: channel count today is barely above 2019. Capital per channel is
nearly five times deeper.**

That is not steady growth — it is a peak and a long decline:

- **Channels peaked at 82,825** (28 Mar 2022) and are now **33,225 — a 59.9% fall**
- **Capacity peaked at 5,851 BTC** (28 Dec 2025), now 3,830 BTC — **34.5% below peak**
- The two peaked **3.75 years apart**: fewer channels, each far deeper
- **A sharp contraction is happening right now**: 38,233 channels on 1 Aug 2026 →
  33,225 on 18 Aug — **13% in seventeen days**, with no explanation found in any
  source

**Concentration is extreme.** The top 10 nodes are endpoints of 35.6% of all
capacity; the top 100 — **0.6% of nodes — hold 76.2%**. (Computed from
mempool.space's raw rankings; attribute as our arithmetic, not their published
figure.)

### Verdict on citing Waugh & Holz in 2026

**Use it, with two specific caveats — do not retire it.**

The mechanism behind their size-dependent failures was **insufficient channel
liquidity** (Temporary Channel Failure, 31.6% of all attempts — their single
largest error class), not nodes being offline. Channel count is essentially
unchanged since then, so the *routing* topology is comparable. But capital per
channel is ~4.7× deeper, which should have **improved** success at larger amounts.

**So their absolute numbers are probably pessimistic for 2026, while the direction
— success falls as payment size rises — should still hold.** State it that way.

**And the structural reason it still bites:** median public channel capacity is
2,042,100 sat. At BTC = $64,186 (18 Aug 2026), **a $200 remittance is ~15% of the
median channel** — and must clear that bar at *every* hop, in the right direction.
That is exactly the condition that produces size-dependent failure.

---

## 4. Reliability — including the intermediate points we did not have

**Waugh & Holz Table I, complete** (3–25 Nov 2019, 4,626 destination nodes):

| Amount | Payment success | Nodes reached |
|---|---|---|
| $0.01 | **71.92%** | 35.24% |
| $1 | 57.82% | 35.19% |
| $5 | 44.06% | 25.66% |
| $10 | 44.15% | — |
| $50 | 30.93% | — |
| **$100** | **17.30%** | — |

The **$5 and $10 rows are new** to this project — the brief only had the endpoints.
The fall is monotonic apart from a flat step at $5→$10.

**Three limits that must travel with this table:**

1. **$100 is the maximum ever tested.** There is **no measurement at $200 or $500
   at any date, by anyone** — and $200 is this paper's primary benchmark. Extending
   the trend there is extrapolation and must be labelled as such.
2. **Only two attempts were allowed per payment.** Real wallets retry many times.
   These are therefore *lower bounds* on what a user would experience.
3. **No confidence intervals exist for any Lightning success figure**, from any
   source. Waugh & Holz probed once over 22 days; there are no repeats.

**No post-2020 size-resolved probing study exists.** Searched specifically; none
found. State as "we found none" rather than "none exists."

### The 99.7% figure — do not set it against 17.3%

River reports **99.7% success across 308,000 transactions** (Aug 2023). This is
**not comparable** to Waugh & Holz and must never be presented as reliability
improving from 17% to 99.7%. It is one commercially-operated, exceptionally
well-connected node sending real payments to counterparties it has liquidity with,
at an average size far below $200.

**River's own report contains a better proxy for everyone else: 2.63% failure on
routed transactions (~97.4% success)** — roughly double their own rate, and River
itself flags it as the more representative number. Use that one if any modern
figure is used at all.

---

## 5. Latency — the paper currently has no source, and now has three

**Waugh & Holz contains no latency measurement at all.** Verified by reading the
full PDF. The only timing-adjacent figure is 336 Payment Timeout errors (0.22% of
attempts) against a four-minute threshold. **Any Lightning latency figure in the
paper currently has no citation behind it.**

What exists, all from 2019–2020:

| Figure | Method | Source |
|---|---|---|
| **median 13.12s**; 40% <10s; **10% >30s** | 7,659 probe attempts, 4,431 nodes, mainnet | Blockstream c-lightning probe plugin (Nov 2019) |
| median 3.36s (3.93s excluding errors); most 1–3 hop routes <10s | 8,256 onions, mainnet | Tikhomirov et al., arXiv 2004.00333 |
| Additive with hops; **independent of amount**; 0.185s local → ~1.0s per public hop | n=25 per cell, **testnet**, hand-built routes | Nisslmueller et al., ICISSP 2020 |

**The two mainnet medians disagree by 4×** (13.12s vs 3.36s) because they measure
different things — a full route round-trip with retries versus a single onion.

**Critically for our decision rule: no p95 or p99 exists anywhere.** Not one source
publishes any percentile beyond a median and a single decile. **`ANALYSIS_PLAN.md`
§10 selects on p95 < 10s, so Lightning cannot be evaluated against that criterion
at all.** That is a hard blocker, not a soft caveat.

The one post-2020 peer-reviewed measurement located (Zhang, Tesfai, Fang & Qian) is
**paywalled** and could not be read.

---

## 6. Cost — the literature confirms our omission, and prices it

**Béres, Seres & Benczúr (Cryptoeconomic Systems / arXiv 1911.09432)** explicitly
state: *"in this work we give no estimate on the cost of opening the channels."*
Our own analysis flags the same omission — **it is standard across the literature**,
which makes disclosing it a strength rather than a confession.

**They also price what the omission is worth, and it is enormous:** for a router to
earn a 5% annual return on the capital locked in its channels, routing fees would
have to rise by **1,240× to 1,680×** (LNBIG 1,239.8×; ACINQ 1,680.5×). Large routers
were charging **under 0.2% of payment value**.

**This is the strongest cost finding available to the paper**, and it reframes the
comparison: Lightning's fees look near-zero *because routing capital is currently
uncompensated*. A sustainable Lightning would cost orders of magnitude more. It is a
simulation, not measured realised fees — say so.

**On-chain amortisation:** network-wide compression is **~53 Lightning payments per
on-chain transaction**. River's own ratio is 252, but River is an unusually
well-run hub — **use 53**, not 252.

**Current fee policy** (18 Aug 2026, all 33,313 announced channels): median fee rate
**101 ppm**, median base fee **500 msat**. Note our own cost model used 165 ppm; the
current median is lower. This is *policy*, not fees actually paid — **no published
measurement of realised fees paid exists at all.**

---

## 7. What nobody has measured — and four things not to cite

**Absences, which are findings:**

- No measured throughput ceiling, from any source
- No success rate at $200 or $500, from any date
- No post-2020 size-resolved probing study
- No p95/p99 latency, from any source
- No post-2020 mainnet latency measurement obtainable
- No confidence intervals on any Lightning success figure
- No realised (as opposed to advertised) routing-fee measurement
- No independent, non-River network-wide transaction count
- Private channel capacity is entirely unmeasured — claimed to be "2× or more" of
  public, unverifiable in principle
- No Lightning performance data along any specific remittance corridor
- No explanation, anywhere, for the 13% contraction in the first 18 days of Aug 2026

### ⚠️ Four figures to avoid

1. **"~80% success for $500+, ~50% for $5K+"** — recurs across search results and
   AI summaries. **False trail; no primary source.**
2. **"Stadelmann (2023), success rates as low as 50%"** — attributed to a real
   arXiv paper that contains no such claim. **Appears to be fabricated.**
3. **"8.6 second median payment time"** — widely repeated (LnRouter 2022),
   **untraceable to any method or dataset**.
4. **Voltage "237,000 payments, 99.94% success" iGaming pilot** — unverified, no
   primary source located.

That these circulate is itself worth a sentence in the paper: **the Lightning
performance literature is thin enough that secondary sources have filled the gap
with numbers that do not exist.**

---

## 8. Remittances specifically — the deployment evidence is weaker than the narrative

- **El Salvador: 0.70% of remittance volume** via crypto (Jan–Apr 2026, $23.1M of
  $3,286.72M), up 44.3% year-on-year. **The decisive caveat: the central bank's
  category is "billeteras de criptomonedas" — an undifferentiated crypto-wallet
  aggregate with no Lightning breakout at all.** It is not a Lightning statistic.
- **Why adoption stayed low is demand-side, not technical.** Alvarez, Argente & Van
  Patten (*Science*, 2023; n=1,800 households): of those who downloaded Chivo, only
  **3% received remittances in bitcoin**; **89% received none**. Cash preference,
  distrust and privacy concerns — not throughput or fees.
- **Chipper Cash** (7M+ users) states 50% of its Bitcoin traffic runs over
  Lightning but publishes **no success rate, no latency, no throughput, nothing**.
- **River states remittances were not a meaningful driver of Lightning growth** —
  gaming, tipping and streaming were. An admission against interest from a
  Lightning-invested company, which makes it more credible.

**This materially weakens any claim that Lightning is a proven remittance rail.**
The deployments exist; the published performance evidence does not.

---

## 9. What this means for the paper's comparison and decision rule

**Lightning cannot be ranked by `ANALYSIS_PLAN.md` §10.** The rule needs sustainable
throughput at $200, p95 latency, and cost. Lightning has **no throughput figure and
no p95 at any size** — two of three inputs are missing, and the third (cost) rests
on advertised policy rather than realised fees.

**This is not a failure of the study. It is a finding, and it should be stated as
the strongest thing this section says:**

> Two of the three architectures could be evaluated against a pre-registered
> decision rule. The third could not — not because it was measured badly, but
> because the quantities the rule requires have never been measured for it by
> anyone. Lightning's capacity is the sum of thousands of private, individually
> invisible channels; there is no observer position from which its throughput is
> defined. A payment architecture whose performance cannot be characterised is a
> different kind of proposition for a remittance operator than one whose can be,
> independent of how fast it is.

**Recommended framing for the three-way comparison:**

- **Rank Polygon and NEAR** against the pre-registered rule.
- **Report Lightning separately**, on the axes where evidence exists: size-dependent
  reliability (direction solid, absolute values 2019-vintage and pessimistic),
  cost (with the 1,240–1,680× capital-return caveat, which is the real story), and
  the structural fact that a $200 payment is ~15% of a median channel.
- **State the absence explicitly** rather than leaving a blank cell.

**Do not** extrapolate Waugh & Holz's curve to $200 and present it as a comparable
reliability figure. **Do** use their curve to argue the *direction*, and pair it with
the median-channel arithmetic, which is current and sourced.
