"""Metadata-filter helpers shared by dense (Chroma `where`) and sparse (Python).

Retrieval works with a plain equality dict (e.g. {"file_type": "pdf"}) rather than
the API schema, keeping the retrieval layer decoupled from `models.schemas`.
"""
from __future__ import annotations

Filters = dict[str, str]


def build_where(filters: Filters | None) -> dict | None:
    """Turn an equality dict into a ChromaDB `where` clause.

    None/empty → None (no filter); one key → a flat equality; multiple keys → `$and`
    (Chroma requires an explicit operator to combine conditions).
    """
    if not filters:
        return None
    clauses = [{key: value} for key, value in filters.items()]
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def metadata_matches(meta: dict | None, filters: Filters | None) -> bool:
    """True if a chunk's metadata satisfies every equality filter (sparse post-filter)."""
    if not filters:
        return True
    meta = meta or {}
    return all(meta.get(key) == value for key, value in filters.items())
