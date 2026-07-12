"""Recursive-by-header chunking (Phase 1 strategy).

Splits a markdown document at its headings into sections, keeping a breadcrumb
`section_path` for provenance, then token-caps oversized sections with overlap.
Fixed-size and semantic strategies are added in Phase 2.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import uuid4

from app.config import ChunkingConfig
from app.modules.ingestion.loader import Document
from app.utils.tokens import count_tokens, split_by_tokens

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    source: str
    section_path: str  # "Path Parameters > Order matters"
    chunk_index: int
    text: str
    token_count: int


def _split_into_sections(text: str, root_title: str) -> list[tuple[str, str]]:
    """Return [(section_path, content)] respecting the heading hierarchy."""
    stack: list[tuple[int, str]] = []  # (level, title)
    buf: list[str] = []
    sections: list[tuple[str, str]] = []

    def current_path() -> str:
        parts = [root_title, *[t for _, t in stack]]
        deduped: list[str] = []
        for p in parts:  # collapse blanks and consecutive repeats (title == H1)
            if p and (not deduped or deduped[-1] != p):
                deduped.append(p)
        return " > ".join(deduped)

    def flush() -> None:
        content = "\n".join(buf).strip()
        if content:
            sections.append((current_path(), content))
        buf.clear()

    for line in text.split("\n"):
        m = _HEADING_RE.match(line)
        if m:
            flush()  # content belongs to the path *before* this heading
            level = len(m.group(1))
            title = m.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
        else:
            buf.append(line)
    flush()
    return sections


def chunk_document(doc: Document, cfg: ChunkingConfig) -> list[Chunk]:
    chunks: list[Chunk] = []
    idx = 0
    for section_path, content in _split_into_sections(doc.text, doc.title):
        for piece in split_by_tokens(content, cfg.max_chunk_tokens, cfg.overlap_tokens):
            piece = piece.strip()
            if len(piece) < cfg.min_chunk_chars:
                continue
            chunks.append(
                Chunk(
                    chunk_id=str(uuid4()),
                    doc_id=doc.doc_id,
                    source=doc.source,
                    section_path=section_path,
                    chunk_index=idx,
                    text=piece,
                    token_count=count_tokens(piece),
                )
            )
            idx += 1
    return chunks
