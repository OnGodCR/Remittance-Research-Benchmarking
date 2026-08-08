"""SQLite storage for benchmark runs.

Design notes
------------
Per-transaction records, never pre-aggregated. Cluster time is the scarcest
resource in this project, so the schema is built so that a question we haven't
thought of yet can be answered by a query rather than by re-running a sweep.

Timestamps are stored as *offsets in seconds from run start*, measured with a
monotonic clock. Wall-clock epoch is recorded once per run (`t0_wall`). This
matters: NTP can step the system clock mid-run, and a settlement latency
computed across such a step would be silently wrong. Offsets are immune to
that; wall-clock is recoverable as `t0_wall + offset` when needed for
correlating against node logs or block explorers.

Amounts and fees are TEXT, not INTEGER. Wei-denominated values exceed the
range where SQLite's 64-bit INTEGER is safe (and float would lose precision
outright). Store the exact decimal string; convert at analysis time.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "1"

_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id              TEXT PRIMARY KEY,
    architecture        TEXT    NOT NULL,   -- polygon | lightning | near | null
    adapter             TEXT    NOT NULL,
    phase               TEXT,               -- project phase that produced this
    arm                 TEXT    NOT NULL,   -- baseline | adversarial
    tx_size_usd         REAL    NOT NULL,
    target_tps          REAL    NOT NULL,
    repeat_index        INTEGER NOT NULL,
    window_seconds      REAL    NOT NULL,
    arrival_seed        INTEGER NOT NULL,
    scheduled_count     INTEGER,
    t0_wall             REAL    NOT NULL,   -- epoch seconds at run start
    ended_wall          REAL,
    harness_version     TEXT,
    config_json         TEXT,
    invalidated         INTEGER NOT NULL DEFAULT 0,
    invalidation_reason TEXT
);

CREATE TABLE IF NOT EXISTS transactions (
    run_id            TEXT    NOT NULL,
    seq               INTEGER NOT NULL,
    scheduled_offset  REAL    NOT NULL,  -- when the Poisson process said to fire
    submitted_offset  REAL,              -- when we actually got it out the door
    confirmed_offset  REAL,
    status            TEXT    NOT NULL,  -- pending|confirmed|failed|timeout
    tx_ref            TEXT,              -- tx hash / payment hash
    amount_native     TEXT,
    gas_used          INTEGER,
    fee_native        TEXT,
    route_hops        INTEGER,           -- Lightning only
    error             TEXT,
    PRIMARY KEY (run_id, seq)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_tx_run_status ON transactions(run_id, status);

-- Per-second time series. Exists so warm-up can be excluded analytically
-- later without re-running anything (claude.md S6: no warm-up discard).
CREATE TABLE IF NOT EXISTS samples (
    run_id    TEXT    NOT NULL,
    second    INTEGER NOT NULL,
    submitted INTEGER NOT NULL DEFAULT 0,
    confirmed INTEGER NOT NULL DEFAULT 0,
    failed    INTEGER NOT NULL DEFAULT 0,
    inflight  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, second)
) WITHOUT ROWID;

-- Node up/down events, from both deliberate fault injection (realism
-- technique #6) and involuntary spot preemption. `source` keeps them
-- separable -- conflating them would confound the adversarial arm.
CREATE TABLE IF NOT EXISTS node_events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id  TEXT NOT NULL,
    offset  REAL NOT NULL,
    node_id TEXT NOT NULL,
    event   TEXT NOT NULL,   -- offline | online
    source  TEXT NOT NULL    -- adversarial | preemption | unknown
);

CREATE INDEX IF NOT EXISTS idx_node_events_run ON node_events(run_id);
"""


@dataclass
class RunConfig:
    """Everything needed to reproduce a single test run."""

    architecture: str
    adapter: str
    tx_size_usd: float
    target_tps: float
    window_seconds: float
    repeat_index: int = 0
    arrival_seed: int = 0
    phase: str | None = None
    arm: str = "baseline"
    harness_version: str = "0.1.0"
    extra: dict[str, Any] = field(default_factory=dict)

    def run_id(self) -> str:
        return (
            f"{self.architecture}-{self.arm}-usd{self.tx_size_usd:g}"
            f"-tps{self.target_tps:g}-r{self.repeat_index}-{uuid.uuid4().hex[:8]}"
        )


