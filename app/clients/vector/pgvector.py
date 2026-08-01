"""Postgres + pgvector backend (Phase 9 production store).

Chunks live in one table: `id`, `embedding vector(N)`, `document`, `metadata jsonb`.
Nearest neighbours use the `<=>` cosine-distance operator against an HNSW index, so
the distance returned matches Chroma's (both cosine) and callers need no conversion.

Metadata filters arrive in Chroma's shape and are translated to SQL over `jsonb`.
Unsupported operators raise instead of being dropped: a silently-ignored filter
would quietly widen a scoped search, which is a correctness bug, not a warning.
"""
from __future__ import annotations

import json

from app.clients.vector.base import StoredChunks, VectorHit
from app.config import get_config
from app.logging_config import get_logger

logger = get_logger(__name__)


class UnsupportedFilter(ValueError):
    """A filter shape this backend cannot express in SQL."""


def _vector_literal(embedding: list[float]) -> str:
    """pgvector accepts '[1,2,3]' text; this avoids depending on the pgvector adapter."""
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"


def _where_sql(where: dict | None, params: list) -> str:
    """Translate a Chroma-shaped filter into a SQL WHERE fragment (empty if none)."""
    if not where:
        return ""
    clauses = where["$and"] if set(where) == {"$and"} else [where]
    sql: list[str] = []
    for clause in clauses:
        for key, value in clause.items():
            if key.startswith("$"):
                raise UnsupportedFilter(f"unsupported combinator: {key}")
            if isinstance(value, dict):
                if set(value) != {"$in"}:
                    raise UnsupportedFilter(f"unsupported operator on {key!r}: {sorted(value)}")
                params.extend([key, [str(v) for v in value["$in"]]])
                sql.append("metadata->>%s = ANY(%s)")
            else:
                params.extend([key, str(value)])
                sql.append("metadata->>%s = %s")
    return " WHERE " + " AND ".join(sql)


class PgVectorStore:
    def __init__(self):
        self._pool = None
        self._ready = False

    # --- connection ----------------------------------------------------------

    @property
    def pool(self):
        if self._pool is None:
            try:
                from psycopg_pool import ConnectionPool
            except ImportError as exc:  # pragma: no cover - environment problem, not logic
                raise RuntimeError(
                    "the pgvector store needs psycopg: uv add 'psycopg[binary,pool]' "
                    "(or set stores.vector back to 'chroma')"
                ) from exc
            cfg = get_config()
            pg = cfg.stores.postgres
            self._pool = ConnectionPool(
                cfg.postgres_dsn(),
                min_size=pg.min_pool_size,
                max_size=pg.max_pool_size,
                open=True,
            )
        return self._pool

    @property
    def table(self) -> str:
        # Config-supplied, never user input; still constrained to a safe identifier.
        name = get_config().stores.postgres.chunks_table
        if not name.replace("_", "").isalnum():
            raise ValueError(f"invalid table name: {name!r}")
        return name

    def _ensure_schema(self) -> None:
        """Create the extension, table and indexes once per process (idempotent)."""
        if self._ready:
            return
        cfg = get_config()
        pg = cfg.stores.postgres
        dim = cfg.models.embedding.dimensions
        with self.pool.connection() as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.execute(
                f"CREATE TABLE IF NOT EXISTS {self.table} ("
                "  id text PRIMARY KEY,"
                f" embedding vector({dim}) NOT NULL,"
                "  document text NOT NULL,"
                "  metadata jsonb NOT NULL DEFAULT '{}'::jsonb)"
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS {self.table}_embedding_hnsw "
                f"ON {self.table} USING hnsw (embedding vector_cosine_ops) "
                f"WITH (m = {pg.hnsw_m}, ef_construction = {pg.hnsw_ef_construction})"
            )
            # Metadata filters are equality on a handful of keys; GIN keeps them cheap.
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS {self.table}_metadata_gin "
                f"ON {self.table} USING gin (metadata)"
            )
        self._ready = True
        logger.info("pgvector schema ready", extra={"table": self.table, "dim": dim})

    # --- VectorStore ---------------------------------------------------------

    def add(self, ids, embeddings, documents, metadatas) -> None:
        self._ensure_schema()
        rows = [
            (cid, _vector_literal(emb), doc, json.dumps(meta or {}))
            for cid, emb, doc, meta in zip(ids, embeddings, documents, metadatas, strict=True)
        ]
        with self.pool.connection() as conn, conn.cursor() as cur:
            # Re-ingest overwrites in place, matching the deterministic-chunk-id contract.
            cur.executemany(
                f"INSERT INTO {self.table} (id, embedding, document, metadata) "
                "VALUES (%s, %s::vector, %s, %s::jsonb) "
                "ON CONFLICT (id) DO UPDATE SET embedding = EXCLUDED.embedding, "
                "document = EXCLUDED.document, metadata = EXCLUDED.metadata",
                rows,
            )

    def query(self, embedding, top_k, where=None) -> list[VectorHit]:
        self._ensure_schema()
        params: list = []
        clause = _where_sql(where, params)
        vec = _vector_literal(embedding)
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT id, document, metadata, embedding <=> %s::vector AS distance "
                f"FROM {self.table}{clause} ORDER BY distance LIMIT %s",
                [vec, *params, top_k],
            )
            return [
                VectorHit(chunk_id=r[0], document=r[1], metadata=r[2] or {}, distance=float(r[3]))
                for r in cur.fetchall()
            ]

    def fetch_all(self) -> StoredChunks:
        self._ensure_schema()
        out = StoredChunks()
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT id, document, metadata FROM {self.table} ORDER BY id")
            for cid, doc, meta in cur.fetchall():
                out.ids.append(cid)
                out.documents.append(doc)
                out.metadatas.append(meta or {})
        return out

    def ids_where(self, where: dict) -> list[str]:
        self._ensure_schema()
        params: list = []
        clause = _where_sql(where, params)
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT id FROM {self.table}{clause}", params)
            return [r[0] for r in cur.fetchall()]

    def delete_ids(self, ids: list[str]) -> None:
        if not ids:
            return
        self._ensure_schema()
        with self.pool.connection() as conn:
            conn.execute(f"DELETE FROM {self.table} WHERE id = ANY(%s)", [list(ids)])

    def delete_where(self, where: dict) -> None:
        self._ensure_schema()
        params: list = []
        clause = _where_sql(where, params)
        if not clause:
            return  # refuse to interpret "no filter" as "delete everything"
        with self.pool.connection() as conn:
            conn.execute(f"DELETE FROM {self.table}{clause}", params)

    def count(self) -> int:
        self._ensure_schema()
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM {self.table}")
            return int(cur.fetchone()[0])

    def dimension(self) -> int | None:
        self._ensure_schema()
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT vector_dims(embedding) FROM {self.table} LIMIT 1")
            row = cur.fetchone()
            return int(row[0]) if row else None

    def reset(self) -> None:
        """Drop the table so the next write can define a different vector width."""
        with self.pool.connection() as conn:
            conn.execute(f"DROP TABLE IF EXISTS {self.table}")
        self._ready = False
        self._ensure_schema()
        logger.info("pgvector table reset", extra={"table": self.table})
