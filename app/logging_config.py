"""Structured JSON logging to stdout (12-factor friendly)."""
from __future__ import annotations

import logging
import sys

try:  # python-json-logger >= 3.1 preferred import path
    from pythonjsonlogger.json import JsonFormatter
except ImportError:  # pragma: no cover - older versions
    from pythonjsonlogger.jsonlogger import JsonFormatter

_CONFIGURED = False


def setup_logging(level: str = "INFO") -> None:
    """Idempotently configure root logging as single-line JSON."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={
                "asctime": "timestamp",
                "levelname": "level",
                "name": "logger",
            },
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
