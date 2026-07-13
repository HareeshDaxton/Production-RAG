"""BM25 sparse retrieval, kept in sync with the dense index.

Dense search matches *meaning*; BM25 matches *exact terms* (function names, error
codes, parameter names) and weights rare words higher. Hybrid search fuses the two.

The chunk collection in ChromaDB is the single source of truth: the BM25 index is
(re)built from `collection.get()` after every ingest and serialized to `paths.bm25_dir`
so it survives restarts. It is small and lives fully in memory at query time.
"""
from __future__ import annotations

import pickle
import re
from dataclasses import dataclass

from app.clients.vectorstore import get_chunks_collection
from app.config import get_config
from app.logging_config import get_logger
from app.modules.retrieval.dense import RetrievedChunk

logger = get_logger(__name__)

_INDEX_FILE = "bm25.pkl"
_TOKEN_RE = re.compile(r"\w+")

# In-process cache so we don't unpickle on every query. Cleared on rebuild.
_cached: BM25Index | None = None


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


@dataclass
class BM25Index:
    ids: list[str]
    texts: list[str]
    metadatas: list[dict]
    bm25: object  # rank_bm25.BM25Okapi (picklable)

    def search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        if not self.ids:
            return []
        scores = self.bm25.get_scores(_tokenize(query))
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        hits: list[RetrievedChunk] = []
        for i in ranked[:top_k]:
            if scores[i] <= 0:  # no term overlap -> not a real match
                continue
            meta = self.metadatas[i] or {}
            hits.append(
                RetrievedChunk(
                    chunk_id=self.ids[i],
                    text=self.texts[i],
                    source=meta.get("source", ""),
                    section_path=meta.get("section_path", ""),
                    score=float(scores[i]),  # raw BM25 score (fusion uses rank, not value)
                )
            )
        return hits


def _index_path():
    cfg = get_config()
    cfg.paths.bm25_dir.mkdir(parents=True, exist_ok=True)
    return cfg.paths.bm25_dir / _INDEX_FILE


def rebuild_bm25_index() -> int:
    """Rebuild the BM25 index from the current chunk collection and persist it."""
    global _cached
    from rank_bm25 import BM25Okapi

    data = get_chunks_collection().get(include=["documents", "metadatas"])
    ids = data.get("ids") or []
    texts = data.get("documents") or []
    metadatas = data.get("metadatas") or []

    corpus = [_tokenize(t) for t in texts]
    # BM25Okapi requires a non-empty corpus; guard the empty-collection case.
    bm25 = BM25Okapi(corpus) if corpus else None
    _cached = BM25Index(ids=ids, texts=texts, metadatas=metadatas, bm25=bm25)

    with _index_path().open("wb") as fh:
        pickle.dump(_cached, fh)
    logger.info("bm25 index rebuilt", extra={"chunks": len(ids)})
    return len(ids)


def get_bm25_index() -> BM25Index | None:
    """Return the in-memory index, loading from disk (or rebuilding) if needed."""
    global _cached
    if _cached is not None:
        return _cached
    path = _index_path()
    if path.exists():
        with path.open("rb") as fh:
            _cached = pickle.load(fh)
        return _cached
    rebuild_bm25_index()  # first use before any explicit rebuild
    return _cached


def sparse_retrieve(query: str, top_k: int) -> list[RetrievedChunk]:
    index = get_bm25_index()
    if index is None or index.bm25 is None:
        return []
    hits = index.search(query, top_k)
    logger.info("sparse retrieval", extra={"query_len": len(query), "hits": len(hits)})
    return hits
