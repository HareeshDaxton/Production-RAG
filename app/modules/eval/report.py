"""Render eval results: console tables, regression deltas vs the previous run, saved artifacts."""
from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from app.clients.db import get_previous_eval_metrics
from app.config import get_config
from app.modules.eval.schemas import EvalSummary

_METRIC_ORDER = [
    "overall_score",
    "retrieval_recall",
    "citation_accuracy",
    "correctness",
    "faithfulness",
    "completeness",
    "idk_accuracy",
]
_REPORT_DIR = Path("data/eval_reports")


def _fmt(v: float) -> str:
    return f"{v:.3f}"


def render_summary(summary: EvalSummary) -> str:
    lines = [
        f"Eval run {summary.run_id}  |  strategy={summary.strategy}  |  {summary.n_cases} cases",
        "-" * 60,
        f"{'metric':<22}{'score':>10}",
    ]
    for key in _METRIC_ORDER:
        if key in summary.metrics:
            lines.append(f"{key:<22}{_fmt(summary.metrics[key]):>10}")
    lines.append("")
    lines.append(f"{'score by case type':<22}")
    for t, s in sorted(summary.by_type.items()):
        lines.append(f"  {t:<20}{_fmt(s):>10}")
    return "\n".join(lines)


def regression_report(summary: EvalSummary) -> str:
    """Compare this run's metrics against the previous run for the same strategy."""
    prev_json = get_previous_eval_metrics(summary.strategy, summary.run_id)
    if not prev_json:
        return "regression: no previous run for this strategy (baseline established)."

    prev = json.loads(prev_json)
    tol = get_config().eval.regression_tolerance
    lines = ["regression vs previous run:", f"{'metric':<22}{'prev':>8}{'now':>8}{'delta':>9}"]
    regressed = False
    for key in _METRIC_ORDER:
        if key in summary.metrics and key in prev:
            now, was = summary.metrics[key], prev[key]
            delta = now - was
            flag = ""
            if key == "overall_score" and delta < -tol:
                flag = "  <-- REGRESSION"
                regressed = True
            lines.append(f"{key:<22}{_fmt(was):>8}{_fmt(now):>8}{delta:>+9.3f}{flag}")
    lines.append("RESULT: " + ("REGRESSION DETECTED" if regressed else "no regression"))
    return "\n".join(lines)


def render_benchmark(summaries: Sequence[EvalSummary]) -> str:
    """Side-by-side comparison of chunking strategies (the Phase 4 headline table)."""
    keys = [k for k in _METRIC_ORDER if any(k in s.metrics for s in summaries)]
    header = f"{'metric':<22}" + "".join(f"{s.strategy:>12}" for s in summaries)
    lines = ["Chunking strategy benchmark", "=" * len(header), header, "-" * len(header)]
    for key in keys:
        row = f"{key:<22}" + "".join(f"{_fmt(s.metrics.get(key, 0.0)):>12}" for s in summaries)
        lines.append(row)
    best = max(summaries, key=lambda s: s.metrics.get("overall_score", 0.0))
    lines.append("-" * len(header))
    lines.append(f"best overall_score: {best.strategy} ({_fmt(best.metrics['overall_score'])})")
    return "\n".join(lines)


def save_report(summary: EvalSummary, name: str = "latest") -> Path:
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = _REPORT_DIR / f"{name}.json"
    path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    return path


def save_benchmark(summaries: Sequence[EvalSummary]) -> Path:
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = _REPORT_DIR / "benchmark.json"
    payload = {s.strategy: s.metrics for s in summaries}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
