# Blockchain Remittance Scaling Architecture Benchmarking

Measuring how three blockchain scaling architectures — a sidechain (Polygon Edge), an off-chain payment network (Lightning) and a sharded chain (NEAR) — perform as remittance rails: throughput, settlement time and cost, under realistic load.

The repository has two parts.

| Folder | What is in it |
|---|---|
| [`gcp-research/`](gcp-research/) | The study itself: the measurement program, the cloud infrastructure it ran on (Google Cloud), every decision and amendment, and the collected data. **Start at [`gcp-research/README.md`](gcp-research/README.md)**, then `RESUME_HERE.md`. |
| [`website/`](website/) | A public website that walks through the study from start to finish, lets visitors explore the results, and replays tests by re-drawing from the payments we actually recorded. It runs entirely in the browser and never contacts a blockchain. |

Commands in `gcp-research/README.md` are run from inside `gcp-research/`.
