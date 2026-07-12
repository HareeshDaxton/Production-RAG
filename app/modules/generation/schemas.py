"""Structured LLM output contract for grounded generation."""
from __future__ import annotations

from pydantic import BaseModel, Field


class GeneratedAnswer(BaseModel):
    answer: str = Field(
        ..., description="Answer grounded ONLY in the context, with inline [n] citations."
    )
    citations_used: list[int] = Field(
        default_factory=list,
        description="Context block numbers actually referenced in the answer.",
    )
    has_sufficient_context: bool = Field(
        ..., description="False if the context did not contain enough info to answer."
    )
