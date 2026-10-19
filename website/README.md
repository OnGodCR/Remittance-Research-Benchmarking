# Website

A public, plain-language companion to the study, in three parts:

1. **The study:** the question, why we built our own networks, the realism layers, how a test works, the cleaning rules and what we found.
2. **Results:** throughput, failures and waiting time for Polygon Edge and NEAR at every measured load, with 95% ranges, plus cost per payment and the published Lightning reliability figures.
3. **Replay a test:** re-draws a five-minute test from payments we actually recorded. It is not a live blockchain and never guesses at conditions we did not measure.

It is a static site with no build step and no server code. Everything runs in the visitor's browser.

| File | What it is |
|---|---|
| `index.html` | Page structure and all the written content |
| `style.css` | Layout and colours (light and dark) |
| `app.js` | Charts, results explorer and replay tool |
| `data/results.json` | The ~0.7 MB summary the page loads |
| `build_data.py` | Builds `results.json` from the study's cleaned data |

## Rebuilding the data file

Run from the repository root:

```bash
gcp-research/.venv/bin/python website/build_data.py
```

It reads `gcp-research/data/clean/all_runs_clean.parquet` (and the 20 NEAR 300/sec tests from the raw data, marked as extra data). It computes every figure by importing `gcp-research/analysis/results.py`, the same code behind the paper's tables. **It refuses to write the file unless the paper's headline figures reproduce exactly.**

## Previewing locally

The page loads its data with a web request, so it must be served rather than opened straight from disk:

```bash
python3 -m http.server 8791 --directory website
```

Then open http://localhost:8791.

## How the replay tool samples

- **Whole runs (cluster sampling, the default):** pick one recorded test at random, then draw payments from inside it. This keeps the test-to-test variation, which is the honest uncertainty. Replaying the five-test study 1,000 times reproduces the paper's 95% ranges.
- **Individual payments (simple random sampling):** draw every payment independently from all tests pooled together. This gives ranges 18 to 120 times narrower. It is shown on purpose, to demonstrate why that method overstates certainty.

What a replay keeps from each recorded test: its payment count, its failure rate, its settlement-time distribution (201 points) and a 5-second timeline. Success counts use a normal approximation to a binomial draw, which is far finer than the test-to-test differences shown.

## Publishing

Not published yet. That is Angad's call, ideally once the paper is submitted, because publishing makes the results public.

The simplest host is **GitHub Pages**. Pages can only serve a repository's root or `/docs` folder directly, so `website/` needs either a small GitHub Actions workflow that publishes it, or a copy in a separate public repository. Pages on a **private** repository needs GitHub Pro, which the GitHub Student Developer Pack includes.
