"""Reciprocal Rank Fusion (RRF): merge several ranked lists into one.

Each list contributes ``weight / (k + rank)`` per item (rank is 1-based). Because it
uses only *positions*, not raw scores, it fuses lists whose scores live on totally
different scales — exactly the dense-similarity vs BM25 situation — without any
normalisation. Items ranked high in multiple lists accumulate the most weight.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[str]],
    weights: Sequence[float] | None = None,
    k: int = 60,
) -> list[tuple[str, float]]:
    """Fuse ranked id-lists → [(id, fused_score)] sorted best-first.

    `ranked_lists[i]` is best-first ids from source i; `weights[i]` scales its votes.
    """
    if weights is None:
        weights = [1.0] * len(ranked_lists)

    scores: dict[str, float] = defaultdict(float)
    for ranking, weight in zip(ranked_lists, weights, strict=False):
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] += weight / (k + rank)

    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
