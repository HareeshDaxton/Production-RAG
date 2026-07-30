"""Retrieval confidence: one 0–1 number for "how good are these chunks?".

Phase 2 keeps it simple and honest — it normalises the top result's score to [0, 1].
Cross-encoder scores are logits, so we squash them with a sigmoid; cosine similarities
are already in range and just get clamped. Phase 3 folds this into a composite score
(retrieval + citation accuracy + LLM self-confidence) that gates the graceful "I don't know".
"""
from __future__ import annotations

import math
from collections.abc import Sequence

# Chunks that are records rather than prose. The cross-encoder (`ms-marco-MiniLM`) is
# trained on natural-language passages, so it scores these around -7..-11 however
# relevant they are — a sigmoid of that is ~0, which would refuse every question about
# a CSV/JSON/XML file. For them the dense cosine is the honest signal.
STRUCTURED_CONTENT_TYPES = frozenset({"row", "object", "element"})


def is_structured(content_type: str | None) -> bool:
    return (content_type or "") in STRUCTURED_CONTENT_TYPES


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def retrieval_confidence(scores: Sequence[float], *, kind: str) -> float:
    """Normalise the best score to [0, 1]. `kind` is "cross_encoder" or "similarity"."""
    if not scores:
        return 0.0
    top = float(scores[0])
    norm = _sigmoid(top) if kind == "cross_encoder" else max(0.0, min(1.0, top))
    return round(norm, 4)
