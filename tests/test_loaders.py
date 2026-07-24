"""M2: multi-format loader dispatch (txt + html). Fast — no models, no ChromaDB."""
from __future__ import annotations

from pathlib import Path

from app.modules.ingestion.loader import (
    REGISTRY,
    allowed_suffixes,
    load_documents,
)
from app.modules.ingestion.loaders import docx as docx_loader
from app.modules.ingestion.loaders import html as html_loader
from app.modules.ingestion.loaders import pdf as pdf_loader
from app.modules.ingestion.loaders import text as text_loader

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "multiformat"


def test_registry_maps_expected_suffixes():
    for suffix, fmt in {
        ".md": "markdown",
        ".markdown": "markdown",
        ".txt": "txt",
        ".html": "html",
        ".htm": "html",
        ".pdf": "pdf",
        ".docx": "docx",
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


# --- M3: PDF + DOCX -----------------------------------------------------------
# Binary fixtures (sample.pdf, scanned.pdf, sample.docx) are generated with
# PyMuPDF / python-docx; see the M3 fixture-generation snippet in the commit history.


def test_pdf_loader_one_block_per_page():
    doc = pdf_loader.load(FIXTURES / "sample.pdf", "sample.pdf")
    assert doc is not None
    assert doc.file_type == "pdf"
    assert doc.title == "FastAPI Guide"
    assert doc.metadata["page_count"] == 2
    assert doc.metadata["has_scanned_pages"] is False
    # one block per page, 1-based page numbers, text preserved
    assert [b.page for b in doc.blocks] == [1, 2]
    assert "Pydantic" in doc.blocks[0].text
    assert "path parameter" in doc.blocks[1].text.lower()


def test_pdf_scanned_page_is_flagged_not_extracted():
    doc = pdf_loader.load(FIXTURES / "scanned.pdf", "scanned.pdf")
    assert doc is not None
    assert doc.metadata["has_scanned_pages"] is True
    assert all(b.content_type == "scanned" for b in doc.blocks)
    # scanned blocks carry no real text (OCR is M4); the chunker drops them
    assert all(b.text.strip() == "" for b in doc.blocks)


def test_docx_loader_headings_and_table():
    doc = docx_loader.load(FIXTURES / "sample.docx", "sample.docx")
    assert doc is not None
    assert doc.file_type == "docx"
    assert doc.title == "FastAPI Guide"
    section_paths = {b.section_path for b in doc.blocks}
    assert "FastAPI Guide > Path Parameters" in section_paths
    assert "FastAPI Guide > Query Parameters" in section_paths
    # the table becomes a table-typed block
    table_blocks = [b for b in doc.blocks if b.content_type == "table"]
    assert table_blocks
    assert "item_id" in table_blocks[0].text
    assert "|" in table_blocks[0].text  # cells are pipe-separated


def test_pdf_docx_dispatch_and_suffixes():
    docs = {d.file_type for d in load_documents(FIXTURES, enabled=["pdf", "docx"])}
    assert docs == {"pdf", "docx"}
    assert allowed_suffixes(enabled=["pdf", "docx"]) == {".pdf", ".docx"}
