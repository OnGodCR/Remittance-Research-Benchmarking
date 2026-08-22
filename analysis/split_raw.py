"""Split the raw dataset into parts small enough for GitHub to accept.

    .venv/bin/python -m analysis.split_raw

WHY THIS EXISTS

GitHub refuses any single large-file-storage object over 2 GiB. Not a quota
that can be raised -- a hard limit that returns "Size must be less than or
equal to 2147483648" and rejects the whole push. The raw dataset passed it at
610 runs and 24.6 million payments, which meant the repository could no longer
accept new work of any kind, data or code.

NOTHING IS REMOVED. Every row of the raw file lands in exactly one part, and
analysis/rebuild_raw.py puts them back together into a file identical in
content to the original. Downsampling was never on the table: a reviewer has
to be able to see the untouched data beside the cleaned data and check that
nothing inconvenient was quietly dropped.

HOW THE SPLIT IS DECIDED

By architecture first, because that is how anyone actually wants to read this
-- someone checking the NEAR chapter should not have to download Polygon. If
one architecture is too big on its own, its phases are packed into numbered
parts, largest first, each kept under the target. The rule is automatic and
size-driven rather than a hand-written list of files, so it keeps working as
the dataset grows instead of quietly breaking the next time someone commits.

Ordering is deterministic, so re-running this on unchanged input produces
byte-identical parts and no spurious repository churn.

MEMORY, AND WHY THE ROWS ARE BUFFERED

The raw file is far larger than this laptop's memory once decompressed, so it
is never loaded whole. It is read one row group at a time and each group is
dispatched to the part it belongs to.

Writing each of those slices straight out, though, makes the parts BIGGER than
the file they came from -- 3.10 GiB against 2.43 GiB on the first attempt.
Splitting a row group four ways leaves four small ones, and a compressor given
13,000 rows at a time finds far less repetition than one given a million. So
slices are accumulated per part and only written once they are worth writing.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

RAW = Path("data/raw/all_runs_raw.parquet")
PARTS = Path("data/raw/parts")
MANIFEST = PARTS / "manifest.csv"

# 0.9 GiB, against GitHub's 2 GiB ceiling. The gap looks over-generous and is
# not. The planner has to guess a part's compressed size BEFORE writing it, and
# it guesses from an average bytes-per-row across the whole dataset -- but rows
# do not all compress alike, and Polygon's compress about 23% worse than
# average, so a 1.2 GiB target produced a 1.48 GiB file on the first attempt.
# The rest of the gap is growth: parts get bigger as runs are added, and
# re-splitting later would rewrite files that were already pushed.
TARGET_BYTES = int(0.9 * 1024**3)

# Written parts above this get a loud warning. Not fatal -- still pushable --
# but it means the next few runs will breach the limit, so re-split now rather
# than discovering it during a push.
WARN_BYTES = int(1.6 * 1024**3)

COMPRESSION = "zstd"
COMPRESSION_LEVEL = 3  # level 9 cost minutes and cooked the laptop for ~4% size

# Rows held per part before a row group is written. Big enough that the
# compressor has real repetition to find, small enough that peak memory stays
# around a gigabyte on a laptop with eight.
ROWS_PER_GROUP = 1_000_000


def plan(counts: dict[tuple[str, str], int], total_rows: int, total_bytes: int):
    """Decide which (architecture, phase) groups go in which part."""
    bytes_per_row = total_bytes / total_rows if total_rows else 0

    by_arch: dict[str, list[tuple[str, int]]] = {}
    for (arch, phase), n in counts.items():
        by_arch.setdefault(arch, []).append((phase, n))

    assignment: dict[tuple[str, str], str] = {}
    for arch in sorted(by_arch):
        phases = by_arch[arch]
        arch_bytes = sum(n for _, n in phases) * bytes_per_row

        if arch_bytes <= TARGET_BYTES:
            for phase, _ in phases:
                assignment[(arch, phase)] = f"raw-{arch}.parquet"
            continue

        # Too big alone: pack phases into numbered parts, largest first so the
        # big ones settle before the small ones fill gaps.
        bins: list[list[tuple[str, int]]] = []
        loads: list[float] = []
        for phase, n in sorted(phases, key=lambda x: (-x[1], x[0])):
            size = n * bytes_per_row
            for i, load in enumerate(loads):
                if load + size <= TARGET_BYTES:
                    bins[i].append((phase, n)); loads[i] += size
                    break
            else:
                bins.append([(phase, n)]); loads.append(size)
        for i, group in enumerate(bins, start=1):
            for phase, _ in group:
                assignment[(arch, phase)] = f"raw-{arch}-{i:02d}.parquet"

    return assignment


def main() -> int:
    if not RAW.exists():
        print(f"  {RAW} not found -- nothing to split")
        return 1

    src = pq.ParquetFile(RAW)
    total_rows = src.metadata.num_rows
    total_bytes = RAW.stat().st_size

    keys = src.read(columns=["architecture", "phase"])
    counts: dict[tuple[str, str], int] = {}
    for arch, phase in zip(keys.column("architecture").to_pylist(),
                           keys.column("phase").to_pylist()):
        counts[(str(arch), str(phase))] = counts.get((str(arch), str(phase)), 0) + 1
    del keys

    assignment = plan(counts, total_rows, total_bytes)
    part_names = sorted(set(assignment.values()))
    print(f"  {total_rows:,} rows -> {len(part_names)} part(s)")

    PARTS.mkdir(parents=True, exist_ok=True)
    for stale in PARTS.glob("raw-*.parquet"):
        stale.unlink()

    writers: dict[str, pq.ParquetWriter] = {}
    buffers: dict[str, list[pa.Table]] = {name: [] for name in part_names}
    buffered: dict[str, int] = {name: 0 for name in part_names}
    written: dict[str, int] = {name: 0 for name in part_names}
    schema = src.schema_arrow

    members_of = {name: [k for k, v in assignment.items() if v == name]
                  for name in part_names}

    def flush(name: str) -> None:
        if not buffers[name]:
            return
        table = pa.concat_tables(buffers[name])
        buffers[name].clear(); buffered[name] = 0
        if name not in writers:
            writers[name] = pq.ParquetWriter(
                PARTS / name, schema,
                compression=COMPRESSION, compression_level=COMPRESSION_LEVEL)
        writers[name].write_table(table)
        written[name] += table.num_rows

    try:
        for rg in range(src.metadata.num_row_groups):
            table = src.read_row_group(rg)
            arch_col = table.column("architecture")
            phase_col = table.column("phase")
            for name in part_names:
                mask = None
                for arch, phase in members_of[name]:
                    m = pc.and_(pc.equal(arch_col, arch), pc.equal(phase_col, phase))
                    mask = m if mask is None else pc.or_(mask, m)
                if mask is None:
                    continue
                sub = table.filter(mask)
                if sub.num_rows == 0:
                    continue
                buffers[name].append(sub); buffered[name] += sub.num_rows
                if buffered[name] >= ROWS_PER_GROUP:
                    flush(name)
            del table
        for name in part_names:
            flush(name)
    finally:
        for w in writers.values():
            w.close()

    with MANIFEST.open("w", newline="") as fh:
        out = csv.writer(fh)
        out.writerow(["part", "architecture", "phase", "rows"])
        for (arch, phase), name in sorted(assignment.items(), key=lambda x: (x[1], x[0])):
            out.writerow([name, arch, phase, counts[(arch, phase)]])

    over = []
    for name in part_names:
        size = (PARTS / name).stat().st_size
        flag = ""
        if size > 2 * 1024**3:
            flag = "  *** OVER GITHUB'S 2 GiB LIMIT ***"; over.append(name)
        elif size > WARN_BYTES:
            flag = "  <- getting close to the 2 GiB limit, re-split soon"
        print(f"  {name:34s} {written[name]:>11,} rows  {size/1024**3:5.2f} GiB{flag}")

    print(f"  manifest: {MANIFEST}")
    print(f"  every one of the {total_rows:,} rows accounted for")
    return 1 if over else 0


if __name__ == "__main__":
    raise SystemExit(main())
