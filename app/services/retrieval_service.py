"""Retrieval service (Phase 9B) — dense + BM25 + fusion + cross-encoder rerank.

This is the only process that needs torch, which is the point of splitting it
out: the api container drops ~2GB of model machinery it never uses.

    RAG_SERVICE_ROLE=retrieval uvicorn app.services.retrieval_service:app --port 8011

It talks to the shared vector store directly (that is why Phase 9A came first —
a local Chroma/SQLite file cannot be shared between containers, Postgres can).
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.config import get_config
from app.logging_config import get_logger, setup_logging
from app.models.internal import ChunkOut, RetrieveRequest, RetrieveResponse
from app.modules.retrieval.retriever import retrieve_local
from app.modules.retrieval.sparse import rebuild_bm25_index

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_config()
    setup_logging(cfg.app.log_level)
    cfg.paths.ensure()
    logger.info("retrieval service ready", extra={"mode": cfg.retrieval.mode})
    yield


app = FastAPI(title="rag-retrieval", version=__version__, lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "retrieval", "version": __version__}


@app.get("/ready")
def ready() -> dict:
    """Ready means the vector store answers — retrieval is useless without it."""
    from app.clients.vectorstore import get_vector_store

    try:
        chunks = get_vector_store().count()
    except Exception as exc:  # noqa: BLE001 - report, don't crash readiness
        return {"status": "degraded", "checks": {"vectors": f"error: {exc}"}}
    return {"status": "ok", "checks": {"vectors": "ok"}, "chunks": chunks}


@app.post("/internal/retrieve", response_model=RetrieveResponse)
def retrieve(req: RetrieveRequest) -> RetrieveResponse:
    # retrieve_local, not retrieve: the facade would route straight back here.
    result = retrieve_local(req.query, req.top_k, req.mode, req.filters)
    return RetrieveResponse(
        chunks=[ChunkOut.of(c) for c in result.chunks],
        confidence=result.confidence,
        mode=result.mode,
    )


@app.post("/internal/bm25/rebuild")
def rebuild() -> dict:
    """Rebuild the keyword index from the vector store.

    BM25 lives with the service that queries it, so ingestion asks for a rebuild
    after indexing rather than writing the index across a container boundary.
    """
    return {"chunks": rebuild_bm25_index()}
