"""Composite confidence: blend three independent signals into one 0-1 score.

    composite = w_retrieval * retrieval_confidence   (Phase 2: were the chunks good?)
              + w_citation  * citation_accuracy      (did the judge back the citations?)
              + w_self      * self_confidence         (how sure was the model itself?)

Weights are config-driven and normalised, so no single signal can dominate silently.
The pipeline compares the result against `quality.idk_threshold` to decide whether to
answer or return a graceful "I don't know".
"""
from __future__ import annotations

from collections.abc import Sequence

from app.config import ConfidenceWeights
from app.modules.quality.verifier import CitationCheck

_VERDICT_SCORE = {"supported": 1.0, "partial": 0.5, "unsupported": 0.0}


def citation_accuracy(checks: Sequence[CitationCheck]) -> float:
    """Fraction of citations the judge supports (partial = half credit).

    No citations at all → 0.0: an answer with zero grounding should not score high.
    """
    if not checks:
        return 0.0
    return sum(_VERDICT_SCORE[c.verdict] for c in checks) / len(checks)


def composite_confidence(
    *,
    retrieval: float,
    citation: float,
    self_confidence: float,
    weights: ConfidenceWeights,
) -> float:
    total = weights.retrieval + weights.citation + weights.self
    if total <= 0:
        return 0.0
    score = (
        weights.retrieval * retrieval
        + weights.citation * citation
        + weights.self * self_confidence
    ) / total
    return round(max(0.0, min(1.0, score)), 4)
