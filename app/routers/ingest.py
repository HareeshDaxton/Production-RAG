"""POST /v1/ingest — index a directory of markdown docs, or upload files directly."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.clients.vectorstore import EmbeddingDimensionMismatch
from app.config import get_config
from app.models.schemas import (
    DocumentsResponse,
    IndexedDocumentOut,
    IngestRequest,
    IngestResponse,
    SystemResponse,
)
from app.modules.ingestion.loader import allowed_suffixes
from app.modules.ingestion.service import (
    delete_document,
    ingest_directory,
    ingest_files,
    list_indexed_documents,
)

router = APIRouter(prefix="/v1", tags=["ingest"])


@router.post("/ingest", response_model=IngestResponse)
def ingest(req: IngestRequest) -> IngestResponse:
    try:
        result = ingest_directory(req.source_dir, reset=req.reset)
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
    allowed = allowed_suffixes()
    payloads: list[tuple[str, bytes]] = []
    for f in files:
        name = f.filename or "upload"
        if Path(name).suffix.lower() not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"unsupported file type: {name}. accepted extensions: {sorted(allowed)}",
            )
        payloads.append((name, await f.read()))

    try:
        result = ingest_files(payloads, reset=reset)
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
    docs = list_indexed_documents()
    return DocumentsResponse(
        documents=[IndexedDocumentOut(**vars(d)) for d in docs],
        total_chunks=sum(d.chunks for d in docs),
    )


@router.delete("/documents/{source:path}")
def remove_document(source: str) -> dict:
    """Drop a document from the index. `:path` so sources with slashes still match."""
    removed = delete_document(source)
    if removed == 0:
        raise HTTPException(status_code=404, detail=f"document not indexed: {source}")
    return {"deleted": True, "source": source, "chunks_removed": removed}


@router.get("/system", response_model=SystemResponse)
def system() -> SystemResponse:
    """Model wiring + corpus size for the UI's system panel."""
    cfg = get_config()
    docs = list_indexed_documents()
    return SystemResponse(
        generation_model=cfg.models.generation.name,
        embedding_model=cfg.models.embedding.name.split("/")[-1],
        retrieval_mode=cfg.retrieval.mode,
        documents=len(docs),
        chunks=sum(d.chunks for d in docs),
    )
