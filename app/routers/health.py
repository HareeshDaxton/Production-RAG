"""Liveness (/health) and readiness (/ready) endpoints."""
from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.config import get_config
from app.models.schemas import HealthResponse, ReadyResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    cfg = get_config()
    return HealthResponse(status="ok", service=cfg.app.name, version=__version__)


@router.get("/ready", response_model=ReadyResponse)
def ready() -> ReadyResponse:
    """Deeper check that backing stores are reachable."""
    checks: dict[str, str] = {}

    try:
        from app.clients.db import get_db

        with get_db() as conn:
            conn.execute("SELECT 1")
        checks["sqlite"] = "ok"
    except Exception as exc:  # noqa: BLE001 - report, don't crash readiness
        checks["sqlite"] = f"error: {exc}"

    try:
        from app.clients.vectorstore import get_chunks_collection

        get_chunks_collection().count()
        checks["chroma"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["chroma"] = f"error: {exc}"

    status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return ReadyResponse(status=status, checks=checks)
