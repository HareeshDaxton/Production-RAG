"""POST /v1/ingest — index a directory of markdown docs."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.schemas import IngestRequest, IngestResponse
from app.modules.ingestion.service import ingest_directory

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
