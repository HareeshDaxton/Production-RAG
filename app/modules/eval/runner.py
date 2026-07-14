"""Eval runner: answer every golden case, score it, aggregate + persist a summary.

Per case:
  - ask() the pipeline (answer + citations + composite confidence + IDK gate)
  - retrieve() again for the retrieved sources (retrieval recall is deterministic)
  - no_answer cases are scored on whether the system correctly refused (idk_correct);
    answerable cases are graded by the judge against the human reference answer.
"""
from __future__ import annotations

import json
import uuid
from collections.abc import Sequence

from app.clients.db import record_eval_run
from app.config import get_config
from app.logging_config import get_logger
from app.modules.eval.metrics import judge_answer, retrieval_recall
from app.modules.eval.schemas import CaseResult, EvalSummary, GoldenCase
from app.modules.pipeline import ask
from app.modules.retrieval.retriever import retrieve

logger = get_logger(__name__)

# Metrics averaged into the headline table (answerable cases only for judge metrics).
_HEADLINE = ["retrieval_recall", "citation_accuracy", "correctness", "faithfulness", "completeness"]


def _score_case(case: GoldenCase, resp, retrieved_sources: set[str]) -> CaseResult:
    recall = retrieval_recall(case.expected_sources, retrieved_sources)
    citation_acc = float(resp.confidence_breakdown.get("citation", 0.0))
    answered = resp.has_sufficient_context

    if case.type == "no_answer":
        # Correct behaviour is to refuse. Score entirely on that.
        idk_correct = not answered
        score = 1.0 if idk_correct else 0.0
        return CaseResult(
            id=case.id, type=case.type, question=case.question, answered=answered,
            retrieval_recall=recall, citation_accuracy=citation_acc, idk_correct=idk_correct,
            correctness=1.0 if idk_correct else 0.0, faithfulness=1.0 if idk_correct else 0.0,
            completeness=1.0 if idk_correct else 0.0, score=score,
            confidence=resp.confidence, retrieval_mode=resp.retrieval_mode,
        )

    # Answerable case: if it wrongly refused, everything judge-related is 0.
    if not answered:
        return CaseResult(
            id=case.id, type=case.type, question=case.question, answered=False,
            retrieval_recall=recall, citation_accuracy=citation_acc, idk_correct=None,
            correctness=0.0, faithfulness=0.0, completeness=0.0,
            score=round(recall * 0.5, 4),  # partial credit if it at least retrieved the right doc
            confidence=resp.confidence, retrieval_mode=resp.retrieval_mode,
        )

    j = judge_answer(case.question, case.expected_answer, resp.answer)
    score = round(
        (recall + citation_acc + j.correctness + j.faithfulness + j.completeness) / 5.0, 4
    )
    return CaseResult(
        id=case.id, type=case.type, question=case.question, answered=True,
        retrieval_recall=recall, citation_accuracy=citation_acc, idk_correct=None,
        correctness=j.correctness, faithfulness=j.faithfulness, completeness=j.completeness,
        score=score, confidence=resp.confidence, retrieval_mode=resp.retrieval_mode,
    )


def _aggregate(case_results: Sequence[CaseResult]) -> tuple[dict[str, float], dict[str, float]]:
    n = len(case_results)
    metrics: dict[str, float] = {}
    for key in _HEADLINE:
        metrics[key] = round(sum(getattr(c, key) for c in case_results) / n, 4) if n else 0.0
    metrics["overall_score"] = round(sum(c.score for c in case_results) / n, 4) if n else 0.0

    no_answer = [c for c in case_results if c.type == "no_answer"]
    if no_answer:
        metrics["idk_accuracy"] = round(
            sum(1 for c in no_answer if c.idk_correct) / len(no_answer), 4
        )

    by_type: dict[str, float] = {}
    for t in {c.type for c in case_results}:
        rows = [c for c in case_results if c.type == t]
        by_type[t] = round(sum(c.score for c in rows) / len(rows), 4)
    return metrics, by_type


def run_eval(
    cases: Sequence[GoldenCase], strategy: str, *, persist: bool = True
) -> EvalSummary:
    """Answer + score every case; aggregate and (optionally) persist the run."""
    cfg = get_config()
    k = cfg.eval.retrieval_k
    run_id = uuid.uuid4().hex[:12]

    results: list[CaseResult] = []
    for case in cases:
        try:
            resp = ask(case.question, top_k=k)
            retrieved_sources = {c.source for c in retrieve(case.question, k).chunks}
            results.append(_score_case(case, resp, retrieved_sources))
        except Exception as exc:  # noqa: BLE001 - one bad case shouldn't kill the run
            logger.warning("eval case failed", extra={"id": case.id, "error": str(exc)})
            results.append(
                CaseResult(
                    id=case.id, type=case.type, question=case.question, answered=False,
                    retrieval_recall=0.0, citation_accuracy=0.0, idk_correct=None,
                    correctness=0.0, faithfulness=0.0, completeness=0.0, score=0.0,
                    confidence=0.0, retrieval_mode="error", error=str(exc),
                )
            )

    metrics, by_type = _aggregate(results)
    summary = EvalSummary(
        run_id=run_id, strategy=strategy, n_cases=len(results),
        metrics=metrics, by_type=by_type, case_results=results,
    )

    if persist:
        record_eval_run(
            run_id=run_id,
            strategy=strategy,
            n_cases=len(results),
            metrics_json=json.dumps(metrics),
            case_rows=[
                (c.id, c.type, c.score, c.model_dump_json()) for c in results
            ],
        )
    logger.info("eval run complete", extra={"run_id": run_id, "strategy": strategy, **metrics})
    return summary
