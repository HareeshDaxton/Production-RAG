"""Phase 5: params-hash (fast) + a real Redis cache hit on paraphrase (slow, gated)."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.config import get_settings
from app.modules.cache.service import params_hash

SAMPLE_DOCS = Path(__file__).resolve().parent.parent / "sample_docs"


# --- fast: params hash -------------------------------------------------------


def test_params_hash_stable_and_sensitive():
    base = params_hash(5, "hybrid")
    assert base == params_hash(5, "hybrid")  # deterministic
    assert base != params_hash(3, "hybrid")  # top_k changes it
    assert base != params_hash(5, "dense")   # mode changes it


# --- slow: real Redis + generation -------------------------------------------


def _redis_up() -> bool:
    try:
        from app.clients.cache import get_cache_client

        return get_cache_client().available()
    except Exception:  # noqa: BLE001
        return False


needs_redis_key = pytest.mark.skipif(
    not (_redis_up() and get_settings().openai_api_key),
    reason="requires Redis (docker compose up -d redis) and OPENAI_API_KEY",
)


@pytest.mark.slow
@needs_redis_key
def test_paraphrase_hits_cache():
    from app.modules.cache import service as cache
    from app.modules.ingestion.service import ingest_directory
    from app.modules.pipeline import ask

    ingest_directory(SAMPLE_DOCS, reset=True)
    cache.flush()

    first = ask("How do I declare a path parameter as an int?")
    assert first.cached is False  # cold → computed

    second = ask("How do I specify an int type for a path parameter?")
    assert second.cached is True  # paraphrase → served from cache
    assert second.cache_similarity is not None and second.cache_similarity >= 0.9
    assert second.answer == first.answer
