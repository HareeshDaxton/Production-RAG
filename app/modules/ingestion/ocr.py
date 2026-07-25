"""Engine-agnostic OCR with graceful degrade.

The single choke point through which images and scanned PDF pages become text.
Loaders call `ocr_image_bytes(...)` and never touch an engine directly. Any failure
— OCR disabled, engine not installed, model download failure, unreadable image —
is logged and returns "" so ingestion never crashes.

Engine is config-selectable (`ingestion.formats.ocr.engine`): easyocr (default;
reuses the installed torch, no system binary) or tesseract (needs a system
Tesseract.exe + optional `pytesseract`).
"""
from __future__ import annotations

import io
from functools import lru_cache

from app.config import get_config
from app.logging_config import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def _easyocr_reader(languages: tuple[str, ...]):
    """Build the EasyOCR reader once (downloads ~90MB of models on first use)."""
    import easyocr  # heavy; imported lazily so app startup never loads it

    return easyocr.Reader(list(languages), gpu=False)


def _easyocr_text(data: bytes, languages: tuple[str, ...]) -> str:
    import numpy as np
    from PIL import Image

    image = Image.open(io.BytesIO(data)).convert("RGB")
    reader = _easyocr_reader(languages)
    lines = reader.readtext(np.array(image), detail=0, paragraph=True)
    return "\n".join(line.strip() for line in lines if line and line.strip())


def _tesseract_text(data: bytes, languages: tuple[str, ...]) -> str:
    import pytesseract  # optional; needs a system Tesseract.exe
    from PIL import Image

    image = Image.open(io.BytesIO(data)).convert("RGB")
    return pytesseract.image_to_string(image, lang="+".join(languages)).strip()


def ocr_image_bytes(data: bytes) -> str:
    """OCR raw image bytes → text. Returns "" if OCR is disabled or anything fails."""
    ocr_cfg = get_config().ingestion.formats.ocr
    if not ocr_cfg.enabled:
        return ""
    if not data:
        return ""

    languages = tuple(ocr_cfg.languages)
    try:
        if ocr_cfg.engine == "tesseract":
            return _tesseract_text(data, languages)
        return _easyocr_text(data, languages)
    except Exception as exc:  # noqa: BLE001 - OCR must never break ingestion
        logger.warning(
            "ocr failed; skipping content",
            extra={"engine": ocr_cfg.engine, "error": str(exc)},
        )
        return ""
