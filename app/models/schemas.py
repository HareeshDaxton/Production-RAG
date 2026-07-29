"""Shared API schemas. Grows per phase."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class ReadyResponse(BaseModel):
    status: str
    checks: dict[str, str]


# --- Ingestion ---------------------------------------------------------------


class IngestRequest(BaseModel):
    source_dir: str | None = Field(
        default=None, description="Directory to ingest; defaults to the configured corpus dir."
    )
    reset: bool = Field(
        default=False, description="Clear existing chunks before ingesting (avoids duplicates)."
    )


class IngestResponse(BaseModel):
    documents_ingested: int
    chunks_created: int
    source_dir: str


class IndexedDocumentOut(BaseModel):
    """One distinct document currently searchable in the chunk collection."""

    source: str
    title: str
    file_type: str
    chunks: int
    pages: int | None = None


class DocumentsResponse(BaseModel):
    documents: list[IndexedDocumentOut]
    total_chunks: int


class SystemResponse(BaseModel):
    """Model wiring surfaced to the UI's system panel."""

    generation_model: str
    embedding_model: str
    retrieval_mode: str
    documents: int
    chunks: int


# --- Ask ---------------------------------------------------------------------


class Citation(BaseModel):
    number: int
    source: str
    section: str | None = None
    text: str
    file_type: str | None = None
    page: int | None = Field(default=None, description="Page number for paginated sources (PDF).")
    locator: str | None = Field(
        default=None,
        description="Structural pointer for non-paginated sources (row/object/element).",
    )
    verdict: Literal["supported", "partial", "unsupported"] | None = Field(
        default=None, description="Judge verdict on whether the source backs the claim."
    )
    verdict_reason: str | None = None


class RetrievalFilters(BaseModel):
    """Equality filters applied to chunk metadata before ranking (M6).

    Unknown keys are rejected so a typo fails loudly instead of silently matching
    nothing. Substring/section filtering is intentionally out of scope — Chroma's
    metadata `where` supports equality, not substring, on metadata fields.
    """

    model_config = ConfigDict(extra="forbid")

    file_type: str | None = Field(
        default=None, description="pdf|docx|csv|json|xml|html|txt|markdown|image"
    )
    source: str | None = Field(default=None, description="Exact source path/filename.")
    content_type: str | None = Field(
        default=None, description="text|table|row|object|element|ocr|code"
    )

    def as_dict(self) -> dict[str, str]:
        """Active (non-None) filters as a flat equality dict."""
        return {k: v for k, v in self.model_dump().items() if v is not None}


class AskRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)
    mode: Literal["hybrid", "dense"] | None = Field(
        default=None, description="Override retrieval mode; defaults to config (hybrid)."
    )
    filters: RetrievalFilters | None = Field(
        default=None, description="Restrict retrieval to chunks matching these metadata equalities."
    )


class AskResponse(BaseModel):
    query: str
    answer: str
    citations: list[Citation]
    chunks_retrieved: int
    has_sufficient_context: bool
    retrieval_mode: str
    retrieval_confidence: float
    confidence: float = Field(
        default=0.0, description="Composite confidence (retrieval + citation + self), 0-1."
    )
    confidence_breakdown: dict[str, float] = Field(default_factory=dict)
    cached: bool = Field(default=False, description="True if served from the semantic cache.")
    cache_similarity: float | None = Field(
        default=None, description="Cosine similarity to the cached query when cached=true."
    )
