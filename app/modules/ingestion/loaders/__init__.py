"""Format loaders. Importing the format modules registers them in `base.REGISTRY`."""
from __future__ import annotations

# Import each format module for its @register side effect (order irrelevant).
from app.modules.ingestion.loaders import (  # noqa: F401
    csv,
    docx,
    html,
    image,
    json,
    markdown,
    pdf,
    text,
    xml,
)
from app.modules.ingestion.loaders.base import REGISTRY, Block, Document, register

__all__ = ["REGISTRY", "Block", "Document", "register"]
