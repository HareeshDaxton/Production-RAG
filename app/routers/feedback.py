"""Auto-eval endpoints: feedback + candidate review queue."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.modules.autoeval import service
from app.modules.autoeval.capture import capture_feedback
from app.modules.autoeval.schemas import FeedbackRequest

router = APIRouter(prefix="/v1", tags=["autoeval"])


@router.post("/feedback")
def feedback(req: FeedbackRequest) -> dict:
    cid = capture_feedback(req.query, req.rating, req.comment)
    return {"recorded": True, "candidate_id": cid}


@router.get("/eval/candidates")
def candidates(status: str | None = None, limit: int = 100) -> dict:
    return {"candidates": service.list_candidates(status, limit)}


@router.post("/eval/candidates/process")
def process(limit: int = 20) -> dict:
    results = service.process_pending(limit)
    return {"processed": [{"id": r.id, "status": r.status} for r in results]}


@router.post("/eval/candidates/{candidate_id}/approve")
def approve(candidate_id: int) -> dict:
    try:
        case = service.approve(candidate_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"approved": True, "case": case.model_dump()}


@router.post("/eval/candidates/{candidate_id}/reject")
def reject(candidate_id: int) -> dict:
    try:
        service.reject(candidate_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"rejected": True}
