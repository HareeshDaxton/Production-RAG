"""M6: metadata-filtered retrieval + filtered cache key. Fast — no models/ChromaDB."""
from __future__ import annotations

from app.models.schemas import AskRequest, RetrievalFilters
from app.modules.cache.service import params_hash
from app.modules.retrieval.filters import build_where, metadata_matches
from app.modules.retrieval.sparse import BM25Index


class _FakeBM25:
    """Deterministic BM25 stub: score = index position (so order is predictable)."""

    def __init__(self, n: int):
        self._n = n

    def get_scores(self, _tokens):
        # Descending scores so ranked order is 0,1,2,...
        return [float(self._n - i) for i in range(self._n)]


def _index(metas: list[dict]) -> BM25Index:
    ids = [f"c{i}" for i in range(len(metas))]
    texts = [f"text {i}" for i in range(len(metas))]
    return BM25Index(ids=ids, texts=texts, metadatas=metas, bm25=_FakeBM25(len(metas)))


# --- build_where --------------------------------------------------------------


def test_build_where_shapes():
    assert build_where(None) is None
    assert build_where({}) is None
    assert build_where({"file_type": "pdf"}) == {"file_type": "pdf"}
    where = build_where({"file_type": "pdf", "source": "g.pdf"})
    assert where == {"$and": [{"file_type": "pdf"}, {"source": "g.pdf"}]}


# --- metadata_matches ---------------------------------------------------------


def test_metadata_matches():
    meta = {"file_type": "csv", "source": "data.csv"}
    assert metadata_matches(meta, None) is True
    assert metadata_matches(meta, {}) is True
    assert metadata_matches(meta, {"file_type": "csv"}) is True
    assert metadata_matches(meta, {"file_type": "pdf"}) is False
    assert metadata_matches(meta, {"file_type": "csv", "source": "other.csv"}) is False


# --- sparse post-filter -------------------------------------------------------


def test_bm25_search_respects_filters():
    idx = _index(
        [
            {"file_type": "pdf"},
            {"file_type": "csv"},
            {"file_type": "pdf"},
            {"file_type": "csv"},
        ]
    )
    hits = idx.search("q", top_k=10, filters={"file_type": "csv"})
    assert {h.chunk_id for h in hits} == {"c1", "c3"}

    unfiltered = idx.search("q", top_k=10)
    assert len(unfiltered) == 4


def test_bm25_search_filter_then_top_k():
    idx = _index([{"file_type": "csv"} for _ in range(5)])
    hits = idx.search("q", top_k=2, filters={"file_type": "csv"})
    assert len(hits) == 2  # top_k applied after filtering


# --- cache correctness (the M6 headline fix) ----------------------------------


def test_filtered_and_unfiltered_hash_differ():
    unfiltered = params_hash(5, "hybrid", None)
    filtered = params_hash(5, "hybrid", {"file_type": "pdf"})
    assert unfiltered != filtered


def test_different_filters_hash_differ():
    a = params_hash(5, "hybrid", {"file_type": "pdf"})
    b = params_hash(5, "hybrid", {"file_type": "csv"})
    assert a != b


def test_same_filters_hash_stable_regardless_of_order():
    a = params_hash(5, "hybrid", {"file_type": "pdf", "source": "g.pdf"})
    b = params_hash(5, "hybrid", {"source": "g.pdf", "file_type": "pdf"})
    assert a == b


# --- schema -------------------------------------------------------------------


def test_retrieval_filters_as_dict_drops_none():
    f = RetrievalFilters(file_type="pdf")
    assert f.as_dict() == {"file_type": "pdf"}


def test_ask_request_rejects_unknown_filter_key():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AskRequest(query="hello there", filters={"bogus": "x"})
