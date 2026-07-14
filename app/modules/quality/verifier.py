"""LLM-as-judge citation verification.

After generation, a second (cheaper) model re-reads each cited source and decides
whether it actually supports the claim it was attached to. One *batched* call rates
every citation at once — cheaper than per-citation calls and the judge sees full
context. This is what turns "the model said [2]" into "[2] is actually supported".
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, Field

from app.clients.llm import get_judge_client
from app.config import get_config
from app.logging_config import get_logger
from app.modules.quality.extractor import ExtractedCitation

logger = get_logger(__name__)

Verdict = Literal["supported", "partial", "unsupported"]

_JUDGE_SYSTEM = """You are a strict fact-checking judge for a documentation assistant.
For each numbered citation you are given a CLAIM (a sentence from an answer) and the
SOURCE text it cites. Decide whether the SOURCE actually supports the CLAIM:
- "supported": the source clearly and directly states the claim.
- "partial": the source is related but only loosely or incompletely supports it.
- "unsupported": the source does not support the claim (or contradicts it).
Judge ONLY against the given source text — do not use outside knowledge.
Return one verdict and a one-sentence reason for every citation number provided."""


class CitationCheck(BaseModel):
    number: int = Field(..., description="The citation number being judged.")
    verdict: Verdict
    reason: str = Field(..., description="One-sentence justification for the verdict.")


class VerificationReport(BaseModel):
    checks: list[CitationCheck]


def _build_prompt(query: str, citations: Sequence[ExtractedCitation]) -> str:
    blocks = [
        f"Citation [{c.number}]\nCLAIM: {c.claim}\nSOURCE: {c.source_text}"
        for c in citations
    ]
    return f"Question: {query}\n\n" + "\n\n".join(blocks)


def verify_citations(
    query: str, citations: Sequence[ExtractedCitation]
) -> list[CitationCheck]:
    """Judge every extracted citation; missing numbers default to 'unsupported'."""
    if not citations:
        return []

    cfg = get_config().models.judge
    report: VerificationReport = get_judge_client().chat.completions.create(
        model=cfg.name,
        response_model=VerificationReport,
        temperature=cfg.temperature,
        messages=[
            {"role": "system", "content": _JUDGE_SYSTEM},
            {"role": "user", "content": _build_prompt(query, citations)},
        ],
    )

    by_number = {c.number: c for c in report.checks}
    checks: list[CitationCheck] = []
    for c in citations:
        checks.append(
            by_number.get(
                c.number,
                CitationCheck(
                    number=c.number,
                    verdict="unsupported",
                    reason="Judge returned no verdict for this citation.",
                ),
            )
        )
    logger.info(
        "citations verified",
        extra={
            "total": len(checks),
            "supported": sum(1 for c in checks if c.verdict == "supported"),
        },
    )
    return checks
