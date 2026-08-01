"""The contract every vector backend implements.

Through Phase 8 the application called ChromaDB's collection object directly, so
Chroma's API leaked into the indexer, both retrievers and the ingestion service.
Phase 9 puts an interface in front of it: `chroma` still runs with no
infrastructure, `pgvector` is the production engine, and the callers cannot tell
which one they are talking to.

Filters keep Chroma's shape (`{"k": v}`, `{"k": {"$in": [...]}}`, `{"$and": [...]}`)
because `retrieval/filters.py` already produces it; each backend translates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class VectorHit:
    """One nearest-neighbour result."""

    chunk_id: str
    document: str
    metadata: dict
    distance: float  # cosine distance in [0, 2]; similarity = 1 - distance


@dataclass
class StoredChunks:
    """Everything in the store, used to rebuild BM25 and list documents."""

    ids: list[str] = field(default_factory=list)
    documents: list[str] = field(default_factory=list)
    metadatas: list[dict] = field(default_factory=list)


class EmbeddingDimensionMismatch(RuntimeError):
    """The stored vectors were written by a different embedding model."""


@runtime_checkable
class VectorStore(Protocol):
    """Operations the RAG pipeline needs from a vector index."""

    def add(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict],
    ) -> None: ...

    def query(
        self, embedding: list[float], top_k: int, where: dict | None = None
    ) -> list[VectorHit]: ...

    def fetch_all(self) -> StoredChunks: ...

    def ids_where(self, where: dict) -> list[str]: ...

    def delete_ids(self, ids: list[str]) -> None: ...

    def delete_where(self, where: dict) -> None: ...

    def count(self) -> int: ...

    def dimension(self) -> int | None:
        """Width of the stored vectors, or None when the store is empty."""
        ...

    def reset(self) -> None: ...


def assert_dimension(store: VectorStore, dim: int) -> None:
    """Fail early, and legibly, when the configured model does not match the store.

    A store fixes its vector width on first write, so switching embedding model
    turns every add and query into a raw driver error deep in the stack. Checking up
    front lets the caller return an actionable message instead.
    """
    found = store.dimension()
    if found is not None and found != dim:
        raise EmbeddingDimensionMismatch(
            f"the index holds {found}-dimension vectors but the configured embedding "
            f"model produces {dim}. Re-ingest with reset=true to rebuild it "
            f"(existing chunks cannot be searched by a different model)."
        )
