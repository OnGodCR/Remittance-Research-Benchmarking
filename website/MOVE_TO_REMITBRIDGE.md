# Moving the benchmark website onto remitbridgelabs.org

**Written 19 Oct 2026.** This is a handoff for a Claude Code session working in the **RemitBridge website repository** (`~/Documents/GitHub/RemitBridge-System-Labs---Website`). Its job is to rebuild this folder's three-part site as a page of that site, then retire this folder.

**How Angad starts it:** open a Claude Code session in the RemitBridge website folder and say:

> Read `~/Documents/GitHub/Remittance-Research-Benchmarking/website/MOVE_TO_REMITBRIDGE.md` and do the move it describes. Ask me the decisions in §1 first.

That repository's own `CLAUDE.md` and `HANDOFF.md` govern how the work is done there: tone, house style, commit rules, verification. Read both before starting. Where this file and those disagree on *how*, they win. This file only says *what* to move and which caveats must survive the move.

---

## 0. What is being moved

The finished study (Polygon Edge, NEAR and Lightning tested as remittance rails, Aug 2026) and a three-part companion site built for it:

| Part | What it shows |
|---|---|
| **The study** | Seven short chapters: the question; why private networks; the four regions and realism layers; how one test works; cleaning rules written before the data; what we found; what this cannot tell you |
| **Results** | Settled-per-second, failure rate and slow-end waiting time against offered load, for Polygon and NEAR, with 95% ranges; filters for amount and normal vs one-computer-failing; a table view; cost per payment; Lightning success rates from the published study |
| **Replay a test** | Re-draws a five-minute test from payments actually recorded, by whole runs (cluster sampling, default) or individual payments (simple random sampling); animates the timeline; "replay the study 1,000 times" shows both methods against the paper's 95% range |

Source files, all in `~/Documents/GitHub/Remittance-Research-Benchmarking/website/`:

| File | Role in the move |
|---|---|
| `index.html` | **All the written copy.** Port the text; drop the markup. |
| `app.js` | Chart drawing, explorer, replay. **The sampling functions port as-is**; the DOM code is rewritten as React. |
| `style.css` | Reference only. The RemitBridge site's own Tailwind tokens replace it. |
| `data/results.json` | The 0.72 MB data file. **Copied, never edited by hand.** |
| `build_data.py` | Stays in the research repo. It makes `results.json` and refuses to write it unless the paper's figures reproduce. |
| `README.md` | Explains the sampling method in more detail. |

---

## 1. Decisions only Angad can make (ask these first)

Nothing gets built until these four are answered.

**1. Which address does the study live at?**
- **Recommended: replace the placeholder at `/remitbench`.** That page already promises "when there are real numbers, they will appear here with the code and the runs behind them", so this keeps that promise. The address is already in Google's index, and nothing links break.
- Alternative: a new page, freeing the RemitBench name for the provider-comparison tool.

This *is* open decision 3 in RemitBridge `HANDOFF.md` §9 ("The testbed. Move it to its own page, keep the RemitBench name on it, or..."). Whatever Angad picks, update §9 and the open items in that repo's `CLAUDE.md` to say it is settled.

**2. When does it go public?**
`/papers` says a paper goes up "once it has been through the team and then the adult advisory group". Putting the results on the live site before that review would go around that rule.
- **Recommended: build it on a branch now and merge to `main` (which deploys) only when Angad says the paper has cleared review.** Vercel gives the branch a private preview URL to show his dad or the advisory group.

**3. Does the full dataset get a public download?**
`results.json` is a summary of each test, not every payment. The paper's methods promise the data and code are published alongside it. The full data is ~3 GB and lives in the research repo (currently private). Options: link the research repo once it is made public, upload the cleaned dataset to a data archive (Zenodo gives a citable DOI, free), or ship the summary only.
- **Recommended: Zenodo for the cleaned dataset when the paper is submitted. The page links it and says plainly until then that the data is not yet public.**

