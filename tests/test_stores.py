"""Phase 9: pluggable stores — filter translation + backend selection (fast, no driver)."""
from __future__ import annotations

import pytest

from app.clients.relational import POSTGRES_SCHEMA, SQLITE_SCHEMA
from app.clients.vector.base import EmbeddingDimensionMismatch, assert_dimension
from app.clients.vector.pgvector import UnsupportedFilter, _vector_literal, _where_sql


class _Store:
    """Minimal stand-in: assert_dimension only asks for the stored width."""

    def __init__(self, dim: int | None):
        self._dim = dim

    def dimension(self) -> int | None:
        return self._dim


# --- filter -> SQL ------------------------------------------------------------


def test_no_filter_is_no_clause():
    params: list = []
    assert _where_sql(None, params) == ""
    assert _where_sql({}, params) == ""
    assert params == []


def test_equality_filter():
    params: list = []
    assert _where_sql({"source": "a.csv"}, params) == " WHERE metadata->>%s = %s"
    assert params == ["source", "a.csv"]


def test_in_filter_becomes_any():
    """A chat scoped to several attached files must match any of them."""
    params: list = []
    sql = _where_sql({"source": {"$in": ["a.csv", "b.pdf"]}}, params)
    assert sql == " WHERE metadata->>%s = ANY(%s)"
    assert params == ["source", ["a.csv", "b.pdf"]]


def test_and_combines_clauses():
    params: list = []
    sql = _where_sql({"$and": [{"file_type": "csv"}, {"source": {"$in": ["a.csv"]}}]}, params)
    assert sql == " WHERE metadata->>%s = %s AND metadata->>%s = ANY(%s)"
    assert params == ["file_type", "csv", "source", ["a.csv"]]


def test_unsupported_operator_raises_rather_than_widening_the_search():
    """Silently dropping a filter would quietly broaden a scoped query — a correctness bug."""
    with pytest.raises(UnsupportedFilter):
        _where_sql({"page_number": {"$gt": 3}}, [])
    with pytest.raises(UnsupportedFilter):
        _where_sql({"$or": [{"a": "b"}]}, [])


def test_values_are_parameterised_never_interpolated():
    """Keys and values are always bound, so a quote in a filename cannot alter the SQL."""
    params: list = []
    sql = _where_sql({"source": "o'brien; DROP TABLE chunks--.csv"}, params)
    assert "o'brien" not in sql
    assert params[1] == "o'brien; DROP TABLE chunks--.csv"


def test_vector_literal_round_trips_floats():
    assert _vector_literal([1.0, -0.5, 0.25]) == "[1.0,-0.5,0.25]"


# --- dimension guard ----------------------------------------------------------


def test_dimension_guard_passes_on_empty_or_matching_store():
    assert_dimension(_Store(None), 1536)  # empty store takes the next write's width
    assert_dimension(_Store(1536), 1536)


def test_dimension_guard_reports_both_widths():
    with pytest.raises(EmbeddingDimensionMismatch) as exc:
        assert_dimension(_Store(768), 1536)
    assert "768" in str(exc.value) and "1536" in str(exc.value)
    assert "reset=true" in str(exc.value)  # the message has to say how to fix it


# --- schema parity ------------------------------------------------------------


def test_both_dialects_declare_the_same_tables():
    tables = {
        "system_events", "ingestion_audit", "eval_runs",
        "eval_case_results", "eval_candidates", "feedback",
    }
    for schema in (SQLITE_SCHEMA, POSTGRES_SCHEMA):
        for table in tables:
            assert f"CREATE TABLE IF NOT EXISTS {table}" in schema
    assert "AUTOINCREMENT" in SQLITE_SCHEMA
    assert "BIGSERIAL" in POSTGRES_SCHEMA  # sqlite's autoincrement is not valid postgres
