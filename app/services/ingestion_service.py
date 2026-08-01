"""Ingestion service (Phase 9B) — loaders, OCR, chunking, indexing.

Split out because this work is bursty and slow (OCR can take a minute per
scanned page) and must not compete with live question answering. It owns the
heavy document dependencies: pymupdf, python-docx, easyocr, pillow.

    RAG_SERVICE_ROLE=ingestion uvicorn app.services.ingestion_service:app --port 8012
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from app import __version__
from app.clients.db import init_db
from app.clients.vector.base import EmbeddingDimensionMismatch
from app.config import get_config
from app.logging_config import get_logger, setup_logging
from app.models.internal import (
    DeleteResult,
    DocumentOut,
    DocumentsOut,
    IngestDirectoryRequest,
    IngestResult,
)
from app.modules.ingestion.loader import allowed_suffixes
from app.modules.ingestion.service import (
    delete_document,
    ingest_directory,
    ingest_files,
    list_indexed_documents,
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_config()
    setup_logging(cfg.app.log_level)
    cfg.paths.ensure()
    init_db()
    logger.info("ingestion service ready", extra={"formats": cfg.ingestion.formats.enabled})
    yield


app = FastAPI(title="rag-ingestion", version=__version__, lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "ingestion", "version": __version__}


@app.get("/ready")
def ready() -> dict:
    from app.clients.vectorstore import get_vector_store

    try:
        get_vector_store().count()
    except Exception as exc:  # noqa: BLE001 - report, don't crash readiness
        return {"status": "degraded", "checks": {"vectors": f"error: {exc}"}}
    return {"status": "ok", "checks": {"vectors": "ok"}}


@app.post("/internal/ingest/directory", response_model=IngestResult)
def ingest_dir(req: IngestDirectoryRequest) -> IngestResult:
    try:
        result = ingest_directory(req.source_dir, reset=req.reset)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EmbeddingDimensionMismatch as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return IngestResult(**vars(result))


@app.post("/internal/ingest/files", response_model=IngestResult)
async def ingest_upload(
    files: list[UploadFile] = File(...),
    reset: bool = Form(default=False),
) -> IngestResult:
    allowed = allowed_suffixes()
    payloads: list[tuple[str, bytes]] = []
    for f in files:
        name = f.filename or "upload"
        if Path(name).suffix.lower() not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"unsupported file type: {name}. accepted: {sorted(allowed)}",
            )
        payloads.append((name, await f.read()))

    try:
        result = ingest_files(payloads, reset=reset)
    except EmbeddingDimensionMismatch as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return IngestResult(**vars(result))


@app.get("/internal/documents", response_model=DocumentsOut)
def documents() -> DocumentsOut:
    return DocumentsOut(documents=[DocumentOut(**vars(d)) for d in list_indexed_documents()])


@app.delete("/internal/documents/{source:path}", response_model=DeleteResult)
def remove(source: str) -> DeleteResult:
    return DeleteResult(chunks_removed=delete_document(source))
