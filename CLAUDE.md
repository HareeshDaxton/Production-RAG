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
- **Phase 0 COMPLETE.** Modular-monolith scaffold: `app/` (config, logging, clients, routers, models,
  modules, utils), `config/system.yaml`, tests. OpenAI key verified working.
- **Phase 1 COMPLETE & validated (8/8 tests green, lint clean).** Working thin slice:
  `POST /v1/ingest` (markdown loader → recursive-by-header chunker → local bge-base embed → ChromaDB)
  and `POST /v1/ask` (dense retrieve top-k → grounded generation via `instructor` → answer + inline
  `[n]` citations + `has_sufficient_context`). Verified end-to-end over the real HTTP API on
  `sample_docs/` (3 docs → 12 chunks; correct cited answer). SQLite schema now ensured on every
  connection (works for API, tests, scripts). `ingest_directory(reset=True)` clears the collection.
- Key dep versions (3.13): fastapi 0.139, openai 2.45, instructor 1.15, chromadb 1.5.9,
  sentence-transformers 5.6, torch 2.13, python-multipart 0.0.32. Embedding = `bge-base-en-v1.5` (768-dim).
- **Phase 1 follow-ups COMPLETE (9/9 tests green, lint clean):**
  - `scripts/fetch_corpus.py` — fetches the FULL FastAPI docs (`docs/en/docs/**/*.md`) + GitHub
    issues into `data/corpus/{docs,issues}` as front-matter markdown (loader ingests unchanged).
    CLI: `--docs-only/--issues-only/--max-issues/--repo/--ref/--stats`; honours `GITHUB_TOKEN`.
    Live-verified (3-issue smoke pull → ingested 3 docs/12 chunks).
  - File-upload ingest: `POST /v1/ingest/upload` (multipart; markdown only) → temp dir → same pipeline.
  - Dedup/upsert on re-ingest: chunk ids are deterministic (`{doc_id}::{idx}`) and `index_chunks`
    deletes a doc's prior chunks before re-adding, so re-ingest is idempotent per-doc (no dupes,
    prunes stale chunks). `reset=True` still does a full-collection wipe. Regression test added.
- **Next: Phase 2** — hybrid retrieval (BM25 + RRF + cross-encoder rerank), 3 switchable chunking
  strategies, retrieval-confidence scoring.

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
- 2026-07-12: **Phase 1 COMPLETE.** Built `app/modules/{ingestion(loader,chunker,indexer,service),
  retrieval(dense),generation(schemas,prompt,generator),pipeline}`, `app/routers/{ingest,ask}`,
  `app/utils/tokens.py`, `sample_docs/*.md`, `tests/test_ingest_ask.py`; extended `models/schemas.py`,
  `clients/{db,vectorstore}`, `config`. Fix: SQLite schema ensured on every connection (tests hit
  `ingest_directory` directly, bypassing API startup). Polish: dedupe repeated section-path segments.
  8/8 tests pass, ruff clean, live `/v1/ingest`+`/v1/ask` verified. NOT committed yet (user commits).
  Next = Phase 2.
- 2026-07-13: **Phase 1 follow-ups COMPLETE** (Phase 1 now fully done). Added `scripts/fetch_corpus.py`
  (full FastAPI docs + GitHub issues → `data/corpus/`), `POST /v1/ingest/upload` (multipart file
  upload), and idempotent re-ingest (deterministic chunk ids + per-doc delete-before-add in
  `index_chunks`; `service.ingest_files`). Added `python-multipart` dep + ruff `flake8-bugbear`
  immutable-calls for FastAPI `File/Form/Query/Depends/Body`. New dedup regression test → 9/9 green,
  ruff clean. Fetch script live-verified (3-issue pull ingested to 12 chunks). User commits.
