"""Local cross-encoder reranker. Loaded lazily; actively used from Phase 2."""
from __future__ import annotations

from functools import lru_cache

from app.config import RerankerConfig, get_config
from app.logging_config import get_logger

logger = get_logger(__name__)


class CrossEncoderReranker:
    def __init__(self, cfg: RerankerConfig):
        self.cfg = cfg
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder

            logger.info("loading reranker model", extra={"model": self.cfg.name})
            self._model = CrossEncoder(self.cfg.name, device=self.cfg.device)
        return self._model

    def rerank(
        self, query: str, candidates: list[tuple[str, str]], top_k: int
    ) -> list[tuple[str, float]]:
        """candidates = [(chunk_id, text)] -> [(chunk_id, score)] sorted desc, top_k."""
        if not candidates:
            return []
        pairs = [(query, text) for _, text in candidates]
        scores = self.model.predict(pairs)
        ranked = sorted(
            ((cid, float(score)) for (cid, _), score in zip(candidates, scores)),
            key=lambda x: x[1],
            reverse=True,
        )
        return ranked[:top_k]


@lru_cache
def get_reranker() -> CrossEncoderReranker:
    return CrossEncoderReranker(get_config().models.reranker)
