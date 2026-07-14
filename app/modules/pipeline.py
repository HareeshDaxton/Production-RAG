"""Query pipeline: retrieve → generate → verify & score → answer or graceful IDK.

Phase 1 built retrieve→generate; Phase 2 added hybrid retrieval + confidence; Phase 3
adds the quality gate: citations are judge-verified, the three confidence signals are
combined, and answers below `quality.idk_threshold` are replaced with an honest
"I don't know" that still shows what was found. Cache layers on in Phase 5.
"""
from __future__ import annotations

from collections.abc import Sequence

from app.config import get_config
from app.logging_config import get_logger
from app.models.schemas import AskResponse, Citation
from app.modules.generation.generator import generate_answer
from app.modules.quality.service import QualityReport, assess
from app.modules.quality.verifier import CitationCheck
from app.modules.retrieval.dense import RetrievedChunk
from app.modules.retrieval.retriever import RetrievalResult, retrieve

logger = get_logger(__name__)

_IDK = "I don't have enough information to answer that based on the indexed documentation."
_SNIPPET_CHARS = 300


def _snippet(text: str) -> str:
    text = text.strip().replace("\n", " ")
    return text if len(text) <= _SNIPPET_CHARS else text[:_SNIPPET_CHARS].rstrip() + "…"


def _to_citations(
    numbers: list[int],
    chunks: Sequence[RetrievedChunk],
    checks: Sequence[CitationCheck] = (),
) -> list[Citation]:
    verdicts = {c.number: c for c in checks}
    citations: list[Citation] = []
    for n in sorted(set(numbers)):
        if 1 <= n <= len(chunks):
            c = chunks[n - 1]
            v = verdicts.get(n)
            citations.append(
                Citation(
                    number=n,
                    source=c.source,
                    section=c.section_path,
                    text=_snippet(c.text),
                    verdict=v.verdict if v else None,
                    verdict_reason=v.reason if v else None,
                )
            )
    return citations


def _idk_answer(chunks: Sequence[RetrievedChunk]) -> str:
    """Honest 'I don't know' that still surfaces the closest matches + a suggestion."""
    if not chunks:
        return (
            f"{_IDK} Nothing in the indexed documentation matched your question — "
            "try rephrasing, or ingest documents that cover this topic."
        )
    found = "\n".join(
        f"- {c.source}" + (f" (Section: {c.section_path})" if c.section_path else "")
        for c in chunks[:3]
    )
    return (
        f"{_IDK} The closest matches I found were:\n{found}\n"
        "These didn't confidently support an answer — try rephrasing or asking about "
        "one of the topics above."
    )


def _idk_response(
    query: str,
    result: RetrievalResult,
    report: QualityReport | None = None,
) -> AskResponse:
    return AskResponse(
        query=query,
        answer=_idk_answer(result.chunks),
        # Surface the closest chunks as provenance so the user sees what was searched.
        citations=_to_citations(
            list(range(1, len(result.chunks) + 1)),
            result.chunks,
            report.checks if report else (),
        ),
        chunks_retrieved=len(result.chunks),
        has_sufficient_context=False,
        retrieval_mode=result.mode,
        retrieval_confidence=result.confidence,
        confidence=report.confidence if report else 0.0,
        confidence_breakdown=report.breakdown if report else {},
    )


def ask(query: str, top_k: int | None = None, mode: str | None = None) -> AskResponse:
    k = top_k or get_config().retrieval.default_top_k
    result = retrieve(query, k, mode)

    if not result.chunks:
        return _idk_response(query, result)

    gen = generate_answer(query, result.chunks)
    report = assess(
        query,
        gen.answer,
        result.chunks,
        self_confidence=gen.self_confidence,
        retrieval_confidence=result.confidence,
    )

    # Below the threshold → refuse to guess; return an honest IDK with what was found.
    if not report.answerable:
        return _idk_response(query, result, report)

    return AskResponse(
        query=query,
        answer=gen.answer,
        citations=_to_citations(gen.citations_used, result.chunks, report.checks),
        chunks_retrieved=len(result.chunks),
        has_sufficient_context=gen.has_sufficient_context,
        retrieval_mode=result.mode,
        retrieval_confidence=result.confidence,
        confidence=report.confidence,
        confidence_breakdown=report.breakdown,
    )
