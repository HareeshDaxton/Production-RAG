"""Identifier-aware retrieval: exact lookup instead of similarity for id questions."""
from __future__ import annotations

import pytest

from app.modules.cache.service import params_hash
from app.modules.retrieval import identifiers as ident


class _Store:
    """Stands in for the vector store: only `ids_where` is consulted."""

    def __init__(self, known: set[str]):
        self.known = known
        self.calls: list[dict] = []

    def ids_where(self, where: dict) -> list[str]:
        self.calls.append(where)
        return ["c1"] if where.get("record_id") in self.known else []


@pytest.fixture
def store(monkeypatch):
    def _install(known: set[str]) -> _Store:
        s = _Store(known)
        monkeypatch.setattr(ident, "get_vector_store", lambda: s)
        return s

    return _install


# --- extraction ---------------------------------------------------------------


def test_extracts_identifier_shapes():
    assert ident.extract_identifiers('tell me about "patient_id": "PAT-20260042"') == [
        "PAT-20260042"
    ]
    assert ident.extract_identifiers("compare MRN_0004 with MRN_0005") == ["MRN_0004", "MRN_0005"]


def test_ignores_ordinary_questions():
    """No digits, no identifier — plain prose must never be treated as a lookup."""
    assert ident.extract_identifiers("what is the treatment for diabetes") == []
    assert ident.extract_identifiers("How do I install FastAPI on Windows?") == []


# --- scoping ------------------------------------------------------------------


def test_known_identifier_scopes_retrieval(store):
    store({"PAT-20260042"})
    assert ident.identifier_filter('about "PAT-20260042"') == {"record_id": "PAT-20260042"}


def test_several_known_identifiers_become_a_membership_filter(store):
    store({"PAT-0001", "PAT-0002"})
    got = ident.identifier_filter("compare PAT-0001 and PAT-0002")
    assert got == {"record_id": ["PAT-0001", "PAT-0002"]}


def test_unknown_identifier_does_not_empty_the_result(store):
    """"COVID-19" is id-shaped but is not a record — the question must still be answered."""
    store(set())
    assert ident.identifier_filter("explain the COVID-19 guidance") is None


def test_existing_filters_are_preserved(store):
    store({"PAT-0001"})
    got = ident.identifier_filter("about PAT-0001", {"source": "patients.json"})
    assert got == {"source": "patients.json", "record_id": "PAT-0001"}


def test_store_failure_degrades_to_the_caller_filters(monkeypatch):
    """An identifier lookup is an optimisation; it must never break a normal ask."""

    def boom():
        raise RuntimeError("store down")

    monkeypatch.setattr(ident, "get_vector_store", boom)
    assert ident.identifier_filter("about PAT-0001", {"source": "x.json"}) == {"source": "x.json"}


# --- the cache collision this fixes -------------------------------------------


def test_different_identifiers_cannot_share_a_cached_answer():
    """Two ids differing by one digit embed at ~0.998 — far above the 0.90 cache
    threshold — so without distinct params hashes the second question is served the
    first one's answer."""
    a = params_hash(5, "hybrid", {"record_id": "PAT-20260042"})
    b = params_hash(5, "hybrid", {"record_id": "PAT-20260043"})
    unscoped = params_hash(5, "hybrid", None)
    assert a != b != unscoped and a != unscoped
