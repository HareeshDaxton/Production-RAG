/** Typed client for the Production RAG FastAPI backend. */
import type {
  AskRequest,
  DocumentsResponse,
  IngestResponse,
  StreamEvent,
  SystemInfo,
} from "@/lib/types";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

export class ApiError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** FastAPI errors are `{detail: string}` or `{detail: [{loc, msg}]}` for 422. */
function describeDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((d) =>
        d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : null,
      )
      .filter(Boolean);
    if (parts.length) return parts.join("; ");
  }
  return fallback;
}

async function failure(res: Response): Promise<ApiError> {
  let detail: unknown;
  try {
    detail = (await res.json())?.detail;
  } catch {
    detail = undefined;
  }
  return new ApiError(
    describeDetail(detail, `Request failed (${res.status} ${res.statusText})`),
    res.status,
  );
}

const UNREACHABLE = `Cannot reach the API at ${API_BASE_URL}. Is the backend running?`;

/**
 * Stream an answer over SSE, invoking `onEvent` for every frame.
 *
 * Frames are delimited by a blank line, and a single network chunk may contain a
 * partial frame — so the tail is buffered until its delimiter arrives rather than
 * parsed eagerly.
 */
export async function askStream(
  payload: AskRequest,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/v1/ask/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    });
  } catch (err) {
    if ((err as Error)?.name === "AbortError") throw err;
    throw new ApiError(UNREACHABLE, 0);
  }

  if (!res.ok) throw await failure(res);
  if (!res.body) throw new ApiError("The server returned an empty stream.", 0);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? ""; // keep the incomplete tail for the next chunk

      for (const frame of frames) {
        const line = frame.trim();
        if (!line.startsWith("data:")) continue;
        try {
          onEvent(JSON.parse(line.slice(5).trim()) as StreamEvent);
        } catch {
          // A malformed frame should not abort an otherwise healthy stream.
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export async function uploadDocuments(files: File[], reset = false): Promise<IngestResponse> {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  form.append("reset", String(reset));
  let res: Response;
  try {
    // No Content-Type header — the browser must set the multipart boundary.
    res = await fetch(`${API_BASE_URL}/v1/ingest/upload`, { method: "POST", body: form });
  } catch {
    throw new ApiError(UNREACHABLE, 0);
  }
  if (!res.ok) throw await failure(res);
  return (await res.json()) as IngestResponse;
}

async function getJson<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`);
  } catch {
    throw new ApiError(UNREACHABLE, 0);
  }
  if (!res.ok) throw await failure(res);
  return (await res.json()) as T;
}

/** Documents currently indexed — drives the History document filter. */
export function getDocuments(): Promise<DocumentsResponse> {
  return getJson<DocumentsResponse>("/v1/documents");
}

/** Model wiring + corpus size for the sidebar system panel. */
export function getSystemInfo(): Promise<SystemInfo> {
  return getJson<SystemInfo>("/v1/system");
}

/** Thumbs ratings; a thumbs-down also enqueues a Phase 6 auto-eval candidate. */
export async function sendFeedback(query: string, rating: "up" | "down"): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/v1/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, rating }),
    });
  } catch {
    throw new ApiError(UNREACHABLE, 0);
  }
  if (!res.ok) throw await failure(res);
}
