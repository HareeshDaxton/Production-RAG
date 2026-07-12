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
