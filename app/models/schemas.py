"""Shared API schemas. Grows per phase."""
from __future__ import annotations

from pydantic import BaseModel, Field


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


# --- Ask ---------------------------------------------------------------------


class Citation(BaseModel):
    number: int
    source: str
    section: str | None = None
    text: str


class AskRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)


class AskResponse(BaseModel):
    query: str
    answer: str
    citations: list[Citation]
    chunks_retrieved: int
    has_sufficient_context: bool