class Store:
    """Thin SQLite wrapper. One database file for the whole project."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (SCHEMA_VERSION,),
        )

    # -- run lifecycle ----------------------------------------------------

    def start_run(self, cfg: RunConfig, scheduled_count: int, t0_wall: float | None = None) -> str:
        run_id = cfg.run_id()
        self.conn.execute(
            """INSERT INTO runs (run_id, architecture, adapter, phase, arm,
                   tx_size_usd, target_tps, repeat_index, window_seconds,
                   arrival_seed, scheduled_count, t0_wall, harness_version,
                   config_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                run_id,
                cfg.architecture,
                cfg.adapter,
                cfg.phase,
                cfg.arm,
                cfg.tx_size_usd,
                cfg.target_tps,
                cfg.repeat_index,
                cfg.window_seconds,
                cfg.arrival_seed,
                scheduled_count,
                t0_wall if t0_wall is not None else time.time(),
                cfg.harness_version,
                json.dumps(cfg.extra, sort_keys=True),
            ),
        )
        return run_id

    def end_run(self, run_id: str) -> None:
        self.conn.execute(
            "UPDATE runs SET ended_wall = ? WHERE run_id = ?", (time.time(), run_id)
        )

    def invalidate_run(self, run_id: str, reason: str) -> None:
        """Mark a run unusable -- e.g. a spot preemption touched it.

        Invalidated runs are kept, never deleted: the preemption log is itself
        data, and a silently dropped run is indistinguishable from one that
        never happened.
        """
        self.conn.execute(
            "UPDATE runs SET invalidated = 1, invalidation_reason = ? WHERE run_id = ?",
            (reason, run_id),
        )

    # -- writes -----------------------------------------------------------

    def record_schedule(self, run_id: str, offsets: Iterable[float]) -> None:
        """Insert the full Poisson schedule up front, status='pending'.

        Writing the schedule before the run means an aborted run still shows
        which transactions were *supposed* to fire, so a crash is visible as
        missing submissions rather than as a shorter run.
        """
        self.conn.executemany(
            "INSERT INTO transactions (run_id, seq, scheduled_offset, status) "
            "VALUES (?,?,?, 'pending')",
            ((run_id, i, off) for i, off in enumerate(offsets)),
        )

    def record_submitted(self, run_id: str, seq: int, offset: float, tx_ref: str | None,
                         amount_native: str | None) -> None:
        self.conn.execute(
            "UPDATE transactions SET submitted_offset=?, tx_ref=?, amount_native=? "
            "WHERE run_id=? AND seq=?",
            (offset, tx_ref, amount_native, run_id, seq),
        )

    def record_outcome(self, run_id: str, seq: int, status: str, *,
                       confirmed_offset: float | None = None,
                       gas_used: int | None = None,
                       fee_native: str | None = None,
                       route_hops: int | None = None,
                       error: str | None = None) -> None:
        self.conn.execute(
            """UPDATE transactions
                  SET status=?, confirmed_offset=?, gas_used=?, fee_native=?,
                      route_hops=?, error=?
                WHERE run_id=? AND seq=?""",
            (status, confirmed_offset, gas_used, fee_native, route_hops, error,
             run_id, seq),
        )

    def record_sample(self, run_id: str, second: int, submitted: int, confirmed: int,
                      failed: int, inflight: int) -> None:
        self.conn.execute(
            """INSERT INTO samples (run_id, second, submitted, confirmed, failed, inflight)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(run_id, second) DO UPDATE SET
                   submitted=excluded.submitted, confirmed=excluded.confirmed,
                   failed=excluded.failed, inflight=excluded.inflight""",
            (run_id, second, submitted, confirmed, failed, inflight),
        )

    def record_node_event(self, run_id: str, offset: float, node_id: str,
                          event: str, source: str) -> None:
        self.conn.execute(
            "INSERT INTO node_events (run_id, offset, node_id, event, source) "
            "VALUES (?,?,?,?,?)",
            (run_id, offset, node_id, event, source),
        )

    # -- reads ------------------------------------------------------------

    def run_summary(self, run_id: str) -> dict[str, Any]:
        """Headline numbers for one run. Analysis lives in Phase 6; this is
        just enough to eyeball whether a run behaved sanely before the next
        one starts."""
        row = self.conn.execute(
            """SELECT
                 COUNT(*)                                            AS scheduled,
                 SUM(submitted_offset IS NOT NULL)                   AS submitted,
                 SUM(status='confirmed')                             AS confirmed,
                 SUM(status IN ('failed','timeout'))                 AS failed,
                 AVG(CASE WHEN status='confirmed'
                          THEN confirmed_offset - submitted_offset END) AS mean_latency,
                 MAX(CASE WHEN submitted_offset IS NOT NULL
                          THEN submitted_offset - scheduled_offset END) AS max_schedule_lag
               FROM transactions WHERE run_id = ?""",
            (run_id,),
        ).fetchone()
        cfg = self.conn.execute(
            "SELECT window_seconds, target_tps FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()

        out = dict(row)
        out["run_id"] = run_id
        out["target_tps"] = cfg["target_tps"]
        # Achieved throughput counts CONFIRMED transactions only (claude.md S7).
        out["achieved_tps"] = (out["confirmed"] or 0) / cfg["window_seconds"]
        return out

    def close(self) -> None:
        self.conn.close()
