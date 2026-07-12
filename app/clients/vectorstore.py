"""ChromaDB persistent vector store (dense index for chunks)."""
from __future__ import annotations

from functools import lru_cache

from app.config import get_config
from app.logging_config import get_logger

logger = get_logger(__name__)

CHUNKS_COLLECTION = "chunks"


@lru_cache
def get_chroma_client():
    import chromadb

    cfg = get_config()
    cfg.paths.chroma_dir.mkdir(parents=True, exist_ok=True)
    path = str(cfg.paths.chroma_dir)
    logger.info("opening chroma", extra={"path": path})
    return chromadb.PersistentClient(path=path)


def get_chunks_collection():
    """Dense chunk collection. Cosine space to match normalised embeddings."""
    return get_chroma_client().get_or_create_collection(
        name=CHUNKS_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )


def reset_chunks_collection():
    """Drop and recreate the chunk collection (used for clean re-ingest / tests)."""
    client = get_chroma_client()
    try:
        client.delete_collection(CHUNKS_COLLECTION)
    except Exception:  # noqa: BLE001 - absent collection is fine
        pass
    logger.info("chunks collection reset")
    return get_chunks_collection()
