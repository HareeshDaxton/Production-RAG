"""POST /v1/ask — grounded, cited answer over the indexed corpus."""
from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.logging_config import get_logger
from app.models.schemas import AskRequest, AskResponse
from app.modules.pipeline import ask as run_ask
from app.modules.pipeline import ask_stream as run_ask_stream

logger = get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["ask"])


@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    return run_ask(req.query, req.top_k, req.mode, req.filters)


def _sse(event: dict) -> str:
    """Encode one Server-Sent Event frame."""
    return f"data: {json.dumps(event, default=str)}\n\n"


@router.post("/ask/stream")
def ask_stream(req: AskRequest) -> StreamingResponse:
    """Same pipeline as /v1/ask, streamed as SSE.

    Emits `meta`, then `delta` frames as the answer is generated, then a terminal
    `final` frame carrying the verified response (citations, confidence, and the IDK
    gate). Errors are delivered as a `error` frame rather than a mid-stream HTTP
    status, since the response has already begun by the time most failures surface.
    """

    def events() -> Iterator[str]:
        try:
            for event in run_ask_stream(req.query, req.top_k, req.mode, req.filters):
                yield _sse(event)
        except Exception as exc:  # noqa: BLE001 - surface failures to the client, don't 500 mid-stream
            logger.exception("ask stream failed")
            yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # stop nginx-style proxies buffering the stream
        },
    )
