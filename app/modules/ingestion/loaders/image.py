"""Image loader: OCR pixels into text (content_type="ocr").

Runs only for image files. If OCR is disabled or fails, `ocr_image_bytes` returns ""
and the document is skipped with a logged warning — ingestion never crashes.
"""
from __future__ import annotations

from pathlib import Path

from app.logging_config import get_logger
from app.modules.ingestion.loaders.base import (
    Block,
    Document,
    filename_title,
    iso_mtime,
    register,
)

logger = get_logger(__name__)


@register("image", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp", ".gif")
def load(path: Path, rel: str) -> Document | None:
    from app.modules.ingestion.ocr import ocr_image_bytes

    text = ocr_image_bytes(path.read_bytes()).strip()
    if not text:
        logger.warning("no OCR text extracted; skipping image", extra={"source": rel})
        return None

    return Document(
        doc_id=rel,
        source=rel,
        title=filename_title(path),
        text=text,
        file_type="image",
        blocks=[Block(text=text, content_type="ocr")],
        metadata={"created_at": iso_mtime(path), "ocr_used": True},
    )
