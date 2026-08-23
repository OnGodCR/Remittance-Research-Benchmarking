# What the capacity test proves — and the claim it can no longer carry

**Written:** 12 August 2026
**Corrected:** 23 August 2026 — see the banner below. The original title was
"The 150/sec ceiling is NEAR's, not our tooling's — the evidence". That title
claimed more than the test shows, and the document now says precisely what is
and is not established.
**Use this when:** stating NEAR's sustainable throughput, and answering the
first question a reviewer will ask about any measured ceiling.

---

> ## ⚠️ CORRECTION, 23 August 2026
>
> The test below validates the **scheduler** — the part of our program that
> creates and times payments. It does **not** validate the **watcher** — the
> part that repeatedly asks the chain whether each payment has finished.
>
> Why not: the fake backend used for the test answers "is it done?" by
> sleeping. **It makes no network calls at all** (`harness/adapters/null.py`,
> `await_confirmation`). But the real NEAR adapter asks the network about
> every waiting payment five times a second, each ask a real network request.
> At 300 payments/second with settlement stretched to ~50 seconds, that is
> roughly 15,000 waiting payments × 5 asks = **~75,000 network requests per
> second issued by our own program** — precisely the load the fake backend
> reproduces as zero.
>
> Our own Polygon adapter's header warned about exactly this figure, in
> writing, as the load that "would collapse the harness long before the
> chain" (`harness/adapters/polygon.py`, file header). The test therefore
> rules out the scheduler as the ceiling and **cannot rule out the watcher**.
>
> Section 5's original explanation of the observed lag — "a slow RPC response
> holds up the send path" — was also wrong as a mechanism: `submit()` hands
> the actual network send to a background task and never waits on the RPC
> (`harness/adapters/near.py`, `submit`). The plausible coupling is different:
> thousands of per-payment asking loops share one program, one connection
> pool and one core scheduler with the sender, and their work grows with the
> number of payments waiting. Polygon's watcher reads whole blocks — its
> client-side work stays flat as payments pile up. NEAR's grows.
>
> **What this means for the published numbers, stated carefully:**
>
> - **The 150/sec headline survives on its own evidence.** Its runs passed
>   the pre-registered lag rule with wide margin, and the 22 Aug rebuilt
>   cluster reproduces the 100/sec cell exactly (99.9/sec both arms, inside
>   the published band). Nothing here disturbs it.
> - **The character of the 200–300/sec cells is now an open question.** The
>   measured "collapse" is real data, but how much of it is the chain
>   failing to finalise and how much is our watcher failing to *observe*
>   finality under its own load cannot be separated from this test. The
>   22 rule-excluded cells (20 at 300/sec, 2 at 200/sec) were excluded by a
>   rule whose input — scheduling lag — the watcher's load inflates on NEAR
>   and not on Polygon (after the multi-process fix, no Polygon run in the
>   published ramp was excluded by it).
> - The separation is being measured directly: the 22 Aug endpoint
>   experiment (`ANALYSIS_PLAN.md` §13, amendment 15) and its follow-ups.
>   Until that lands, the paper must not assert that the 200/sec collapse
>   is a property of NEAR.
>
> A per-architecture watcher is not itself a flaw — each chain is watched
> the way that chain is watched in practice, which is the equitable choice.
> The flaw was claiming a test that removes the watcher's work validates a
> conclusion that depends on it.

---

## 1. Why this document has to exist

`claude.md` §8 is explicit: *"Validate generator capacity first, against a null
endpoint. Without this we cannot claim an observed throughput ceiling belongs to
the blockchain rather than to our own tooling — and at 300 TPS that's a live
risk."*

The risk became concrete. At 200/sec the NEAR runs reported growing scheduling
lag — the sender drifting behind its own timetable — and one of five repeats
crossed the pre-registered 50 ms exclusion threshold. Growing lag is exactly
what a saturated generator looks like. If it *was* our sender, then "NEAR tops
out between 150 and 200/sec" is not a finding about NEAR at all.

## 2. The test

`harness.cli capacity` runs the full load ramp against a **null backend** that
does nothing but wait. Any limit that appears is ours by construction.

**The setting that matters is `--settle-delay`.** It fixes how long the fake
backend takes to "settle", and therefore how many payments the harness is
tracking at once — which is the load that actually stresses it. In-flight count
is roughly `rate × settlement time`, so the delay must match the chain being
measured or the test is too easy.

**The first run got this wrong.** It used 11 seconds, NEAR's settlement at low
load. But at 200/sec NEAR's settlement had risen to 47–67 seconds, so the real
in-flight backlog was 4–6× what the test reproduced. That first result — "300/sec
is fine" — was not evidence for the condition in question, and was re-run.

