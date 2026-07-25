"""JSON loader (stdlib): one block per top-level element.

A JSON document is a tree; its natural unit is a record. A top-level array
yields one block per element (`$[i]`); a top-level object yields one block per
key (`$.key`), except an all-scalar object collapses to a single block so tiny
configs are not over-fragmented. Malformed JSON is skipped with a logged warning.
"""
from __future__ import annotations

import json as _json
from pathlib import Path

from app.logging_config import get_logger
from app.modules.ingestion.loaders.base import (
    Block,
    Document,
    filename_title,
    iso_mtime,
    read_text,
    register,
)

logger = get_logger(__name__)


def _dump(value) -> str:
    return _json.dumps(value, indent=2, ensure_ascii=False, sort_keys=False)


def _blocks_for(data) -> list[Block]:
    if isinstance(data, list):
        return [
            Block(text=_dump(item), locator=f"$[{i}]", content_type="object")
            for i, item in enumerate(data)
        ]
    if isinstance(data, dict):
        # All-scalar object → keep whole (one small record); else split per key.
        if all(not isinstance(v, (dict, list)) for v in data.values()):
            return [Block(text=_dump(data), locator="$", content_type="object")]
        return [
            Block(text=_dump(value), locator=f"$.{key}", content_type="object")
            for key, value in data.items()
        ]
    # Top-level scalar.
    return [Block(text=_dump(data), locator="$", content_type="object")]


@register("json", ".json")
def load(path: Path, rel: str) -> Document | None:
    try:
        data = _json.loads(read_text(path))
    except ValueError as exc:
        logger.warning("invalid JSON; skipping", extra={"source": rel, "error": str(exc)})
        return None

    blocks = [b for b in _blocks_for(data) if b.text.strip()]
    if not blocks:
        return None

    return Document(
        doc_id=rel,
        source=rel,
        title=filename_title(path),
        text="\n\n".join(b.text for b in blocks),
        file_type="json",
        blocks=blocks,
        metadata={"created_at": iso_mtime(path)},
    )
