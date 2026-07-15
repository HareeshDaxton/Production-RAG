"""Cache admin: GET /v1/cache/stats, POST /v1/cache/flush."""
from __future__ import annotations

from fastapi import APIRouter

from app.modules.cache import service as cache

router = APIRouter(prefix="/v1/cache", tags=["cache"])


@router.get("/stats")
def cache_stats() -> dict:
    return cache.stats()


@router.post("/flush")
def cache_flush() -> dict:
    return {"flushed": cache.flush()}
