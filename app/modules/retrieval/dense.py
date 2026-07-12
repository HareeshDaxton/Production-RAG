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
        RetrievedChunk(
            chunk_id=cid,
            text=text,
            source=(meta or {}).get("source", ""),
            section_path=(meta or {}).get("section_path", ""),
            score=1.0 - float(dist),  # chroma cosine distance -> similarity
        )
        for cid, text, meta, dist in zip(ids, docs, metas, dists, strict=False)
    ]
    logger.info("dense retrieval", extra={"query_len": len(query), "hits": len(hits)})
    return hits
