"""Phase 3: citation extraction + confidence math (fast), verify/IDK gate (slow, needs key)."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.config import ConfidenceWeights, get_settings
from app.modules.quality.confidence import citation_accuracy, composite_confidence
from app.modules.quality.extractor import extract_citations
from app.modules.quality.verifier import CitationCheck
from app.modules.retrieval.dense import RetrievedChunk

SAMPLE_DOCS = Path(__file__).resolve().parent.parent / "sample_docs"


def _chunk(n: int, text: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"c{n}", text=text, source=f"doc{n}.md", section_path=f"S{n}", score=1.0
    )


# --- fast: extraction --------------------------------------------------------


def test_extract_pairs_marker_with_claim_and_source():
    chunks = [_chunk(1, "Order matters."), _chunk(2, "Declare item_id as int.")]
    answer = "Declare the type as int [2]. Path order is significant [1]."
    got = extract_citations(answer, chunks)
    assert [c.number for c in got] == [1, 2]
    two = next(c for c in got if c.number == 2)
    assert "int" in two.claim and two.source_text == "Declare item_id as int."


def test_extract_drops_out_of_range_markers():
    chunks = [_chunk(1, "only one chunk")]
    got = extract_citations("Bogus reference [5] and valid [1].", chunks)
    assert [c.number for c in got] == [1]


def test_build_context_shows_page_and_section():
    from app.modules.generation.prompt import build_context

    chunks = [
        RetrievedChunk(
            chunk_id="c1",
            text="Rate limits use a token bucket.",
            source="guide.pdf",
            section_path="Guide > Auth",
            score=1.0,
            file_type="pdf",
            page_number=12,
        )
    ]
    ctx = build_context(chunks)
    assert 'From "guide.pdf"' in ctx
    assert "p.12" in ctx
    assert "Section: Guide > Auth" in ctx


# --- fast: confidence math ---------------------------------------------------


def test_citation_accuracy_partial_credit():
    checks = [
        CitationCheck(number=1, verdict="supported", reason="x"),
        CitationCheck(number=2, verdict="partial", reason="x"),
        CitationCheck(number=3, verdict="unsupported", reason="x"),
    ]
    assert citation_accuracy(checks) == pytest.approx(0.5)


def test_citation_accuracy_empty_is_zero():
    assert citation_accuracy([]) == 0.0


def test_composite_weights_and_clamp():
    w = ConfidenceWeights(retrieval=0.4, citation=0.4, self=0.2)
    assert composite_confidence(retrieval=1.0, citation=1.0, self_confidence=1.0, weights=w) == 1.0
    mid = composite_confidence(retrieval=0.5, citation=0.5, self_confidence=0.5, weights=w)
    assert mid == pytest.approx(0.5)
    low = composite_confidence(retrieval=0.0, citation=0.0, self_confidence=0.0, weights=w)
    assert low == 0.0


# --- slow: real judge + IDK gate over the sample corpus ----------------------


@pytest.fixture(scope="module")
def ingested():
    from app.modules.ingestion.service import ingest_directory

    return ingest_directory(SAMPLE_DOCS, reset=True)


needs_key = pytest.mark.skipif(
    not get_settings().openai_api_key,
    reason="requires OPENAI_API_KEY (env or .env) for generation + judge",
)


@pytest.mark.slow
@needs_key
def test_in_corpus_answer_is_verified_and_confident(ingested):
    from app.modules.pipeline import ask

    resp = ask("How do I declare a path parameter as an int?")
    assert resp.has_sufficient_context is True
    assert 0.0 <= resp.confidence <= 1.0
    assert resp.citations, "an answerable question should cite sources"
    # every citation carries a judge verdict
    assert all(c.verdict in {"supported", "partial", "unsupported"} for c in resp.citations)
    assert set(resp.confidence_breakdown) == {"retrieval", "citation", "self"}


@pytest.mark.slow
@needs_key
def test_out_of_corpus_question_gets_graceful_idk(ingested):
    from app.modules.pipeline import ask

    resp = ask("What is the best recipe for sourdough bread?")
    assert resp.has_sufficient_context is False
    assert "enough information" in resp.answer
