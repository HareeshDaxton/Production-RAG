"""Auto-eval orchestration: process the queue, then human approve/reject.

process_pending() drafts each pending candidate (double-run + dedup) and sets a status:
  - rejected_duplicate : already covered by a golden case
  - auto_approved      : the two drafts agreed (still needs a human ok)
  - needs_review       : drafts disagreed → a human must decide
approve() appends the case to the candidates file (NOT the hand-authored golden set).
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from app.clients import db
from app.config import get_config
from app.logging_config import get_logger
from app.modules.autoeval.generator import draft, is_duplicate, runs_agree
from app.modules.eval.schemas import GoldenCase

logger = get_logger(__name__)


@dataclass
class ProcessResult:
    id: int
    status: str


def process_pending(limit: int = 20) -> list[ProcessResult]:
    from app.modules.retrieval.retriever import retrieve

    k = get_config().eval.retrieval_k
    results: list[ProcessResult] = []
    for cand in db.list_candidates("pending", limit):
        cid, query = cand["id"], cand["query"]

        if is_duplicate(query):
            db.update_candidate(cid, status="rejected_duplicate")
            results.append(ProcessResult(cid, "rejected_duplicate"))
            continue

        chunks = retrieve(query, k).chunks
        d1, d2 = draft(query, chunks), draft(query, chunks)
        agree = runs_agree(d1, d2)
        status = "auto_approved" if agree else "needs_review"
        db.update_candidate(
            cid,
            proposed_answer=d1.answer,
            proposed_type=d1.type,
            proposed_sources=json.dumps(d1.sources),
            agreement=int(agree),
            status=status,
        )
        results.append(ProcessResult(cid, status))
    logger.info("candidates processed", extra={"count": len(results)})
    return results


def approve(candidate_id: int) -> GoldenCase:
    cand = db.get_candidate(candidate_id)
    if not cand:
        raise ValueError(f"candidate {candidate_id} not found")
    if not cand.get("proposed_answer") or not cand.get("proposed_type"):
        raise ValueError(f"candidate {candidate_id} not processed yet (run process first)")

    case = GoldenCase(
        id=f"auto-{candidate_id}",
        type=cand["proposed_type"],
        question=cand["query"],
        expected_answer=cand["proposed_answer"],
        expected_sources=json.loads(cand.get("proposed_sources") or "[]"),
        notes=f"auto-eval candidate (reason={cand.get('reason')})",
    )
    path = get_config().autoeval.candidates_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(case.model_dump_json() + "\n")

    db.update_candidate(candidate_id, status="approved")
    logger.info("candidate approved", extra={"id": candidate_id, "path": str(path)})
    return case


def reject(candidate_id: int) -> None:
    if not db.get_candidate(candidate_id):
        raise ValueError(f"candidate {candidate_id} not found")
    db.update_candidate(candidate_id, status="rejected")


def list_candidates(status: str | None = None, limit: int = 100) -> list[dict]:
    return db.list_candidates(status, limit)
