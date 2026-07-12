"""Ingestion orchestrator: load -> chunk -> index, with an audit record."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.clients.db import record_ingestion
from app.clients.vectorstore import reset_chunks_collection
from app.config import get_config
from app.logging_config import get_logger
from app.modules.ingestion.chunker import chunk_document
from app.modules.ingestion.indexer import index_chunks
from app.modules.ingestion.loader import load_documents

logger = get_logger(__name__)


@dataclass
class IngestResult:
    documents: int
    chunks: int
    source_dir: str


def ingest_directory(source_dir: str | Path | None = None, reset: bool = False) -> IngestResult:
    """Ingest all markdown under `source_dir` (defaults to config corpus dir).

    `reset=True` clears the existing chunk collection first (avoids duplicate chunks
    when re-ingesting the same corpus; proper dedup/upsert arrives later).
    """
    cfg = get_config()
    src = Path(source_dir) if source_dir else cfg.ingestion.corpus.dir

    if reset:
        reset_chunks_collection()

    docs = load_documents(src)
    chunks = [c for doc in docs for c in chunk_document(doc, cfg.ingestion.chunking)]
    n = index_chunks(chunks)

    record_ingestion(source=str(src), documents=len(docs), chunks=n)
    logger.info(
        "ingestion complete",
        extra={"documents": len(docs), "chunks": n, "dir": str(src), "reset": reset},
    )
    return IngestResult(documents=len(docs), chunks=n, source_dir=str(src))
