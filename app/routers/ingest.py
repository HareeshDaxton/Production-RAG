"""POST /v1/ingest — index a directory of markdown docs, or upload files directly."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.clients.ingestion_client import IngestionServiceError
from app.clients.vectorstore import EmbeddingDimensionMismatch
from app.config import get_config
from app.models.schemas import (
    DocumentsResponse,
    IndexedDocumentOut,
    IngestRequest,
    IngestResponse,
    SystemResponse,
)
from app.services.role import INGESTION, runs_locally

router = APIRouter(prefix="/v1", tags=["ingest"])


def _document_out(d) -> IndexedDocumentOut:
    """Works for the local dataclass and the client's pydantic model alike."""
    return IndexedDocumentOut(
        source=d.source, title=d.title, file_type=d.file_type,
        chunks=d.chunks, pages=d.pages,
    )


def _ingestion():
    """The ingestion module, or an HTTP client with the same function names.

    Phase 9B: when `services.mode` is distributed and this process is the api,
    ingestion happens in another container. Both objects expose
    ingest_directory / ingest_files / list_indexed_documents / delete_document
    with identical signatures, so nothing below branches on it.
    """
    if runs_locally(INGESTION):
        from app.modules.ingestion import service

        return service
    from app.clients import ingestion_client

    return ingestion_client


@router.post("/ingest", response_model=IngestResponse)
def ingest(req: IngestRequest) -> IngestResponse:
    try:
        result = _ingestion().ingest_directory(req.source_dir, reset=req.reset)
    except IngestionServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EmbeddingDimensionMismatch as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return IngestResponse(
        documents_ingested=result.documents,
        chunks_created=result.chunks,
        source_dir=result.source_dir,
    )


@router.post("/ingest/upload", response_model=IngestResponse)
async def ingest_upload(
    files: list[UploadFile] = File(..., description="Documents to ingest (see accepted types)."),
    reset: bool = Form(default=False, description="Wipe the collection before ingesting."),
) -> IngestResponse:
    # Validate here only when ingestion runs in this process: importing the loader
    # registry pulls in every parser, which the api image intentionally lacks. When
    # ingestion is remote it performs the same check and its 400 is passed through.
    if runs_locally(INGESTION):
        from app.modules.ingestion.loader import allowed_suffixes

        allowed = allowed_suffixes()
        for f in files:
            name = f.filename or "upload"
            if Path(name).suffix.lower() not in allowed:
                raise HTTPException(
                    status_code=400,
                    detail=f"unsupported file type: {name}. accepted extensions: {sorted(allowed)}",
                )

    payloads = [((f.filename or "upload"), await f.read()) for f in files]

    try:
        result = _ingestion().ingest_files(payloads, reset=reset)
    except IngestionServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except EmbeddingDimensionMismatch as exc:
        # 409, not 500: the request is fine, the index is stale. A raw 500 escapes the
        # CORS middleware, so the browser reports it as an unreachable API.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return IngestResponse(
        documents_ingested=result.documents,
        chunks_created=result.chunks,
        source_dir=result.source_dir,
    )


@router.get("/documents", response_model=DocumentsResponse)
def documents() -> DocumentsResponse:
    """Documents currently searchable — powers the UI's document filter."""
    docs = _ingestion().list_indexed_documents()
    return DocumentsResponse(
        documents=[_document_out(d) for d in docs],
        total_chunks=sum(d.chunks for d in docs),
    )


@router.delete("/documents/{source:path}")
def remove_document(source: str) -> dict:
    """Drop a document from the index. `:path` so sources with slashes still match."""
    removed = _ingestion().delete_document(source)
    if removed == 0:
        raise HTTPException(status_code=404, detail=f"document not indexed: {source}")
    return {"deleted": True, "source": source, "chunks_removed": removed}


@router.get("/system", response_model=SystemResponse)
def system() -> SystemResponse:
    """Model wiring + corpus size for the UI's system panel."""
    cfg = get_config()
    docs = _ingestion().list_indexed_documents()
    return SystemResponse(
        generation_model=cfg.models.generation.name,
        embedding_model=cfg.models.embedding.name.split("/")[-1],
        retrieval_mode=cfg.retrieval.mode,
        documents=len(docs),
        chunks=sum(d.chunks for d in docs),
    )
