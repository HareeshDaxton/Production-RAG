"""Plain-text loader: no structure, so the whole body is a single Block."""
from __future__ import annotations

from pathlib import Path

from app.modules.ingestion.loaders.base import (
    Block,
    Document,
    filename_title,
    iso_mtime,
    read_text,
    register,
)


@register("txt", ".txt")
def load(path: Path, rel: str) -> Document | None:
    body = read_text(path).strip()
    if not body:
        return None
    return Document(
        doc_id=rel,
        source=rel,
        title=filename_title(path),
        text=body,
        file_type="txt",
        blocks=[Block(text=body, content_type="text")],
        metadata={"created_at": iso_mtime(path)},
    )
