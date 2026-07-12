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
    texts = [c.text for c in chunks]
    embeddings = get_embedder().embed_texts(texts)  # document-side (no query prefix)
    get_chunks_collection().add(
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
            }
            for c in chunks
        ],
    )
    logger.info("chunks indexed", extra={"count": len(chunks)})
    return len(chunks)