**4. What happens to the old placeholder content?**
The current `/remitbench` page has a "How the setups compare" table taken from published vendor specifications. It claims sharding 2,500 to 10,000+ TPS and sidechains 1,500 to 5,000. **Our measurements contradict it**: Polygon Edge sustained 200/sec and NEAR 150/sec. It also has "The six tests" tabs (500 to 10,000 TPS targets) describing a plan that was never run in that form.
- **Recommended: delete both.** Leaving vendor claims beside our own measurement invites exactly the misreading the site argues against. If Angad wants to keep the vendor table as context, it must say in its heading that these are the makers' claims and that our measurements came out far lower.

---

## 2. Where everything goes

| From (research repo) | To (RemitBridge repo) |
|---|---|
| `website/data/results.json` | `public/data/remitbench/results.json`. Fetched at runtime like `public/data/rpw`, never imported into the bundle. |
| Story copy in `index.html` | The page component, as JSX prose |
| `app.js` sampling functions | `src/lib/replay.js`, pure functions, no DOM: `gauss`, `binom`, `pick`, `okRate`, `drawLatency`, `pctl`, `oneTest`, plus a `replayStudy(runs, method, n=1000, reps=5)` extracted from `replayMany` |
| `app.js` charts | `src/components/remitbench/`: `LoadChart.jsx` (also used for the failure chart), `TimelineChart.jsx`, `ReplayHistogram.jsx`, `LightningChart.jsx`, `RegionMap.jsx` |
| `app.js` explorer and replay UI | `src/components/remitbench/ResultsExplorer.jsx`, `Replay.jsx` |
| Constants `LN_SUCCESS`, `COST`, `COST_LIMIT` | `src/data/figures.js`, with sources (see §4). Not inline constants. |
| `cellNotes()` caveat text | `src/data/remitbenchNotes.js`, one entry per caveat, so the wording lives in one place |

Then wire it up the way that repo always does:
- **`src/App.jsx` and `src/routes.js`.** Both must change if the address changes; nothing changes if it stays `/remitbench`.
- **`src/routes.js`.** Update the `/coming-soon` blurb, which says "including RemitBench". Add the page to a nav group so it appears in the header, footer and home index. "Reading" or a new "Research" group are the natural places; ask Angad which.
- **`src/lib/seo.js`.** New title and description for the page. This is the only place search metadata is edited.
- **`src/pages/ComingSoon.jsx`.** It links to RemitBench as an unfinished design. Reword it, since the study is now finished.
- **`src/data/researchPapers.js`.** If the paper's entry describes the study, link it to the page.

---

## 3. Rules from the RemitBridge repo that the port must follow

These come from that repo's `CLAUDE.md`. The standalone site breaks several of them, so each needs a deliberate fix.

| Rule there | What it means for this port |
|---|---|
| **Every component renders without a window** (prerendered with `renderToString`, then hydrated) | `fetch` the JSON in a `useEffect`, rendering a "Loading the recorded tests" state first. `Math.random` only inside click handlers. Read `matchMedia('(prefers-reduced-motion)')` in an effect. Charts render at a fixed default width on the server, then measure their container with a `ResizeObserver` in an effect. **A `hydration:` line in the console means a rule was broken.** |
| **No pill labels** | The "recommended" tag on the sampling card is a pill. Use small caps plus a filled dot instead. |
| **No em-dashes in site copy** | The standalone copy has them in the region map ("US — largest sender") and a few sentences. Replace them. En-dashes in number ranges (199.7–201.9) are fine. |
| **Colour alternates white and mint by section; no third accent colour** | Section backgrounds follow that rule. The three networks still need three chart colours. Take them from the series colours in the site's `palette.js` (the `ink`/`bar` keys) rather than inventing new ones. If no three are distinguishable for colour-blind readers, ask Angad before adding any. |
| **House style: no semicolons, single quotes; never run Prettier across the repo** | Port by hand, in that style. |
| **Every statistic is in `figures.js` with a source and `usedOn`** | See §4. This is the biggest piece of work in the move. |
| **Comments explain why, not what** | Keep the "why" comments from `app.js` (normal approximation, quantile drawing, why cluster sampling). |
| **Branch before pushing anything experimental** | Work on a branch until decision 2 says merge. |

---

## 4. Every number needs a source in `figures.js`

The RemitBridge site's sources page renders every figure with where it came from. The study's numbers are the lab's **own measurements**, a different kind of claim from a looked-up figure, and `figures.js` already marks the lab's own work as `derived`. Follow that convention and add:

