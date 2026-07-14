"""Eval metrics: deterministic (retrieval recall) + judge (correctness/faithfulness/completeness).

The judge grades the system answer against the *human* reference answer — not against
another model's output — which is what keeps the evaluation non-circular and credible.
"""
from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, Field

from app.clients.llm import get_judge_client
from app.config import get_config
from app.logging_config import get_logger

logger = get_logger(__name__)


def _source_matches(expected: str, retrieved: set[str]) -> bool:
    return any(r == expected or r.endswith(expected) or expected.endswith(r) for r in retrieved)


def retrieval_recall(expected_sources: Sequence[str], retrieved_sources: set[str]) -> float:
    """Fraction of expected sources present among the retrieved chunk sources.

    No expected sources (e.g. a no_answer case) → 1.0: nothing was required.
    """
    if not expected_sources:
        return 1.0
    hits = sum(1 for e in expected_sources if _source_matches(e, retrieved_sources))
    return round(hits / len(expected_sources), 4)


_JUDGE_SYSTEM = """You are grading a documentation assistant's answer against a trusted
REFERENCE answer written by a human. Score three things from 0.0 to 1.0:
- correctness: is the SYSTEM answer factually correct and consistent with the REFERENCE?
- completeness: does it cover the key points present in the REFERENCE?
- faithfulness: is it self-consistent and free of invented/contradictory claims?
Grade only against the REFERENCE and the question. Be strict but fair; a partially
correct answer should score in between. Return the three scores and a one-line reason."""


class EvalJudgment(BaseModel):
    correctness: float = Field(..., ge=0.0, le=1.0)
    completeness: float = Field(..., ge=0.0, le=1.0)
    faithfulness: float = Field(..., ge=0.0, le=1.0)
    reason: str


def judge_answer(question: str, reference: str, system_answer: str) -> EvalJudgment:
    cfg = get_config().models.judge
    prompt = (
        f"QUESTION:\n{question}\n\n"
        f"REFERENCE answer (trusted, human-written):\n{reference}\n\n"
        f"SYSTEM answer (to grade):\n{system_answer}"
    )
    return get_judge_client().chat.completions.create(
        model=cfg.name,
        response_model=EvalJudgment,
        temperature=cfg.temperature,
        messages=[
            {"role": "system", "content": _JUDGE_SYSTEM},
            {"role": "user", "content": prompt},
        ],
    )
