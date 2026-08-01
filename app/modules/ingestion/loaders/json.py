"""JSON loader (stdlib): structure-aware descent to one block per record.

A JSON export is one document but often hundreds of records. Splitting only at the
top level leaves a single enormous block — `{"patients": [...]}` becomes one 50KB
block that token-slicing then cuts mid-record, so no chunk holds a whole patient and
every chunk carries the same useless locator. Instead the loader descends:

  * a list of objects always explodes, one block per element (`$.patients[41]`)
  * an object is kept whole if it fits `max_record_tokens`, otherwise split per key
  * scalars and lists of scalars stay with their parent

Each record's scalar fields are lifted into `Block.fields`, which become chunk
metadata — that is what allows `"patient_id": "PAT-20260042"` to be answered by an
exact lookup rather than by hoping the embedding lands on the right record.

Malformed JSON is skipped with a logged warning; ingest never crashes.
"""
from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Any

from app.config import JsonFormatConfig, get_config
from app.logging_config import get_logger
from app.modules.ingestion.loaders.base import (
    Block,
    Document,
    filename_title,
    iso_mtime,
    read_text,
    register,
)
from app.utils.tokens import count_tokens

logger = get_logger(__name__)


def _dump(value: Any) -> str:
    return _json.dumps(value, indent=2, ensure_ascii=False, sort_keys=False)


def _is_scalar(value: Any) -> bool:
    return not isinstance(value, (dict, list))


def _flatten_fields(value: Any, cfg: JsonFormatConfig, prefix: str = "") -> dict:
    """Scalar leaves of a record as `{"diagnosis.primary": "Asthma"}`.

    Only scalars, only up to `max_fields`, and only values short enough to be worth
    filtering on — metadata is for identity and equality, not for storing the record
    a second time.
    """
    out: dict = {}
    if not isinstance(value, dict):
        return out
    for key, val in value.items():
        if len(out) >= cfg.max_fields:
            break
        name = f"{prefix}{key}"
        if _is_scalar(val):
            if val is None:
                continue
            text = str(val)
            if len(text) <= cfg.max_field_chars:
                out[name] = val if isinstance(val, (int, float, bool)) else text
        elif isinstance(val, dict):
            out.update(_flatten_fields(val, cfg, prefix=f"{name}."))
    return dict(list(out.items())[: cfg.max_fields])


def _record_id(fields: dict, cfg: JsonFormatConfig) -> str | None:
    """The record's identifier, if it has one — first key that looks like an id.

    Matching is on the *leaf* name so `patient_id` and `name.id` both qualify, and
    exact-match keys ("id") win over suffix matches to avoid picking "guid" over "id".
    """
    lowered = {k.lower(): v for k, v in fields.items() if isinstance(v, (str, int))}
    for key in cfg.id_keys:
        for name, value in lowered.items():
            leaf = name.rsplit(".", 1)[-1]
            if leaf == key or leaf.endswith(f"_{key}") or leaf.endswith(key):
                return str(value)
    return None


def _walk(value: Any, path: str, cfg: JsonFormatConfig, depth: int) -> list[Block]:
    """Turn a JSON node into blocks, descending only while a node is too big."""
    if isinstance(value, list):
        # A list of scalars is a value, not a set of records — keep it with its key.
        if not value or all(_is_scalar(v) for v in value):
            return [_block(value, path, cfg)]
        if depth >= cfg.max_depth:
            return [_block(value, path, cfg)]
        blocks: list[Block] = []
        for i, item in enumerate(value):
            blocks.extend(_walk(item, f"{path}[{i}]", cfg, depth + 1))
        return blocks

    if isinstance(value, dict):
        text = _dump(value)
        # Fits → this *is* a record; keep it whole so one chunk holds one record.
        if count_tokens(text) <= cfg.max_record_tokens or depth >= cfg.max_depth:
            return [_block(value, path, cfg)]
        blocks = []
        for key, val in value.items():
            blocks.extend(_walk(val, f"{path}.{key}", cfg, depth + 1))
        return blocks

    return [_block(value, path, cfg)]


def _block(value: Any, path: str, cfg: JsonFormatConfig) -> Block:
    fields = _flatten_fields(value, cfg) if cfg.extract_fields else {}
    rid = _record_id(fields, cfg) if fields else None
    if rid:
        fields = {**fields, "record_id": rid}
    return Block(text=_dump(value), locator=path, content_type="object", fields=fields)


@register("json", ".json")
def load(path: Path, rel: str) -> Document | None:
    try:
        data = _json.loads(read_text(path))
    except ValueError as exc:
        logger.warning("invalid JSON; skipping", extra={"source": rel, "error": str(exc)})
        return None

    cfg = get_config().ingestion.formats.json_format
    blocks = [b for b in _walk(data, "$", cfg, depth=0) if b.text.strip()]
    if not blocks:
        return None

    logger.info(
        "json loaded",
        extra={"source": rel, "blocks": len(blocks),
               "with_id": sum(1 for b in blocks if b.fields.get("record_id"))},
    )
    return Document(
        doc_id=rel,
        source=rel,
        title=filename_title(path),
        text="\n\n".join(b.text for b in blocks),
        file_type="json",
        blocks=blocks,
        metadata={"created_at": iso_mtime(path)},
    )
