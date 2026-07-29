"""FastAPI application entrypoint (modular monolith).

Run: uv run uvicorn app.main:app --reload
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.clients.db import init_db
from app.config import get_config
from app.logging_config import get_logger, setup_logging
from app.routers import ask, cache, feedback, health, ingest

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_config()
    setup_logging(cfg.app.log_level)
    cfg.paths.ensure()
    init_db()
    logger.info(
        "startup complete",
        extra={"service": cfg.app.name, "version": __version__, "env": cfg.app.environment},
    )
    yield
    logger.info("shutdown")


def create_app() -> FastAPI:
    cfg = get_config()
    setup_logging(cfg.app.log_level)
    app = FastAPI(title=cfg.app.name, version=__version__, lifespan=lifespan)
    # Browser clients (Phase 8 frontend) are cross-origin from the API; without this
    # every fetch from the Next.js dev server is blocked by the same-origin policy.
    if cfg.cors.enabled:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cfg.cors.allow_origins,
            allow_credentials=cfg.cors.allow_credentials,
            allow_methods=cfg.cors.allow_methods,
            allow_headers=cfg.cors.allow_headers,
        )
    app.include_router(health.router)
    app.include_router(ingest.router)
    app.include_router(ask.router)
    app.include_router(cache.router)
    app.include_router(feedback.router)
    return app


app = create_app()
