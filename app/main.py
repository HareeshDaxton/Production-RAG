"""FastAPI application entrypoint (modular monolith).

Run: uv run uvicorn app.main:app --reload
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.clients.db import init_db
from app.config import get_config
from app.logging_config import get_logger, setup_logging
from app.routers import health

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
    app.include_router(health.router)
    return app


app = create_app()
