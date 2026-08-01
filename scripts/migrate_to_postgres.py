"""Copy an existing ChromaDB + SQLite install into Postgres/pgvector (Phase 9).

Vectors are moved as-is — they are *not* re-embedded, so this costs nothing and the
answers stay bit-identical. That also means the embedding model must be unchanged
since ingest; if you switched models, re-ingest instead of migrating.

    uv run python scripts/migrate_to_postgres.py --dry-run   # report only
    uv run python scripts/migrate_to_postgres.py             # vectors + rows
    uv run python scripts/migrate_to_postgres.py --rows-only

Afterwards set both providers in config/system.yaml:

    stores:
      vector: pgvector
      relational: postgres
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.clients.vector.chroma import ChromaVectorStore  # noqa: E402
from app.config import get_config  # noqa: E402

# Order matters only for readability; there are no cross-table foreign keys.
TABLES = [
    "system_events",
    "ingestion_audit",
    "eval_runs",
    "eval_case_results",
    "eval_candidates",
    "feedback",
]


def _batched(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def migrate_vectors(batch_size: int, dry_run: bool) -> int:
    """Chroma chunks -> pgvector, embeddings included (no re-embedding)."""
    source = ChromaVectorStore()
    if source.count() == 0:
        print("  vectors: chroma is empty, nothing to copy")
        return 0

    raw = source.collection.get(include=["documents", "metadatas", "embeddings"])
    ids = list(raw.get("ids") or [])
    docs = list(raw.get("documents") or [])
    metas = [m or {} for m in (raw.get("metadatas") or [])]
    embs = raw.get("embeddings")
    embeddings = [list(map(float, e)) for e in (embs if embs is not None else [])]

    if len(embeddings) != len(ids):
        raise SystemExit(f"chroma returned {len(embeddings)} embeddings for {len(ids)} ids")

    print(f"  vectors: {len(ids)} chunks, dim={len(embeddings[0]) if embeddings else 0}")
    if dry_run:
        return len(ids)

    from app.clients.vector.pgvector import PgVectorStore

    target = PgVectorStore()
    target.reset()  # a partial copy is worse than an obvious empty one
    for chunk in _batched(list(range(len(ids))), batch_size):
        target.add(
            [ids[i] for i in chunk],
            [embeddings[i] for i in chunk],
            [docs[i] for i in chunk],
            [metas[i] for i in chunk],
        )
        print(f"    copied {chunk[-1] + 1}/{len(ids)}", end="\r")
    print(f"    copied {len(ids)}/{len(ids)}   ")
    return len(ids)


def migrate_rows(dry_run: bool) -> dict[str, int]:
    """SQLite operational tables -> Postgres, preserving ids and timestamps."""
    cfg = get_config()
    path = cfg.paths.sqlite_path
    if not path.exists():
        print(f"  rows: no sqlite database at {path}")
        return {}

    lite = sqlite3.connect(str(path))
    lite.row_factory = sqlite3.Row
    counts: dict[str, int] = {}
    payload: dict[str, list[dict]] = {}
    for table in TABLES:
        try:
            rows = [dict(r) for r in lite.execute(f"SELECT * FROM {table}")]
        except sqlite3.OperationalError:
            rows = []  # table never created in this install
        counts[table] = len(rows)
        payload[table] = rows
    lite.close()

    print("  rows: " + ", ".join(f"{t}={n}" for t, n in counts.items()))
    if dry_run:
        return counts

    from app.clients.relational import POSTGRES_SCHEMA, _postgres_connection

    conn = _postgres_connection()
    try:
        conn.executescript(POSTGRES_SCHEMA)
        for table, rows in payload.items():
            if not rows:
                continue
            cols = list(rows[0].keys())
            placeholders = ", ".join("?" for _ in cols)
            conn.executemany(
                f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders}) "
                "ON CONFLICT DO NOTHING",  # re-running the migration is safe
                [[r[c] for c in cols] for r in rows],
            )
        # Sequences keep their own counter, so after copying explicit ids the next
        # INSERT would collide unless they are advanced past the highest id.
        for table, pk in (("eval_candidates", "id"), ("feedback", "id"),
                          ("system_events", "event_id"), ("ingestion_audit", "audit_id")):
            if counts.get(table):
                conn.execute(
                    f"SELECT setval(pg_get_serial_sequence('{table}', '{pk}'), "
                    f"COALESCE((SELECT MAX({pk}) FROM {table}), 1))"
                )
        conn.commit()
    finally:
        conn.close()
    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="report what would move, change nothing")
    ap.add_argument("--rows-only", action="store_true", help="skip vectors")
    ap.add_argument("--vectors-only", action="store_true", help="skip relational rows")
    ap.add_argument("--batch-size", type=int, default=500)
    args = ap.parse_args()

    cfg = get_config()
    print(f"source: chroma={cfg.paths.chroma_dir}  sqlite={cfg.paths.sqlite_path}")
    print(f"target: {cfg.postgres_dsn()}")
    if args.dry_run:
        print("(dry run — nothing will be written)")

    if not args.rows_only:
        migrate_vectors(args.batch_size, args.dry_run)
    if not args.vectors_only:
        migrate_rows(args.dry_run)

    if not args.dry_run:
        print("\ndone. now set stores.vector: pgvector and stores.relational: postgres")


if __name__ == "__main__":
    main()
