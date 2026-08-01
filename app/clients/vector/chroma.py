"""ChromaDB backend — the zero-infrastructure default (tests, laptop runs).

Behaviour is exactly what the app did through Phase 8; this only moves it behind
the `VectorStore` interface so pgvector can stand in its place.
"""
from __future__ import annotations

from app.clients.vector.base import StoredChunks, VectorHit
from app.config import get_config
from app.logging_config import get_logger

logger = get_logger(__name__)

CHUNKS_COLLECTION = "chunks"


def _client():
    import chromadb

    cfg = get_config()
    cfg.paths.chroma_dir.mkdir(parents=True, exist_ok=True)
    path = str(cfg.paths.chroma_dir)
    logger.info("opening chroma", extra={"path": path})
    return chromadb.PersistentClient(path=path)


class ChromaVectorStore:
    def __init__(self):
        self._chroma = None

    @property
    def _c(self):
        if self._chroma is None:
            self._chroma = _client()
        return self._chroma

    @property
    def collection(self):
        """Cosine space, to match the normalised embeddings we store."""
        return self._c.get_or_create_collection(
            name=CHUNKS_COLLECTION, metadata={"hnsw:space": "cosine"}
        )

    def add(self, ids, embeddings, documents, metadatas) -> None:
        self.collection.add(
            ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas
        )

    def query(self, embedding, top_k, where=None) -> list[VectorHit]:
        collection = self.collection
        total = collection.count()
        if total == 0:
            return []
        res = collection.query(
            query_embeddings=[embedding], n_results=min(top_k, total), where=where
        )
        return [
            VectorHit(chunk_id=cid, document=doc, metadata=meta or {}, distance=float(dist))
            for cid, doc, meta, dist in zip(
                res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0],
                strict=False,
            )
        ]

    def fetch_all(self) -> StoredChunks:
        data = self.collection.get(include=["documents", "metadatas"])
        return StoredChunks(
            ids=list(data.get("ids") or []),
            documents=list(data.get("documents") or []),
            metadatas=[m or {} for m in (data.get("metadatas") or [])],
        )

    def ids_where(self, where: dict) -> list[str]:
        return list(self.collection.get(where=where, include=[]).get("ids") or [])

    def delete_ids(self, ids: list[str]) -> None:
        if ids:
            self.collection.delete(ids=ids)

    def delete_where(self, where: dict) -> None:
        try:
            self.collection.delete(where=where)
        except Exception:  # noqa: BLE001 - empty/absent collection is fine
            logger.debug("no matching chunks to delete")

    def count(self) -> int:
        return self.collection.count()

    def dimension(self) -> int | None:
        try:
            stored = self.collection.get(limit=1, include=["embeddings"])["embeddings"]
        except Exception:  # noqa: BLE001 - an unreadable collection is not this check's problem
            return None
        if stored is None or len(stored) == 0:
            return None
        return len(stored[0])

    def reset(self) -> None:
        try:
            self._c.delete_collection(CHUNKS_COLLECTION)
        except Exception:  # noqa: BLE001 - absent collection is fine
            pass
        logger.info("chunks collection reset")
        self.collection  # noqa: B018 - recreate eagerly so callers see an empty store
