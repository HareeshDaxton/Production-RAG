"""XML loader (lxml): one block per top-level element.

Each direct child of the root becomes a block with an XPath-style locator
(`/root/child[i]`, 1-based per tag). Block text is the element's readable text
(attributes summarized, tags stripped). A root with no element children collapses
to a single block. Malformed XML is skipped with a logged warning.
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


def _localname(tag) -> str:
    from lxml import etree

    if not isinstance(tag, str):
        return "node"
    return etree.QName(tag).localname


def _element_text(el) -> str:
    from lxml import etree

    parts: list[str] = []
    if el.attrib:
        parts.append(" ".join(f"{_localname(k)}={v}" for k, v in el.attrib.items()))
    text = " ".join(t.strip() for t in el.itertext() if t and t.strip())
    if text:
        parts.append(text)
    return "\n".join(parts) if parts else etree.tostring(el, encoding="unicode").strip()


@register("xml", ".xml")
def load(path: Path, rel: str) -> Document | None:
    from lxml import etree

    try:
        root = etree.parse(str(path)).getroot()
    except (etree.XMLSyntaxError, OSError) as exc:
        logger.warning("invalid XML; skipping", extra={"source": rel, "error": str(exc)})
        return None

    root_name = _localname(root.tag)
    children = [c for c in root if isinstance(c.tag, str)]  # skip comments/PIs

    blocks: list[Block] = []
    if not children:
        text = _element_text(root)
        if text.strip():
            blocks.append(Block(text=text, locator=f"/{root_name}", content_type="element"))
    else:
        counts: dict[str, int] = {}
        for child in children:
            name = _localname(child.tag)
            counts[name] = counts.get(name, 0) + 1
            text = _element_text(child)
            if not text.strip():
                continue
            locator = f"/{root_name}/{name}[{counts[name]}]"
            blocks.append(Block(text=text, locator=locator, content_type="element"))

    if not blocks:
        return None

    return Document(
        doc_id=rel,
        source=rel,
        title=filename_title(path),
        text="\n\n".join(b.text for b in blocks),
        file_type="xml",
        blocks=blocks,
        metadata={"created_at": iso_mtime(path)},
    )
