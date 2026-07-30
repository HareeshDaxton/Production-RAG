"""POST /v1/title — name a conversation from its first question (ChatGPT-style)."""
from __future__ import annotations

from fastapi import APIRouter

from app.models.schemas import TitleRequest, TitleResponse
from app.modules.generation.generator import fallback_title, generate_title

router = APIRouter(prefix="/v1", tags=["chat"])


@router.post("/title", response_model=TitleResponse)
def title(req: TitleRequest) -> TitleResponse:
    """Cheap, isolated call so the UI can rename a chat without touching the answer path.

    `generate_title` never raises; it degrades to a trimmed question, and `generated`
    tells the client which of the two it got.
    """
    result = generate_title(req.question)
    return TitleResponse(title=result, generated=result != fallback_title(req.question))
