"""HTTP client for the ingestion service, shaped like the in-process functions.

Mirrors `ingestion/service.py`: same arguments, same return types, so routers do
not branch on whether the split is switched on.
"""
from __future__ import annotations

import httpx

from app.config import get_config
from app.logging_config import get_logger
from app.models.internal import (
    DeleteResult,
    DocumentOut,
    DocumentsOut,
    IngestDirectoryRequest,
    IngestResult,
)

logger = get_logger(__name__)


class IngestionServiceError(RuntimeError):
    """The ingestion service could not be reached or failed.

    `status_code` carries the service's own status so the api can pass a
    validation failure through as a 400 rather than flattening it to a 502.
    """

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def _client() -> httpx.Client:
    cfg = get_config().services
    return httpx.Client(
        base_url=cfg.ingestion_url,
        timeout=httpx.Timeout(cfg.timeout_seconds, connect=cfg.connect_timeout_seconds),
    )


def _post(path: str, **kwargs) -> dict:
    try:
        with _client() as client:
            res = client.post(path, **kwargs)
            res.raise_for_status()
            return res.json()
    except httpx.HTTPStatusError as exc:
        # Preserve the service's own message (e.g. a 409 dimension mismatch), which
        # is far more useful to the caller than "request failed".
        detail = ""
        try:
            detail = exc.response.json().get("detail", "")
        except Exception:  # noqa: BLE001 - non-JSON error body
            detail = exc.response.text[:200]
        raise IngestionServiceError(detail or str(exc), exc.response.status_code) from exc
    except httpx.HTTPError as exc:
        raise IngestionServiceError(f"ingestion service unavailable: {exc}") from exc


def ingest_directory(source_dir: str | None = None, reset: bool = False) -> IngestResult:
    body = IngestDirectoryRequest(source_dir=source_dir, reset=reset).model_dump()
    return IngestResult.model_validate(_post("/internal/ingest/directory", json=body))


def ingest_files(files: list[tuple[str, bytes]], reset: bool = False) -> IngestResult:
    payload = [("files", (name, data)) for name, data in files]
    return IngestResult.model_validate(
        _post("/internal/ingest/files", files=payload, data={"reset": str(reset).lower()})
    )


def list_indexed_documents() -> list[DocumentOut]:
    """Returns the same shape as the local function: a flat list of documents."""
    try:
        with _client() as client:
            res = client.get("/internal/documents")
            res.raise_for_status()
            return DocumentsOut.model_validate(res.json()).documents
    except httpx.HTTPError as exc:
        raise IngestionServiceError(f"ingestion service unavailable: {exc}") from exc


def delete_document(source: str) -> int:
    try:
        with _client() as client:
            res = client.delete(f"/internal/documents/{source}")
            res.raise_for_status()
            return DeleteResult.model_validate(res.json()).chunks_removed
    except httpx.HTTPError as exc:
        raise IngestionServiceError(f"ingestion service unavailable: {exc}") from exc