**The second run still reproduced only half the condition.** It matched the
*number* of payments tracked at once. It did not — could not, with a backend
that never touches the network — reproduce the *asking work* those payments
create on NEAR. See the correction banner: this is the gap the original
version of this document missed.

## 3. Results

Both runs pinned to spare cores and writing to a separate database, so the live
measurements were untouched.

| Offered | Achieved (11s settle) | p95 lag | Achieved (**50s settle**) | p95 lag |
|---|---|---|---|---|
| 10/sec | 9.3 | 1.8 ms | 9.3 | 2.0 ms |
| 50/sec | 49.1 | 1.8 ms | 49.1 | 1.9 ms |
| 100/sec | 99.3 | 1.6 ms | 99.3 | 1.8 ms |
| 150/sec | 148.8 | 1.2 ms | 148.8 | 1.6 ms |
| 200/sec | 199.4 | 1.2 ms | **199.4** | **1.4 ms** |
| 300/sec | 298.6 | 1.1 ms | **298.6** | **1.2 ms** |

At 300/sec with a 50-second settlement the harness is tracking roughly **15,000
payments at once** — as many as the real chain ever imposed — and holds p95
scheduling lag at **1.2 ms**.

## 4. What follows — the corrected version

**The scheduler is not the ceiling at any load level in the pre-registered
ramp.** Creating, timing and tracking 15,000 concurrent payments costs the
program almost nothing when checking them costs nothing.

What does NOT follow is the original conclusion that "the degradation measured
at 200/sec is the chain's, not ours". The degradation at 200/sec was observed
through a watcher doing tens of thousands of network requests per second of
its own, and this test is silent about that watcher. The honest statement:

| Claim | Status |
|---|---|
| The sender can schedule 300/sec | **Proven** (this test) |
| NEAR sustains 150/sec | **Proven** (measured, rule-clean, reproduced on the rebuilt cluster) |
| The 200–300/sec collapse belongs to NEAR | **Open** — under direct test since 22 Aug |

## 5. Then why did the real runs show growing lag?

Two candidate mechanisms, and this test distinguishes neither:

1. **The chain's congestion, reflected honestly.** Settlement stretched from
   ~12s to ~50–67s, multiplying the number of payments our program had to
   track. If the chain had settled promptly, the watcher's load would never
   have grown.
2. **Our watcher's own weight.** Each waiting payment runs an asking loop;
   at 200/sec+ those loops number in the thousands and share the program
   with the sender. Their cost lands on the same clock the exclusion rule
   reads.

These are not exclusive — the first causes the second. The point is that the
lag cannot be read as a pure symptom of the chain, because part of it is
manufactured inside our own process, and only on NEAR, whose watcher works
per payment rather than per block.

## 6. What was done about the run that crossed the threshold

**Nothing — the rule was applied as written.** Lag growth across the five
200/sec repeats was +39.6, +41.1, **+54.3**, +38.6 and +29.7 ms. The third
crosses the pre-registered 50 ms threshold (`ANALYSIS_PLAN.md` §13, amendment 1)
and is excluded. Four valid repeats remain at that load.

The rule's own justification is that the *offered* arrival pattern drifted from
the intended Poisson process, and it did drift, whatever the cause. Keeping the
run because a separate test suggests the cause was external would be relaxing a
pre-registered criterion after seeing which run it removes. The interpretation
belongs in this document; the data handling stays mechanical.

## 7. The sentence this licenses in the paper — narrowed

The original version of this section licensed:

> *"…the observed ceiling is a property of the network under test rather than
> of the instrument."*

**That sentence can no longer be written.** What the evidence supports is:

> NEAR's sustainable throughput was measured at 150 payments/second under the
> full realism stack. The measurement program's scheduling core was
> independently validated to sustain 300 payments/second (p95 scheduling lag
> 1.2 ms against a null backend tracking an equivalent number of in-flight
> payments). Settlement observation on NEAR is per-payment, so at loads past
> the measured ceiling the instrument's own observation work grows with
> congestion; the attribution of the degradation seen at 200–300/sec is
> examined separately [endpoint experiment / amendment 15].

## 8. Reproducing

```bash
cd /opt/benchmark && ./.venv/bin/python -m harness.cli \
  --db /tmp/capacity50.sqlite capacity --window 60 --settle-delay 50
```

Runs under `phase='capacity-check'`, which is in `NON_RESULT_PHASES`, so these
runs can never leak into results. Set `--settle-delay` to the settlement time
observed **at the load being defended**, not at low load.

**A capacity test that would actually close the gap** — should anyone build
it — must make the fake backend answer "is it done?" over a real socket with
a realistic response time, so the watcher pays per-payment network cost. The
null backend cannot do this by design; it exists to isolate the scheduler,
and that is the only thing it isolates.
