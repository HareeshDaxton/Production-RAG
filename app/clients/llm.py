"""Unified LLM client.

Phase 0 scope: OpenAI generation, with an `instructor`-patched client ready for the
structured (Pydantic) outputs used from Phase 1 onward. The judge path is configurable
(OpenAI now, Ollama later); embeddings/rerank stay local (see embeddings.py/reranker.py).
"""
from __future__ import annotations

from functools import lru_cache

from app.config import get_config, get_settings
from app.logging_config import get_logger

logger = get_logger(__name__)


@lru_cache
def get_openai_client():
    """Raw synchronous OpenAI client."""
    from openai import OpenAI

    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    return OpenAI(api_key=settings.openai_api_key)


@lru_cache
def get_instructor_client():
    """OpenAI client patched by instructor to enforce Pydantic response schemas."""
    import instructor

    return instructor.from_openai(get_openai_client())


def simple_generate(prompt: str, model: str | None = None, max_tokens: int = 64) -> str:
    """Minimal unstructured completion — used by the Phase 0 generation smoke test."""
    cfg = get_config().models.generation
    resp = get_openai_client().chat.completions.create(
        model=model or cfg.name,
        messages=[{"role": "user", "content": prompt}],
        temperature=cfg.temperature,
        max_tokens=max_tokens,
        timeout=cfg.timeout,
    )
    return resp.choices[0].message.content or ""
