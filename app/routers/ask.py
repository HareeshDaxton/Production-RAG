"""POST /v1/ask — grounded, cited answer over the indexed corpus."""
from __future__ import annotations

from fastapi import APIRouter

from app.models.schemas import AskRequest, AskResponse
from app.modules.pipeline import ask as run_ask

router = APIRouter(prefix="/v1", tags=["ask"])


@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    return run_ask(req.query, req.top_k, req.mode)
