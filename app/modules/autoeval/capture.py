"""Flag weak answers and enqueue them as eval candidates (cheap: a DB insert, no LLM).

Runs inline in pipeline.ask on a cache miss. The expensive draft-generation happens
later in a separate process step, so capturing never slows /ask.
"""
from __future__ import annotations

from app.clients.db import enqueue_candidate
from app.config import get_config
from app.logging_config import get_logger
from app.models.schemas import AskResponse

logger = get_logger(__name__)


def should_flag(response: AskResponse) -> tuple[bool, str]:
    """Decide whether this answer is worth capturing, and why."""
    cfg = get_config().autoeval
    if response.cached:
        return False, ""  # already captured when first computed
    if cfg.capture_idk and not response.has_sufficient_context:
        return True, "idk"
    if response.confidence < cfg.flag_confidence_threshold:
        return True, "low_confidence"
    return False, ""


def capture(query: str, response: AskResponse) -> int | None:
    """Enqueue a candidate if the answer is flagged. Returns the candidate id or None."""
    cfg = get_config().autoeval
    if not cfg.enabled:
        return None
    flag, reason = should_flag(response)
    if not flag:
        return None
    sources = ",".join(c.source for c in response.citations)
    cid = enqueue_candidate(query, reason, sources)
    logger.info("eval candidate captured", extra={"id": cid, "reason": reason})
    return cid


def capture_feedback(query: str, rating: str, comment: str | None) -> int | None:
    """A thumbs-down enqueues a candidate directly (independent of confidence)."""
    from app.clients.db import record_feedback

    record_feedback(query, rating, comment)
    if rating == "down" and get_config().autoeval.enabled:
        cid = enqueue_candidate(query, "thumbs_down", "")
        logger.info("eval candidate from feedback", extra={"id": cid})
        return cid
    return None
