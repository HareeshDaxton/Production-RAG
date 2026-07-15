"""Redis Stack (RediSearch) client for the semantic cache.

Stores each answered query as a HASH: its query embedding (a COSINE HNSW vector),
a params-hash + corpus-version (TAG filters), and the serialized response. Lookups do
a KNN-1 search pre-filtered to the same params + corpus version.

Everything degrades gracefully: if the cache is disabled or Redis is unreachable, every
method is a no-op / miss and the pipeline runs normally. The cache must never break /ask.
"""
from __future__ import annotations

import uuid
from functools import lru_cache

import numpy as np

from app.config import get_config
from app.logging_config import get_logger

logger = get_logger(__name__)

_STATS_PREFIX = "cachestats:"  # deliberately NOT under key_prefix so it isn't indexed


class SemanticCacheClient:
    def __init__(self):
        cfg = get_config()
        self.cfg = cfg.cache
        self.dim = cfg.models.embedding.dimensions
        self._redis = None
        self._ready = False

    # --- connection / index --------------------------------------------------

    @property
    def redis(self):
        if self._redis is None:
            import redis

            # Bounded timeouts so a down/slow Redis never hangs /ask (a refused port
            # still fails instantly; the timeout only caps unreachable-host waits).
            self._redis = redis.Redis.from_url(
                self.cfg.redis_url,
                decode_responses=False,
                socket_connect_timeout=3.0,
                socket_timeout=3.0,
            )
        return self._redis

    def available(self) -> bool:
        """True if the cache is enabled and Redis answers PING (index ensured once)."""
        if not self.cfg.enabled:
            return False
        try:
            self.redis.ping()
            if not self._ready:
                self._ensure_index()
                self._ready = True
            return True
        except Exception as exc:  # noqa: BLE001 - any Redis problem → run without cache
            logger.warning("semantic cache unavailable", extra={"error": str(exc)})
            return False

    def _ensure_index(self) -> None:
        from redis.commands.search.field import TagField, VectorField
        from redis.commands.search.index_definition import IndexDefinition, IndexType

        try:
            self.redis.ft(self.cfg.index_name).info()
            return  # already exists
        except Exception:  # noqa: BLE001 - not found → create it
            pass
        schema = (
            VectorField(
                "embedding",
                "HNSW",
                {"TYPE": "FLOAT32", "DIM": self.dim, "DISTANCE_METRIC": "COSINE"},
            ),
            TagField("params_hash"),
            TagField("corpus_version"),
        )
        definition = IndexDefinition(prefix=[self.cfg.key_prefix], index_type=IndexType.HASH)
        self.redis.ft(self.cfg.index_name).create_index(schema, definition=definition)
        logger.info("semantic cache index created", extra={"index": self.cfg.index_name})

    # --- read / write --------------------------------------------------------

    @staticmethod
    def _to_bytes(vec: list[float]) -> bytes:
        return np.asarray(vec, dtype=np.float32).tobytes()

    def search(
        self, vec: list[float], params_hash: str, corpus_version: str
    ) -> tuple[float, str] | None:
        """Return (cosine_similarity, response_json) of the nearest matching entry, or None."""
        from redis.commands.search.query import Query

        q = (
            Query(f"(@params_hash:{{{params_hash}}} @corpus_version:{{{corpus_version}}})"
                  "=>[KNN 1 @embedding $vec AS dist]")
            .return_fields("dist", "response")
            .sort_by("dist")
            .dialect(2)
        )
        try:
            res = self.redis.ft(self.cfg.index_name).search(
                q, query_params={"vec": self._to_bytes(vec)}
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("cache search failed", extra={"error": str(exc)})
            return None
        if not res.docs:
            return None
        doc = res.docs[0]
        similarity = 1.0 - float(doc.dist)  # COSINE distance → similarity
        response = doc.response
        if isinstance(response, bytes):
            response = response.decode("utf-8")
        return similarity, response

    def store(
        self,
        vec: list[float],
        params_hash: str,
        corpus_version: str,
        query: str,
        response_json: str,
    ) -> None:
        key = f"{self.cfg.key_prefix}{uuid.uuid4().hex}"
        try:
            self.redis.hset(
                key,
                mapping={
                    "embedding": self._to_bytes(vec),
                    "params_hash": params_hash,
                    "corpus_version": corpus_version,
                    "query": query,
                    "response": response_json,
                },
            )
            self.redis.expire(key, self.cfg.ttl_seconds)
        except Exception as exc:  # noqa: BLE001
            logger.warning("cache store failed", extra={"error": str(exc)})

    def flush(self) -> int:
        """Delete all cached entries (keeps the index). Returns count removed."""
        removed = 0
        try:
            for key in self.redis.scan_iter(match=f"{self.cfg.key_prefix}*"):
                self.redis.delete(key)
                removed += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("cache flush failed", extra={"error": str(exc)})
        return removed

    # --- stats ---------------------------------------------------------------

    def incr_stat(self, name: str) -> None:
        try:
            self.redis.incr(f"{_STATS_PREFIX}{name}")
        except Exception:  # noqa: BLE001 - stats are best-effort
            pass

    def get_stats(self) -> dict[str, int]:
        out = {"hit": 0, "miss": 0, "near_miss": 0}
        try:
            for name in out:
                val = self.redis.get(f"{_STATS_PREFIX}{name}")
                out[name] = int(val) if val else 0
        except Exception:  # noqa: BLE001
            pass
        return out


@lru_cache
def get_cache_client() -> SemanticCacheClient:
    return SemanticCacheClient()
