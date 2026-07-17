"""Auto-eval API/LLM contracts."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.modules.eval.schemas import CaseType


class FeedbackRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=2000)
    rating: Literal["up", "down"]
    comment: str | None = Field(default=None, max_length=1000)


class DraftCase(BaseModel):
    """The LLM's proposed golden case for a flagged query (drafted, not trusted)."""

    answer: str = Field(..., description="Concise correct reference answer, grounded in context.")
    type: CaseType = Field(..., description="simple | multi_hop | ambiguous | no_answer")
    sources: list[str] = Field(
        default_factory=list, description="Supporting source paths (empty for no_answer)."
    )
