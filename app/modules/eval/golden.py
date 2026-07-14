"""Load and validate the human-authored golden set from JSONL."""
from __future__ import annotations

import json
from pathlib import Path

from app.config import get_config
from app.logging_config import get_logger
from app.modules.eval.schemas import GoldenCase

logger = get_logger(__name__)


def load_golden_set(path: str | Path | None = None) -> list[GoldenCase]:
    """Parse `eval/golden_set.jsonl` (one JSON object per non-empty line)."""
    p = Path(path) if path else get_config().eval.golden_path
    if not p.exists():
        raise FileNotFoundError(f"golden set not found: {p}")

    cases: list[GoldenCase] = []
    ids: set[str] = set()
    for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            case = GoldenCase(**json.loads(line))
        except Exception as exc:  # noqa: BLE001 - surface which line is malformed
            raise ValueError(f"invalid golden case on line {lineno}: {exc}") from exc
        if case.id in ids:
            raise ValueError(f"duplicate golden case id: {case.id!r} (line {lineno})")
        ids.add(case.id)
        cases.append(case)

    logger.info("golden set loaded", extra={"cases": len(cases), "path": str(p)})
    return cases
