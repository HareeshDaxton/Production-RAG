# Production RAG — Hybrid Search + Semantic Cache + Auto-Eval

A production-shaped Retrieval-Augmented Generation system over the **FastAPI docs +
GitHub issues** corpus. It combines triple retrieval (dense + BM25 + reranking),
citation verification, graceful "I don't know", a semantic cache, and an auto-growing
evaluation suite.

> **Status: Phase 0 (foundations).** Built incrementally in 9 phases — see the master plan.

## Stack
- **API:** FastAPI (modular monolith → services in Phase 8)
- **Vectors:** ChromaDB · **Sparse:** BM25 (Phase 2) · **Metadata/audit:** SQLite (→ Postgres Phase 8)
- **Models:** local embeddings (`bge-small-en-v1.5`) + local cross-encoder rerank +
  configurable judge; **OpenAI** for final grounded generation
- **Tooling:** `uv` (packaging), `pytest`, `ruff`

## Quickstart
```bash
# 1. install deps (creates .venv + uv.lock)
uv sync

# 2. configure secrets
cp .env.example .env          # then add your OPENAI_API_KEY

# 3. run the API
uv run uvicorn app.main:app --reload
#   -> http://127.0.0.1:8000/health   and   /ready   and   /docs

# 4. run tests
uv run pytest                 # add -m "not slow" to skip model-download tests
```

## Layout
```
app/
  config.py         # typed config (config/system.yaml + .env)
  logging_config.py # structured JSON logging
  main.py           # FastAPI app factory
  clients/          # embeddings, reranker, vectorstore, sqlite, llm
  routers/          # health (query/ingest/mgmt added per phase)
  modules/          # RAG modules, filled phase by phase
config/system.yaml  # all thresholds/models/paths (no magic numbers in code)
tests/              # smoke tests now; eval harness from Phase 4
```
