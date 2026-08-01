"""Pluggable vector backends (Phase 9): `chroma` for zero-infra, `pgvector` for prod."""
from app.clients.vector.base import (
    EmbeddingDimensionMismatch,
    StoredChunks,
    VectorHit,
    VectorStore,
    assert_dimension,
)

__all__ = [
    "EmbeddingDimensionMismatch",
    "StoredChunks",
    "VectorHit",
    "VectorStore",
    "assert_dimension",
]
