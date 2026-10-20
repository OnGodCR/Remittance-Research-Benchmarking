# Retiring the nine NEAR snapshots

**Written 19 Oct 2026. Do this before 6 Nov 2026**, when the $300 Google Cloud credit expires and the snapshots start billing the card.

## Why

The nine 13 Aug snapshots in `project-c4c87dcb-da41-4caf-922` are the last Google Cloud items still billing: ~373 GB in the `us` multi-region, **about $24/month**. Snapshots cannot be paused; they bill for as long as they exist.

## What is on them, and what deleting them loses

| Snapshot | Holds | Already kept elsewhere? |
|---|---|---|
| `snap-near-generator` (6 GB stored) | The program that sent the test payments, and its working folder, including **`validator_liveness.jsonl`**, the health log proving each published NEAR run had its full set of computers | **No.** This is what `scripts/rescue_generator_snapshot.sh` copies out. |
| `snap-near-validator-0` … `-7` (~46 GB each) | Each NEAR computer's copy of the chain, and its node logs | The original token contract is committed (`data/reference/contracts/`). Every payment's timings are in `data/raw` and `data/clean`. The chain databases themselves are not kept anywhere. |

**After deletion, the NEAR results can no longer be re-checked against the chain itself**, only against our own records of each payment and the health log. That is normal for a finished study, but say so in Limitations: *"the private chains were deleted after collection; per-payment records and the validator health log are retained."*

Moving the full images somewhere else was considered and rejected. Downloading 373 GB out of Google costs roughly $45 in transfer fees. It also needs far more disk than this laptop has. Free archives cap well below that size (Zenodo: 50 GB per record).

## Steps

**1. Rescue the health log.** About 15 minutes; it costs well under $0.10, from the credit:

```bash
./scripts/rescue_generator_snapshot.sh --dry-run
./scripts/rescue_generator_snapshot.sh
```

The first prints the plan and touches nothing. The second does it. It deletes its own temporary machine and disk on exit, and Google deletes the machine after 60 minutes regardless. It stops with **"do NOT delete the snapshots"** if the health log did not come back.

**2. Check what came back**, in `data/near_supplementary/rescued_generator_13aug/`:
- `rescued_logs.tar.gz` contains `data/working/validator_liveness.jsonl`. The script checks this.
- `manifest.tsv` lists every file that was on the generator, including ones not copied. Skim it for anything else worth keeping before step 4. A file not copied is gone after step 4.
- `validator_liveness.sha256` is the health log's fingerprint, taken on the machine.

**3. Commit and push that folder.** Ask Claude; it's data, so it stays in the repo. If the paper's dataset goes to Zenodo, include it there too.

**4. Delete the snapshots.** Irreversible, so Angad runs it himself:

```bash
gcloud compute snapshots delete snap-near-generator snap-near-validator-0 snap-near-validator-1 snap-near-validator-2 snap-near-validator-3 snap-near-validator-4 snap-near-validator-5 snap-near-validator-6 snap-near-validator-7 --project project-c4c87dcb-da41-4caf-922
```

It asks for confirmation before deleting.

**5. Confirm nothing is left:**

```bash
gcloud compute snapshots list --project project-c4c87dcb-da41-4caf-922
gcloud compute disks list --project project-c4c87dcb-da41-4caf-922
gcloud compute instances list --project project-c4c87dcb-da41-4caf-922
```

All three should print nothing. In the console, Billing → Reports should show snapshot storage falling to zero within a day or two.

**6. Check the Polygon project too.** `remittances-benchmarking` is under a different Google login: `angadkochar2@gmail.com` cannot list it. RESUME_HERE says its machines were destroyed on 24 Aug with no snapshots kept. Confirm in the console, signed in with the account that owns it, that it has no machines, disks or snapshots.

**7. Update the record.** Mark the snapshots deleted, with the date, in `RESUME_HERE.md` and `docs/spend_ledger.md`.
