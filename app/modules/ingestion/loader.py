"""Document loading: dispatch each file to its registered format loader.

This module is a thin facade over the `loaders/` package:
- re-exports `Block` / `Document` (and `MARKDOWN_SUFFIXES`) so existing imports keep working;
- `load_documents()` walks a directory and routes each file by suffix, honoring the
  configured format allowlist (`ingestion.formats.enabled`);
- `allowed_suffixes()` exposes the accepted upload extensions for the API gate.

Adding a format is a matter of dropping a new module in `loaders/` and registering it —
no change to this dispatcher.
"""
from __future__ import annotations

from pathlib import Path

from app.config import get_config
from app.logging_config import get_logger
from app.modules.ingestion.loaders import REGISTRY, Block, Document  # noqa: F401 - re-exported
from app.modules.ingestion.loaders.markdown import MARKDOWN_SUFFIXES  # noqa: F401 - back-compat

logger = get_logger(__name__)

__all__ = ["Block", "Document", "MARKDOWN_SUFFIXES", "allowed_suffixes", "load_documents"]


def _enabled_set(enabled: list[str] | None) -> set[str]:
    if enabled is None:
        return set(get_config().ingestion.formats.enabled)
    return set(enabled)


def allowed_suffixes(enabled: list[str] | None = None) -> set[str]:
    """File suffixes accepted right now = registered loaders ∩ configured allowlist."""
    allow = _enabled_set(enabled)
    return {suffix for suffix, (fmt, _) in REGISTRY.items() if fmt in allow}


def load_documents(source_dir: Path, enabled: list[str] | None = None) -> list[Document]:
    """Recursively load every supported, allowlisted file under `source_dir`."""
    source_dir = Path(source_dir)
    if not source_dir.exists():
        raise FileNotFoundError(f"corpus directory not found: {source_dir}")

    allow = _enabled_set(enabled)
    docs: list[Document] = []
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue
        entry = REGISTRY.get(path.suffix.lower())
        if entry is None:
            continue
        fmt, loader = entry
        if fmt not in allow:
            continue
        rel = path.relative_to(source_dir).as_posix()
        doc = loader(path, rel)
        if doc is not None:
            docs.append(doc)

    logger.info("documents loaded", extra={"count": len(docs), "dir": str(source_dir)})
    return docs
