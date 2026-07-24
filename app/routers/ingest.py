"""POST /v1/ingest — index a directory of markdown docs, or upload files directly."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.models.schemas import IngestRequest, IngestResponse
from app.modules.ingestion.loader import allowed_suffixes
from app.modules.ingestion.service import ingest_directory, ingest_files

router = APIRouter(prefix="/v1", tags=["ingest"])


@router.post("/ingest", response_model=IngestResponse)
def ingest(req: IngestRequest) -> IngestResponse:
    try:
        result = ingest_directory(req.source_dir, reset=req.reset)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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

    result = ingest_files(payloads, reset=reset)
    return IngestResponse(
        documents_ingested=result.documents,
        chunks_created=result.chunks,
        source_dir=result.source_dir,
    )
