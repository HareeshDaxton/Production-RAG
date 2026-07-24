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
from pydantic import BaseModel
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
    provider: str = "local"
    name: str = "BAAI/bge-small-en-v1.5"
    dimensions: int = 384
    device: str = "cpu"
    # bge retrieval models benefit from a query-side instruction prefix.
    query_prefix: str = "Represent this sentence for searching relevant passages: "
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


class ModelsConfig(BaseModel):
    embedding: EmbeddingConfig = EmbeddingConfig()
    reranker: RerankerConfig = RerankerConfig()
    generation: GenerationConfig = GenerationConfig()
    judge: JudgeConfig = JudgeConfig()


class RetrievalConfig(BaseModel):
    default_top_k: int = 5  # final chunks returned to generation
    mode: str = "hybrid"  # "hybrid" (dense+BM25+RRF+rerank) or "dense" (Phase 1 path)
    dense_candidates: int = 20  # pool pulled from the dense index before fusion
    sparse_candidates: int = 20  # pool pulled from BM25 before fusion
    rrf_k: int = 60  # RRF damping constant (standard default)
    dense_weight: float = 1.0  # RRF weight for the dense ranking
    sparse_weight: float = 1.0  # RRF weight for the BM25 ranking
    rerank_candidates: int = 20  # fused candidates fed to the cross-encoder reranker


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


class CorpusConfig(BaseModel):
    dir: Path = Path("data/corpus")  # default ingest source (populated by fetch script)


class FormatsConfig(BaseModel):
    # Formats accepted on ingest/upload. Grows one entry per phase as loaders land
    # (M2: markdown/txt/html; M3: +pdf/docx; M4: +image; M5: +csv/json/xml).
    enabled: list[str] = ["markdown", "txt", "html"]


class IngestionConfig(BaseModel):
    corpus: CorpusConfig = CorpusConfig()
    chunking: ChunkingConfig = ChunkingConfig()
    formats: FormatsConfig = FormatsConfig()


class AppConfig(BaseModel):
    app: AppMeta = AppMeta()
    paths: Paths = Paths()
    models: ModelsConfig = ModelsConfig()
    retrieval: RetrievalConfig = RetrievalConfig()
    ingestion: IngestionConfig = IngestionConfig()
    quality: QualityConfig = QualityConfig()
    eval: EvalConfig = EvalConfig()
    cache: CacheConfig = CacheConfig()
    autoeval: AutoEvalConfig = AutoEvalConfig()


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
