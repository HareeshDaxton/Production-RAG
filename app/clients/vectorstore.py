"""Vector store facade: hands the app whichever backend `stores.vector` selects.

Callers depend on the `VectorStore` interface only, so swapping ChromaDB for
Postgres/pgvector is a config change rather than a code change.
"""
from __future__ import annotations

from functools import lru_cache

from app.clients.vector.base import (
    EmbeddingDimensionMismatch,
    StoredChunks,
    VectorHit,
    VectorStore,
    assert_dimension,
)
from app.config import get_config
from app.logging_config import get_logger

logger = get_logger(__name__)

__all__ = [
    "EmbeddingDimensionMismatch",
    "StoredChunks",
    "VectorHit",
    "VectorStore",
    "assert_dimension",
    "get_vector_store",
    "reset_vector_store",
]


@lru_cache
def get_vector_store() -> VectorStore:
    provider = get_config().stores.vector.lower()
    if provider == "pgvector":
        from app.clients.vector.pgvector import PgVectorStore

        logger.info("vector store: pgvector")
        return PgVectorStore()
    if provider != "chroma":
        logger.warning(
            "unknown vector provider; falling back to chroma", extra={"provider": provider}
        )
    from app.clients.vector.chroma import ChromaVectorStore

    return ChromaVectorStore()


def reset_vector_store() -> VectorStore:
    """Drop and recreate the chunk store (clean re-ingest / tests)."""
    store = get_vector_store()
    store.reset()
    return store
