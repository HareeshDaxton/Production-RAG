"""SQLite audit/metadata store for early phases.

Deliberately minimal now; the richer schema (query_records, eval_cases, ...) lands
with the phases that need it, and migrates to Postgres+pgvector in Phase 8.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from app.config import get_config
from app.logging_config import get_logger

logger = get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS system_events (
    event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    details    TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ingestion_audit (
    audit_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    source     TEXT,
    documents  INTEGER,
    chunks     INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS eval_runs (
    run_id       TEXT PRIMARY KEY,
    strategy     TEXT,
    n_cases      INTEGER,
    metrics_json TEXT,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS eval_case_results (
    run_id       TEXT,
    case_id      TEXT,
    case_type    TEXT,
    score        REAL,
    metrics_json TEXT
);
"""


def _connect() -> sqlite3.Connection:
    cfg = get_config()
    cfg.paths.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(cfg.paths.sqlite_path))
    conn.row_factory = sqlite3.Row
    # Ensure schema on every connection (idempotent) so any entry point —
    # API, tests, or scripts — always has the tables, not just API startup.
    conn.executescript(_SCHEMA)
    return conn


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(_SCHEMA)
    logger.info("sqlite initialized")


def record_event(event_type: str, details: str | None = None) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO system_events (event_type, details) VALUES (?, ?)",
            (event_type, details),
        )


def record_ingestion(source: str, documents: int, chunks: int) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO ingestion_audit (source, documents, chunks) VALUES (?, ?, ?)",
            (source, documents, chunks),
        )


def record_eval_run(
    run_id: str,
    strategy: str,
    n_cases: int,
    metrics_json: str,
    case_rows: list[tuple[str, str, float, str]],
) -> None:
    """Persist an eval run + its per-case rows (case_id, case_type, score, metrics_json)."""
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO eval_runs (run_id, strategy, n_cases, metrics_json) "
            "VALUES (?, ?, ?, ?)",
            (run_id, strategy, n_cases, metrics_json),
        )
        conn.executemany(
            "INSERT INTO eval_case_results (run_id, case_id, case_type, score, metrics_json) "
            "VALUES (?, ?, ?, ?, ?)",
            [(run_id, cid, ctype, score, mj) for (cid, ctype, score, mj) in case_rows],
        )


def get_corpus_version() -> int:
    """Monotonic corpus version = latest ingestion_audit id (0 if never ingested).

    Every ingest inserts an audit row, so this bumps on each ingest — the semantic
    cache tags entries with it and only serves matches for the current version, which
    invalidates stale answers after a re-ingest with no extra bookkeeping.
    """
    with get_db() as conn:
        row = conn.execute("SELECT MAX(audit_id) AS v FROM ingestion_audit").fetchone()
    return int(row["v"]) if row and row["v"] is not None else 0


def get_previous_eval_metrics(strategy: str, before_run_id: str) -> str | None:
    """Most recent prior run's metrics JSON for a strategy (for regression deltas)."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT metrics_json FROM eval_runs WHERE strategy = ? AND run_id != ? "
            "ORDER BY created_at DESC LIMIT 1",
            (strategy, before_run_id),
        ).fetchone()
    return row["metrics_json"] if row else None