**One source entry for the study itself:** RemitBridge Labs blockchain remittance benchmark, Aug 2026, with the cleaned-data file name and the commit that built `results.json`. Use the Zenodo DOI once decision 3 produces one.

**One source entry for Waugh & Holz:** Waugh, F. & Holz, R. (2020), *An empirical study of availability and reliability properties of the Bitcoin Lightning Network*, arXiv:2006.14358, https://arxiv.org/abs/2006.14358.

**Figures to register**, each with `usedOn: ['/remitbench']` (or the chosen address):

| Figure | Value | Source |
|---|---|---|
| Polygon Edge sustained at $200 | 200/sec (200.9 settled, 0.00% failed, p95 4.77 s) | study |
| NEAR sustained at $200 | 150/sec (150.1 settled, 0.15% failed, p95 19.20 s) | study |
| NEAR at 200/sec | 47.5/sec, 76.3% failed (**on hold**, see §5) | study |
| NEAR at 300/sec | 9.9/sec, 96.69% failed (**rule-excluded, marked extra data**) | study |
| Polygon at 300/sec | 270.5/sec, 9.97% failed (**later re-described**, see §5) | study |
| Polygon follow-up past 300 | 290.5 / 202.5 / 108.3 / 96.5 at 300/400/500/600, exploratory, one test each | study |
| Node failures, capacity lost | Polygon 26% at 200/sec; NEAR 76% at 150/sec (arms **not equally harsh**) | study |
| Cost per payment | NEAR $0.000365, Polygon $0.0006 at every amount; Lightning $0.0032 / $0.0134* / $0.0523 / $0.1467 at $10/$50/$200/$500 | study (*$50 Lightning assumed route length, never run) |
| Lightning success by size | 71.9% ($0.01), 57.8% ($1), 44.1% ($5), 44.2% ($10), 30.9% ($50), 17.3% ($100); node reachability 35.2 / 35.2 / 25.7 / 33.7 / 9.2 / 4.8% | Waugh & Holz |
| Lightning test network vs real | about 620 times fewer channels (51 vs ~31.4–31.8k) | study + Waugh & Holz |
| Tests | 610 recorded, 293 kept, 20 shown as marked extra data; 9.6 million payments kept | study |
| Spend | about $124 of a $300 cloud credit | study |
| NEAR block timer | ran at 2 s (default 0.6 s); preliminary 1.2 s test cut median wait 12.20 s to 7.18 s, **one to two surviving tests only** | study |
| Remittance volume | ~$905B a year, about 150 payments a second at $200 | Check `figures.js` first. It probably already has a World Bank/KNOMAD flows figure. **Reuse that one and its source rather than adding a second**, and if the two disagree, flag it to Angad. |

Every number above was checked against the cleaned data on 19 Oct 2026 by `build_data.py` and `gcp-research/analysis/results.py`. **Do not round differently from these.** The research repo's `gcp-research/COMPARISON.md` is the master table, and its §9 says where each number comes from.

---

## 5. Caveats that must travel with their numbers

These are not optional decoration. Each one corresponds to a withdrawn or conditional finding in the paper (`gcp-research/ANALYSIS_PLAN.md` §13 amendments). Whenever its number appears (chart point, tooltip, table row, replay result), the caveat appears beside it. Copy the wording from `cellNotes()` in `app.js`, removing em-dashes.

