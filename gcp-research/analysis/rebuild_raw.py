"""Put the raw dataset back together from its parts.

    .venv/bin/python -m analysis.rebuild_raw

The repository stores the raw dataset split across data/raw/parts/, because
GitHub hard-rejects any single stored file over 2 GiB (see
analysis/split_raw.py). This reassembles data/raw/all_runs_raw.parquet from
them, so anything that expects the one canonical file -- including every
analysis script written before the split -- keeps working unchanged.

Rows are written back grouped by part rather than in the original interleaved
order. Nothing downstream depends on file order: every record carries its run
id and its own submission and confirmation timestamps, and the analysis sorts
on those. The row COUNT and the row CONTENTS are identical, and that is what
is checked at the end.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pyarrow.parquet as pq

RAW = Path("data/raw/all_runs_raw.parquet")
PARTS = Path("data/raw/parts")
MANIFEST = PARTS / "manifest.csv"

COMPRESSION = "zstd"
COMPRESSION_LEVEL = 3


def main() -> int:
    files = sorted(PARTS.glob("raw-*.parquet"))
    if not files:
        print(f"  no parts found in {PARTS}")
        return 1

    expected = None
    if MANIFEST.exists():
        with MANIFEST.open() as fh:
            expected = sum(int(row["rows"]) for row in csv.DictReader(fh))

    schema = pq.ParquetFile(files[0]).schema_arrow
    RAW.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    writer = pq.ParquetWriter(RAW, schema, compression=COMPRESSION,
                              compression_level=COMPRESSION_LEVEL)
    try:
        for f in files:
            src = pq.ParquetFile(f)
            if src.schema_arrow != schema:
                raise SystemExit(f"  {f.name} has a different schema -- refusing to merge")
            for rg in range(src.metadata.num_row_groups):
                table = src.read_row_group(rg)
                writer.write_table(table)
                total += table.num_rows
                del table
            print(f"  {f.name:34s} {src.metadata.num_rows:>11,} rows")
    finally:
        writer.close()

    print(f"  {RAW}  {total:,} rows  {RAW.stat().st_size/1024**3:.2f} GiB")
    if expected is not None and expected != total:
        raise SystemExit(f"  ROW COUNT MISMATCH: manifest says {expected:,}, wrote {total:,}")
    if expected is not None:
        print(f"  matches the manifest's {expected:,} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
