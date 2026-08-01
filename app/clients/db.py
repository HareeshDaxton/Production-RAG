"""Operational store: audit, eval, auto-eval and feedback rows.

The queries live here; `relational.py` decides whether they run on SQLite (the
zero-infrastructure default) or Postgres (Phase 9). Placeholders are written `?`
and translated per dialect, so this module is engine-agnostic.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from app.clients.relational import Connection, get_connection, provider
from app.logging_config import get_logger

logger = get_logger(__name__)


@contextmanager
def get_db() -> Iterator[Connection]:
    with get_connection() as conn:
        yield conn


def init_db() -> None:
    """Ensure the schema exists (connecting already does; this makes it explicit)."""
    with get_db():
        pass
    logger.info("relational store initialized", extra={"provider": provider()})


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
        # `ON CONFLICT ... excluded` is the upsert both dialects understand
        # (SQLite's `INSERT OR REPLACE` is not valid Postgres).
        conn.execute(
            "INSERT INTO eval_runs (run_id, strategy, n_cases, metrics_json) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT (run_id) DO UPDATE SET strategy = excluded.strategy, "
            "n_cases = excluded.n_cases, metrics_json = excluded.metrics_json",
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


def enqueue_candidate(query: str, reason: str, retrieved_sources: str) -> int:
    with get_db() as conn:
        return conn.insert_returning_id(
            "INSERT INTO eval_candidates (query, reason, retrieved_sources) VALUES (?, ?, ?)",
            (query, reason, retrieved_sources),
        )


def withdraw_thumbs_down(query: str) -> int:
    """Pull a thumbs-down's candidate back out of the queue when the vote is taken back.

    Only touches rows still `pending` — once a candidate has been drafted, reviewed or
    approved, its history stands. Returns how many rows were withdrawn.
    """
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE eval_candidates SET status = 'withdrawn' "
            "WHERE query = ? AND reason = 'thumbs_down' AND status = 'pending'",
            (query,),
        )
        return int(cur.rowcount)


def record_feedback(query: str, rating: str, comment: str | None) -> int:
    with get_db() as conn:
        return conn.insert_returning_id(
            "INSERT INTO feedback (query, rating, comment) VALUES (?, ?, ?)",
            (query, rating, comment),
        )


def list_candidates(status: str | None = None, limit: int = 100) -> list[dict]:
    with get_db() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM eval_candidates WHERE status = ? ORDER BY id DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM eval_candidates ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
    return [dict(r) for r in rows]


def get_candidate(candidate_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM eval_candidates WHERE id = ?", (candidate_id,)
        ).fetchone()
    return dict(row) if row else None


def update_candidate(candidate_id: int, **fields) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    with get_db() as conn:
        conn.execute(
            f"UPDATE eval_candidates SET {cols} WHERE id = ?",
            (*fields.values(), candidate_id),
        )


def get_previous_eval_metrics(strategy: str, before_run_id: str) -> str | None:
    """Most recent prior run's metrics JSON for a strategy (for regression deltas)."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT metrics_json FROM eval_runs WHERE strategy = ? AND run_id != ? "
            "ORDER BY created_at DESC LIMIT 1",
            (strategy, before_run_id),
        ).fetchone()
    return row["metrics_json"] if row else None