1. **NEAR at 200/sec and above is under re-check.** Part of the collapse may be our own program, which checks each waiting payment one by one over the network. The 150/sec result is unaffected.
2. **NEAR at 300/sec is rule-excluded.** Our sending program fell slightly behind schedule. All 20 tests agree with each other, so it is shown as marked extra data: hollow marker, dashed line. It is never mixed with clean results.
3. **Polygon at 300/sec was later found to be partly our setup.** Every settlement check went to one computer. Spread over four, it reached 290.5 and then fell: 202.5 at 400 and 96.5 at 600. **The old "Polygon degrades gracefully, NEAR collapses" framing is withdrawn.** Both collapse; NEAR's collapse is about five times steeper. Never write "graceful".
4. **The failing-computer tests are not equally harsh.** Switching off one of NEAR's 8 computers left one of its lanes with a single computer, the minimum allowed, and NEAR shut the failed computer out for about four hours. Polygon kept 3 of its 4. Both tests are far harsher than the real networks.
5. **NEAR's waiting times are at a 2-second block timer**, needed to span four continents. The pre-set 10-second rule disqualifies NEAR only at that setting.
6. **Lightning cannot be replayed or ranked.** Its reliability comes from the published study, because our test network was ~620 times smaller than the real one. In the replay tool it is a disabled option with that reason as its tooltip.
7. **Missing tests:** NEAR at 200/sec had only 4 of 5 tests survive cleaning at $10 and at $200. Say so wherever those cells show.
8. **Untested combinations are disabled, never guessed.** The replay tool greys out load levels that were not measured.
9. **Lightning moves bitcoin, not a stablecoin**, so it carries exchange-rate risk the other two don't.
10. **Scope:** best-case estimates from controlled, partly realistic networks. Only the settlement step was tested, not converting cash at each end. SWIFT interoperability is design only, nothing was built. NEAR ran 4 lanes with 2 computers each. Polygon Edge was frozen by its makers in Dec 2024.

**Also remove:** the old placeholder's claim that the testbed "has not produced results we are willing to publish". Once decision 2 is met, that stops being true.

---

## 6. Checks before calling it done

The RemitBridge repo's rule is that nothing ships on "the build passed". Specifically:

1. **`npm test` with new tests for `src/lib/replay.js`:**
   - With a fixed random seed (inject a seeded generator; do not monkey-patch `Math.random` globally), replaying the five-test study 1,000 times by whole runs lands the middle 95% within 15% of the paper's 95% range, for at least these cells: Polygon $200 at 200 and 300; NEAR $200 at 150 and 200; both failing-computer arms at their knee. (Checked by hand on 19 Oct 2026: all matched.)
   - Simple random sampling gives a narrower range than whole runs in every cell with more than one test.
   - `binom(n, 0)` is 0 and `binom(n, 1)` is n.
2. **`npm run build`, then `vite preview`.** Open the page **with the trailing slash** (`/remitbench/`), because preview serves the SPA fallback without it. **The console must be clean: no `hydration:` lines.**
3. **Drive it in the browser and read state back out of the DOM.** Every filter combination renders. Each caveat in §5 appears where its number does. "Replay one test" and "Replay 1,000 times" both produce output. Lightning is disabled with its tooltip.
4. **Check 320px width for sideways scrolling** on every new section.
5. **Read `dist/remitbench/index.html` directly** and confirm the story text is in it. That proves the prerender wrote the body, so crawlers see it.
6. **Sources page:** every figure in §4 appears there with `/remitbench` in its places used.

---

## 7. After it is live

In the **research** repository, once Angad confirms the new page is live:
- Delete `website/index.html`, `app.js` and `style.css`. Keep `build_data.py` and `data/results.json`: the research repo stays the one place the data file is built from. Update `website/README.md` to say the page now lives on remitbridgelabs.org and that the JSON is copied there after each rebuild.
- Update the root `README.md` table to match.

**Rebuilding later:** if the study's data ever changes, run this in the research repo:

```bash
gcp-research/.venv/bin/python website/build_data.py
```

Then copy the new `website/data/results.json` over `public/data/remitbench/results.json` in the RemitBridge repo, and commit both.

---

## 8. Known state of the research repo at handoff

- **The local cleaned data file is newer than the copy on GitHub.** The 19 Aug version is local; GitHub has the 13 Aug one. The local one is correct: it matches the committed exclusions log and reproduces every published figure. It is uncommitted because it would add ~700 MB of large-file storage. `results.json` was built from the local one.
- **Disk space on Angad's Mac is tight** (it ran out completely on 19 Oct 2026; ~5 GB free after a cleanup). If it runs short again, `gcp-research/data/raw/all_runs_raw.parquet` (2.6 GB, untracked) can be deleted safely; it is rebuilt from `data/raw/parts/` by `analysis/rebuild_raw.py`. `build_data.py` reads `parts/raw-near.parquet`, not the combined file, so it still works without it.
