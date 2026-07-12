# CLAUDE.md — Production RAG

> **Maintenance:** Claude owns this file. Update it whenever a conversation produces a durable
> decision, convention, or status change — and tell the user in-chat what changed each time.
> Keep it concise and current; it loads into context every session.

## Project
Portfolio-grade **Production RAG** system fusing BASWE Projects 6 (Hybrid Search) + 7 (Semantic
Cache) + 13 (Auto-Eval). Answers questions over the **FastAPI** docs + GitHub issues corpus.
Full 9-phase plan (source of truth): `C:\Users\Hareesh\.claude\plans\hey-now-act-as-deep-creek.md`.
Remote: https://github.com/HareeshDaxton/Production-RAG (branch `main`).

## Environment
- OS: Windows 11, PowerShell (primary shell). Project root: `e:\Production_RAG`.
- Python: **3.13.12** in the project `venv` (created by **uv**). The venv has **no `pip`** — this is
  normal for uv-managed envs.
- **Package manager: `uv`** (`C:\Users\Hareesh\.local\bin\uv.exe`). Install deps with
  `uv pip install --python e:\Production_RAG\venv\Scripts\python.exe ...` (targets the existing venv).
  Dependency source of truth = `pyproject.toml`. Do NOT use bare `pip`.
- Generation provider = **OpenAI** (`OPENAI_API_KEY` in `.env`). Embeddings/rerank/judge stay local/config.
- Secrets: never hardcode API keys — use `.env` (gitignored).

## Architecture guardrails
- **Modular monolith now → hard split into services in Phase 8.** Keep module boundaries clean
  (`app/{routers,modules,clients,models,utils}`) so the split is mechanical, not a rewrite.
- **Do not add infra before its phase:** Redis (cache) = Phase 5; Postgres+pgvector = Phase 8.
  Early datastores are ChromaDB (vectors) + SQLite (metadata/audit/eval) only.
- **Models:** local embeddings (`bge-base-en-v1.5`, **768-dim** — keep `models.embedding.dimensions`
  in sync with the model) + local cross-encoder rerank +
  configurable judge (Ollama or cheap API). API used only for final grounded generation.
- **No OCR** — corpus is text-first (markdown/HTML/issues JSON).

## Conventions
- **Config-driven:** thresholds, model names, chunking strategies live in `config/system.yaml` —
  no magic numbers in code.
- Pydantic for all request/response and LLM structured output (`instructor`).
- Structured JSON logging. Every phase ships with a smoke test + targeted unit tests.
- From Phase 4 on, the eval harness is the regression gate before merging later phases.

## Commands
- Install deps: `uv sync` (or `uv add <pkg>` / `uv add --dev <pkg>`).
- One-shot install of the whole manifest: `uv add -r requirements.txt`. NOTE: `requirements.txt` is a
  deliberate convenience installer (grouped by phase; frontend + Phase-8 infra commented). `pyproject.toml`
  + `uv.lock` remain the source of truth. **Do not delete `requirements.txt`.**
- Run API: `uv run uvicorn app.main:app --reload` → `/health`, `/ready`, `/docs`.
- Tests: `uv run pytest -m "not slow"` (fast) · `uv run pytest -m slow` (loads models) · `uv run pytest` (all).
- Lint: `uv run ruff check .`

## Status
- **Phase 0 COMPLETE & validated.** Modular-monolith scaffold in place: `app/` (config, logging,
  clients {embeddings, reranker, vectorstore, sqlite, llm}, routers/health, models, modules, utils),
  `config/system.yaml`, `tests/`. ChromaDB + SQLite init OK; local `bge-small-en-v1.5` embeds to
  384-dim OK; `/health` + `/ready` green. 3 fast tests pass, embedding slow test passes.
- **One path unverified — needs user:** OpenAI generation. Add `OPENAI_API_KEY` to `.env`
  (copy `.env.example`), then `uv run pytest` confirms `test_generation_roundtrip`.
- Key dep versions (3.13): fastapi 0.139, openai 2.45, instructor 1.15, chromadb 1.5.9,
  sentence-transformers 5.6, torch 2.13.
- **Next: Phase 1** — FastAPI corpus loader (docs + GitHub issues) → recursive chunking → dense
  index → cited generation → `POST /v1/ingest` + `POST /v1/ask`.

## Update log
- 2026-07-10: Created. Captured plan pointer, environment, architecture guardrails, conventions, status.
- 2026-07-11: Phase 0 started. Env facts locked: venv is uv-managed Python 3.13.12 (no pip); use `uv`
  for deps; generation provider = OpenAI. Next concrete step: create `pyproject.toml` + `app/` package
  and run `uv pip install` into the venv (pause if a heavy wheel fails).
- 2026-07-11: Phase 0 COMPLETE. User ran `uv init` (git repo + pyproject + `.venv`); adopted uv-project
  workflow (`uv add`, `uv.lock`). All deps installed on 3.13. Built app scaffold, config, clients,
  health/ready, structured logging, smoke tests (pass). Added Commands section. Only OpenAI generation
  path awaits the user's `.env` key. Next = Phase 1.
- 2026-07-11: Committed Phase 0 as 7 clean Conventional-Commits and pushed to GitHub
  (origin/main, HareeshDaxton/Production-RAG). Added `.gitattributes` (LF). `.claude/settings.local.json`
  gitignored; empty `requirements.txt` removed.
