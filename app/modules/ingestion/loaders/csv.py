"""CSV loader (stdlib): group data rows into self-describing blocks.

A CSV is records, not prose, so blocks are made of whole rows (never split
mid-record) and each block prepends the header so every chunk is self-describing
(`col: value`). `formats.csv.rows_per_chunk` controls how many rows per block.
"""
from __future__ import annotations

import csv as _csv
import io
from pathlib import Path

from app.config import get_config
from app.modules.ingestion.loaders.base import (
    Block,
    Document,
    filename_title,
    iso_mtime,
    read_text,
    register,
)


def _normalise_header(header: list[str]) -> list[str]:
    """Give every column a name.

    Spreadsheet exports routinely merge header cells — one "Identifier" spanning three
    columns leaves two blanks — and a blank name renders as a bare ": value", which is
    noise to both the embedder and the reader. Blanks inherit the last named column
    with a positional suffix ("Identifier 2"), so every field stays addressable.
    """
    named: list[str] = []
    last, run = "", 1
    for i, raw in enumerate(header):
        name = raw.strip()
        if name:
            last, run = name, 1
        elif last:
            run += 1
            name = f"{last} {run}"
        else:
            name = f"column{i + 1}"
        named.append(name)
    return named


def _render_row(header: list[str], row: list[str]) -> str:
    """`col: value` pairs, skipping empty cells — a blank carries no information."""
    pairs = []
    for i, raw in enumerate(row):
        value = raw.strip()
        if not value:
            continue
        col = header[i] if i < len(header) else f"column{i + 1}"
        pairs.append(f"{col}: {value}")
    return " | ".join(pairs)


@register("csv", ".csv")
def load(path: Path, rel: str) -> Document | None:
    reader = _csv.reader(io.StringIO(read_text(path)))
    rows = [r for r in reader if any(cell.strip() for cell in r)]
    if not rows:
        return None

    header = _normalise_header(rows[0])
    data = rows[1:]
    if not data:
        return None

    header_line = "Columns: " + ", ".join(header)
    per_chunk = get_config().ingestion.formats.csv.rows_per_chunk

    blocks: list[Block] = []
    for start in range(0, len(data), per_chunk):
        window = data[start : start + per_chunk]
        body = "\n".join(_render_row(header, r) for r in window)
        # 1-based data-row range (header excluded).
        locator = f"rows {start + 1}-{start + len(window)}"
        blocks.append(
            Block(text=f"{header_line}\n{body}", locator=locator, content_type="row")
        )

    return Document(
        doc_id=rel,
        source=rel,
        title=filename_title(path),
        text="\n\n".join(b.text for b in blocks),
        file_type="csv",
        blocks=blocks,
        metadata={"created_at": iso_mtime(path), "row_count": len(data)},
    )
