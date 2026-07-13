"""Hybrid retrieval: dense + BM25 → RRF fusion → cross-encoder rerank → confidence.

Pipeline:
    1. dense_retrieve  -> top `dense_candidates`   (semantic matches)
    2. sparse_retrieve -> top `sparse_candidates`  (exact-term matches)
    3. RRF fusion of the two rankings (config weights) -> one ranked list
    4. cross-encoder rerank of the top `rerank_candidates` -> final `top_k`
    5. retrieval confidence from the top rerank score

Returns the same `RetrievedChunk` list the Phase 1 pipeline already consumes, so
generation is unchanged; only ranking quality improves.
"""
from __future__ import annotations

from app.clients.reranker import get_reranker
from app.config import get_config
from app.logging_config import get_logger
from app.modules.retrieval.confidence import retrieval_confidence
from app.modules.retrieval.dense import RetrievedChunk, dense_retrieve
from app.modules.retrieval.fusion import reciprocal_rank_fusion
from app.modules.retrieval.sparse import sparse_retrieve

logger = get_logger(__name__)


def hybrid_retrieve(query: str, top_k: int) -> tuple[list[RetrievedChunk], float]:
    cfg = get_config().retrieval

    dense_hits = dense_retrieve(query, cfg.dense_candidates)
    sparse_hits = sparse_retrieve(query, cfg.sparse_candidates)
    if not dense_hits and not sparse_hits:
        return [], 0.0

    # id -> chunk (dense text preferred; identical text either way)
    pool: dict[str, RetrievedChunk] = {}
    for h in sparse_hits:
        pool[h.chunk_id] = h
    for h in dense_hits:
        pool[h.chunk_id] = h

    fused = reciprocal_rank_fusion(
        [[h.chunk_id for h in dense_hits], [h.chunk_id for h in sparse_hits]],
        weights=[cfg.dense_weight, cfg.sparse_weight],
        k=cfg.rrf_k,
    )
    candidate_ids = [cid for cid, _ in fused[: cfg.rerank_candidates]]
    candidates = [(cid, pool[cid].text) for cid in candidate_ids]

    reranked = get_reranker().rerank(query, candidates, top_k)  # [(id, score)] desc
    results = [
        RetrievedChunk(
            chunk_id=cid,
            text=pool[cid].text,
            source=pool[cid].source,
            section_path=pool[cid].section_path,
            score=score,  # cross-encoder relevance score
        )
        for cid, score in reranked
    ]
    confidence = retrieval_confidence([s for _, s in reranked], kind="cross_encoder")
    logger.info(
        "hybrid retrieval",
        extra={
            "dense": len(dense_hits),
            "sparse": len(sparse_hits),
            "fused": len(fused),
            "final": len(results),
            "confidence": confidence,
        },
    )
    return results, confidence
