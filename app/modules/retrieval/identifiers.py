"""Exact lookup for identifier questions.

Embeddings are the wrong tool for `"patient_id": "PAT-20260042"`. Two ids differing
by one digit embed at ~0.998 cosine, so nearest-neighbour search cannot reliably
separate them and the reranker cannot either — the winning chunk is effectively
arbitrary. Worse, the semantic cache treats those queries as the same question.

So when a query names something that looks like an identifier, and a record with
that id is actually indexed, retrieval is *scoped* to those records with a metadata
equality filter. Similarity then only orders records that are already correct.

The filter is applied only on a confirmed hit: an id-shaped token that matches
nothing (a version number, "COVID-19") must not silently empty the result set.
"""
from __future__ import annotations

import re

from app.clients.vectorstore import get_vector_store
from app.logging_config import get_logger
from app.modules.retrieval.filters import Filters

logger = get_logger(__name__)

# Two shapes worth trying, both requiring a digit so ordinary words never match:
#   PAT-20260042, MRN_0004   — alphanumeric joined by - or _
#   A1C, ICD10               — an uppercase run containing a digit
_DASHED = re.compile(
    r"\b[A-Za-z]*\d[A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)+\b"  # 2026-04, 4a-x
    r"|\b[A-Za-z]+(?:[-_][A-Za-z0-9]*\d[A-Za-z0-9]*)+\b"  # PAT-20260042, MRN_0004
)
_UPPER_CODE = re.compile(r"\b(?=[A-Z0-9]*\d)[A-Z][A-Z0-9]{3,}\b")
_MAX_CANDIDATES = 8


def extract_identifiers(query: str) -> list[str]:
    """Id-shaped tokens in a question, in order, de-duplicated."""
    found: list[str] = []
    for pattern in (_DASHED, _UPPER_CODE):
        for match in pattern.finditer(query):
            token = match.group(0)
            if token not in found:
                found.append(token)
    return found[:_MAX_CANDIDATES]


def identifier_filter(query: str, base: Filters | None = None) -> Filters | None:
    """Narrow `base` to the records a query names, when those records exist.

    Returns the filters to use (possibly unchanged). Any store error degrades to the
    caller's filters — an identifier lookup is an optimisation, never a gate.
    """
    candidates = extract_identifiers(query)
    if not candidates:
        return base

    try:
        store = get_vector_store()
        matched = [c for c in candidates if store.ids_where({"record_id": c})]
    except Exception as exc:  # noqa: BLE001 - never let this break a normal question
        logger.warning("identifier lookup failed", extra={"error": str(exc)})
        return base

    if not matched:
        return base  # id-shaped but not in the corpus — answer the question normally

    scoped: Filters = dict(base or {})
    scoped["record_id"] = matched[0] if len(matched) == 1 else matched
    logger.info("identifier scope applied", extra={"identifiers": matched})
    return scoped
