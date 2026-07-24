"""Markdown loader: front-matter aware, emits one Block per heading section."""
from __future__ import annotations

import re
from pathlib import Path

import frontmatter

from app.modules.ingestion.loaders.base import (
    Document,
    blocks_from_sections,
    filename_title,
    iso_mtime,
    read_text,
    register,
)

MARKDOWN_SUFFIXES = {".md", ".markdown"}
_H1_RE = re.compile(r"^#\s+(.*)$", re.MULTILINE)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def _title_for(meta: dict, body: str, path: Path) -> str:
    if meta.get("title"):
        return str(meta["title"])
    m = _H1_RE.search(body)
    if m:
        return m.group(1).strip()
    return filename_title(path)


def split_into_sections(text: str, root_title: str) -> list[tuple[str, str]]:
    """Return [(section_path, content)] respecting the markdown heading hierarchy."""
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


@register("markdown", ".md", ".markdown")
def load(path: Path, rel: str) -> Document | None:
    post = frontmatter.loads(read_text(path))
    body = post.content.strip()
    if not body:
        return None
    title = _title_for(post.metadata, body, path)
    return Document(
        doc_id=rel,
        source=rel,
        title=title,
        text=body,
        file_type="markdown",
        blocks=blocks_from_sections(split_into_sections(body, title)),
        metadata={"created_at": iso_mtime(path)},
    )
