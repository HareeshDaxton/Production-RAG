"""Phase 2: RRF fusion (fast), plus hybrid/sparse/chunking behaviour (slow, loads models)."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.config import ChunkingConfig
from app.modules.ingestion.chunker import chunk_document
from app.modules.ingestion.loader import Document
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
