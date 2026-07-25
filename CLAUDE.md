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
- **OCR is in-scope (Ingestion-v2 M4)** — reverses the original "No OCR" guardrail. OCR runs
  **only** for image files + *scanned* PDF pages (text PDFs/DOCX/HTML keep native extraction).
  Engine is config-selectable (`easyocr` default | `tesseract`); disabled/unavailable → scanned
  content is skipped gracefully, ingest never crashes.

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
- **Phase 2 COMPLETE & validated (15/15 tests green, lint clean).** Hybrid retrieval:
  `app/modules/retrieval/{sparse,fusion,confidence,hybrid,retriever}.py`. Flow =
  dense (top `dense_candidates`) + BM25 sparse (top `sparse_candidates`) → **RRF fusion**
  (config weights, `rrf_k`) → **cross-encoder rerank** (top `rerank_candidates` → `default_top_k`)
  → **retrieval confidence** (sigmoid of top rerank score; cosine-clamp in dense mode). BM25 index
  (`rank_bm25`, pickled to `paths.bm25_dir`) is rebuilt from ChromaDB after every ingest (source of
  truth = the chunk collection). Mode is config-driven (`retrieval.mode: hybrid`) with per-request
  override `AskRequest.mode` (`hybrid|dense`); `AskResponse` now returns `retrieval_mode` +
  `retrieval_confidence`. **3 chunking strategies** behind `chunking.strategy`
  (`recursive` | `fixed` | `semantic`); each chunk tagged with `strategy` in metadata (for the
  Phase 4 benchmark). Semantic chunker embeds sentences and cuts when cosine sim drops below
  `semantic_threshold`. Live dense-vs-hybrid demo on `sample_docs`: hybrid gives sharper ranking +
  confidence 0.999 vs dense 0.773 on a keyword query.
- **Phase 3 COMPLETE & validated (22 tests green — 11 fast + 11 slow, lint clean).** Quality layer:
  `app/modules/quality/{extractor,verifier,confidence,service}.py`. Flow (in `pipeline.ask`) =
  generate answer → **extract** inline `[n]` → **verify** each via batched LLM judge
  (`models.judge` = gpt-4o-mini) → per-citation verdict `supported|partial|unsupported` →
  **composite confidence** = weighted blend of retrieval conf + citation accuracy + model
  self-confidence (`quality.confidence_weights`, normalised) → **IDK gate**: below
  `quality.idk_threshold` (0.45) return a graceful "I don't know" that still lists the closest
  matches + a suggestion. `GeneratedAnswer` gained `self_confidence`; `AskResponse` gained
  `confidence` + `confidence_breakdown`; `Citation` gained `verdict` + `verdict_reason`.
  `verify_citations: false` skips the judge to save cost. Live-validated: in-corpus →
  confidence 0.999 + verdict=supported; out-of-corpus → IDK at 0.18 (model self-rated 0.9 but
  retrieval/citation 0.0 caught it — the reason to blend signals).
- **Phase 4 COMPLETE & validated (17 tests green — 14 fast + 3 slow, lint clean).** Evaluation
  harness (the regression gate): `app/modules/eval/{schemas,golden,metrics,runner,report}.py` +
  `scripts/run_eval.py`. **Golden set** = `eval/golden_set.jsonl` (git-tracked), **20 human-authored
  cases** over the REAL 154-doc FastAPI corpus (12 simple, 4 multi_hop, 2 ambiguous, 2 no_answer).
  Corpus fetched via `scripts/fetch_corpus.py --docs-only` → 154 docs → 2112 chunks (recursive).
  **Metrics** per case: deterministic `retrieval_recall` (expected_sources ⊆ retrieved) +
  `citation_accuracy` (Phase 3 verdicts) + `idk_accuracy` (no_answer → correctly refused); judge
  (`models.judge`=gpt-4o-mini, graded vs the HUMAN reference, non-circular) `correctness` +
  `faithfulness` + `completeness`. Runner persists to SQLite `eval_runs`/`eval_case_results`; report
  prints a table + **regression deltas vs the previous run** (`eval.regression_tolerance`), plus a
  3-chunker `render_benchmark` comparison. CLI: `run_eval.py` (single), `--benchmark` (all 3
  chunkers), `--strategy`, `--limit`. Config: `eval.{golden_path,retrieval_k,regression_tolerance,
  strategies}`. **Live result** (recursive, gpt-4o-mini answers, 20 cases): overall **0.918**,
  retrieval_recall 0.925, correctness 0.950, faithfulness 0.975, completeness 0.940,
  citation_accuracy 0.698, **idk_accuracy 1.000**. Regression gate proven: it flagged the
  gpt-4o→gpt-4o-mini answer-model downgrade (0.969→0.918). NOTE: `models.generation` was switched to
  **gpt-4o-mini** to cut eval cost (comment in yaml to bump back to gpt-4o). The 3-chunker benchmark
  command works but wasn't run on the final set (cost). Golden set is designed to grow toward 50-100+.
