"""Contracts for the internal service-to-service API (Phase 9B).

Separate from `models/schemas.py` on purpose: those are the public API the
frontend depends on, these are between our own processes and may change freely.
Both sides import these, so a drift is a type error rather than a runtime
surprise.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.modules.retrieval.dense import RetrievedChunk


class ChunkOut(BaseModel):
    """A retrieved chunk on the wire. Mirrors the `RetrievedChunk` dataclass."""

    chunk_id: str
    text: str
    source: str
    section_path: str = ""
    score: float = 0.0
    file_type: str = ""
    title: str = ""
    page_number: int | None = None
    locator: str | None = None
    content_type: str = "text"

    @classmethod
    def of(cls, chunk: RetrievedChunk) -> ChunkOut:
        return cls(**vars(chunk))

    def to_chunk(self) -> RetrievedChunk:
        return RetrievedChunk(**self.model_dump())


class RetrieveRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(..., ge=1, le=100)
    mode: str | None = None
    # Free-form because retrieval filters are engine-shaped dicts, not the public
    # RetrievalFilters model (which the api service has already resolved by now).
    filters: dict | None = None


class RetrieveResponse(BaseModel):
    chunks: list[ChunkOut]
    confidence: float
    mode: str


class IngestDirectoryRequest(BaseModel):
    source_dir: str | None = None
    reset: bool = False


class IngestResult(BaseModel):
    documents: int
    chunks: int
    source_dir: str


class DocumentOut(BaseModel):
    source: str
    title: str
    file_type: str
    chunks: int
    pages: int | None = None


class DocumentsOut(BaseModel):
    documents: list[DocumentOut]


class DeleteResult(BaseModel):
    chunks_removed: int
