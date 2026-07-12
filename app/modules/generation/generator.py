"""Call the LLM to produce a grounded, cited answer as structured output."""
from __future__ import annotations

from collections.abc import Sequence

from app.clients.llm import get_instructor_client
from app.config import get_config
from app.logging_config import get_logger
from app.modules.generation.prompt import SYSTEM_PROMPT, build_user_prompt
from app.modules.generation.schemas import GeneratedAnswer
from app.modules.retrieval.dense import RetrievedChunk

logger = get_logger(__name__)


def generate_answer(query: str, chunks: Sequence[RetrievedChunk]) -> GeneratedAnswer:
    cfg = get_config().models.generation
    client = get_instructor_client()
    result: GeneratedAnswer = client.chat.completions.create(
        model=cfg.name,
        response_model=GeneratedAnswer,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(query, chunks)},
        ],
    )
    logger.info(
        "answer generated",
        extra={
            "citations": len(result.citations_used),
            "sufficient": result.has_sufficient_context,
        },
    )
    return result
