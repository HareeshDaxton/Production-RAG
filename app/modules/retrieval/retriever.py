"""Top-level retrieval dispatcher: pick dense or hybrid, return chunks + confidence.

The pipeline calls `retrieve()` and never needs to know which strategy ran. Mode is
config-driven (`retrieval.mode`) with an optional per-request override, so the
dense-vs-hybrid A/B demo is a single field on `/v1/ask`.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.config import get_config
from app.modules.retrieval.confidence import retrieval_confidence
from app.modules.retrieval.dense import RetrievedChunk, dense_retrieve
from app.modules.retrieval.hybrid import hybrid_retrieve

VALID_MODES = ("hybrid", "dense")


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk]
    confidence: float
    mode: str


def retrieve(query: str, top_k: int, mode: str | None = None) -> RetrievalResult:
    resolved = (mode or get_config().retrieval.mode).lower()
    if resolved not in VALID_MODES:
        resolved = "hybrid"

    if resolved == "dense":
        chunks = dense_retrieve(query, top_k)
        confidence = retrieval_confidence([c.score for c in chunks], kind="similarity")
        return RetrievalResult(chunks=chunks, confidence=confidence, mode="dense")

    chunks, confidence = hybrid_retrieve(query, top_k)
    return RetrievalResult(chunks=chunks, confidence=confidence, mode="hybrid")
