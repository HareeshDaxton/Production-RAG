"""Phase 6: flag decision + capture (fast); draft→process→approve (slow, needs key)."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.config import get_settings
from app.models.schemas import AskResponse
from app.modules.autoeval.capture import capture, should_flag

SAMPLE_DOCS = Path(__file__).resolve().parent.parent / "sample_docs"


def _resp(conf: float, sufficient: bool, cached: bool = False) -> AskResponse:
    return AskResponse(
        query="q", answer="a", citations=[], chunks_retrieved=1,
        has_sufficient_context=sufficient, retrieval_mode="hybrid",
        retrieval_confidence=0.5, confidence=conf, cached=cached,
    )


# --- fast: flag logic + enqueue ----------------------------------------------


def test_should_flag_variants():
    assert should_flag(_resp(0.9, True)) == (False, "")           # confident answer
    assert should_flag(_resp(0.3, True)) == (True, "low_confidence")
    assert should_flag(_resp(0.9, False)) == (True, "idk")        # IDK
    assert should_flag(_resp(0.2, False, cached=True)) == (False, "")  # cached → skip


def test_capture_enqueues_only_when_flagged():
    assert isinstance(capture("some weak query", _resp(0.9, False)), int)  # IDK → enqueued
    assert capture("a good query", _resp(0.95, True)) is None              # confident → skip


# --- slow: draft + process + approve -----------------------------------------


needs_key = pytest.mark.skipif(
    not get_settings().openai_api_key, reason="requires OPENAI_API_KEY (env or .env)"
)


@pytest.mark.slow
@needs_key
def test_process_and_approve(tmp_path):
    from app.clients import db
    from app.config import get_config
    from app.modules.autoeval import service
    from app.modules.ingestion.service import ingest_directory

    ingest_directory(SAMPLE_DOCS, reset=True)
    get_config().autoeval.candidates_path = tmp_path / "candidates.jsonl"

    cid = db.enqueue_candidate("How do I declare a path parameter as an int?", "low_confidence", "")
    results = service.process_pending(limit=50)
    mine = next(r for r in results if r.id == cid)
    assert mine.status in {"auto_approved", "needs_review", "rejected_duplicate"}

    cand = db.get_candidate(cid)
    if mine.status != "rejected_duplicate":
        assert cand["proposed_answer"] and cand["proposed_type"]
        case = service.approve(cid)
        assert case.id == f"auto-{cid}"
        assert (tmp_path / "candidates.jsonl").exists()
        assert db.get_candidate(cid)["status"] == "approved"
