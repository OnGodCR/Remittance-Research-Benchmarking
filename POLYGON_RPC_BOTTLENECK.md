# The Polygon ceiling is the RPC endpoint, not the architecture

**Measured 19 Aug 2026**, on the supplementary cluster in project
`remittances-benchmarking`. This finding supersedes part of what
`RESUME_HERE.md` §3 says about what limits Polygon's throughput, and it needs
to reach the paper.

---

## 1. What was being tested, and what turned up instead

The supplementary test was meant to answer an auditor's objection: is
Polygon's measured ~270 payments/sec ceiling a real architectural limit, or an
artefact of a transaction-queue size we never tuned? The plan was to run the
same cluster twice with the queue at its shipped size and at eight times that.

Both attempts lost the load level the question lives at. At 300 payments/sec
the benchmarking program repeatedly fell behind its own schedule and
auto-invalidated the runs — 7 of 10 in the first attempt, and again after the
sending machine was doubled from 8 processors to 16.

Doubling the sender changing nothing is what prompted measuring where the work
actually lands.

## 2. The measurement

Taken during a live 300 payments/sec run, sampling `/proc/stat` over 6 seconds
on every machine at once. Connection counts are established TCP sessions to
port 8545, the JSON-RPC port.

| Machine | Role | CPU busy | RPC connections |
|---|---|---|---|
| validator-0 | consensus **and the only RPC endpoint** | **84.1%** | 540 |
| validator-1 | consensus only | 9.0% | 0 |
| validator-2 | consensus only | 8.5% | 0 |
| validator-3 | consensus only | 14.0% | 0 |
| generator | submits the payments | 12.4% | 540 |

Every machine has 4 processors except the generator, which has 16.

## 3. What it means

The three validators doing only consensus work sit between 8% and 14% busy.
The one that *also* answers RPC sits at 84%, holding 540 open connections. The
sending machine — the component the harness blamed — is nearly idle.

**Consensus is not the constraint. The block gas limit is not the constraint.
The sending program is not the constraint. One node's RPC service is.**

The harness's "generator saturated" verdict was accurate about the symptom and
misleading about the cause: its workers fall behind schedule because they are
blocked waiting on RPC replies, not because they lack processor time. Raising
the generator to 16 processors was therefore the wrong fix, and it is recorded
here as a wrong turn rather than quietly dropped.

Two properties of the workload concentrate load on that one node:

1. **Every submission goes to a single endpoint.** The harness is configured
   with one `rpc_url` and all 46 sender wallets submit through it.
2. **Settlement is checked one payment at a time.** Polygon Edge v1.3.2 does
   not implement `eth_getBlockReceipts`, so the adapter falls back to polling
   each payment's receipt individually. At 300/sec with a measured mean
   settlement of 21.96 s, roughly 6,600 payments are in flight at once, each
   being polled.

So the node must serve ~300 submissions/sec *plus* thousands of receipt
lookups/sec, while also producing and validating blocks, on 4 processors.

## 4. Why this matters to the published result

The published Phase 2 sweep used the **same single-endpoint design**, with
validator-0 on 8 processors instead of 4. The structural bottleneck was
therefore present there too — with twice the capacity, which is consistent
with the published ceiling (~270/sec) landing near this cluster's (~266/sec)
despite half the processors. A limit set by consensus or by the gas limit
would have been expected to scale with processor count. This one did not.

**The claim that Polygon's ~270 payments/sec is an architectural ceiling is
not currently supported.** It may instead be the throughput of one Polygon
Edge node's JSON-RPC service under a receipt-polling workload. Until that is
separated, the number should be described as *the measured throughput of this
deployment*, not as a property of the sidechain architecture.

This is the auditor's objection landing, just not where anyone expected: the
suspect setting was the transaction queue, and the actual constraint was the
endpoint in front of it.

## 4b. What the PUBLISHED dataset shows when you look for the same strain

Two checks were run against the study's own database, 19 Aug 2026.

**First, the saturation rule was re-applied to all 498 runs in the study.**
Zero verdicts changed. The criterion has been applied uniformly and the
published dataset is internally consistent under it. No published run is
invalid on this measure.

**Second, absolute scheduling lag was measured, not just its growth.** The
rule tests whether lag GROWS across a run, deliberately: lag that is large but
steady shifts every submission by the same offset and does not reduce the
offered rate, whereas lag that grows means the sender is losing ground. That
logic is sound. But it means a run can sit permanently far behind schedule and
still pass.

Published `phase-2-full-stack` runs, valid, $200:

