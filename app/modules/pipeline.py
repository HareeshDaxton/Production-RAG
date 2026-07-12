"""Query pipeline (Phase 1): dense retrieve -> grounded generate -> assemble response.

Cache, hybrid retrieval, citation verification, and confidence scoring layer on in
later phases; the boundaries here stay stable so those slot in without a rewrite.
"""
from __future__ import annotations

from app.config import get_config
from app.logging_config import get_logger
from app.models.schemas import AskResponse, Citation
from app.modules.generation.generator import generate_answer
from app.modules.retrieval.dense import RetrievedChunk, dense_retrieve

logger = get_logger(__name__)

_IDK = "I don't have enough information to answer that based on the indexed documentation."
_SNIPPET_CHARS = 300


def _snippet(text: str) -> str:
    text = text.strip().replace("\n", " ")
    return text if len(text) <= _SNIPPET_CHARS else text[:_SNIPPET_CHARS].rstrip() + "…"


def _to_citations(numbers: list[int], chunks: list[RetrievedChunk]) -> list[Citation]:
    citations: list[Citation] = []
    for n in sorted(set(numbers)):
        if 1 <= n <= len(chunks):
            c = chunks[n - 1]
            citations.append(
                Citation(number=n, source=c.source, section=c.section_path, text=_snippet(c.text))
            )
    return citations


def ask(query: str, top_k: int | None = None) -> AskResponse:
    k = top_k or get_config().retrieval.default_top_k
    chunks = dense_retrieve(query, k)

    if not chunks:
        return AskResponse(
            query=query,
            answer=_IDK,
            citations=[],
            chunks_retrieved=0,
            has_sufficient_context=False,
        )

    gen = generate_answer(query, chunks)
    return AskResponse(
        query=query,
        answer=gen.answer,
        citations=_to_citations(gen.citations_used, chunks),
        chunks_retrieved=len(chunks),
        has_sufficient_context=gen.has_sufficient_context,
    )
