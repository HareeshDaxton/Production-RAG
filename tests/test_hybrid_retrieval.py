"""Phase 2: RRF fusion (fast), plus hybrid/sparse/chunking behaviour (slow, loads models)."""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from app.config import ChunkingConfig
from app.modules.ingestion.chunker import chunk_document
from app.modules.ingestion.loader import Block, Document
from app.modules.retrieval.dense import RetrievedChunk
from app.modules.retrieval.fusion import reciprocal_rank_fusion

SAMPLE_DOCS = Path(__file__).resolve().parent.parent / "sample_docs"


# --- fast: pure fusion logic (no models) -------------------------------------


def test_rrf_rewards_agreement_across_lists():
    dense = ["a", "b", "c"]
    sparse = ["b", "d", "a"]
    fused = reciprocal_rank_fusion([dense, sparse], weights=[1.0, 1.0], k=60)
    order = [cid for cid, _ in fused]
    # "b" is rank1 in sparse and rank2 in dense -> should top a list where nothing else
    # appears twice as favourably.
    assert order[0] == "b"
    assert set(order) == {"a", "b", "c", "d"}


def test_rrf_weight_shifts_ranking():
    dense = ["x", "y"]
    sparse = ["y", "x"]
    # Heavily weighting sparse should put its top item ("y") first.
    fused = reciprocal_rank_fusion([dense, sparse], weights=[0.1, 5.0], k=60)
    assert fused[0][0] == "y"


# --- fast: confidence source depends on content type (no models) --------------


class _FakeReranker:
    """Returns a fixed cross-encoder logit for every candidate."""

    def __init__(self, score: float):
        self._score = score

    def rerank(self, _query, candidates, top_k):
        return [(cid, self._score) for cid, _ in candidates][:top_k]


def _wire(monkeypatch, chunk, rerank_score: float):
    from app.modules.retrieval import hybrid

    monkeypatch.setattr(hybrid, "dense_retrieve", lambda *a, **k: [chunk])
    monkeypatch.setattr(hybrid, "sparse_retrieve", lambda *a, **k: [])
    monkeypatch.setattr(hybrid, "get_reranker", lambda: _FakeReranker(rerank_score))
    return hybrid


def _chunk(content_type: str, cosine: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="c1", text="Id: 1 | name: Ada", source="p.csv",
        section_path="", score=cosine, content_type=content_type,
    )


def test_structured_confidence_comes_from_the_cosine_not_the_cross_encoder(monkeypatch):
    """CSV/JSON/XML records are out of distribution for `ms-marco-MiniLM`: it scores
    them ~-8 however relevant they are, and sigmoid(-8) ≈ 0 made the quality gate
    refuse every question about a structured file."""
    hybrid = _wire(monkeypatch, _chunk("row", 0.82), rerank_score=-8.0)
    _, confidence = hybrid.hybrid_retrieve("what does this data say", top_k=1)
    assert confidence == 0.82


def test_prose_confidence_still_comes_from_the_cross_encoder(monkeypatch):
    hybrid = _wire(monkeypatch, _chunk("text", 0.82), rerank_score=2.0)
    _, confidence = hybrid.hybrid_retrieve("what is attention", top_k=1)
    assert confidence == round(1 / (1 + math.exp(-2.0)), 4)


def test_structured_fallback_can_be_switched_off(monkeypatch):
    from app.config import get_config

    monkeypatch.setattr(get_config().retrieval, "structured_confidence_from_dense", False)
    hybrid = _wire(monkeypatch, _chunk("row", 0.82), rerank_score=-8.0)
    _, confidence = hybrid.hybrid_retrieve("what does this data say", top_k=1)
    assert confidence < 0.01  # back to sigmoid(-8)


# --- fast: block-based chunking carries per-chunk metadata (no models) --------


def _doc_with_blocks() -> Document:
    return Document(
        doc_id="guide.md",
        source="guide.md",
        title="Guide",
        file_type="markdown",
        blocks=[
            Block(
                text="Path parameters are declared in the URL path with a type.",
                section_path="Guide > Path Params",
                content_type="text",
            ),
            Block(
                text="Query parameters follow a question mark in the request URL.",
                section_path="Guide > Query Params",
                content_type="text",
            ),
        ],
        metadata={"created_at": "2026-01-01T00:00:00+00:00"},
    )


