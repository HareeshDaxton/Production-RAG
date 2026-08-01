"""HTTP client for the retrieval service, shaped like the in-process function.

`retrieve()` here takes and returns exactly what `retriever.retrieve_local()`
does, so the caller cannot tell which one it got. That symmetry is what keeps
`pipeline.py` free of any distribution logic.
"""
from __future__ import annotations

import httpx

from app.config import get_config
from app.logging_config import get_logger
from app.models.internal import RetrieveRequest, RetrieveResponse
from app.modules.retrieval.filters import Filters

logger = get_logger(__name__)


class RetrievalServiceError(RuntimeError):
    """The retrieval service could not be reached or failed."""


def _client() -> httpx.Client:
    cfg = get_config().services
    return httpx.Client(
        base_url=cfg.retrieval_url,
        timeout=httpx.Timeout(cfg.timeout_seconds, connect=cfg.connect_timeout_seconds),
    )


def retrieve(
    query: str, top_k: int, mode: str | None = None, filters: Filters | None = None
) -> RetrieveResponse:
    payload = RetrieveRequest(query=query, top_k=top_k, mode=mode, filters=filters)
    try:
        with _client() as client:
            res = client.post("/internal/retrieve", json=payload.model_dump())
            res.raise_for_status()
            return RetrieveResponse.model_validate(res.json())
    except httpx.HTTPError as exc:
        # Retrieval is not optional — an unanswerable question is better than a
        # silently empty context that the model would then hallucinate around.
        raise RetrievalServiceError(f"retrieval service unavailable: {exc}") from exc


def rebuild_bm25() -> int:
    """Ask retrieval to rebuild its keyword index (called after an ingest)."""
    try:
        with _client() as client:
            res = client.post("/internal/bm25/rebuild")
            res.raise_for_status()
            return int(res.json().get("chunks", 0))
    except httpx.HTTPError as exc:
        # A stale BM25 index degrades ranking; it does not invalidate the ingest.
        logger.warning("bm25 rebuild call failed", extra={"error": str(exc)})
        return 0
