"""HTML loader (BeautifulSoup): strip noise, turn h1..h6 into section Blocks.

Produces the same heading-breadcrumb sections markdown does, so an answer sourced
from a web page can still cite `Section: Guide > Auth`.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.modules.ingestion.loaders.base import (
    Document,
    blocks_from_sections,
    filename_title,
    iso_mtime,
    read_text,
    register,
)

_STRIP_TAGS = ["script", "style", "nav", "header", "footer", "aside", "form"]
_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_WS_RE = re.compile(r"\s+")


def _soup(html: str):
    from bs4 import BeautifulSoup

    try:
        return BeautifulSoup(html, "lxml")
    except Exception:  # noqa: BLE001 - fall back to the stdlib parser if lxml is unavailable
        return BeautifulSoup(html, "html.parser")


def _title(soup, path: Path) -> str:
    if soup.title and soup.title.string and soup.title.string.strip():
        return soup.title.string.strip()
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    return filename_title(path)


def _sections(soup, root_title: str) -> list[tuple[str, str]]:
    """Walk the body in document order, segmenting text at headings into
    (section_path, content) pairs. Text is collected once (leaf strings only)."""
    from bs4 import NavigableString, Tag

    stack: list[tuple[int, str]] = []
    buf: list[str] = []
    sections: list[tuple[str, str]] = []

    def current_path() -> str:
        parts = [root_title, *[t for _, t in stack]]
        deduped: list[str] = []
        for p in parts:
            if p and (not deduped or deduped[-1] != p):
                deduped.append(p)
        return " > ".join(deduped)

    def flush() -> None:
        content = _WS_RE.sub(" ", " ".join(buf)).strip()
        if content:
            sections.append((current_path(), content))
        buf.clear()

    body = soup.body or soup
    for node in body.descendants:
        if isinstance(node, Tag) and node.name and node.name.lower() in _HEADINGS:
            flush()  # content so far belongs to the path *before* this heading
            level = int(node.name[1])
            title = node.get_text(" ", strip=True)
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
        elif isinstance(node, NavigableString):
            parent = node.parent
            if parent and parent.name and parent.name.lower() in _HEADINGS:
                continue  # heading text is already captured as the section boundary
            text = str(node).strip()
            if text:
                buf.append(text)
    flush()
    return sections


@register("html", ".html", ".htm")
def load(path: Path, rel: str) -> Document | None:
    soup = _soup(read_text(path))
    for tag in soup(_STRIP_TAGS):
        tag.decompose()
    title = _title(soup, path)
    sections = _sections(soup, title)
    if not sections:
        return None
    body = "\n\n".join(content for _, content in sections)
    return Document(
        doc_id=rel,
        source=rel,
        title=title,
        text=body,
        file_type="html",
        blocks=blocks_from_sections(sections),
        metadata={"created_at": iso_mtime(path)},
    )
