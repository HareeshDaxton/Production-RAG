"""Semantic cache service: lookup/store logic, params-hash, corpus-version, stats.

A cache entry is only reused when the query embedding is within `threshold` cosine
similarity of a stored query AND the request params (top_k, mode, generation model,
verify flag) AND the corpus version all match. That conservatism is deliberate — a
loose cache serves subtly-wrong answers, which is worse than a cache miss.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.clients.cache import get_cache_client
from app.clients.db import get_corpus_version
from app.config import get_config
from app.logging_config import get_logger
from app.models.schemas import AskResponse

logger = get_logger(__name__)


@dataclass
class CacheLookup:
    hit: bool
    similarity: float
    response: AskResponse | None


def params_hash(top_k: int, mode: str) -> str:
    """Stable hash of everything that changes the answer besides the query text."""
    cfg = get_config()
    parts = "|".join(
        str(x)
        for x in (
            top_k,
            mode,
            cfg.models.generation.name,
            cfg.quality.verify_citations,
        )
    )
    return hashlib.sha1(parts.encode()).hexdigest()[:16]


def lookup(query: str, embedding: list[float], top_k: int, mode: str) -> CacheLookup:
    """Check the cache. HIT only when similarity >= threshold; near-misses logged, not served."""
    client = get_cache_client()
    if not client.available():
        return CacheLookup(hit=False, similarity=0.0, response=None)

    cfg = get_config().cache
    ph = params_hash(top_k, mode)
    cv = str(get_corpus_version())
    found = client.search(embedding, ph, cv)

    if not found:
        client.incr_stat("miss")
        return CacheLookup(hit=False, similarity=0.0, response=None)

    similarity, response_json = found
    if similarity >= cfg.threshold:
        client.incr_stat("hit")
        resp = AskResponse.model_validate_json(response_json)
        resp.cached = True
        resp.cache_similarity = round(similarity, 4)
        logger.info("cache hit", extra={"similarity": round(similarity, 4)})
        return CacheLookup(hit=True, similarity=similarity, response=resp)

    if similarity >= cfg.threshold - cfg.near_miss_margin:
        client.incr_stat("near_miss")
        logger.info("cache near-miss", extra={"similarity": round(similarity, 4)})
    else:
        client.incr_stat("miss")
    return CacheLookup(hit=False, similarity=similarity, response=None)


def store(query: str, embedding: list[float], top_k: int, mode: str, response: AskResponse) -> None:
    client = get_cache_client()
    if not client.available():
        return
    ph = params_hash(top_k, mode)
    cv = str(get_corpus_version())
    # Persist the un-cached form so a later hit reports cached=true, not the stored value.
    to_store = response.model_copy(update={"cached": False, "cache_similarity": None})
    client.store(embedding, ph, cv, query, to_store.model_dump_json())


def stats() -> dict:
    client = get_cache_client()
    counts = client.get_stats()
    total = counts["hit"] + counts["miss"] + counts["near_miss"]
    hit_rate = round(counts["hit"] / total, 4) if total else 0.0
    cost_saved = round(counts["hit"] * get_config().cache.cost_per_answer_usd, 4)
    return {
        **counts,
        "total": total,
        "hit_rate": hit_rate,
        "cost_saved_usd": cost_saved,
        "available": client.available(),
    }


def flush() -> int:
    return get_cache_client().flush()
