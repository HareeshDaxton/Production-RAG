"""Ingestion orchestrator: load -> chunk -> index, with an audit record."""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.clients.db import record_ingestion
from app.clients.vectorstore import get_vector_store, reset_vector_store
from app.config import get_config
from app.logging_config import get_logger
from app.modules.ingestion.chunker import chunk_document
from app.modules.ingestion.indexer import index_chunks
from app.modules.ingestion.loader import load_documents
from app.modules.retrieval.sparse import rebuild_bm25_index
from app.services.role import RETRIEVAL, runs_locally

logger = get_logger(__name__)


def _refresh_keyword_index() -> None:
    """Keep BM25 in step with the vectors.

    The index belongs to whoever queries it, so when retrieval runs in its own
    process the ingestion service asks it to rebuild rather than writing the
    index across a container boundary.
    """
    if runs_locally(RETRIEVAL):
        rebuild_bm25_index()
        return
    from app.clients import retrieval_client

    retrieval_client.rebuild_bm25()


@dataclass
class IngestResult:
    documents: int
    chunks: int
    source_dir: str


@dataclass
class IndexedDocument:
    source: str
    title: str
    file_type: str
    chunks: int
    pages: int | None  # highest page seen (paginated sources only)


def delete_document(source: str) -> int:
    """Remove every chunk belonging to one source. Returns the count deleted.

    The BM25 index is rebuilt afterwards — it is a snapshot of the collection, so
    skipping the rebuild would leave keyword search matching deleted documents.
    """
    store = get_vector_store()
    ids = store.ids_where({"source": source})
    if not ids:
        return 0

    store.delete_ids(ids)
    _refresh_keyword_index()
    # Deleting changes what is retrievable, so cached answers built from this
    # document must not keep being served.
    record_ingestion(f"delete:{source}", 0, 0)
    logger.info("document deleted", extra={"source": source, "chunks": len(ids)})
    return len(ids)


def list_indexed_documents() -> list[IndexedDocument]:
    """Distinct documents currently in the chunk collection.

    The collection is the source of truth for what is searchable — `ingestion_audit`
    only records the directory an ingest ran against, not individual files.
    """
    grouped: dict[str, IndexedDocument] = {}
    for meta in get_vector_store().fetch_all().metadatas:
        meta = meta or {}
        source = str(meta.get("source") or "")
        if not source:
            continue
        page = meta.get("page_number")
        existing = grouped.get(source)
        if existing is None:
            grouped[source] = IndexedDocument(
                source=source,
                title=str(meta.get("title") or source),
                file_type=str(meta.get("file_type") or ""),
                chunks=1,
                pages=int(page) if isinstance(page, int) else None,
            )
        else:
            existing.chunks += 1
            if isinstance(page, int):
                existing.pages = max(existing.pages or 0, page)
    return sorted(grouped.values(), key=lambda d: d.source)


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
        reset_vector_store()

    docs = load_documents(src)
    chunks = [c for doc in docs for c in chunk_document(doc, cfg.ingestion.chunking)]
    n = index_chunks(chunks)

    # Keep the BM25 sparse index in sync with the dense index (hybrid needs both).
    _refresh_keyword_index()

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
