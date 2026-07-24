"""Chunking strategies (config-selectable), each tagging its chunks with `strategy`.

- recursive : token-cap each structural block (markdown heading-sections), keeping the
              block's `section_path` breadcrumb.
- fixed     : fixed-size token windows *across* blocks (ignores structure — a naive
              baseline), but each window is still attributed back to its source block
              so page/section metadata is preserved.
- semantic  : split where the topic shifts — embed sentences, cut when similarity drops;
              each group inherits its first sentence's block metadata.

Every chunk is produced from exactly one block and inherits that block's metadata, so
page/section provenance survives all three strategies. `chunk_document` dispatches on
`cfg.strategy`; only one strategy is active per ingest (the tag lets Phase 4 benchmark
all three against the same corpus).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import ChunkingConfig
from app.modules.ingestion.loader import Block, Document
from app.utils.tokens import count_tokens, decode_tokens, encode_tokens, split_by_tokens

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
    # --- per-chunk metadata enrichment (inherited from the source block/doc) ---
    file_type: str
    title: str
    page_number: int | None
    locator: str | None
    content_type: str
    char_count: int
    created_at: str


def chunk_document(doc: Document, cfg: ChunkingConfig) -> list[Chunk]:
    if cfg.strategy == "recursive":
        return _chunk_recursive(doc, cfg)
    if cfg.strategy == "fixed":
        return _chunk_fixed(doc, cfg)
    if cfg.strategy == "semantic":
        return _chunk_semantic(doc, cfg)
    raise ValueError(f"unknown chunking strategy: {cfg.strategy!r}")


def _blocks_for(doc: Document) -> list[Block]:
    """Loaders provide blocks; fall back to a single block from `text` if none given
    (keeps direct `Document(..., text=...)` construction working)."""
    if doc.blocks:
        return doc.blocks
    return [Block(text=doc.text, section_path=doc.title)]


def _make_chunk(doc: Document, block: Block, idx: int, text: str, strategy: str) -> Chunk:
    return Chunk(
        # Deterministic id (doc + position) so re-ingesting the same document
        # overwrites its chunks instead of duplicating them.
        chunk_id=f"{doc.doc_id}::{idx}",
        doc_id=doc.doc_id,
        source=doc.source,
        section_path=block.section_path or doc.title,
        chunk_index=idx,
        text=text,
        token_count=count_tokens(text),
        strategy=strategy,
        file_type=doc.file_type,
        title=doc.title,
        page_number=block.page,
        locator=block.locator,
        content_type=block.content_type,
        char_count=len(text),
        created_at=str(doc.metadata.get("created_at", "")),
    )


# --- recursive: token-cap each structural block ------------------------------


def _chunk_recursive(doc: Document, cfg: ChunkingConfig) -> list[Chunk]:
    chunks: list[Chunk] = []
    idx = 0
    for block in _blocks_for(doc):
        for piece in split_by_tokens(block.text, cfg.max_chunk_tokens, cfg.overlap_tokens):
            piece = piece.strip()
            if len(piece) < cfg.min_chunk_chars:
                continue
            chunks.append(_make_chunk(doc, block, idx, piece, "recursive"))
            idx += 1
    return chunks


# --- fixed: token windows across blocks (structure-ignoring baseline) --------


def _chunk_fixed(doc: Document, cfg: ChunkingConfig) -> list[Chunk]:
    """Fixed-size windows over the whole document, ignoring block boundaries — but
    each window is attributed to the block its first token came from, so metadata
    (page/section) is still carried."""
    blocks = _blocks_for(doc)
    flat_ids: list[int] = []
    flat_block: list[int] = []  # block index per token id
    for bi, block in enumerate(blocks):
        ids = encode_tokens(block.text)
        flat_ids.extend(ids)
        flat_block.extend([bi] * len(ids))

    chunks: list[Chunk] = []
    idx = 0
    if not flat_ids:
        return chunks
    step = max(1, cfg.max_chunk_tokens - cfg.overlap_tokens)
    n = len(flat_ids)
    for start in range(0, n, step):
        window = flat_ids[start : start + cfg.max_chunk_tokens]
        if not window:
            break
        piece = decode_tokens(window).strip()
        if len(piece) >= cfg.min_chunk_chars:
            chunks.append(_make_chunk(doc, blocks[flat_block[start]], idx, piece, "fixed"))
            idx += 1
        if start + cfg.max_chunk_tokens >= n:
            break
    return chunks


# --- semantic (embedding-based) ----------------------------------------------


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT_RE.split(text) if s.strip()]


def _chunk_semantic(doc: Document, cfg: ChunkingConfig) -> list[Chunk]:
    """Group consecutive sentences while they stay on-topic (cosine sim to the
    running group's mean embedding); cut when similarity drops or the token cap is hit.
    Sentences are tagged with their source block; each group inherits its first
    sentence's block metadata."""
    import numpy as np

    from app.clients.embeddings import get_embedder

    blocks = _blocks_for(doc)
    sentences: list[str] = []
    sent_block: list[int] = []  # source block index per sentence
    for bi, block in enumerate(blocks):
        for s in _split_sentences(block.text):
            sentences.append(s)
            sent_block.append(bi)
    if not sentences:
        return []

    embs = np.array(get_embedder().embed_texts(sentences))  # normalized -> dot = cosine

    groups: list[tuple[int, str]] = []  # (block_index, text)
    cur: list[str] = [sentences[0]]
    cur_idx: list[int] = [0]

    for i in range(1, len(sentences)):
        centroid = embs[cur_idx].mean(axis=0)
        sim = float(centroid @ embs[i] / (np.linalg.norm(centroid) or 1.0))
        over_cap = count_tokens(" ".join(cur)) >= cfg.max_chunk_tokens
        if sim < cfg.semantic_threshold or over_cap:
            groups.append((sent_block[cur_idx[0]], " ".join(cur)))
            cur, cur_idx = [sentences[i]], [i]
        else:
            cur.append(sentences[i])
            cur_idx.append(i)
    groups.append((sent_block[cur_idx[0]], " ".join(cur)))

    chunks: list[Chunk] = []
    idx = 0
    for block_idx, group in groups:
        block = blocks[block_idx]
        # Safety token-cap in case a single low-similarity run still ran long.
        for piece in split_by_tokens(group, cfg.max_chunk_tokens, cfg.overlap_tokens):
            piece = piece.strip()
            if len(piece) < cfg.min_chunk_chars:
                continue
            chunks.append(_make_chunk(doc, block, idx, piece, "semantic"))
            idx += 1
    return chunks