| Offered | Runs | Lag growth | **Absolute p95 lag** |
|---|---|---|---|
| 200/sec | 32 | 0.0 ms | **63.8 ms** |
| 300/sec | 30 | 0.6 ms | **562.8 ms** |

At 300/sec the published runs were submitting roughly **half a second behind
schedule**, nearly nine times the lag at 200/sec, while passing the growth
test with 0.6 ms to spare.

This does **not** invalidate them. The rule was pre-registered, it was applied
correctly, and changing a rule after seeing which runs it would exclude is the
exact practice the analysis plan exists to prevent. The figures reproduce: the
published 270.5/sec at 300 offered recomputes from the raw database to 270.5.

What it does show is that the published 300/sec runs were measured on an
instrument under visible strain, and that the strain appears exactly where
this document says the bottleneck is. Taken with the direct measurement in
§5b, the three numbers line up:

| Configuration | Validators | Endpoints | Achieved at 300 offered |
|---|---|---|---|
| Published | 8 processors | 1 | 270.5/sec (p95 lag 563 ms) |
| Tonight | 4 processors | 1 | 274.9/sec (saturated, invalid) |
| Tonight | 4 processors | 4 | **290.5/sec** (p95 lag ~0) |

Halving the validators changed nothing. Spreading the settlement checks
changed everything. That is the signature of a limit that lives in one node's
request service rather than in consensus or block capacity.

## 5. The test that would settle it

Spread submissions and receipt polling across all four validators' RPC
endpoints instead of one, and re-measure the ceiling.

- **If throughput rises materially**, the published ceiling is a deployment
  artefact and must be re-stated. The architecture's real ceiling is higher
  and still unmeasured.
- **If it does not rise**, the constraint is downstream of the endpoint —
  consensus or execution — and the published framing is safe.

This needs a change to the harness, which currently accepts a single
`rpc_url`. That is a change to the measuring instrument mid-study and must be
recorded as such: any run using multiple endpoints is not directly comparable
with the published single-endpoint runs, which is precisely why the comparison
has to be run on one cluster with both configurations.

## 5b. RESULT — measured 19 Aug 2026, and it is worse than expected

The test in §5 was run. Same cluster, same load, minutes apart, changing only
where settlement checks are sent.

| Settlement checks via | Achieved | Failures | Schedule slip | Valid |
|---|---|---|---|---|
| 1 node (the published method) | 274.9/sec | 8.3% | **+228.6 ms** | **no — saturated** |
| 4 nodes | **290.5/sec** | **3.1%** | **+0.3 ms** | yes |

Two things happened together. The saturation disappeared -- a 760-fold
improvement in schedule slip, turning an invalid run into a clean one -- and
throughput rose while failures fell by nearly two thirds.

**On 4-processor validators, this beats the published 270.5/sec measured on
8-processor ones.** The published figure was substantially a measure of how
fast one node can answer questions about payments, not of how fast the
sidechain can settle them.

### And the ceiling is a cliff, not a plateau

With the bottleneck removed, the load ramp was pushed past 300 for the first
time. Every run below kept its schedule (slip ≈ 0), so these describe the
chain, not our tooling. One run each -- exploratory, enough to locate the
knee, not enough to publish.

| Offered | Achieved | Refused at the door | Accepted then stuck |
|---|---|---|---|
| 300 | **290.5** | 0 | 2,758 |
| 400 | 202.5 | 1,153 | 58,304 |
| 500 | 108.3 | 44,932 | 72,950 |
| 600 | 96.5 | 87,121 | 63,885 |

Polygon peaks near 290/sec and then **collapses to a third of that**. It does
not degrade gently.

**This contradicts one of the paper's headline comparisons.** `RESUME_HERE.md`
§3 and `COMPARISON.md` state that Polygon degrades gracefully past its knee
while NEAR collapses, and present that contrast as the more interesting
finding than either ceiling. That contrast was drawn from a ramp that stopped
at 300/sec -- which is Polygon's knee, not past it. "Graceful degradation past
the knee" was a claim about a region that had never been measured.

Both architectures collapse. NEAR's collapse is still steeper (to about 7% of
peak at twice peak offered, against Polygon's 33%), so a real difference in
degree survives, but "graceful versus catastrophic" does not.

### The failure mechanism also shifts with load

At 300/sec every failure is a payment accepted and then left unsettled, with
zero refusals. As load rises the mix inverts: by 600/sec most payments are
refused at the door. That is the queue filling up -- first the node accepts
everything and cannot keep up, then the queue saturates and it starts turning
work away.

Note this differs from the published single-endpoint finding that *every*
failure was a submission rejection. Relieving the bottleneck lets more
payments in, which converts refusals into stuck payments. The measurement
method changes which failure mode is observed, and that must be stated
whenever either failure mode is reported.

