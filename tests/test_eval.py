"""Phase 4: golden loading + deterministic metrics (fast); a real eval run (slow, needs key)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import get_settings
from app.modules.eval.golden import load_golden_set
from app.modules.eval.metrics import retrieval_recall
from app.modules.eval.runner import _score_case
from app.modules.eval.schemas import GoldenCase

SAMPLE_DOCS = Path(__file__).resolve().parent.parent / "sample_docs"


# --- fast: golden set + deterministic metrics --------------------------------


def test_golden_set_loads_and_validates():
    cases = load_golden_set()
    assert len(cases) >= 12
    types = {c.type for c in cases}
    assert {"simple", "multi_hop", "no_answer", "ambiguous"} <= types
    assert all(c.id and c.question and c.expected_answer for c in cases)


def test_retrieval_recall_subset_and_empty():
    pp = "docs/tutorial/path-params.md"
    assert retrieval_recall([pp], {pp}) == 1.0
    assert retrieval_recall(["a.md", "b.md"], {"a.md"}) == 0.5
    assert retrieval_recall([], {"anything.md"}) == 1.0  # no_answer requires nothing
    # endswith matching tolerates path prefixes
    assert retrieval_recall(["path-params.md"], {pp}) == 1.0


def _fake_resp(answered: bool):
    return SimpleNamespace(
        answer="...",
        has_sufficient_context=answered,
        confidence=0.9 if answered else 0.1,
        confidence_breakdown={"citation": 1.0 if answered else 0.0},
        retrieval_mode="hybrid",
    )


def test_no_answer_case_scores_on_refusal():
    case = GoldenCase(id="n1", type="no_answer", question="q?", expected_answer="n/a")
    # correctly refused -> full score
    good = _score_case(case, _fake_resp(answered=False), set())
    assert good.idk_correct is True and good.score == 1.0
    # wrongly answered -> zero
    bad = _score_case(case, _fake_resp(answered=True), set())
    assert bad.idk_correct is False and bad.score == 0.0


# --- slow: a real end-to-end eval run over the sample corpus ------------------


needs_key = pytest.mark.skipif(
    not get_settings().openai_api_key, reason="requires OPENAI_API_KEY (env or .env)"
)


@pytest.mark.slow
@needs_key
def test_run_eval_produces_valid_summary():
    from app.modules.eval.runner import run_eval
    from app.modules.ingestion.service import ingest_directory

    ingest_directory(SAMPLE_DOCS, reset=True)
    cases = [
        GoldenCase(
            id="e1", type="simple",
            question="How do I declare a path parameter as an int?",
            expected_answer="Use a Python type annotation like item_id: int.",
            expected_sources=["path-parameters.md"],
        ),
        GoldenCase(
            id="e2", type="no_answer",
            question="How do I configure OAuth2 scopes with JWT here?",
            expected_answer="Not covered by the sample docs.",
        ),
    ]
    summary = run_eval(cases, "recursive", persist=False)
    assert summary.n_cases == 2
    assert 0.0 <= summary.metrics["overall_score"] <= 1.0
    assert "retrieval_recall" in summary.metrics
