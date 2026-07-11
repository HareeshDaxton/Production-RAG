"""Local embedding model (sentence-transformers). Free, runs on CPU.

Kept local per the hybrid-LLM decision: only final generation uses an API.
"""
from __future__ import annotations

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


@lru_cache
def get_embedder() -> LocalEmbedder:
    return LocalEmbedder(get_config().models.embedding)
