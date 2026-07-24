"""DOCX loader (python-docx): heading styles become section breadcrumbs, tables become
table blocks — the same block shape markdown/html produce, so nothing downstream changes.

Only the modern zipped `.docx` is supported (python-docx cannot read legacy binary `.doc`).
"""
from __future__ import annotations

from pathlib import Path

from app.modules.ingestion.loaders.base import (
    Block,
    Document,
    filename_title,
    iso_mtime,
    register,
)


def _heading_level(style_name: str | None) -> int | None:
    """Return the heading level (1-6) for a Word heading style, else None."""
    if not style_name:
        return None
    name = style_name.strip().lower()
    if name.startswith("heading"):
        tail = name.replace("heading", "").strip()
        if tail.isdigit():
            level = int(tail)
            return level if 1 <= level <= 6 else 6
        return 1  # "Heading" with no number → top level
    if name == "title":
        return 1
    return None


def _table_text(table) -> str:
    rows = []
    for row in table.rows:
        cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
        rows.append(" | ".join(cells))
    return "\n".join(r for r in rows if r.strip())


def _iter_body(doc):
    """Yield ('para', paragraph) / ('table', table) in document order."""
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    parent = doc.element.body
    for child in parent.iterchildren():
        if child.tag.endswith("}p"):
            yield "para", Paragraph(child, doc)
        elif child.tag.endswith("}tbl"):
            yield "table", Table(child, doc)


@register("docx", ".docx")
def load(path: Path, rel: str) -> Document | None:
    from docx import Document as DocxDocument

    doc = DocxDocument(str(path))

    stack: list[tuple[int, str]] = []  # (level, heading text)
    buf: list[str] = []
    blocks: list[Block] = []
    doc_title: str | None = None

    def current_path() -> str | None:
        parts = [t for _, t in stack]
        deduped: list[str] = []
        for p in parts:
            if p and (not deduped or deduped[-1] != p):
                deduped.append(p)
        return " > ".join(deduped) if deduped else None

    def flush_text() -> None:
        content = "\n".join(buf).strip()
        if content:
            blocks.append(Block(text=content, section_path=current_path(), content_type="text"))
        buf.clear()

    for kind, item in _iter_body(doc):
        if kind == "para":
            level = _heading_level(item.style.name if item.style else None)
            text = item.text.strip()
            if level is not None:
                flush_text()  # text so far belongs to the section *before* this heading
                if text:
                    if doc_title is None:
                        doc_title = text
                    while stack and stack[-1][0] >= level:
                        stack.pop()
                    stack.append((level, text))
            elif text:
                buf.append(text)
        else:  # table
            flush_text()
            table_text = _table_text(item)
            if table_text:
                blocks.append(
                    Block(text=table_text, section_path=current_path(), content_type="table")
                )
    flush_text()

    if not blocks:
        return None

    title = doc_title or filename_title(path)
    return Document(
        doc_id=rel,
        source=rel,
        title=title,
        text="\n\n".join(b.text for b in blocks),
        file_type="docx",
        blocks=blocks,
        metadata={"created_at": iso_mtime(path)},
    )
