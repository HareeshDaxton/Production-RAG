"""Embed chunks (local) and write them to the ChromaDB dense index."""
from __future__ import annotations

from app.clients.embeddings import get_embedder
from app.clients.vectorstore import get_chunks_collection
from app.logging_config import get_logger
from app.modules.ingestion.chunker import Chunk

logger = get_logger(__name__)


def _chunk_metadata(c: Chunk) -> dict:
    """Flat-scalar metadata for ChromaDB (nested dicts / None are not allowed).

    Keys whose value is None are omitted — Chroma permits heterogeneous keys per
    document, and omission keeps `where` metadata filters clean.
    """
    md: dict = {
        "doc_id": c.doc_id,
        "source": c.source,
        "file_type": c.file_type,
        "title": c.title,
        "section_path": c.section_path,
        "content_type": c.content_type,
        "chunk_index": c.chunk_index,
        "token_count": c.token_count,
        "char_count": c.char_count,
        "strategy": c.strategy,
    }
    if c.page_number is not None:
        md["page_number"] = c.page_number
    if c.locator is not None:
        md["locator"] = c.locator
    if c.created_at:
        md["created_at"] = c.created_at
    return md


def index_chunks(chunks: list[Chunk]) -> int:
    if not chunks:
        return 0
    collection = get_chunks_collection()

    # Idempotent re-ingest: drop any prior chunks for these documents first, so
    # editing/re-running a doc replaces its chunks (and prunes stale ones) rather
    # than piling up duplicates. Deterministic chunk ids alone would overwrite
    # position-for-position but leave orphans when a doc shrinks; this handles both.
    doc_ids = sorted({c.doc_id for c in chunks})
    try:
        collection.delete(where={"doc_id": {"$in": doc_ids}})
    except Exception:  # noqa: BLE001 - empty/absent collection is fine
        logger.debug("no prior chunks to delete", extra={"docs": len(doc_ids)})

    texts = [c.text for c in chunks]
    embeddings = get_embedder().embed_texts(texts)  # document-side (no query prefix)
    collection.add(
        ids=[c.chunk_id for c in chunks],
        embeddings=embeddings,
        documents=texts,
        metadatas=[_chunk_metadata(c) for c in chunks],
    )
    logger.info("chunks indexed", extra={"count": len(chunks)})
    return len(chunks)
