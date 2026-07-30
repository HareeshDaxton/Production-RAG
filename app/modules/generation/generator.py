"""Call the LLM to produce a grounded, cited answer as structured output."""
from __future__ import annotations

from collections.abc import Iterator, Sequence

from app.clients.llm import get_instructor_client
from app.config import get_config
from app.logging_config import get_logger
from app.modules.generation.prompt import SYSTEM_PROMPT, build_title_prompt, build_user_prompt
from app.modules.generation.schemas import GeneratedAnswer, GeneratedTitle
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


def _trim(text: str, max_chars: int) -> str:
    """Collapse whitespace and cut at a word boundary."""
    clean = " ".join(text.split())
    if len(clean) <= max_chars:
        return clean
    cut = clean[:max_chars].rsplit(" ", 1)[0]
    return f"{cut or clean[:max_chars]}…"


def _clean_title(raw: str) -> str:
    """Strip the decorations models like to add around a title.

    Quotes and punctuation nest (`"Understanding RAG"?`), so peel until stable
    rather than in one pass.
    """
    title = " ".join(raw.split())
    while True:
        peeled = title.strip("\"'`“”‘’ ").rstrip(".!?:;")
        if peeled == title:
            return title
        title = peeled


def fallback_title(question: str) -> str:
    """What a conversation is called when titling is off or the model call fails."""
    return _trim(question, get_config().models.title.max_chars)


def generate_title(question: str) -> str:
    """Name a conversation from its opening question, ChatGPT-style.

    Never raises and never blocks the answer: any failure (or `enabled: false`)
    degrades to the trimmed question, which is what the UI shows meanwhile.
    """
    cfg = get_config().models.title
    fallback = fallback_title(question)
    if not cfg.enabled:
        return fallback

    try:
        result: GeneratedTitle = get_instructor_client().chat.completions.create(
            model=cfg.name,
            response_model=GeneratedTitle,
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
            messages=[
                {"role": "system", "content": build_title_prompt(cfg.max_words)},
                {"role": "user", "content": question},
            ],
        )
    except Exception:  # noqa: BLE001 - a missing title must never fail the chat
        logger.warning("title generation failed; falling back to the question", exc_info=True)
        return fallback

    title = _clean_title(result.title)
    logger.info("title generated", extra={"title": title})
    return _trim(title, cfg.max_chars) if title else fallback


def stream_answer(query: str, chunks: Sequence[RetrievedChunk]) -> Iterator[GeneratedAnswer]:
    """Yield progressively-filled `GeneratedAnswer` objects as the model streams.

    `create_partial` emits the same structured contract as `generate_answer`, one
    partial at a time, so the caller can forward `answer` deltas to the client while
    still ending up with citations/self_confidence for the quality layer. Fields are
    None until the model reaches them — callers must treat every field as optional.
    """
    cfg = get_config().models.generation
    client = get_instructor_client()
    return client.chat.completions.create_partial(
        model=cfg.name,
        response_model=GeneratedAnswer,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(query, chunks)},
        ],
    )
