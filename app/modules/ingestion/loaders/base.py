"""Shared contract for format loaders: the block-based IR, a suffix→loader registry,
and small helpers reused across formats.

Each format module (`markdown`, `text`, `html`, …) registers itself with
`@register(<format_name>, <suffix>, …)`. The dispatcher in `loader.py` walks a
directory, routes each file to its registered loader, and keeps only formats that
are in the configured allowlist. `base` imports nothing from `loader`, so there is
no circular dependency.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


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


# A loader turns a file into a Document (or None to skip, e.g. empty body).
Loader = Callable[[Path, str], "Document | None"]

# suffix (lowercased, incl. dot) -> (format_name, loader)
REGISTRY: dict[str, tuple[str, Loader]] = {}


def register(format_name: str, *suffixes: str) -> Callable[[Loader], Loader]:
    """Decorator: register a loader for a format name and one or more file suffixes."""

    def deco(fn: Loader) -> Loader:
        for suffix in suffixes:
            REGISTRY[suffix.lower()] = (format_name, fn)
        return fn

    return deco


# --- shared helpers ----------------------------------------------------------


def read_text(path: Path) -> str:
    """Decode a file as UTF-8, replacing undecodable bytes (never raises on encoding)."""
    return path.read_bytes().decode("utf-8", errors="replace")


def filename_title(path: Path) -> str:
    return path.stem.replace("-", " ").replace("_", " ").title()


def iso_mtime(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()
    except OSError:
        return ""


def blocks_from_sections(sections: list[tuple[str, str]]) -> list[Block]:
    """Turn [(section_path, content)] into text Blocks (shared by markdown + html)."""
    return [
        Block(text=content, section_path=section_path, content_type="text")
        for section_path, content in sections
    ]
