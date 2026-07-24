"""M2: multi-format loader dispatch (txt + html). Fast — no models, no ChromaDB."""
from __future__ import annotations

from pathlib import Path

from app.modules.ingestion.loader import (
    REGISTRY,
    allowed_suffixes,
    load_documents,
)
from app.modules.ingestion.loaders import html as html_loader
from app.modules.ingestion.loaders import text as text_loader

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "multiformat"


def test_registry_maps_expected_suffixes():
    for suffix, fmt in {
        ".md": "markdown",
        ".markdown": "markdown",
        ".txt": "txt",
        ".html": "html",
        ".htm": "html",
    }.items():
        assert REGISTRY[suffix][0] == fmt


def test_txt_loader_single_block():
    doc = text_loader.load(FIXTURES / "sample.txt", "sample.txt")
    assert doc is not None
    assert doc.file_type == "txt"
    assert doc.title == "Sample"
    assert len(doc.blocks) == 1
    assert doc.blocks[0].content_type == "text"
    assert "FastAPI" in doc.blocks[0].text
    assert doc.metadata.get("created_at")


def test_html_loader_builds_heading_sections():
    doc = html_loader.load(FIXTURES / "sample.html", "sample.html")
    assert doc is not None
    assert doc.file_type == "html"
    assert doc.title == "FastAPI Guide"
    section_paths = {b.section_path for b in doc.blocks}
    assert "FastAPI Guide > Path Parameters" in section_paths
    assert "FastAPI Guide > Query Parameters" in section_paths
    # noise tags are stripped
    joined = "\n".join(b.text for b in doc.blocks)
    assert "navigation" not in joined.lower()
    assert "ignore this script" not in joined.lower()
    assert "int" in joined  # code content preserved as text


def test_dispatch_respects_allowlist():
    both = {d.file_type for d in load_documents(FIXTURES, enabled=["txt", "html"])}
    assert both == {"txt", "html"}

    only_txt = {d.file_type for d in load_documents(FIXTURES, enabled=["txt"])}
    assert only_txt == {"txt"}


def test_allowed_suffixes_reflects_enabled():
    assert allowed_suffixes(enabled=["txt"]) == {".txt"}
    assert allowed_suffixes(enabled=["markdown", "txt", "html"]) == {
        ".md",
        ".markdown",
        ".txt",
        ".html",
        ".htm",
    }
