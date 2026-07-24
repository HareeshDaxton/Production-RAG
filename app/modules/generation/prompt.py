"""Grounded generation prompt: numbered context + strict citation rules."""
from __future__ import annotations

from collections.abc import Sequence

from app.modules.retrieval.dense import RetrievedChunk

SYSTEM_PROMPT = """You are a technical documentation assistant for FastAPI.
Answer the user's question using ONLY the numbered context below.

Rules:
1. Cite sources inline as [1], [2], ... using the numbers of the context blocks you rely on.
2. Only cite blocks you actually used, and list them in `citations_used`.
3. If the context does not contain enough information, set `has_sufficient_context` to false
   and say you don't have enough information — do NOT guess.
4. Preserve exact code, identifiers, and symbols from the context.
5. Do not use outside knowledge. Be concise.
6. Set `self_confidence` (0-1) to how sure you are the answer is correct and fully grounded
   in the context — be honest and use a low value if the context was thin or you had to stretch."""


def _locator(c: RetrievedChunk) -> str:
    """Human-readable provenance suffix: page and/or section, when known."""
    parts: list[str] = []
    if c.page_number is not None:
        parts.append(f"p.{c.page_number}")
    if c.section_path:
        parts.append(f"Section: {c.section_path}")
    return f" ({', '.join(parts)})" if parts else ""


def build_context(chunks: Sequence[RetrievedChunk]) -> str:
    blocks = [
        f'[{i}] From "{c.source}"{_locator(c)}\n{c.text}'
        for i, c in enumerate(chunks, start=1)
    ]
    return "\n\n".join(blocks)


def build_user_prompt(query: str, chunks: Sequence[RetrievedChunk]) -> str:
    return f"Question: {query}\n\nContext:\n{build_context(chunks)}"
