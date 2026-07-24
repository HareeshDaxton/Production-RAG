"""Load documents into a normalized, block-based intermediate representation.

Loaders emit an ordered list of `Block`s — contiguous text spans that each carry
their own local metadata (page, section breadcrumb, structural locator, content
type). Every chunk is later produced from exactly one block and inherits that
block's metadata, so page/section provenance survives all three chunking strategies.

Phase M1 handles markdown (heading-section blocks). Additional formats (TXT, HTML,
PDF, DOCX, CSV, JSON, XML, images) are added as dedicated loaders in later phases.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import frontmatter

from app.logging_config import get_logger

logger = get_logger(__name__)

MARKDOWN_SUFFIXES = {".md", ".markdown"}
_H1_RE = re.compile(r"^#\s+(.*)$", re.MULTILINE)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


@dataclass
class Block:
    """A contiguous span of a document with its own local metadata."""

    text: str
    page: int | None = None  # 1-based page number (PDF); None otherwise
    section_path: str | None = None  # heading breadcrumb, e.g. "Guide > Auth > Rate Limiting"
    locator: str | None = None  # structured pointer, e.g. "rows 10-19" / "$.items[3]"
    content_type: str = "text"  # text|table|code|row|object|element|ocr


@dataclass
class Document:
    doc_id: str  # stable id (relative posix path)
    source: str  # human-readable source (relative path / filename)
    title: str
    text: str = ""  # full body (join of block texts); kept for back-compat
    file_type: str = "text"  # pdf|docx|txt|markdown|html|csv|json|xml|image
    blocks: list[Block] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)  # doc-level (created_at, page_count, ocr_used)


def _title_for(meta: dict, body: str, path: Path) -> str:
    if meta.get("title"):
        return str(meta["title"])
    m = _H1_RE.search(body)
    if m:
        return m.group(1).strip()
    return path.stem.replace("-", " ").replace("_", " ").title()


def split_into_sections(text: str, root_title: str) -> list[tuple[str, str]]:
    """Return [(section_path, content)] respecting the markdown heading hierarchy.

    Moved here from the chunker so markdown produces heading-section *blocks* at
    load time; the recursive chunker then just token-caps each block.
    """
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


def _markdown_blocks(body: str, title: str) -> list[Block]:
    return [
        Block(text=content, section_path=section_path, content_type="text")
        for section_path, content in split_into_sections(body, title)
    ]


def _iso_mtime(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()
    except OSError:
        return ""


def load_documents(source_dir: Path) -> list[Document]:
    """Recursively load all markdown files under `source_dir`."""
    source_dir = Path(source_dir)
    if not source_dir.exists():
        raise FileNotFoundError(f"corpus directory not found: {source_dir}")

    docs: list[Document] = []
    for path in sorted(source_dir.rglob("*")):
        if path.suffix.lower() not in MARKDOWN_SUFFIXES or not path.is_file():
            continue
        raw = path.read_text(encoding="utf-8")
        post = frontmatter.loads(raw)
        body = post.content.strip()
        if not body:
            continue
        rel = path.relative_to(source_dir).as_posix()
        title = _title_for(post.metadata, body, path)
        docs.append(
            Document(
                doc_id=rel,
                source=rel,
                title=title,
                text=body,
                file_type="markdown",
                blocks=_markdown_blocks(body, title),
                metadata={"created_at": _iso_mtime(path)},
            )
        )
    logger.info("documents loaded", extra={"count": len(docs), "dir": str(source_dir)})
    return docs
