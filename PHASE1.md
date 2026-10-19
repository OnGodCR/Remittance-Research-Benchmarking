# Phase 1, in plain language

No jargon. This explains what Phase 1 does, what gets deployed, what happens during a test, how results are recorded, and what "it worked" looks like.

---

## What Phase 1 actually is

**A dress rehearsal, not the experiment.** Nothing Phase 1 produces goes in the paper. Its only job is to prove the machinery works before we start paying for real measurements.

It's like calibrating a scale before weighing anything. If the scale is off, every weight you record afterward is garbage — and you won't find out until it's too late to fix.

**We deliberately don't care what the throughput number is in Phase 1.** If it reports 8 transactions per second, fine. The only question is: *did the machinery record what actually happened, accurately?*

---

## What gets deployed

Four things, in one cloud region.

**1. A small private blockchain.** We rent a handful of computers from Google and install Polygon Edge on each. They talk to each other and agree on a shared ledger — a real blockchain running real production software, that only we can use.

That last part is the whole point. On a public test network you share with strangers, so a slow result might just mean someone else was busy. On ours, every delay we measure is genuinely ours.

**2. A fake digital dollar.** A small program deployed onto that blockchain that behaves like USDC — it can be held and sent, one token equals one dollar. We invented it, but it works identically to real stablecoins, which is what matters for measuring cost.

Why a stablecoin rather than the blockchain's own coin: real remittances move dollars, not crypto. And sending a stablecoin costs about **three times** as much as sending the native coin. Measure the wrong one and we'd understate the true cost of a remittance threefold.

**3. A stack of test wallets, pre-loaded with money.** Many wallets, not one — see "what will probably go wrong" below.

**4. One separate computer running the test program.** Not part of the blockchain. It's the thing sending payments and holding the stopwatch.

---

## What happens during a single test run

**Step 1 — Write the script in advance.**
Before anything sends, the program generates a complete list of exactly when each payment should fire: payment #1 at 0.03 seconds, #2 at 0.11 seconds, and so on.

The spacing is **random, not even**. Real people send money at random moments; they don't take turns on a metronome. Evenly-spaced traffic is unrealistically easy on a system because the pile-ups that break things never happen. Random spacing produces natural clumps.

Writing the script in advance also means a run can be replayed with the identical traffic pattern. So if two runs differ, it's the blockchain that differed — not the traffic we happened to generate.

**Step 2 — Start the clock and fire.**
The program sends each payment at its appointed moment.

**It does not wait for one payment to finish before sending the next.** If it did, we'd be measuring how long a single payment takes, over and over — a completely different and much easier question than "how much can this handle at once." Real load means many payments in flight simultaneously.

**Step 3 — Watch each payment separately.**
Every payment gets its own watcher. When the blockchain confirms it, we record that exact moment. The gap between "sent" and "confirmed" is the **settlement latency** — the number that matters most for remittances.

**Step 4 — Give up at 60 seconds.**
Anything unconfirmed by then is recorded as failed. Sixty seconds is roughly ten times longer than this blockchain should ever need; past that, a remittance has failed in any sense a real person would care about.

**Step 5 — Take a pulse every second.**
Once per second we snapshot: how many sent, confirmed, failed, and still waiting.

---

## How results are recorded

**One database file.** Think of it as an extremely reliable spreadsheet that can be queried. Four tables:

| Table | One row per… | What it holds |
|---|---|---|
| `runs` | test run | Settings used — payment size, target rate, duration, random seed |
| `transactions` | **individual payment** | The important one — see below |
| `samples` | second of each run | The per-second pulse |
| `node_events` | node going up or down | For correlating crashes against slowdowns |

**The `transactions` table is the real asset.** For every single payment: when it was *supposed* to send, when it *actually* sent, when it confirmed, whether it worked, how much gas it burned, and the error text if it failed.

**Why store every payment instead of just averages:** if we saved only "average settlement was 3.2 seconds," and three months later you want to know "what did the worst 5% look like?", you'd have to re-run everything — and re-running costs money. Storing every payment makes future questions free. Cluster time is the scarcest resource in this project, so this is the cheapest insurance available.

**Timestamps are stored as offsets from run start, not clock times.** Computers periodically correct their clocks against the internet, and if that correction lands mid-run, a latency measured across it would be silently wrong. Offsets from a steadily-counting internal timer can't be affected by that.

---

## What you'll actually see

A printed summary in the terminal. Real output from the harness test run on 7 Aug 2026:

```
[null-baseline-usd200-tps25-r0] 241 tx scheduled @ 25 TPS over 10s
[null-baseline-usd200-tps25-r0] send window closed, draining 13 in flight...
[null-baseline-usd200-tps25-r0] offered=25 achieved=24.1 TPS | ok=241 fail=0
[null-baseline-usd200-tps25-r0] lag mean=0.9ms p95=1.3ms -- generator kept up
```

Reading it:

- **offered** — how fast we tried to send
- **achieved** — how fast it actually completed
- **ok / fail** — successes and failures
- **lag** — whether our own program kept up (see below)

**The gap between offered and achieved is the entire project.** At low rates they're nearly identical. Push harder and achieved stops keeping up, then falls behind badly. The point where that begins is the **knee** — and finding the knee for each of the three architectures *is* the paper's contribution. Not one number: a curve.

Charts come in Phase 6. Phase 1 produces no graphics.

---

## The self-check that keeps us honest

Here's a trap that would quietly ruin the whole study.

Suppose at 200 payments per second the numbers flatten out. The natural conclusion is that the blockchain hit its limit. But it might be that **our own test program** couldn't send any faster. Identical-looking result, completely different meaning — one is a finding, the other is a bug we published.

So the program checks itself. It compares when each payment was *supposed* to fire against when it *actually* fired. If it starts running late, the bottleneck is us, not the blockchain.

If a run trips this check, it **marks itself invalid automatically** rather than quietly handing over a bad number. The 7 Aug test showed 1.3ms of lag — essentially perfect.

---

## What "Phase 1 worked" means

1. One command brings the blockchain up
2. The token deploys and wallets get funded
3. A five-minute run at a slow rate completes without crashing
4. The database holds one row per payment, with sensible timestamps
5. Numbers look plausible — a couple of seconds to settle, nearly everything succeeding
6. **The auto-shutdown fires.** Non-negotiable: GCP budget alerts only send email, they do not stop spending
7. We learn the real hourly cost

**Expected cost: $3–5.** A few small machines for a few hours.

---

## What will probably go wrong (already designed around)

**Wallet collisions.** Every wallet numbers its payments in strict order — 1, 2, 3. Fire fifty at once from a single wallet and they collide and jam. This looks *exactly* like the blockchain struggling, which would be a fake result. That's why we use a pool of wallets rather than one.

**Quota errors.** Google caps how many machines an account may run. That's what the quota increase requests are for — including the separate "Preemptible CPUs" quota, which is easy to miss and only fails later.

**Chip mismatch.** Angad's Mac uses a different processor type than Google's servers, so anything built locally may need rebuilding for the cloud. This is a large part of why Phase 1 runs in the cloud rather than on the laptop.

---

## Status

- **Harness core: built and verified, 7 Aug 2026.** Arrival generation, concurrent submission, timing, failure accounting, and the saturation self-check all pass end-to-end against a synthetic backend. No cloud spend involved.
- **Not yet built:** Polygon adapter, the test stablecoin contract, the wallet-funding script, and the OpenTofu infrastructure definitions.
