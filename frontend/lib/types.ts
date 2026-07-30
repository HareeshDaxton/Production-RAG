/** Mirrors `app/models/schemas.py`. Keep in sync with the backend. */

export type Verdict = "supported" | "partial" | "unsupported";
export type RetrievalMode = "hybrid" | "dense";

export interface Citation {
  number: number;
  source: string;
  section: string | null;
  text: string;
  file_type: string | null;
  page: number | null;
  locator: string | null;
  verdict: Verdict | null;
  verdict_reason: string | null;
}

/** Mirrors `RetrievalFilters` — `source` takes one filename or several (matches any). */
export interface RetrievalFilters {
  file_type?: string;
  source?: string | string[];
  content_type?: string;
}

export interface AskRequest {
  query: string;
  top_k?: number;
  mode?: RetrievalMode;
  filters?: RetrievalFilters;
}

export interface AskResponse {
  query: string;
  answer: string;
  citations: Citation[];
  chunks_retrieved: number;
  has_sufficient_context: boolean;
  retrieval_mode: string;
  retrieval_confidence: number;
  confidence: number;
  confidence_breakdown: Record<string, number>;
  cached: boolean;
  cache_similarity: number | null;
}

export interface IngestResponse {
  documents_ingested: number;
  chunks_created: number;
  source_dir: string;
}

/** GET /v1/documents — what is currently searchable. */
export interface IndexedDocument {
  source: string;
  title: string;
  file_type: string;
  chunks: number;
  pages: number | null;
}

export interface DocumentsResponse {
  documents: IndexedDocument[];
  total_chunks: number;
}

/** POST /v1/title — ChatGPT-style conversation naming. */
export interface TitleResponse {
  title: string;
  /** False when the backend fell back to a trim of the question. */
  generated: boolean;
}

/** GET /v1/system — model wiring for the sidebar panel. */
export interface SystemInfo {
  generation_model: string;
  embedding_model: string;
  retrieval_mode: string;
  documents: number;
  chunks: number;
}

/** SSE frames emitted by POST /v1/ask/stream (see `pipeline.ask_stream`). */
export type StreamEvent =
  | { type: "meta"; retrieval_mode: string; chunks_retrieved: number }
  | { type: "delta"; text: string }
  | { type: "final"; streamed: boolean; replaced: boolean; response: AskResponse }
  | { type: "error"; message: string };

// --- client-side view models -------------------------------------------------

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  /** Streamed text while in flight; replaced by the verified answer on `final`. */
  content: string;
  createdAt: number;
  response?: AskResponse;
  error?: string;
  /** True while tokens are still arriving — drives the caret. */
  streaming?: boolean;
  /** The quality gate replaced the streamed text with a refusal. */
  replaced?: boolean;
  /** The question that produced this answer, so Regenerate can replay it. */
  prompt?: string;
  feedback?: "up" | "down";
  /** Files attached to this question — rendered above the bubble, like ChatGPT. */
  attachments?: string[];
}

export interface Conversation {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: ChatMessage[];
  /**
   * Sources (`IndexedDocument.source`) attached in this chat. The index is shared,
   * but a chat that has attachments answers **from those files only** (sent as
   * `filters.source`), so a new chat starts clean instead of inheriting the last upload.
   */
  attachments: string[];
}
