"""Metadata-filter helpers shared by dense (Chroma `where`) and sparse (Python).

Retrieval works with a plain equality dict (e.g. {"file_type": "pdf"}) rather than
the API schema, keeping the retrieval layer decoupled from `models.schemas`.
"""
from __future__ import annotations

# A value is either one literal (equality) or several (membership) — the latter is
# what scopes a question to the handful of files attached to it.
Filters = dict[str, str | list[str]]


def _clause(key: str, value: str | list[str]) -> dict:
    if isinstance(value, list):
        return {key: {"$in": value}}
    return {key: value}


def build_where(filters: Filters | None) -> dict | None:
    """Turn a filter dict into a ChromaDB `where` clause.

    None/empty → None (no filter); one key → a flat clause; multiple keys → `$and`
    (Chroma requires an explicit operator to combine conditions). List values become
    `$in`, so `{"source": ["a.csv", "b.pdf"]}` matches either file.
    """
    if not filters:
        return None
    clauses = [_clause(key, value) for key, value in filters.items()]
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def metadata_matches(meta: dict | None, filters: Filters | None) -> bool:
    """True if a chunk's metadata satisfies every filter (sparse post-filter)."""
    if not filters:
        return True
    meta = meta or {}
    return all(
        meta.get(key) in value if isinstance(value, list) else meta.get(key) == value
        for key, value in filters.items()
    )
