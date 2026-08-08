# Resume Here — state as of 8 August 2026

Everything in the cloud is **destroyed**. Nothing is billing. Verified: 0 machines, 0 disks, 0 addresses, 0 of 32 processors in use.

---

## Where Phase 1 got to

**Phase 1 substantially succeeded.** The full pipeline was proven end to end on real cloud infrastructure:

- 4-validator Polygon Edge cluster deployed and reached consensus
- Chain produced blocks continuously
- Test dollar contract deployed (524,778 gas)
- 46 sender wallets funded
- Benchmark ran against the live chain: **308 payments, 0 failures, 5.1 achieved vs 5 offered**

That last line is the thing Phase 1 existed to prove: the machinery deploys, submits, measures, and records correctly against a real blockchain.

---

## The one unresolved issue

**The load generator was saturated at just 5 payments/second** — 204ms average scheduling lag, which auto-flagged the run invalid.

This is **not** a harness limit. The same code sustained 300/second at 1.1ms lag against a local target. The cause is that the benchmark was run **from the laptop over the public internet**, so every submission paid a transatlantic round trip.

**Fix, for the first thing to do on resuming:** run the harness on the `bench-p1-generator` machine, which sits in the same region as the validators. That was always the design — Phase 1 just skipped it because the generator machine only gets prepared by its startup script, and the harness itself was never copied onto it.

Concretely, `generator_setup.sh` ends with "Next: copy the harness to /opt/benchmark and create its virtualenv." That step needs writing and adding to the bootstrap.

Until that is done, **no throughput number from this project is trustworthy**, because the harness would be the bottleneck rather than the chain.

---

## Five real bugs found and fixed

Each would have cost hours or produced wrong data. All fixes are committed.

1. **macOS ships bash 3.2** (2007), which lacks `mapfile`. Bootstrap script rewritten to be portable.
2. **`--tunnel-through-iap=false` is invalid** — it is a switch, not a key=value flag. gcloud rejected every remote command, and because failures were swallowed the script just looped "not ready yet" until timeout. Ten minutes of billing for nothing.
3. **Polygon Edge v1.3.2 flags differ from the documentation.** `--ibft-validator` does not exist; it is `--validators`, and with the default BLS validator type each entry is `<address>:<BLS key>`. There is no `--force` flag. Genesis must also run from a directory the `edge` user can read, or it fails with a misleading "failed to read from prefix" error.
4. **Genesis file is written 0660 owned by `edge`**, so copying it to the other validators returned an empty file. Needs `sudo cat`.
5. **The contract would not deploy.** Solidity 0.8.20+ targets the Shanghai instruction set (April 2023), which includes PUSH0. Polygon Edge v1.3.2 predates it. The failure is deceptive: the transaction is accepted, mined, and reverts having consumed *exactly* the full gas limit. Fixed by compiling with `evm_version="london"`.

## The most dangerous bug of all

6. **Proof-of-authority block headers broke settlement detection entirely.** Polygon Edge stores validator signatures in each block's `extraData`, making it far longer than Ethereum's 32-byte limit. web3 rejected every block as malformed, so no settlement was ever detected, every payment timed out at 60 seconds, and the run reported **100% failure**.

This one matters beyond the fix. "The architecture failed every single transaction" is a perfectly plausible-sounding result that would have gone straight into the paper. It was our client refusing to read the blocks. Fixed by injecting `ExtraDataToPOAMiddleware`.

**This is the strongest argument for why Phase 1 exists**, and it is worth a sentence in the Methodology section.

---

## Cost

Roughly **$0.30–0.50 total** for the whole session — five small machines for about 90 minutes on spot pricing.

Google's billing reports on a 6–24 hour delay, so the console will still show $0 for a while. That is expected and is not evidence of anything.

Credit position: **$300, expires 6 November 2026.**

---

## Next session, in order

1. **Write the harness deployment step** — copy the code to the generator machine, create its virtualenv, and run benchmarks from there rather than from the laptop. Add it to `bootstrap_cluster.sh`.
2. **Re-run Phase 1 properly** from in-region. Confirm the generator is no longer the bottleneck, then run the real 300-second validation at 5/second.
3. **Record the real per-hour cost** once Google's billing catches up — that is the number for the budget conversation.
4. **Then Phase 2**: multi-region, injected latency, hardware matching, background traffic, adversarial nodes — one at a time, per `claude.md` §9.

## Before Phase 2, one thing needs requesting

The account's **global processor cap is 32**, which is what broke the first deployment. Phase 2 needs 7 validators at 8 processors plus a generator = **60**.

Request an increase of `CPUS_ALL_REGIONS` to at least 64. It is not instant, so do it early.

**Do not request "Preemptible CPUs" quota.** It currently reads 0, which means it has never been requested — and in that state spot machines fall back on the regular processor quota. Requesting it would lock spot machines into a separate, smaller bucket and make things worse.
