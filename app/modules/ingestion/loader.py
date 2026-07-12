"""Load markdown documents from a directory into normalized `Document` objects.

Frontmatter-aware (FastAPI docs use YAML front-matter). Phase 1 handles markdown;
HTML / GitHub-issues loaders are added when we wire the full corpus fetcher.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import frontmatter

from app.logging_config import get_logger

logger = get_logger(__name__)

MARKDOWN_SUFFIXES = {".md", ".markdown"}
_H1_RE = re.compile(r"^#\s+(.*)$", re.MULTILINE)


@dataclass
class Document:
    doc_id: str  # stable id (relative posix path)
    source: str  # human-readable source (relative path)
    title: str
    text: str  # markdown body, front-matter stripped


def _title_for(meta: dict, body: str, path: Path) -> str:
    if meta.get("title"):
        return str(meta["title"])
    m = _H1_RE.search(body)
    if m:
        return m.group(1).strip()
    return path.stem.replace("-", " ").replace("_", " ").title()


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
        docs.append(
            Document(
                doc_id=rel,
                source=rel,
                title=_title_for(post.metadata, body, path),
                text=body,
            )
        )
    logger.info("documents loaded", extra={"count": len(docs), "dir": str(source_dir)})
    return docs