## 5c. A SECOND drift: the chain gets slower as it grows

Noticed 19 Aug 2026 while the repeated measurement was running. The 400/sec
runs, in the order they were measured on one continuously-running chain:

| Order | Achieved | Chain size when run |
|---|---|---|
| 1st (repeat 0) | 241.3/sec | smaller |
| 2nd (repeat 1) | 232.2/sec | ~1.2 GB |
| 3rd (repeat 2) | **173.7/sec** | ~1.3 GB, 12,600 blocks |

All three runs held their schedule (slip under 0.3 ms), so this is the chain,
not our tooling.

**State growth was the first explanation, and the next data point weakened
it.** If a growing chain were the driver, every load level should drift down
together. Measured across the same three repeats:

| Offered | Repeat 0 | Repeat 1 | Repeat 2 | Spread |
|---|---|---|---|---|
| 400/sec | 241.3 | 232.2 | 173.7 | **28%** |
| 500/sec | 145.9 | 155.1 | 146.8 | **6%** |

500/sec is steady across the same chain growth that supposedly cost 400/sec a
quarter of its throughput. So growth is not doing the work, and the honest
reading is that **400/sec sits right at the cliff edge, where the system is
unstable and outcomes scatter**. 500/sec is far enough past it to be reliably
broken, and 300/sec is comfortably below it -- both reproduce tightly.

That is itself worth reporting: the region immediately past the knee is not
just lower, it is *less predictable*, which for a payment system is arguably
the worse property. An operator can plan around a firm ceiling; a ceiling that
varies 28% run to run is much harder to size for.

**What this protects and what it does not.**

The one-endpoint versus four-endpoint comparison is SAFE: the two arms
alternate *within* each repeat, minutes apart on a chain of essentially the
same size, so growth affects both equally and cancels. That is the same
property that made the alternating design worth the extra restarts.

The collapse curve should be reported as a RANGE, not a mean, at least at
400/sec. Averaging the three figures into "216/sec" would hide a 28% spread
that is a property of the system rather than measurement noise.

**And it bears on the published study.** The published sweep ran 140 runs on
one continuously-growing chain, in a fixed low-to-high load order. So its
high-load runs were measured last, on the biggest chain, immediately after the
heaviest preceding step. Three separate mechanisms therefore push the
published 300/sec figure DOWN relative to what the architecture can do:

1. every settlement check funnelled through one node (§2-§5b),
2. no drain between runs, so each inherited the previous queue (see the note
   in `scripts/run_endpoint_ab.sh`),
3. chain-state growth over the sweep -- plausible but NOT demonstrated here;
   the 400/sec scatter that first suggested it is better explained by
   instability at the cliff edge, since 500/sec stayed steady across the same
   growth.

None of them were errors at the time -- they are ordinary consequences of
running a long sweep on one chain, and every benchmark of this kind has them.
They matter because the number produced was then described as an architectural
ceiling.

## 5d. THE REPEATED MEASUREMENT — 5 repeats, computed from the raw data

The §5b result was one run per condition. This is the repeated version, 35
runs collected 19 Aug 2026, every figure recomputed from
`data/raw/all_runs_raw.parquet` under the pre-registered rules (10-second
warm-up discarded, success means settled within 60 seconds) rather than read
off the console.

### The control did its job

| 200/sec | Valid runs | Achieved | Range | Failures |
|---|---|---|---|---|
| One endpoint | 5 | 200.9 | 198.7–202.5 | **0.00%** |
| Four endpoints | 5 | **200.9** | **198.7–202.5** | **0.00%** |

Identical means, identical ranges, zero failures on both sides. At a load
where nothing is under strain, the two arms are indistinguishable — which is
the only thing that makes the 300/sec difference interpretable.

That control failed twice during collection and both failures were bugs of
ours, not the chain's: receipt lookups racing ahead of block propagation, and
a run starting before the previous one's queue had drained. Neither would have
been visible without a check that could fail.

### At 300/sec the single endpoint produces no usable measurement at all

| 300/sec | Valid runs | Invalid | Achieved | Failures |
|---|---|---|---|---|
| One endpoint | **0** | **6** | — | — |
| Four endpoints | **5** | 1 | **300.4** (298.3–302.2) | **0.00%** |

Every single-endpoint run at 300/sec auto-invalidated: the sending program
fell 272–709 ms behind its own schedule, against a 50 ms limit, in all five
repeats. Four endpoints held 0.1–0.2 ms every time.

**Where both arms produced a number before invalidation, that number was
identical** — 299.7, 301.1, 298.5, 300.7, 302.0 in matched pairs, with zero
failures on both sides. The chain was never the constraint at this load. Only
our ability to observe it was.

