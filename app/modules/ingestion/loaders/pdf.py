"""PDF loader (PyMuPDF): one Block per page, so page numbers ride through to citations.

Text-based PDFs use native extraction. A page whose extractable text falls below
`ingestion.formats.pdf.scanned_text_density_threshold` is treated as *scanned* — flagged
here (content_type="scanned", doc metadata has_scanned_pages=True) and left for M4 to OCR.
Until then a scanned block carries no real text, so the chunker's min_chunk_chars gate
drops it and retrieval is unaffected.
"""
from __future__ import annotations

from pathlib import Path

from app.config import get_config
from app.modules.ingestion.loaders.base import (
    Block,
    Document,
    filename_title,
    iso_mtime,
    register,
)


def _title(meta: dict, path: Path) -> str:
    title = (meta or {}).get("title")
    if title and str(title).strip():
        return str(title).strip()
    return filename_title(path)


def _ocr_page(page, dpi: int) -> str:
    """Render a scanned PDF page to an image and OCR it. "" if OCR off/failed."""
    from app.modules.ingestion.ocr import ocr_image_bytes

    png = page.get_pixmap(dpi=dpi).tobytes("png")
    return ocr_image_bytes(png).strip()


@register("pdf", ".pdf")
def load(path: Path, rel: str) -> Document | None:
    import fitz  # PyMuPDF

    fmt = get_config().ingestion.formats
    threshold = fmt.pdf.scanned_text_density_threshold

    blocks: list[Block] = []
    has_scanned = False
    ocr_used = False
    with fitz.open(path) as pdf:
        page_count = pdf.page_count
        pdf_meta = pdf.metadata or {}
        for i, page in enumerate(pdf):
            text = page.get_text("text").strip()
            if len(text) >= threshold:
                blocks.append(Block(text=text, page=i + 1, content_type="text"))
                continue
            # Text-poor page: likely scanned. OCR it if enabled, else flag for later.
            has_scanned = True
            ocr_text = _ocr_page(page, fmt.ocr.dpi) if fmt.ocr.enabled else ""
            if ocr_text:
                ocr_used = True
                blocks.append(Block(text=ocr_text, page=i + 1, content_type="ocr"))
            else:
                blocks.append(Block(text="", page=i + 1, content_type="scanned"))

    if not any(b.text.strip() for b in blocks):
        # Nothing extractable (empty, or scanned with OCR off/failed).
        if not has_scanned:
            return None

    return Document(
        doc_id=rel,
        source=rel,
        title=_title(pdf_meta, path),
        text="\n\n".join(b.text for b in blocks if b.text),
        file_type="pdf",
        blocks=blocks,
        metadata={
            "created_at": iso_mtime(path),
            "page_count": page_count,
            "has_scanned_pages": has_scanned,
            "ocr_used": ocr_used,
        },
    )
