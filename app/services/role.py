"""Which half of the system this process is.

One codebase, three entrypoints. A process announces its role through
RAG_SERVICE_ROLE (api | ingestion | retrieval | monolith) and everything else
follows from that plus `services.mode`:

    mode=monolith                  → every component runs in-process
    mode=distributed, role=api     → retrieval and ingestion are HTTP calls
    mode=distributed, role=retrieval → retrieval runs locally (it *is* the
                                       service), everything else is remote

That last case is the one that matters: without it the retrieval service would
call itself over HTTP forever.
"""
from __future__ import annotations

import os

from app.config import get_config

ROLE_ENV = "RAG_SERVICE_ROLE"

API = "api"
INGESTION = "ingestion"
RETRIEVAL = "retrieval"
MONOLITH = "monolith"

VALID_ROLES = (API, INGESTION, RETRIEVAL, MONOLITH)


def current_role() -> str:
    role = os.getenv(ROLE_ENV, MONOLITH).strip().lower()
    return role if role in VALID_ROLES else MONOLITH


def is_distributed() -> bool:
    return get_config().services.mode.lower() == "distributed"


def runs_locally(component: str) -> bool:
    """True when this process should execute `component` itself rather than call it."""
    if not is_distributed():
        return True
    return current_role() in (component, MONOLITH)
