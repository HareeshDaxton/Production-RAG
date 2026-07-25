"""M2: multi-format loader dispatch (txt + html). Fast — no models, no ChromaDB."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.modules.ingestion.loader import (
    REGISTRY,
    allowed_suffixes,
    load_documents,
)
from app.modules.ingestion.loaders import docx as docx_loader
from app.modules.ingestion.loaders import html as html_loader
from app.modules.ingestion.loaders import image as image_loader
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
        ".png": "image",
        ".jpg": "image",
        ".jpeg": "image",
        ".tiff": "image",
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


def test_pdf_scanned_page_is_flagged_not_extracted(monkeypatch):
    # Fake OCR to "" so the fast suite never loads the real engine; this asserts the
    # detection + degrade path (OCR yields nothing → page stays flagged scanned).
    monkeypatch.setattr("app.modules.ingestion.ocr.ocr_image_bytes", lambda _data: "")
    doc = pdf_loader.load(FIXTURES / "scanned.pdf", "scanned.pdf")
    assert doc is not None
    assert doc.metadata["has_scanned_pages"] is True
    assert all(b.content_type == "scanned" for b in doc.blocks)
    # scanned blocks carry no real text when OCR is unavailable; the chunker drops them
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


def test_pdf_docx_dispatch_and_suffixes(monkeypatch):
    # Directory sweep hits scanned.pdf; fake OCR so the fast suite skips the real engine.
    monkeypatch.setattr("app.modules.ingestion.ocr.ocr_image_bytes", lambda _data: "")
    docs = {d.file_type for d in load_documents(FIXTURES, enabled=["pdf", "docx"])}
    assert docs == {"pdf", "docx"}
    assert allowed_suffixes(enabled=["pdf", "docx"]) == {".pdf", ".docx"}


# --- M4: OCR (images + scanned PDF pages) -------------------------------------
# Fast tests patch the OCR choke point so wiring is covered without downloading
# the ~90MB EasyOCR models. A slow test exercises the real engine when present.


def test_image_loader_ocr_block(monkeypatch):
    monkeypatch.setattr(
        "app.modules.ingestion.ocr.ocr_image_bytes", lambda _data: "hello from ocr"
    )
    doc = image_loader.load(FIXTURES / "sample_image.png", "sample_image.png")
    assert doc is not None
    assert doc.file_type == "image"
    assert doc.metadata["ocr_used"] is True
    assert len(doc.blocks) == 1
    assert doc.blocks[0].content_type == "ocr"
    assert doc.blocks[0].text == "hello from ocr"


def test_image_loader_skips_when_no_text(monkeypatch):
    # OCR disabled or failed → "" → the document is skipped, never crashes.
    monkeypatch.setattr("app.modules.ingestion.ocr.ocr_image_bytes", lambda _data: "")
    assert image_loader.load(FIXTURES / "sample_image.png", "sample_image.png") is None


def test_pdf_scanned_page_filled_by_ocr(monkeypatch):
    monkeypatch.setattr(
        "app.modules.ingestion.ocr.ocr_image_bytes", lambda _data: "recovered page text"
    )
    doc = pdf_loader.load(FIXTURES / "scanned.pdf", "scanned.pdf")
    assert doc is not None
    assert doc.metadata["ocr_used"] is True
    assert doc.metadata["has_scanned_pages"] is True
    ocr_blocks = [b for b in doc.blocks if b.content_type == "ocr"]
    assert ocr_blocks and ocr_blocks[0].text == "recovered page text"
    assert ocr_blocks[0].page == 1


def test_pdf_scanned_page_degrades_when_ocr_empty(monkeypatch):
    # OCR returns "" (disabled/failed) → page stays flagged scanned, ocr_used False.
    monkeypatch.setattr("app.modules.ingestion.ocr.ocr_image_bytes", lambda _data: "")
    doc = pdf_loader.load(FIXTURES / "scanned.pdf", "scanned.pdf")
    assert doc is not None
    assert doc.metadata["ocr_used"] is False
    assert doc.metadata["has_scanned_pages"] is True
    assert all(b.content_type == "scanned" and b.text == "" for b in doc.blocks)


def test_ocr_disabled_returns_empty(monkeypatch):
    from app.config import get_config
    from app.modules.ingestion import ocr

    cfg = get_config()
    monkeypatch.setattr(cfg.ingestion.formats.ocr, "enabled", False)
    # Disabled short-circuits before any engine import, so bytes content is irrelevant.
    assert ocr.ocr_image_bytes(b"\x89PNG whatever") == ""


@pytest.mark.slow
def test_real_ocr_reads_image_text():
    """Real EasyOCR over the committed PNG (downloads models on first run)."""
    pytest.importorskip("easyocr")
    from app.modules.ingestion.ocr import ocr_image_bytes

    text = ocr_image_bytes((FIXTURES / "sample_image.png").read_bytes()).lower()
    assert "fastapi" in text