**300.4 payments/sec with zero failures, on 4-processor validators, against
the published 270.5/sec with 9.97% failures on 8-processor ones.**

### The collapse, five repeats each

| Offered | Achieved | Range | Failures |
|---|---|---|---|
| 300 | **300.4** | 298.3–302.2 | 0.00% |
| 400 | 209.8 | 166.0–236.2 | 47.4% |
| 500 | 141.2 | 134.6–153.0 | 63.8% |
| 600 | 110.0 | 101.0–119.9 | 69.3% |

Peak is at or above 300; at twice that offered load the chain delivers 110/sec
— **37% of peak**. Polygon collapses. The knee is somewhere between 300 and
400 and is being measured separately.

Note the ranges. 300/sec reproduces within 1.3%, and 400/sec within 34%. The
region immediately past the knee is not merely slower but markedly less
predictable, which for a payment system is the harder property to design
around: an operator can size for a firm ceiling, not for one that varies by a
third between identical runs.

## 5e. WHERE THE KNEE ACTUALLY IS — 20 runs, 5 repeats per step

Every published statement puts Polygon's knee at 300 payments/sec. That was
never measured as a knee: 300 was simply the top of the pre-registered ramp,
so it is the last point before the data stops, not the point where the
architecture stops. With the endpoint bottleneck removed, 300/sec turned out
to be comfortably clean, so the knee had to be found rather than assumed.

Measured 19 Aug 2026, four endpoints, 5 repeats each, computed from
`data/raw/all_runs_raw.parquet` under the pre-registered rules:

| Offered | Achieved | Range | Mean failures | Worst run |
|---|---|---|---|---|
| **320** | **320.5** | 319.0–322.3 | **0.00%** | **0.00%** |
| 340 | 337.9 | 331.5–340.1 | 0.70% | 2.61% |
| 360 | 286.2 | **242.5–351.4** | 20.44% | 32.63% |
| 380 | 235.1 | 192.0–276.6 | 38.24% | 49.82% |

**320/sec is the highest load that is reliably perfect**: five runs, zero
failed payments in any of them, throughput within 3.3/sec across repeats.

**340/sec still works but is no longer perfect** — 0.70% of payments lost on
average, and one repeat lost 2.61%.

**360/sec is where it becomes a coin flip.** Across five identical runs
throughput ranged from 242.5 to 351.4 — a **45% swing at the same offered
load** — with failures from a few percent to a third. One repeat nearly kept
up; two lost a third of everything.

**380/sec is reliably broken**, though still noisy.

### The shape matters more than the number

An earlier note in this document called the knee "a sharp cliff" on the
strength of one repeat. Five repeats show something different and more useful:
there is no clean threshold. There is a **band from roughly 340 to 380 where
behaviour becomes unpredictable**, sitting between a deterministic clean
region below and a deterministic broken region above.

For a remittance system that band is the dangerous part. A benchmark run once
at 360/sec could report 351/sec and 2% failures — which reads as healthy — or
242/sec and 33% failures, which reads as collapse. Both are true. An operator
sizing capacity from a single measurement in that region would be badly
misled, in either direction.

**Revised headline for the paper.** On this cluster Polygon Edge sustains
**320 payments/sec with zero failures**, degrades slightly to 340, and becomes
unstable above that. The published figure of 270.5/sec with 9.97% failures at
300 offered describes the single-endpoint measurement setup, not the
architecture. These are 4-processor validators against the published 8, so the
absolute numbers are this deployment's, but they are a floor rather than a
ceiling: better hardware would not be expected to do worse.

## 6. What is NOT affected

- The 100/sec and 200/sec runs, in both queue settings, completed cleanly with
  zero failures and no scheduling lag. Nothing about them is in question.
- The **kind** of failure still tracked the queue size in every valid run:
  at the shipped size, payments were refused at submission; at eight times the
  size, payments were accepted and then timed out unsettled. That is about
  what the node does with what it receives and does not depend on the ceiling
  question.

## 7. A selection problem in the queue experiment, recorded for completeness

Even setting the bottleneck aside, the queue comparison had a flaw worth
stating. The enlarged queue accepts payments the default queue refuses — that
is its entire purpose. Accepted payments are then polled for settlement. So
the enlarged arm imposes strictly more RPC load than the default arm, and is
therefore more likely to trigger the saturation rule and be excluded.

**The treatment influences the probability of exclusion.** Comparing the
survivors is biased, and no amount of repeats fixes it. The queue question
cannot be answered by this design while the RPC endpoint is the constraint —
which is a further reason to fix the endpoint first.
