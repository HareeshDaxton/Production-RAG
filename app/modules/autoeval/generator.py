"""Draft a reference case for a flagged query, with a double-run agreement + dedup check.

The draft is a *proposal* for human review, never trusted on its own — that's what keeps
the golden set credible. We run the draft twice and only mark it auto-approvable when the
two runs agree; and we drop questions that already duplicate an existing golden case.
"""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from app.clients.embeddings import get_embedder
from app.clients.llm import get_judge_client
from app.config import get_config
from app.logging_config import get_logger
from app.modules.autoeval.schemas import DraftCase
from app.modules.eval.golden import load_golden_set
from app.modules.generation.prompt import build_context
from app.modules.retrieval.dense import RetrievedChunk

logger = get_logger(__name__)

_DRAFT_SYSTEM = """You are drafting an evaluation reference case for a FastAPI docs assistant.
Given a QUESTION and retrieved CONTEXT, write the concise, correct reference answer grounded
ONLY in the context. Classify the case type: "simple" (one doc), "multi_hop" (needs two docs),
"ambiguous" (under-specified), or "no_answer" (context does not answer it). For no_answer,
briefly say it isn't covered. Do not invent facts beyond the context."""


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    va, vb = np.asarray(a), np.asarray(b)
    denom = (np.linalg.norm(va) * np.linalg.norm(vb)) or 1.0
    return float(va @ vb / denom)


def draft(query: str, chunks: Sequence[RetrievedChunk]) -> DraftCase:
    cfg = get_config().models.judge
    context = build_context(chunks) if chunks else "(no context retrieved)"
    d: DraftCase = get_judge_client().chat.completions.create(
        model=cfg.name,
        response_model=DraftCase,
        temperature=0.2,
        messages=[
            {"role": "system", "content": _DRAFT_SYSTEM},
            {"role": "user", "content": f"QUESTION:\n{query}\n\nCONTEXT:\n{context}"},
        ],
    )
    # Trust real retrieved paths over model-written ones (avoid hallucinated sources).
    if d.type == "no_answer":
        d.sources = []
    else:
        d.sources = list(dict.fromkeys(c.source for c in chunks))[:3]
    return d


def runs_agree(a: DraftCase, b: DraftCase) -> bool:
    if a.type != b.type:
        return False
    emb = get_embedder()
    sim = _cosine(emb.embed_query(a.answer), emb.embed_query(b.answer))
    return sim >= get_config().autoeval.agreement_threshold


def is_duplicate(query: str) -> bool:
    """True if the query is near-identical to an existing golden question."""
    try:
        golden = load_golden_set()
    except FileNotFoundError:
        return False
    if not golden:
        return False
    emb = get_embedder()
    qv = emb.embed_query(query)
    threshold = get_config().autoeval.dedup_threshold
    return any(_cosine(qv, emb.embed_query(g.question)) >= threshold for g in golden)
