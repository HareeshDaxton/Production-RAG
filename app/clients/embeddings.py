"""Embedding models behind one interface.

Two providers, selected by `models.embedding.provider`:

- `local`  — sentence-transformers on CPU. Free, no network, but every ingest and
  every query runs a transformer forward pass on the machine.
- `openai` — the embeddings API (`text-embedding-3-*`). No CPU cost and no model
  weights to load, at the price of a network call and a per-token charge.

Both expose `embed_texts` (document side) and `embed_query` (query side), so the
retriever, indexer, cache and auto-eval call sites are provider-agnostic.
"""
from __future__ import annotations

import math
from functools import lru_cache

from app.config import EmbeddingConfig, get_config
from app.logging_config import get_logger

logger = get_logger(__name__)


class LocalEmbedder:
    def __init__(self, cfg: EmbeddingConfig):
        self.cfg = cfg
        self._model = None

    @property
    def model(self):
        # Heavy import + weight load deferred until first use (keeps API startup fast).
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("loading embedding model", extra={"model": self.cfg.name})
            self._model = SentenceTransformer(self.cfg.name, device=self.cfg.device)
        return self._model

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed documents/passages (no query prefix)."""
        vecs = self.model.encode(
            texts,
            batch_size=self.cfg.batch_size,
            normalize_embeddings=self.cfg.normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return vecs.tolist()

    def embed_query(self, query: str) -> list[float]:
        """Embed a search query (applies the retrieval instruction prefix)."""
        text = f"{self.cfg.query_prefix}{query}" if self.cfg.query_prefix else query
        return self.embed_texts([text])[0]


class OpenAIEmbedder:
    """OpenAI embeddings API. No local weights, no CPU inference."""

    def __init__(self, cfg: EmbeddingConfig):
        self.cfg = cfg

    def _kwargs(self) -> dict:
        # Only the v3 models accept `dimensions`; passing it keeps config the single
        # source of truth for the vector width the store and cache are built around.
        if self.cfg.name.startswith("text-embedding-3") and self.cfg.dimensions:
            return {"dimensions": self.cfg.dimensions}
        return {}

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        from app.clients.llm import get_openai_client

        client = get_openai_client()
        vectors: list[list[float]] = []
        # One request per batch: the API takes a list, and batching keeps a large
        # ingest from opening thousands of connections.
        for start in range(0, len(texts), self.cfg.batch_size):
            batch = texts[start : start + self.cfg.batch_size]
            resp = client.embeddings.create(model=self.cfg.name, input=batch, **self._kwargs())
            vectors.extend(item.embedding for item in sorted(resp.data, key=lambda d: d.index))
        return [_unit(v) for v in vectors] if self.cfg.normalize else vectors

    def embed_query(self, query: str) -> list[float]:
        """No instruction prefix: that is a bge convention, not an OpenAI one."""
        text = f"{self.cfg.query_prefix}{query}" if self.cfg.query_prefix else query
        return self.embed_texts([text])[0]


def _unit(vec: list[float]) -> list[float]:
    """Scale to unit length so cosine similarity is a plain dot product.

    Full-width v3 vectors already arrive normalised, but shortened ones (the
    `dimensions` parameter) do not, and the cache compares raw cosines.
    """
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm else vec


@lru_cache
def get_embedder() -> LocalEmbedder | OpenAIEmbedder:
    cfg = get_config().models.embedding
    if cfg.provider == "openai":
        logger.info("using openai embeddings", extra={"model": cfg.name, "dim": cfg.dimensions})
        return OpenAIEmbedder(cfg)
    return LocalEmbedder(cfg)
