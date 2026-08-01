"""Relational backend selection: `sqlite` (zero-infra default) or `postgres`.

`db.py` holds the queries and keeps its public API; this module decides which
engine runs them. The two dialects differ in three places only, so the adapter
stays thin rather than pulling in an ORM:

  * placeholders   — sqlite `?`, psycopg `%s`
  * autoincrement  — `INTEGER PRIMARY KEY AUTOINCREMENT` vs `BIGSERIAL`
  * new row id     — `cursor.lastrowid` vs `INSERT ... RETURNING`

Queries are written once with `?` and translated here.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from app.config import get_config
from app.logging_config import get_logger

logger = get_logger(__name__)

# Table shapes are identical; only the id/timestamp types are dialect-specific.
_TABLES = """
CREATE TABLE IF NOT EXISTS system_events (
    event_id   {pk},
    event_type TEXT NOT NULL,
    details    TEXT,
    created_at {ts}
);

CREATE TABLE IF NOT EXISTS ingestion_audit (
    audit_id   {pk},
    source     TEXT,
    documents  INTEGER,
    chunks     INTEGER,
    created_at {ts}
);

CREATE TABLE IF NOT EXISTS eval_runs (
    run_id       TEXT PRIMARY KEY,
    strategy     TEXT,
    n_cases      INTEGER,
    metrics_json TEXT,
    created_at   {ts}
);

CREATE TABLE IF NOT EXISTS eval_case_results (
    run_id       TEXT,
    case_id      TEXT,
    case_type    TEXT,
    score        {real},
    metrics_json TEXT
);

CREATE TABLE IF NOT EXISTS eval_candidates (
    id                {pk},
    query             TEXT NOT NULL,
    reason            TEXT,
    retrieved_sources TEXT,
    proposed_answer   TEXT,
    proposed_type     TEXT,
    proposed_sources  TEXT,
    agreement         INTEGER,
    status            TEXT DEFAULT 'pending',
    created_at        {ts}
);

CREATE TABLE IF NOT EXISTS feedback (
    id         {pk},
    query      TEXT NOT NULL,
    rating     TEXT,
    comment    TEXT,
    created_at {ts}
);
"""

SQLITE_SCHEMA = _TABLES.format(
    pk="INTEGER PRIMARY KEY AUTOINCREMENT",
    ts="DATETIME DEFAULT CURRENT_TIMESTAMP",
    real="REAL",
)
POSTGRES_SCHEMA = _TABLES.format(
    pk="BIGSERIAL PRIMARY KEY",
    ts="TIMESTAMPTZ DEFAULT now()",
    real="DOUBLE PRECISION",
)


def provider() -> str:
    return get_config().stores.relational.lower()


class Connection:
    """Uniform cursor API over sqlite3 and psycopg, with `?` placeholders."""

    def __init__(self, raw, dialect: str):
        self._raw = raw
        self.dialect = dialect

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.dialect == "postgres" else sql

    def execute(self, sql: str, params: tuple | list = ()):
        return self._raw.execute(self._sql(sql), tuple(params))

    def insert_returning_id(self, sql: str, params: tuple | list, pk: str = "id") -> int:
        """INSERT and return the new row's id, whichever dialect is in play."""
        if self.dialect == "postgres":
            cur = self._raw.execute(self._sql(f"{sql} RETURNING {pk}"), tuple(params))
            return int(cur.fetchone()[pk])
        return int(self._raw.execute(sql, tuple(params)).lastrowid)

    def executemany(self, sql: str, rows) -> None:
        if self.dialect == "postgres":
            with self._raw.cursor() as cur:
                cur.executemany(self._sql(sql), [tuple(r) for r in rows])
        else:
            self._raw.executemany(sql, [tuple(r) for r in rows])

    def executescript(self, script: str) -> None:
        if self.dialect == "postgres":
            self._raw.execute(script)
        else:
            self._raw.executescript(script)

    def commit(self) -> None:
        self._raw.commit()

    def close(self) -> None:
        self._raw.close()


def _sqlite_connection() -> Connection:
    cfg = get_config()
    cfg.paths.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(str(cfg.paths.sqlite_path))
    raw.row_factory = sqlite3.Row
    # Ensure schema on every connection (idempotent) so any entry point —
    # API, tests, or scripts — always has the tables, not just API startup.
    raw.executescript(SQLITE_SCHEMA)
    return Connection(raw, "sqlite")


def _postgres_connection() -> Connection:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover - environment problem, not logic
        raise RuntimeError(
            "the postgres store needs psycopg: uv add 'psycopg[binary,pool]' "
            "(or set stores.relational back to 'sqlite')"
        ) from exc

    raw = psycopg.connect(get_config().postgres_dsn(), row_factory=dict_row, autocommit=False)
    raw.execute(POSTGRES_SCHEMA)
    raw.commit()
    return Connection(raw, "postgres")


@contextmanager
def get_connection() -> Iterator[Connection]:
    conn = _postgres_connection() if provider() == "postgres" else _sqlite_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
