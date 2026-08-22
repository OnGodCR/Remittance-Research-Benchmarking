# The raw dataset

`all_runs_raw.parquet` is the canonical raw file: every payment from every run,
nothing removed, invalidated runs included and flagged. It is **not stored in
the repository directly** — GitHub hard-rejects any single large-file-storage
object over 2 GiB, and this file passed that at 610 runs and 24.6 million
payments. It is not a quota that can be raised.

It is stored **split across `parts/` instead**, and rebuilt on demand:

```bash
.venv/bin/python -m analysis.rebuild_raw
```

That writes `all_runs_raw.parquet` back, and every script that expects the one
canonical file keeps working unchanged.

To go the other way after new runs are exported:

```bash
.venv/bin/python -m analysis.split_raw
```

## Nothing was removed

Every row of the raw file is in exactly one part, and the split refuses to
finish if the counts do not add up. `parts/manifest.csv` lists which
architecture and phase live in which part, with row counts, so a reviewer can
check the arithmetic without opening a single data file.

Downsampling was never an option. The point of keeping raw beside clean is
that a reviewer can see the untouched data and verify that nothing inconvenient
was quietly dropped.

## Why the parts are split the way they are

By architecture first, because that is how people actually read this — someone
checking the NEAR chapter should not have to download Polygon. Where one
architecture is too large on its own, its phases are packed into numbered parts
under a size target. The rule is automatic rather than a hand-written list, so
it keeps working as the dataset grows.
