"""Typed contracts for the eval harness: the golden answer key and result records."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CaseType = Literal["simple", "multi_hop", "no_answer", "ambiguous"]


class GoldenCase(BaseModel):
    """One human-authored evaluation case (the credibility spine — not LLM-generated)."""

    id: str
    type: CaseType
    question: str
    expected_answer: str
    expected_sources: list[str] = Field(
        default_factory=list,
        description="Source paths that should be retrieved/cited (empty for no_answer).",
    )
    notes: str = ""


class CaseResult(BaseModel):
    id: str
    type: CaseType
    question: str
    answered: bool  # system produced an answer (vs graceful IDK)

    # deterministic metrics
    retrieval_recall: float  # fraction of expected_sources present in retrieved chunks
    citation_accuracy: float  # from Phase 3 verdicts
    idk_correct: bool | None  # no_answer cases only: did it correctly refuse?

    # judge metrics (0 for no_answer, which is scored on idk_correct instead)
    correctness: float
    faithfulness: float
    completeness: float

    score: float  # blended per-case score in [0, 1]
    confidence: float  # system composite confidence
    retrieval_mode: str
    error: str | None = None


class EvalSummary(BaseModel):
    run_id: str
    strategy: str
    n_cases: int
    metrics: dict[str, float]  # averaged headline metrics
    by_type: dict[str, float]  # mean score per case type
    case_results: list[CaseResult]