- **Phase 5 COMPLETE & validated (19 tests green — 17 fast + 2 slow, lint clean).** Semantic cache:
  `app/clients/cache.py` (Redis Stack / RediSearch) + `app/modules/cache/service.py`. `pipeline.ask`
  now: embed query once → **cache lookup** (RediSearch KNN-1, COSINE HNSW, pre-filtered by
  params-hash + corpus-version) → HIT if sim ≥ `cache.threshold` (**0.90**) returns stored
  `AskResponse` (`cached=true`, no LLM) → MISS runs full pipeline then **stores** {embedding,
  params_hash, corpus_version, response, TTL}. **Invalidation** = `corpus_version` = MAX(audit_id)
  from `ingestion_audit`, so every ingest bumps it and stale entries are never served (zero coupling
  to Redis). Near-miss band ([0.80,0.90)) logged not served. `AskResponse.{cached,cache_similarity}`;
  `GET /v1/cache/stats` + `POST /v1/cache/flush`; `scripts/cache_loadtest.py`. **Graceful-degrade**:
  cache off or Redis down → pipeline runs normally (bounded socket timeouts, never hangs /ask).
  Infra: `docker-compose.yml` runs `redis/redis-stack` mapped to **host 6380** (6379 was taken by
  another project). Live demo: cold 26s → exact rerun HIT sim=1.0 190ms → paraphrase HIT sim=0.936
  195ms → post-reingest MISS (invalidation). NOTE threshold 0.90 chosen from measured bge-base sims
  (paraphrase ~0.89-0.94, unrelated ~0.47); hit latency ~190ms (query still embedded on CPU), not the
  plan's <50ms, but ~130x faster than cold.
- **Phase 6 COMPLETE & validated (19 fast tests green, lint clean).** Auto-eval loop:
  `app/modules/autoeval/{schemas,capture,generator,service}.py` + `app/routers/feedback.py`.
  `pipeline.ask` (cache miss) → **capture** (cheap DB insert) flags weak answers into SQLite
  `eval_candidates`: triggers = composite conf < `autoeval.flag_confidence_threshold` (0.6), IDK, or
  thumbs-down via `POST /v1/feedback`. Separate **process** step (`POST /v1/eval/candidates/process`,
  gpt-4o-mini) **double-run drafts** a reference (answer+type; sources taken from the real retrieved
  chunks, not model-written) → runs agree (answer cosine ≥ `agreement_threshold` 0.85 + same type) =
  `auto_approved`, disagree = `needs_review`, near-dup of a golden question (≥ `dedup_threshold` 0.92)
  = `rejected_duplicate`. **Review**: `GET /v1/eval/candidates`, `.../{id}/approve` (appends a
  `GoldenCase` to `eval/candidates.jsonl` — SEPARATE from the hand-authored golden set to protect the
  spine), `.../{id}/reject`. Human gate always; drafts never auto-join the golden set. Live demo:
  out-of-corpus query → IDK (conf 0.0006) → captured → drafted `no_answer`/auto_approved → approved to
  candidates.jsonl. Config: `autoeval.{enabled,flag_confidence_threshold,capture_idk,dedup_threshold,
  agreement_threshold,candidates_path}`.
