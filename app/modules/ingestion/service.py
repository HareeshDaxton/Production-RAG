"""Ingestion orchestrator: load -> chunk -> index, with an audit record."""
from __future__ import annotations

import tempfile
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

    Re-ingest is idempotent per document: a doc's chunks are replaced on re-run
    (see `index_chunks`), so duplicates never accumulate. `reset=True` additionally
    wipes the *whole* collection first — use it to drop documents that no longer
    exist anywhere in the source, or for a guaranteed-clean rebuild.
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


def ingest_files(files: list[tuple[str, bytes]], reset: bool = False) -> IngestResult:
    """Ingest uploaded markdown files (name + raw bytes) without a corpus directory.

    Writes them to a temp dir and reuses the directory pipeline, so chunking,
    dedup and auditing behave identically to `ingest_directory`. `doc_id`/`source`
    become the uploaded filename.
    """
    if not files:
        return IngestResult(documents=0, chunks=0, source_dir="upload")

    with tempfile.TemporaryDirectory(prefix="rag-upload-") as tmp:
        tmp_dir = Path(tmp)
        for name, data in files:
            # flatten to basename so an uploaded path can't escape the temp dir
            (tmp_dir / Path(name).name).write_bytes(data)
        result = ingest_directory(tmp_dir, reset=reset)

    # Report a stable, human-readable source instead of the temp path.
    return IngestResult(documents=result.documents, chunks=result.chunks, source_dir="upload")
