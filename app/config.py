"""Typed, config-driven settings.

Two sources of truth:
- Secrets / env-specific values from environment or `.env`  -> `Settings`
- Non-secret application config from `config/system.yaml`    -> `AppConfig`

Everything the app needs is reachable via cached `get_config()` / `get_settings()`.
No magic numbers in code — thresholds, model names and paths live in system.yaml.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "system.yaml"


class Settings(BaseSettings):
    """Secrets and environment-specific values (never committed)."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    openai_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    config_path: Path = DEFAULT_CONFIG_PATH
    # Overrides stores.postgres.dsn — the yaml default is local dev credentials, and
    # a real deployment's connection string belongs in the environment, not in git.
    postgres_dsn: str | None = None


# --- config/system.yaml schema (typed) --------------------------------------


class AppMeta(BaseModel):
    name: str = "production-rag"
    environment: str = "development"
    log_level: str = "INFO"


class Paths(BaseModel):
    data_dir: Path = Path("data")
    chroma_dir: Path = Path("data/chroma")
    sqlite_path: Path = Path("data/audit/app.sqlite")
    bm25_dir: Path = Path("data/bm25_index")

    def ensure(self) -> None:
        """Create runtime directories if missing (idempotent)."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.chroma_dir.mkdir(parents=True, exist_ok=True)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.bm25_dir.mkdir(parents=True, exist_ok=True)


class EmbeddingConfig(BaseModel):
    provider: str = "openai"  # "openai" (API, no CPU) or "local" (sentence-transformers)
    name: str = "text-embedding-3-small"
    dimensions: int = 1536  # must match the model and the vectors already in the store
    device: str = "cpu"  # local provider only
    # bge retrieval models want a query-side instruction prefix; OpenAI models do not.
    query_prefix: str = ""
    batch_size: int = 64
    normalize: bool = True


class RerankerConfig(BaseModel):
    provider: str = "local"
    name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    device: str = "cpu"


class GenerationConfig(BaseModel):
    provider: str = "openai"
    name: str = "gpt-4o"
    temperature: float = 0.1
    max_tokens: int = 1000
    timeout: int = 30


class JudgeConfig(BaseModel):
    provider: str = "openai"  # "openai" or "ollama" (configurable, used from Phase 3)
    name: str = "gpt-4o-mini"
    temperature: float = 0.0


class TitleConfig(BaseModel):
    """Cheap model that names a conversation from its first question (ChatGPT-style)."""

    enabled: bool = True  # False = fall back to a trimmed question, no LLM call
    provider: str = "openai"
    name: str = "gpt-4o-mini"
    temperature: float = 0.3  # a little latitude produces better phrasing than 0.0
    max_words: int = 5
    max_tokens: int = 48  # a title is a handful of tokens; cap the cost hard
    max_chars: int = 60  # hard truncation guard for the sidebar/header


class ModelsConfig(BaseModel):
    embedding: EmbeddingConfig = EmbeddingConfig()
    reranker: RerankerConfig = RerankerConfig()
    generation: GenerationConfig = GenerationConfig()
    judge: JudgeConfig = JudgeConfig()
    title: TitleConfig = TitleConfig()


class RetrievalConfig(BaseModel):
    default_top_k: int = 5  # final chunks returned to generation
    mode: str = "hybrid"  # "hybrid" (dense+BM25+RRF+rerank) or "dense" (Phase 1 path)
    dense_candidates: int = 20  # pool pulled from the dense index before fusion
    sparse_candidates: int = 20  # pool pulled from BM25 before fusion
    rrf_k: int = 60  # RRF damping constant (standard default)
    dense_weight: float = 1.0  # RRF weight for the dense ranking
    sparse_weight: float = 1.0  # RRF weight for the BM25 ranking
    rerank_candidates: int = 20  # fused candidates fed to the cross-encoder reranker
    # Structured records (CSV/JSON/XML) are out of distribution for the cross-encoder,
    # which scores them ~0 and makes the quality gate refuse them. Confidence for those
    # comes from the dense cosine instead; ranking still uses the reranker.
    structured_confidence_from_dense: bool = True
    # Retrieval confidence when a query named a record id and that record was found
    # by exact metadata match — stronger evidence than a similarity score.
    identifier_match_confidence: float = 0.95


class ChunkingConfig(BaseModel):
    strategy: str = "recursive"  # "recursive" | "fixed" | "semantic"
    max_chunk_tokens: int = 512
    overlap_tokens: int = 64
    min_chunk_chars: int = 40  # drop trivially small fragments
    semantic_threshold: float = 0.6  # cosine sim below which the semantic chunker cuts


class ConfidenceWeights(BaseModel):
    retrieval: float = 0.4  # weight of Phase 2 retrieval confidence
    citation: float = 0.4  # weight of the fraction of citations the judge supports
    self: float = 0.2  # weight of the model's own self-reported confidence


class QualityConfig(BaseModel):
    verify_citations: bool = True  # run the LLM judge (False = skip to save cost)
    idk_threshold: float = 0.45  # composite confidence below this → graceful "I don't know"
    confidence_weights: ConfidenceWeights = ConfidenceWeights()


class EvalConfig(BaseModel):
    golden_path: Path = Path("eval/golden_set.jsonl")  # human-authored answer key (tracked)
    retrieval_k: int = 5  # top_k used when answering eval questions
    regression_tolerance: float = 0.03  # overall-score drop beyond this = regression
    strategies: list[str] = ["recursive", "fixed", "semantic"]  # chunkers to benchmark


class AutoEvalConfig(BaseModel):
    enabled: bool = True  # capture flagged queries as eval candidates
    flag_confidence_threshold: float = 0.6  # composite conf below this → candidate
    capture_idk: bool = True  # also capture graceful-IDK answers
    dedup_threshold: float = 0.92  # question sim >= this to a golden case → duplicate
    agreement_threshold: float = 0.85  # double-run answer sim >= this → runs agree
    candidates_path: Path = Path("eval/candidates.jsonl")  # approved drafts land here


class CacheConfig(BaseModel):
    enabled: bool = True  # off, or Redis unreachable → pipeline runs normally (no cache)
    redis_url: str = "redis://localhost:6379"
    threshold: float = 0.90  # cosine sim >= this → cache HIT (conservative; paraphrases ~0.90-0.94)
    near_miss_margin: float = 0.10  # sim in [threshold-margin, threshold) → logged, NOT served
    ttl_seconds: int = 86400  # entry lifetime (1 day)
    index_name: str = "rag_cache_idx"
    key_prefix: str = "cache:"
    cost_per_answer_usd: float = 0.002  # estimate used for the cost-saved stat


class PostgresConfig(BaseModel):
    """Connection settings for the Phase 9 Postgres/pgvector backends."""

    dsn: str = "postgresql://rag:rag@localhost:5433/rag"  # override via POSTGRES_DSN
    chunks_table: str = "chunks"
    # HNSW build parameters; the defaults suit corpora up to ~1M vectors.
    hnsw_m: int = 16
    hnsw_ef_construction: int = 64
    min_pool_size: int = 1
    max_pool_size: int = 5


class StoresConfig(BaseModel):
    """Where vectors and operational rows live (Phase 9).

    Both are pluggable so the project still runs with no Docker: `chroma` + `sqlite`
    is the laptop/test path, `pgvector` + `postgres` the production one. The
    application code talks to an interface and never to a specific engine.
    """

    vector: str = "chroma"  # chroma | pgvector
    relational: str = "sqlite"  # sqlite | postgres
    postgres: PostgresConfig = PostgresConfig()


class CorsConfig(BaseModel):
    """Browser access for the Phase 8 frontend (dev server on :3000)."""

    enabled: bool = True
    allow_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    allow_credentials: bool = True
    allow_methods: list[str] = ["*"]
    allow_headers: list[str] = ["*"]


class CorpusConfig(BaseModel):
    dir: Path = Path("data/corpus")  # default ingest source (populated by fetch script)


class PdfFormatConfig(BaseModel):
    # Chars of extractable text per page below this → treat the page as scanned.
    # M3 flags such pages; M4 OCRs them. Text-based PDFs use native extraction.
    scanned_text_density_threshold: int = 100


class OcrConfig(BaseModel):
    # OCR runs only for image files + scanned PDF pages. Off/unavailable → graceful skip.
    enabled: bool = True
    engine: str = "easyocr"  # easyocr (default, no system binary) | tesseract
    languages: list[str] = ["en"]
    dpi: int = 200  # render resolution for scanned PDF pages before OCR


class CsvFormatConfig(BaseModel):
    rows_per_chunk: int = 20  # data rows grouped into one block (header prepended)


class JsonFormatConfig(BaseModel):
    """Structure-aware JSON records.

    A 10k-line export is one document but hundreds of records; splitting only at the
    top level leaves a single enormous block that token-slicing then cuts mid-record.
    The loader descends until each record fits, so one record becomes one chunk.
    """

    max_record_tokens: int = 400  # a node bigger than this is split by key/element
    max_depth: int = 6  # guard against pathological nesting
    extract_fields: bool = True  # copy a record's scalar fields into chunk metadata
    max_fields: int = 16  # cap per record (Chroma stores flat scalars)
    max_field_chars: int = 120  # values longer than this are not worth filtering on
    # First matching key becomes `record_id`, which powers exact identifier lookup.
    id_keys: list[str] = ["id", "_id", "uid", "uuid", "code", "mrn", "number", "key"]


class FormatsConfig(BaseModel):
    # Formats accepted on ingest/upload. Grows one entry per phase as loaders land
    # (M2: markdown/txt/html; M3: +pdf/docx; M4: +image; M5: +csv/json/xml).
    enabled: list[str] = [
        "markdown", "txt", "html", "pdf", "docx", "image", "csv", "json", "xml"
    ]
    pdf: PdfFormatConfig = PdfFormatConfig()
    ocr: OcrConfig = OcrConfig()
    csv: CsvFormatConfig = CsvFormatConfig()
    # Aliased: the yaml key stays `json`, but `BaseModel.json` is taken, so the
    # attribute is named `json_format` to avoid shadowing it.
    json_format: JsonFormatConfig = Field(default_factory=JsonFormatConfig, alias="json")

    model_config = ConfigDict(populate_by_name=True)


class IngestionConfig(BaseModel):
    corpus: CorpusConfig = CorpusConfig()
    chunking: ChunkingConfig = ChunkingConfig()
    formats: FormatsConfig = FormatsConfig()


class AppConfig(BaseModel):
    app: AppMeta = AppMeta()
    cors: CorsConfig = CorsConfig()
    paths: Paths = Paths()
    models: ModelsConfig = ModelsConfig()
    retrieval: RetrievalConfig = RetrievalConfig()
    ingestion: IngestionConfig = IngestionConfig()
    quality: QualityConfig = QualityConfig()
    eval: EvalConfig = EvalConfig()
    cache: CacheConfig = CacheConfig()
    autoeval: AutoEvalConfig = AutoEvalConfig()
    stores: StoresConfig = StoresConfig()

    def postgres_dsn(self) -> str:
        """Effective DSN: the environment wins over the yaml dev default."""
        return get_settings().postgres_dsn or self.stores.postgres.dsn


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_config() -> AppConfig:
    """Load and validate config/system.yaml (falls back to defaults if absent)."""
    path = get_settings().config_path
    data: dict = {}
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return AppConfig(**data)
