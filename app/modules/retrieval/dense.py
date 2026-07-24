"""Dense retrieval: embed the query and pull nearest chunks from ChromaDB."""
from __future__ import annotations

from dataclasses import dataclass

from app.clients.embeddings import get_embedder
from app.clients.vectorstore import get_chunks_collection
from app.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    source: str
    section_path: str
    score: float  # cosine similarity in [0, 1] (higher = closer)
    # --- per-chunk metadata (defaults keep older constructors working) ---
    file_type: str = ""
    title: str = ""
    page_number: int | None = None
    locator: str | None = None
    content_type: str = "text"


def chunk_from_meta(chunk_id: str, text: str, meta: dict | None, score: float) -> RetrievedChunk:
    """Build a RetrievedChunk from a Chroma/BM25 metadata dict (shared by dense + sparse)."""
    meta = meta or {}
    return RetrievedChunk(
        chunk_id=chunk_id,
        text=text,
        source=meta.get("source", ""),
        section_path=meta.get("section_path", ""),
        score=score,
        file_type=meta.get("file_type", ""),
        title=meta.get("title", ""),
        page_number=meta.get("page_number"),
        locator=meta.get("locator"),
        content_type=meta.get("content_type", "text"),
    )


def dense_retrieve(query: str, top_k: int) -> list[RetrievedChunk]:
    collection = get_chunks_collection()
    if collection.count() == 0:
        return []

    qvec = get_embedder().embed_query(query)  # query-side prefix applied here
    res = collection.query(
        query_embeddings=[qvec],
        n_results=min(top_k, collection.count()),
    )
    ids = res["ids"][0]
    docs = res["documents"][0]
    metas = res["metadatas"][0]
    dists = res["distances"][0]

    hits = [
        chunk_from_meta(cid, text, meta, 1.0 - float(dist))  # chroma cosine distance -> similarity
        for cid, text, meta, dist in zip(ids, docs, metas, dists, strict=False)
    ]
    logger.info("dense retrieval", extra={"query_len": len(query), "hits": len(hits)})
    return hits
