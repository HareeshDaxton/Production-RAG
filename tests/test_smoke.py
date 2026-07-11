"""Phase 0 smoke tests.

- config loads and is typed
- FastAPI /health and /ready respond
- local embedding round-trips to the configured dimensionality
- (optional) OpenAI generation round-trips when a key is present
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import get_config, get_settings
from app.main import create_app

client = TestClient(create_app())


def test_config_loads():
    cfg = get_config()
    assert cfg.app.name == "production-rag"
    assert cfg.models.embedding.dimensions == 384
    assert cfg.models.generation.provider == "openai"


def test_health_endpoint():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "production-rag"


def test_ready_endpoint():
    r = client.get("/ready")
    assert r.status_code == 200
    checks = r.json()["checks"]
    assert checks.get("sqlite") == "ok"
    assert checks.get("chroma") == "ok"


@pytest.mark.slow
def test_local_embedding_roundtrip():
    from app.clients.embeddings import get_embedder

    vec = get_embedder().embed_query("How do I declare a path operation in FastAPI?")
    assert len(vec) == get_config().models.embedding.dimensions


@pytest.mark.skipif(
    not get_settings().openai_api_key, reason="OPENAI_API_KEY not set"
)
def test_generation_roundtrip():
    from app.clients.llm import simple_generate

    out = simple_generate("Reply with exactly one word: pong", max_tokens=5)
    assert isinstance(out, str) and out.strip()
