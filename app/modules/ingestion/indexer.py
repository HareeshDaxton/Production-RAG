"""Embed chunks (local) and write them to the ChromaDB dense index."""
from __future__ import annotations

from app.clients.embeddings import get_embedder
from app.clients.vectorstore import get_chunks_collection
from app.logging_config import get_logger
from app.modules.ingestion.chunker import Chunk

logger = get_logger(__name__)


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
        metadatas=[
            {
                "doc_id": c.doc_id,
                "source": c.source,
                "section_path": c.section_path,
                "chunk_index": c.chunk_index,
                "token_count": c.token_count,
                "strategy": c.strategy,
            }
            for c in chunks
        ],
    )
    logger.info("chunks indexed", extra={"count": len(chunks)})
    return len(chunks)
