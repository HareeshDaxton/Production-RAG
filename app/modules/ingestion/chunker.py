"""Chunking strategies (config-selectable), each tagging its chunks with `strategy`.

- recursive : split on markdown headings, keep a `section_path` breadcrumb, then token-cap.
- fixed     : plain token windows with overlap; ignores structure (simple baseline).
- semantic  : split where the topic shifts — embed sentences, cut when similarity drops.

`chunk_document` dispatches on `cfg.strategy`. Only one strategy is active per ingest;
the tag lets Phase 4 benchmark all three against the same corpus.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import ChunkingConfig
from app.modules.ingestion.loader import Document
from app.utils.tokens import count_tokens, split_by_tokens

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
# Sentence boundary: end punctuation + space, or a blank line.
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n{2,}")


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    source: str
    section_path: str  # "Path Parameters > Order matters"
    chunk_index: int
    text: str
    token_count: int
    strategy: str


def chunk_document(doc: Document, cfg: ChunkingConfig) -> list[Chunk]:
    if cfg.strategy == "recursive":
        return _chunk_recursive(doc, cfg)
    if cfg.strategy == "fixed":
        return _chunk_fixed(doc, cfg)
    if cfg.strategy == "semantic":
        return _chunk_semantic(doc, cfg)
    raise ValueError(f"unknown chunking strategy: {cfg.strategy!r}")


def _make_chunk(doc: Document, section_path: str, idx: int, text: str, strategy: str) -> Chunk:
    return Chunk(
        # Deterministic id (doc + position) so re-ingesting the same document
        # overwrites its chunks instead of duplicating them.
        chunk_id=f"{doc.doc_id}::{idx}",
        doc_id=doc.doc_id,
        source=doc.source,
        section_path=section_path,
        chunk_index=idx,
        text=text,
        token_count=count_tokens(text),
        strategy=strategy,
    )


# --- recursive-by-headers ----------------------------------------------------


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


def _chunk_recursive(doc: Document, cfg: ChunkingConfig) -> list[Chunk]:
    chunks: list[Chunk] = []
    idx = 0
    for section_path, content in _split_into_sections(doc.text, doc.title):
        for piece in split_by_tokens(content, cfg.max_chunk_tokens, cfg.overlap_tokens):
            piece = piece.strip()
            if len(piece) < cfg.min_chunk_chars:
                continue
            chunks.append(_make_chunk(doc, section_path, idx, piece, "recursive"))
            idx += 1
    return chunks


# --- fixed-size token windows ------------------------------------------------


def _chunk_fixed(doc: Document, cfg: ChunkingConfig) -> list[Chunk]:
    chunks: list[Chunk] = []
    idx = 0
    for piece in split_by_tokens(doc.text, cfg.max_chunk_tokens, cfg.overlap_tokens):
        piece = piece.strip()
        if len(piece) < cfg.min_chunk_chars:
            continue
        chunks.append(_make_chunk(doc, doc.title, idx, piece, "fixed"))
        idx += 1
    return chunks


# --- semantic (embedding-based) ----------------------------------------------


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT_RE.split(text) if s.strip()]


def _chunk_semantic(doc: Document, cfg: ChunkingConfig) -> list[Chunk]:
    """Group consecutive sentences while they stay on-topic (cosine sim to the
    running group's mean embedding); cut when similarity drops or the token cap is hit."""
    import numpy as np

    from app.clients.embeddings import get_embedder

    sentences = _split_sentences(doc.text)
    if not sentences:
        return []

    embs = np.array(get_embedder().embed_texts(sentences))  # normalized -> dot = cosine

    groups: list[str] = []
    cur: list[str] = [sentences[0]]
    cur_idx: list[int] = [0]

    for i in range(1, len(sentences)):
        centroid = embs[cur_idx].mean(axis=0)
        sim = float(centroid @ embs[i] / (np.linalg.norm(centroid) or 1.0))
        over_cap = count_tokens(" ".join(cur)) >= cfg.max_chunk_tokens
        if sim < cfg.semantic_threshold or over_cap:
            groups.append(" ".join(cur))
            cur, cur_idx = [sentences[i]], [i]
        else:
            cur.append(sentences[i])
            cur_idx.append(i)
    groups.append(" ".join(cur))

    chunks: list[Chunk] = []
    idx = 0
    for group in groups:
        # Safety token-cap in case a single low-similarity run still ran long.
        for piece in split_by_tokens(group, cfg.max_chunk_tokens, cfg.overlap_tokens):
            piece = piece.strip()
            if len(piece) < cfg.min_chunk_chars:
                continue
            chunks.append(_make_chunk(doc, doc.title, idx, piece, "semantic"))
            idx += 1
    return chunks
