"""Semantic-cache load test: mixed unique / repeat / paraphrase queries.

Measures hit rate, hit-vs-miss latency, and estimated cost saved. Misses call the
generation model, so the base-question set is kept small. Requires Redis (docker
compose up -d redis), an ingested corpus, and OPENAI_API_KEY.

    uv run python scripts/cache_loadtest.py
"""
# ruff: noqa: E402  (sys.path shim must run before importing `app`)
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.modules.cache import service as cache
from app.modules.pipeline import ask

# (label, query). paraphrase/repeat rows target an earlier base question's meaning.
WORKLOAD = [
    ("base", "How do I declare a path parameter as an int in FastAPI?"),
    ("base", "How do I make a query parameter optional?"),
    ("base", "How do I return a 404 error when an item is not found?"),
    ("base", "How do I enable CORS in FastAPI?"),
    ("base", "How do I receive an uploaded file?"),
    ("repeat", "How do I declare a path parameter as an int in FastAPI?"),
    ("paraphrase", "How can I set the type of a path parameter to integer?"),
    ("paraphrase", "What's the way to make a query parameter not required?"),
    ("paraphrase", "How do I respond with a 404 when the item doesn't exist?"),
    ("paraphrase", "How do I turn on CORS for my FastAPI app?"),
    ("paraphrase", "How do I accept a file upload in FastAPI?"),
]


def main() -> int:
    print(f"flushing cache: removed {cache.flush()} entries\n")

    hit_lat: list[float] = []
    miss_lat: list[float] = []
    for label, query in WORKLOAD:
        t0 = time.perf_counter()
        resp = ask(query)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        (hit_lat if resp.cached else miss_lat).append(dt_ms)
        tag = f"HIT sim={resp.cache_similarity}" if resp.cached else "miss"
        print(f"  [{label:10}] {dt_ms:8.1f} ms  {tag}  | {query[:48]}")

    s = cache.stats()
    avg = lambda xs: round(sum(xs) / len(xs), 1) if xs else 0.0  # noqa: E731
    print("\n--- summary ---")
    print(f"queries        : {len(WORKLOAD)}")
    print(f"hits / misses  : {len(hit_lat)} / {len(miss_lat)}")
    print(f"hit_rate       : {s['hit_rate']}")
    print(f"avg hit  latency: {avg(hit_lat)} ms")
    print(f"avg miss latency: {avg(miss_lat)} ms")
    print(f"cost_saved_usd : {s['cost_saved_usd']}  (near_miss={s['near_miss']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
