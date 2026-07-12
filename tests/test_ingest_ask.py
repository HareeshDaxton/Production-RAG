"""Phase 1 integration: ingest the bundled sample docs, retrieve, and (with a key) ask.

Marked `slow` because they load the local embedding model.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.config import get_settings

SAMPLE_DOCS = Path(__file__).resolve().parent.parent / "sample_docs"


@pytest.fixture(scope="module")
def ingested():
    from app.modules.ingestion.service import ingest_directory

    return ingest_directory(SAMPLE_DOCS, reset=True)


@pytest.mark.slow
def test_ingest_creates_chunks(ingested):
    assert ingested.documents >= 3
    assert ingested.chunks >= ingested.documents


@pytest.mark.slow
def test_dense_retrieval_finds_relevant_doc(ingested):
    from app.modules.retrieval.dense import dense_retrieve

    hits = dense_retrieve("How do I declare a path parameter with a type?", top_k=3)
    assert len(hits) >= 1
    # the most relevant doc for this question is path-parameters.md
    assert any("path-parameters" in h.source for h in hits)
    assert hits[0].score > 0.0


@pytest.mark.slow
@pytest.mark.skipif(not get_settings().openai_api_key, reason="OPENAI_API_KEY not set")
def test_ask_returns_cited_answer(ingested):
    from app.modules.pipeline import ask

    resp = ask("How do I declare a path parameter with an int type in FastAPI?", top_k=3)
    assert resp.chunks_retrieved >= 1
    assert resp.has_sufficient_context is True
    assert resp.answer.strip()
    assert len(resp.citations) >= 1
    # citations must reference retrieved blocks
    assert all(1 <= c.number <= resp.chunks_retrieved for c in resp.citations)
