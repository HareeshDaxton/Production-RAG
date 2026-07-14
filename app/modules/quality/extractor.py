"""Citation extraction: map each inline [N] marker to the claim it backs and its source.

The generator writes answers like "Declare the type as `int` [2]." We parse those
markers, pair each cited number with the sentence(s) that reference it (the *claim*)
and the corresponding retrieved chunk (the *source*), so the judge can check whether
the source actually supports the claim. Numbers outside the retrieved range are
dropped (a citation to a non-existent block is itself a failure the caller can see).
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.modules.retrieval.dense import RetrievedChunk

_CITATION_RE = re.compile(r"\[(\d+)\]")
# Sentence boundary: end punctuation followed by whitespace.
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class ExtractedCitation:
    number: int
    claim: str  # the answer sentence(s) that cite this number
    source_text: str  # the cited chunk's text
    source: str  # filename
    section: str  # section breadcrumb


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT_RE.split(text.strip()) if s.strip()]


def extract_citations(
    answer: str, chunks: Sequence[RetrievedChunk]
) -> list[ExtractedCitation]:
    """Return one ExtractedCitation per distinct in-range [N] used in the answer."""
    claims: dict[int, list[str]] = {}
    for sentence in _sentences(answer):
        for m in _CITATION_RE.finditer(sentence):
            n = int(m.group(1))
            if 1 <= n <= len(chunks):
                claims.setdefault(n, []).append(sentence)

    extracted: list[ExtractedCitation] = []
    for n in sorted(claims):
        chunk = chunks[n - 1]
        extracted.append(
            ExtractedCitation(
                number=n,
                claim=" ".join(claims[n]),
                source_text=chunk.text,
                source=chunk.source,
                section=chunk.section_path,
            )
        )
    return extracted
