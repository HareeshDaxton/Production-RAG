"""Quality assessment: extract → verify → score, producing one report for the pipeline.

Given a generated answer and the chunks it was built from, this runs citation
verification (optional, config-gated), computes the composite confidence, and decides
whether the answer clears the IDK threshold. The pipeline uses the report to either
return the answer (annotated with per-citation verdicts) or a graceful "I don't know".
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.config import get_config
from app.logging_config import get_logger
from app.modules.quality.confidence import citation_accuracy, composite_confidence
from app.modules.quality.extractor import extract_citations
from app.modules.quality.verifier import CitationCheck, verify_citations
from app.modules.retrieval.dense import RetrievedChunk

logger = get_logger(__name__)


@dataclass
class QualityReport:
    checks: list[CitationCheck]  # per-citation verdicts (empty if verification skipped)
    citation_accuracy: float
    confidence: float  # composite, in [0, 1]
    breakdown: dict[str, float]  # {"retrieval", "citation", "self"}
    answerable: bool  # confidence >= quality.idk_threshold


def assess(
    query: str,
    answer_text: str,
    chunks: Sequence[RetrievedChunk],
    *,
    self_confidence: float,
    retrieval_confidence: float,
) -> QualityReport:
    cfg = get_config().quality

    extracted = extract_citations(answer_text, chunks)
    if cfg.verify_citations:
        checks = verify_citations(query, extracted)
        cit_acc = citation_accuracy(checks)
    else:
        # No judge: trust that citations exist (can't measure accuracy without it).
        checks = []
        cit_acc = 1.0 if extracted else 0.0

    confidence = composite_confidence(
        retrieval=retrieval_confidence,
        citation=cit_acc,
        self_confidence=self_confidence,
        weights=cfg.confidence_weights,
    )
    report = QualityReport(
        checks=checks,
        citation_accuracy=round(cit_acc, 4),
        confidence=confidence,
        breakdown={
            "retrieval": round(retrieval_confidence, 4),
            "citation": round(cit_acc, 4),
            "self": round(self_confidence, 4),
        },
        answerable=confidence >= cfg.idk_threshold,
    )
    logger.info(
        "quality assessed",
        extra={
            "confidence": confidence,
            "citation_accuracy": report.citation_accuracy,
            "answerable": report.answerable,
        },
    )
    return report