- **Ingestion-v2 track (multi-format + metadata enrichment + filtered retrieval)** — plan:
  `C:\Users\hareesh\.claude\plans\ok-now-here-this-peaceful-quail.md`. Six phases (M1–M6) that turn
  the markdown-only loader into a production ingestion layer: block-based IR, per-chunk metadata
  enrichment threaded to citations, formats (PDF/DOCX/TXT/MD/HTML/CSV/JSON/XML/**image OCR**), and
  retrieval-time metadata filtering. **NOTE: this reverses the old "No OCR" guardrail** — OCR is now
  in-scope for image files + scanned PDF pages only (text PDFs keep native extraction); the guardrail
  is formally updated in phase M4.
  - **M1 DONE & validated (committed + pushed; ruff clean, fast tests green).** Block-based IR:
    `loader.Block` + `Document` gains `file_type/blocks/metadata`; markdown loader emits heading-section
    blocks (`split_into_sections` moved loader-side). `Chunk` + all 3 chunkers now attribute every chunk
    to one source block and inherit its metadata (`file_type,title,page_number,locator,content_type,
    char_count,created_at`) — fixed windows are mapped back to their block via a token→block index so
    page/section survive *every* strategy. `index_chunks` writes flat-scalar Chroma metadata (omits
    None). `RetrievedChunk` + `chunk_from_meta` helper carry the new fields through dense/sparse/hybrid
    (hybrid uses `dataclasses.replace`). `prompt.build_context` renders `From "x" (p.N, Section: …)`;
    `Citation` gains `file_type/page/locator`, filled in `pipeline._to_citations`. `extractor.py`
    intentionally unchanged (metadata reaches citations via `RetrievedChunk`, not the extractor). New
    fast tests in `test_hybrid_retrieval.py` (block-metadata on recursive/fixed) + `test_quality.py`
    (context shows page/section).
  - **M2 DONE & validated (ruff clean, 24 fast tests pass).** Multi-format loader dispatch:
    new `app/modules/ingestion/loaders/` package — `base.py` (moved `Block`/`Document`, a
    suffix→`(format,loader)` `REGISTRY` + `@register` decorator, shared helpers
    `blocks_from_sections`/`read_text`/`iso_mtime`/`filename_title`), `markdown.py` (moved; identical
    behaviour), `text.py` (single block), `html.py` (BeautifulSoup+lxml: strips
    script/style/nav/header/footer/aside/form, walks h1..h6 into the same heading-breadcrumb sections
    as markdown). `loader.py` is now a thin facade: re-exports `Block`/`Document`/`MARKDOWN_SUFFIXES`
    (back-compat) and holds `load_documents(dir, enabled=None)` + `allowed_suffixes()`, both honoring
    the config allowlist. Config: `ingestion.formats.enabled` (`FormatsConfig`; M2 = `[markdown,txt,
    html]`, grows per phase). Router `/v1/ingest/upload` now gates on `allowed_suffixes()` (message
    lists accepted extensions). Adding a format = drop a module in `loaders/` + `@register` — no
    dispatcher change. Tests: `tests/test_loaders.py` (fast, no models/chroma) + fixtures under
    `tests/fixtures/multiformat/`. **No new deps** (bs4/lxml already installed).
  - **M3 DONE & validated (ruff clean, 28 fast tests pass — +4 for pdf/docx).** PDF + DOCX loaders:
    `loaders/pdf.py` (PyMuPDF/`fitz`: **one Block per page** with 1-based `page`, native text
    extraction; doc metadata `page_count`+`has_scanned_pages`) and `loaders/docx.py` (python-docx:
    heading styles → `section_path` breadcrumb Blocks like markdown/html; tables → pipe-joined
    `content_type="table"` Blocks; `.doc` legacy binary NOT supported). **Scanned-page detection:** a
    PDF page with < `formats.pdf.scanned_text_density_threshold` (100) chars of extractable text is
    flagged `content_type="scanned"` with empty text (dropped by the chunker's `min_chunk_chars`
    gate) and `has_scanned_pages=True` — **actual OCR is deferred to M4**; M3 never crashes on scanned
    input. Config: `formats.enabled` += `pdf,docx`; new `PdfFormatConfig.scanned_text_density_threshold`.
    Deps added: `pymupdf 1.28.0` + `python-docx 1.2.0`. Loaders register via `@register`; no
    dispatcher change (block IR from M1 already threads page/section → citations). Binary fixtures
    (`sample.pdf`, `scanned.pdf`, `sample.docx`) generated with the libs, committed under
    `tests/fixtures/multiformat/`; fast tests in `tests/test_loaders.py`.
  - **M4 DONE & validated (ruff clean, 33 fast tests pass — +5 for OCR; real-OCR slow test green).**
    OCR for images + scanned PDF pages. New `app/modules/ingestion/ocr.py` — engine-agnostic choke
    point (`ocr_image_bytes(bytes) -> str`; `@lru_cache` reader, lazy heavy import): engine
    config-selectable (`easyocr` default, reuses installed torch, no system binary | `tesseract`,
    needs system Tesseract.exe + optional `pytesseract`). **Graceful degrade**: OCR disabled /
    engine missing / model-download fail / unreadable image → logged warning + `""`, ingest never
    crashes. New `loaders/image.py` (`@register "image"`, suffixes `.png/.jpg/.jpeg/.tiff/.tif/.bmp/
    .webp/.gif`) → OCR → one `content_type="ocr"` Block, `metadata.ocr_used=True`; empty OCR → skip.
    `loaders/pdf.py` scanned branch now renders the page to PNG (`page.get_pixmap(dpi=ocr.dpi)`) →
    OCR → `content_type="ocr"` Block + `metadata.ocr_used=True`; OCR off/empty → unchanged M3
    behavior (empty `scanned` block, dropped by chunker). Config: `formats.enabled` += `image`; new
    `OcrConfig{enabled,engine,languages,dpi}`. Deps: `pillow 12.3.0` + `easyocr 1.7.2` (pulls
    opencv-headless/scikit-image/torchvision; ~90MB EasyOCR models download on first real OCR).
    Fixture `sample_image.png` (Pillow-rendered text). **Tests**: fast wiring via monkeypatched OCR
    (image block, empty-skip, scanned fill-in, degrade-to-M3, disabled short-circuit) + a `slow`
    real-EasyOCR test (`importorskip`). NOTE: fast tests MUST fake OCR — the M3 dispatch/scanned
    tests were updated to patch `ocr.ocr_image_bytes` so the directory sweep over `scanned.pdf`
    never loads the real engine.
  - **M5 DONE & validated (ruff clean, 39 fast tests pass — +6 for csv/json/xml).** Structured
    formats + a `structured` chunker. New `loaders/{csv,json,xml}.py`: **CSV** (stdlib) groups
    `formats.csv.rows_per_chunk` (20) data rows per Block, prepends the header (`Columns: …`) so each
    chunk is self-describing, `content_type="row"`, `locator="rows a-b"`; **JSON** (stdlib) → one
    Block per top-level element (array `$[i]` / object `$.key`; all-scalar object stays whole),
    `content_type="object"`; **XML** (installed `lxml`) → one Block per direct child of root,
    `locator="/root/child[i]"` (1-based per tag, attributes summarized), `content_type="element"`.
    Malformed JSON/XML → skipped with a logged warning (never crashes). **Chunker**: `chunk_document`
    now dispatches on `doc.file_type` — csv/json/xml use `_chunk_structured` (one record→one chunk,
    `strategy="structured"`, `split_by_tokens` safety cap for oversized records), **bypassing**
    recursive/fixed/semantic regardless of `chunking.strategy`. **Prompt**: `_locator` now also
    renders the structured `locator` (e.g. `From "products.csv" (rows 21-40)`), so structured
    provenance shows in both the generation context and `Citation` (locator already threaded via M1).
    Config: `formats.enabled` += `csv,json,xml`; new `CsvFormatConfig.rows_per_chunk`. **No new deps**
    (stdlib + existing lxml). Fixtures `tests/fixtures/multiformat/sample.{csv,json,xml}`; fast tests
    in `test_loaders.py` (row/object/element locators, header prepend, rows_per_chunk split,
    structured passthrough, dispatch). NOTE: for csv/json/xml the `chunking.strategy` setting is
    intentionally ignored — file_type wins.
  - **M6 DONE & validated (ruff clean, 48 fast tests pass — +9 for filtering/cache).** Metadata-
    filtered retrieval — **final phase; ingestion-v2 track COMPLETE.** New `AskRequest.filters`
    (`RetrievalFilters`, `extra="forbid"` so typos 400): equality on `file_type` / `source` /
    `content_type`. New `app/modules/retrieval/filters.py`: `build_where` (None→no filter; 1 key→flat;
    N keys→`$and`, Chroma's required combinator) + `metadata_matches` (Python equality for sparse).
    Threaded as `filters: dict|None` (default None, so every existing call site is unchanged) through
    `dense_retrieve` (Chroma `where=`), `BM25Index.search`/`sparse_retrieve` (post-filter then top_k),
    `hybrid_retrieve` (both retrievers filtered at source → fused pool/rerank only see matches),
    `retrieve`, `pipeline._answer`/`ask`, `routers/ask.py`. **Cache correctness fix**: `params_hash`
    now folds in a canonical (order-independent) filters key, and `lookup`/`store` take `filters` — so
    a filtered query can never be served an unfiltered (or differently-filtered) cached answer. Empty
    filtered result → existing graceful IDK. **Design note**: equality only — Chroma metadata `where`
    has no substring op, so `section`-substring filtering is intentionally out of scope (documented,
    not half-built). No new deps/infra. Tests `tests/test_retrieval_filters.py` (where-shapes,
    match, BM25 post-filter+top_k, filtered≠unfiltered≠different-filter cache hashes, order-stable
    hash, extra-key rejection).
- **ENVIRONMENT NOTE (2026-07-24):** post-reinstall the venv/uv were rebuilt by the user; `uv` lives at
  `C:\Users\hareesh\AppData\Local\Programs\Python\Python312\Scripts\uv.exe` (not on PATH). The earlier
  ChromaDB native-DLL load failure (missing MSVC runtime) is **resolved** — the full fast suite incl.
  `test_ready_endpoint` is green.
- **Phase 7 (deferred, original plan)** — API surface polish + Streamlit dashboard (query UI,
  citations, confidence, hybrid-vs-dense toggle, cache panel, eval + review-queue views).

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
- 2026-07-13: **Phase 2 COMPLETE.** Hybrid retrieval engine: new
  `app/modules/retrieval/{sparse,fusion,confidence,hybrid,retriever}.py` (BM25 + RRF + cross-encoder
  rerank + confidence); `retriever.retrieve(query,k,mode)` dispatches dense|hybrid. BM25 rebuilt from
  ChromaDB after each ingest (`service.py`), serialized to `paths.bm25_dir`. Chunker refactored into a
  3-strategy dispatcher (recursive/fixed/semantic) with a `strategy` metadata tag; `index_chunks` now
  writes it. Config: `retrieval.{mode,dense_candidates,sparse_candidates,rrf_k,dense_weight,
  sparse_weight,rerank_candidates}` + `chunking.semantic_threshold`. Schemas: `AskRequest.mode`,
  `AskResponse.{retrieval_mode,retrieval_confidence}`; pipeline + ask router pass mode through. Tests:
  `tests/test_hybrid_retrieval.py` (fast RRF units + slow sparse/hybrid/dispatch/chunking) → 15/15
  green, ruff clean. Live dense-vs-hybrid demo verified. NOTE: this work was rebuilt after an
  accidental IDE "discard all changes" wiped the uncommitted Phase 2 tree. Next = Phase 3.
- 2026-07-14: **Phase 3 COMPLETE.** Quality layer: new `app/modules/quality/{extractor,verifier,
  confidence,service}.py`. `pipeline.ask` now: generate → extract `[n]` → batched judge verify
  (per-citation `supported|partial|unsupported`) → composite confidence (retrieval + citation
  accuracy + self-confidence, config weights) → IDK gate below `quality.idk_threshold`. Added
  `get_judge_client()` (llm.py, reuses instructor client w/ judge model). Config: `quality.{verify_
  citations,idk_threshold,confidence_weights}`. Schemas: `GeneratedAnswer.self_confidence`,
  `AskResponse.{confidence,confidence_breakdown}`, `Citation.{verdict,verdict_reason}`; generation
  prompt got a self_confidence rule. Tests: `tests/test_quality.py` (fast extraction+confidence math;
  slow judge/IDK gated on `.env` key) → 22 total green, ruff clean. Live in-corpus (0.999/supported)
  + out-of-corpus (IDK @ 0.18) verified. User commits. Next = Phase 4.
- 2026-07-15: **Phase 4 COMPLETE.** Evaluation harness: new `app/modules/eval/{schemas,golden,metrics,
  runner,report}.py` + `scripts/run_eval.py`; SQLite `eval_runs`/`eval_case_results` (db.py). Fetched
  the REAL corpus (`fetch_corpus.py --docs-only` → 154 docs/2112 chunks). Authored a human golden set
  `eval/golden_set.jsonl` (git-tracked) — started at 100 cases, **trimmed to 20 on user request to cut
  API cost** (12 simple/4 multi_hop/2 ambiguous/2 no_answer). Metrics = deterministic (retrieval_recall,
  citation_accuracy, idk_accuracy) + judge (correctness/faithfulness/completeness vs the HUMAN
  reference, gpt-4o-mini). Report = table + regression deltas vs previous run + 3-chunker benchmark
  table. Switched `models.generation` gpt-4o→**gpt-4o-mini** to cut cost. Live single run (recursive):
  overall 0.918, idk_accuracy 1.000; regression gate correctly flagged the gpt-4o→mini downgrade.
  Tests: `tests/test_eval.py` (fast golden/metrics/no_answer scoring; slow end-to-end) → 14 fast green,
  lint clean. Full 3-chunker benchmark command works but not run on final set (cost). User commits.
  Next = Phase 5.
- 2026-07-16: **Phase 5 COMPLETE.** Semantic cache (Redis Stack / RediSearch): new `app/clients/
  cache.py`, `app/modules/cache/{__init__,service}.py`, `app/routers/cache.py`, `docker-compose.yml`,
  `scripts/cache_loadtest.py`, `tests/test_cache.py`. `pipeline.ask` embeds once → RediSearch KNN
  lookup (COSINE HNSW, filtered by params-hash + corpus-version) → HIT ≥ threshold 0.90 returns stored
  AskResponse (no LLM), MISS runs pipeline then stores with TTL. Invalidation via corpus_version =
  MAX(audit_id) (db.get_corpus_version) — every ingest bumps it, no Redis coupling. Added
  `AskResponse.{cached,cache_similarity}`, `CacheConfig`, `/v1/cache/{stats,flush}`. Graceful-degrade
  (bounded socket timeouts) so a down Redis never breaks /ask. GOTCHAS fixed: redis-py 8 module is
  `redis.commands.search.index_definition` (not `indexDefinition`); connect timeout 0.5s too tight for
  Docker-Windows (→3.0s); host 6379 taken by another project's redis → mapped redis-stack to **6380**.
  Live: cold 26s → exact HIT 190ms → paraphrase HIT sim=0.936 → post-reingest MISS (invalidation).
  19 tests green (17 fast + 2 slow), lint clean. User commits. Next = Phase 6.
- 2026-07-25: **Ingestion-v2 M6 COMPLETE — track finished.** Metadata-filtered retrieval.
  `AskRequest.filters` (`RetrievalFilters`, equality on file_type/source/content_type, unknown keys
  rejected). New `app/modules/retrieval/filters.py` (`build_where` → Chroma `where` incl. `$and`;
  `metadata_matches` → sparse Python filter). Filters threaded (default None) through
  dense/sparse/hybrid/`retrieve`/pipeline/`routers/ask.py`; hybrid filters both retrievers at source.
  **Cache fix**: `params_hash` + `lookup`/`store` now include a canonical filters key so filtered
  queries never hit unfiltered cached answers. Equality-only by design (Chroma has no metadata
  substring op → section-substring deferred). No new deps. Tests `tests/test_retrieval_filters.py`
  (9 fast). Ruff clean, 48 fast tests green. **Ingestion-v2 (M1–M6) is now 100% complete**: block IR
  → 9 formats (md/txt/html/pdf/docx/image-OCR/csv/json/xml) → per-chunk metadata → citations →
  filtered retrieval. Remaining project work = deferred original Phase 7 (Streamlit dashboard/API
  polish) + Phase 8 (service split + Postgres/pgvector). User commits.
- 2026-07-25: **Ingestion-v2 M5 COMPLETE.** Structured formats (CSV/JSON/XML) + a `structured`
  chunker. New `loaders/{csv,json,xml}.py`: CSV groups rows (header prepended, `locator="rows a-b"`,
  `content_type="row"`); JSON → one block per top-level element (`$[i]`/`$.key`, `content_type=
  "object"`); XML (lxml) → one block per root child (`/root/child[i]`, `content_type="element"`).
  Malformed JSON/XML skipped with a warning. `chunker.chunk_document` dispatches on `doc.file_type`:
  csv/json/xml → new `_chunk_structured` (one record→one chunk, `strategy="structured"`, token-cap
  safety split), bypassing the text strategies. `prompt._locator` now renders the structured
  `locator` too (shows in context + citations). Added `CsvFormatConfig` + enabled csv/json/xml in
  `config.py`/`system.yaml`. No new deps (stdlib + existing lxml). Fixtures `sample.{csv,json,xml}`
  + tests in `test_loaders.py`. Ruff clean, 39 fast tests green. Next = M6 (metadata-filtered
  retrieval). User commits.
- 2026-07-25: **Ingestion-v2 M4 COMPLETE.** OCR for images + scanned PDF pages. **Reverses the
  "No OCR" architecture guardrail** (formally updated above). New `app/modules/ingestion/ocr.py`
  (engine-agnostic `ocr_image_bytes`, lazy `@lru_cache` reader, `easyocr` default | `tesseract`,
  graceful degrade → `""` on any failure). New `loaders/image.py` (OCR image files →
  `content_type="ocr"` block). `loaders/pdf.py` scanned pages now rendered → OCR'd (`ocr_used`
  metadata); OCR off/empty falls back to M3 behavior. Added `OcrConfig` + `image` to
  `config.py`/`system.yaml`. Deps: `pillow 12.3.0`, `easyocr 1.7.2` (+opencv-headless/scikit-image/
  torchvision; ~90MB models on first run) via `uv add`. Fixture `sample_image.png`; tests in
  `test_loaders.py` (fast monkeypatched wiring + `slow` real-OCR). Updated M3 pdf tests to fake OCR
  so the fast suite never loads the engine. Ruff clean, 33 fast tests green + slow real-OCR passed.
  Next = M5 (CSV/JSON/XML). User commits.
- 2026-07-24: **Ingestion-v2 M3 COMPLETE.** PDF + DOCX loaders. New `app/modules/ingestion/loaders/
  {pdf,docx}.py`: PDF (PyMuPDF) emits one Block per page (1-based `page`, native text extraction,
  doc metadata `page_count`/`has_scanned_pages`) with scanned-page detection (text density <
  `formats.pdf.scanned_text_density_threshold`=100 → `content_type="scanned"`, empty text, flagged
  for M4 OCR); DOCX (python-docx) maps heading styles → `section_path` Blocks + tables →
  `content_type="table"` Blocks. Registered in `loaders/__init__.py`; added `PdfFormatConfig` +
  enabled `pdf,docx` in `config.py`/`system.yaml`. Deps: `pymupdf 1.28.0`, `python-docx 1.2.0` (via
  `uv add`). Fixtures `tests/fixtures/multiformat/{sample.pdf,scanned.pdf,sample.docx}` +
  `tests/test_loaders.py` cases (per-page blocks, scanned flagging, heading/table, dispatch). Ruff
  clean, 28 fast tests green. Block IR from M1 threads page/section straight to citations — no
  chunker/retrieval/prompt changes needed. Next = M4 (OCR). User commits.
- 2026-07-17: **Phase 6 COMPLETE.** Auto-eval loop: new `app/modules/autoeval/{schemas,capture,
  generator,service}.py`, `app/routers/feedback.py`, SQLite `eval_candidates`+`feedback` tables +
  db helpers. `pipeline.ask` calls `capture()` (cheap insert) on cache miss → flags conf<0.6 / IDK;
  `POST /v1/feedback` thumbs-down also enqueues. `POST /v1/eval/candidates/process` double-run drafts
  (gpt-4o-mini) → auto_approved/needs_review/rejected_duplicate; approve appends to
  `eval/candidates.jsonl` (separate from golden_set.jsonl, human-gated). Endpoints:
  feedback + candidates list/process/approve/reject. Config `autoeval.*`. Tests
  `tests/test_autoeval.py` (fast flag/enqueue; slow process/approve) → 19 fast green, lint clean.
  Live demo: IDK query auto-captured → drafted no_answer → approved. User commits. Next = Phase 7.
