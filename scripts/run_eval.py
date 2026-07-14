"""Run the evaluation harness (the Phase 4 regression gate).

    uv run python scripts/run_eval.py                  # eval current index; regression vs last run
    uv run python scripts/run_eval.py --strategy fixed # re-ingest with a strategy, then eval
    uv run python scripts/run_eval.py --benchmark      # eval all 3 chunkers -> comparison table
    uv run python scripts/run_eval.py --limit 4        # only the first N cases (cheap smoke)

Answering questions calls the generation + judge models, so a full run makes API calls.
"""
# ruff: noqa: E402  (sys.path shim must run before importing `app`)
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make `app` importable

from app.config import get_config
from app.modules.eval.golden import load_golden_set
from app.modules.eval.report import (
    regression_report,
    render_benchmark,
    render_summary,
    save_benchmark,
    save_report,
)
from app.modules.eval.runner import run_eval
from app.modules.ingestion.service import ingest_directory


def _reingest(strategy: str) -> None:
    cfg = get_config()
    cfg.ingestion.chunking.strategy = strategy  # mutate the cached config for this process
    print(f"  ingesting corpus with strategy={strategy} ...", flush=True)
    result = ingest_directory(cfg.ingestion.corpus.dir, reset=True)
    print(f"  ingested {result.documents} docs -> {result.chunks} chunks", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the RAG evaluation harness.")
    parser.add_argument("--benchmark", action="store_true", help="compare all 3 chunkers")
    parser.add_argument("--strategy", help="re-ingest with this chunker, then eval")
    parser.add_argument("--reingest", action="store_true", help="re-ingest before eval")
    parser.add_argument("--limit", type=int, help="evaluate only the first N cases")
    parser.add_argument("--golden", help="path to a golden set JSONL (default: config)")
    args = parser.parse_args()

    cases = load_golden_set(args.golden)
    if args.limit:
        cases = cases[: args.limit]
    print(f"loaded {len(cases)} golden cases")

    if args.benchmark:
        summaries = []
        for strat in get_config().eval.strategies:
            print(f"\n=== strategy: {strat} ===")
            _reingest(strat)
            summary = run_eval(cases, strat)
            print(render_summary(summary))
            summaries.append(summary)
        print("\n" + render_benchmark(summaries))
        print(f"\nsaved: {save_benchmark(summaries)}")
        return 0

    strategy = args.strategy or get_config().ingestion.chunking.strategy
    if args.strategy or args.reingest:
        _reingest(strategy)
    summary = run_eval(cases, strategy)
    print("\n" + render_summary(summary))
    print("\n" + regression_report(summary))
    print(f"\nsaved: {save_report(summary)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