def test_recursive_carries_block_metadata():
    doc = _doc_with_blocks()
    cfg = ChunkingConfig(
        strategy="recursive", max_chunk_tokens=64, overlap_tokens=8, min_chunk_chars=1
    )
    chunks = chunk_document(doc, cfg)
    assert chunks
    assert all(c.file_type == "markdown" and c.title == "Guide" for c in chunks)
    assert all(c.content_type == "text" for c in chunks)
    assert all(c.char_count == len(c.text) for c in chunks)
    assert all(c.created_at == "2026-01-01T00:00:00+00:00" for c in chunks)
    # recursive respects block boundaries -> section breadcrumbs preserved verbatim
    assert {c.section_path for c in chunks} == {"Guide > Path Params", "Guide > Query Params"}


def test_fixed_attributes_windows_to_source_blocks():
    doc = _doc_with_blocks()
    cfg = ChunkingConfig(strategy="fixed", max_chunk_tokens=64, overlap_tokens=8, min_chunk_chars=1)
    chunks = chunk_document(doc, cfg)
    assert chunks
    assert all(c.strategy == "fixed" and c.file_type == "markdown" for c in chunks)
    # every window is attributed back to a real block's section breadcrumb
    assert all(
        c.section_path in {"Guide > Path Params", "Guide > Query Params"} for c in chunks
    )


# --- slow: real retrieval over the sample corpus -----------------------------


@pytest.fixture(scope="module")
def ingested():
    from app.modules.ingestion.service import ingest_directory

    return ingest_directory(SAMPLE_DOCS, reset=True)


@pytest.mark.slow
def test_sparse_finds_exact_identifier(ingested):
    from app.modules.retrieval.sparse import sparse_retrieve

    hits = sparse_retrieve("read_item function", top_k=5)
    assert hits, "BM25 should match the exact code identifier"
    assert any("path-parameters" in h.source for h in hits)


@pytest.mark.slow
def test_hybrid_returns_ranked_results_with_confidence(ingested):
    from app.modules.retrieval.hybrid import hybrid_retrieve

    chunks, confidence = hybrid_retrieve("How do I type a path parameter as int?", top_k=3)
    assert 1 <= len(chunks) <= 3
    assert 0.0 <= confidence <= 1.0
    assert any("path-parameters" in c.source for c in chunks)


@pytest.mark.slow
def test_retriever_dispatch_dense_and_hybrid(ingested):
    from app.modules.retrieval.retriever import retrieve

    dense = retrieve("declare a path parameter type", top_k=3, mode="dense")
    hybrid = retrieve("declare a path parameter type", top_k=3, mode="hybrid")
    assert dense.mode == "dense" and hybrid.mode == "hybrid"
    assert dense.chunks and hybrid.chunks
    assert 0.0 <= dense.confidence <= 1.0 and 0.0 <= hybrid.confidence <= 1.0


@pytest.mark.slow
def test_chunking_strategies_tag_their_chunks(ingested):
    doc = Document(
        doc_id="t.md",
        source="t.md",
        title="Test",
        text=(
            "# Heading\n\nFastAPI validates types with Pydantic. It parses request bodies.\n\n"
            "## Section\n\nPath parameters are declared in the URL. Query parameters follow a "
            "question mark. Response models shape the output."
        ),
    )
    for strategy in ("recursive", "fixed", "semantic"):
        cfg = ChunkingConfig(strategy=strategy, max_chunk_tokens=64, overlap_tokens=8)
        chunks = chunk_document(doc, cfg)
        assert chunks, f"{strategy} produced no chunks"
        assert all(c.strategy == strategy for c in chunks)
        assert all(c.chunk_id == f"t.md::{c.chunk_index}" for c in chunks)
        # every chunk carries enrichment metadata regardless of strategy
        assert all(c.char_count == len(c.text) and c.content_type for c in chunks)
        assert all(c.section_path for c in chunks)
