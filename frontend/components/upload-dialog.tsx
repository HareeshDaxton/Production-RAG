"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, CloudUpload, FileText, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ApiError, uploadDocuments } from "@/lib/api";
import { cn, formatBytes } from "@/lib/utils";

/** Mirrors the backend allowlist (`ingestion.formats.enabled` -> allowed_suffixes()). */
const ACCEPT = [
  ".pdf", ".docx", ".md", ".markdown", ".txt", ".html", ".htm",
  ".csv", ".json", ".xml",
  ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp", ".gif",
].join(",");

type Status = "uploading" | "done" | "failed";

interface Item {
  file: File;
  status: Status;
}

const keyOf = (file: File) => `${file.name}:${file.size}`;
/** `ingest_files` flattens uploads to their basename — that becomes the `source`. */
const sourceOf = (file: File) => file.name.split(/[\\/]/).pop() || file.name;

export function UploadDialog({
  open,
  onClose,
  onIngested,
}: {
  open: boolean;
  onClose: () => void;
  /** Receives the ingested `source` values (the backend keys documents by basename). */
  onIngested?: (sources: string[]) => void | Promise<void>;
}) {
  const [items, setItems] = useState<Item[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chunks, setChunks] = useState(0);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    // Each opening is a fresh session — otherwise the last upload's rows linger.
    setItems([]);
    setError(null);
    setChunks(0);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const mark = useCallback((batch: File[], status: Status) => {
    const keys = new Set(batch.map(keyOf));
    setItems((prev) =>
      prev.map((item) => (keys.has(keyOf(item.file)) ? { ...item, status } : item)),
    );
  }, []);

  /** Send a batch straight to the API — adding a file *is* the ingest trigger. */
  const ingest = useCallback(
    async (batch: File[]) => {
      setBusy(true);
      setError(null);
      try {
        const result = await uploadDocuments(batch, false);
        setChunks((n) => n + result.chunks_created);
        mark(batch, "done");
        await onIngested?.(batch.map(sourceOf));
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Upload failed");
        mark(batch, "failed");
      } finally {
        setBusy(false);
      }
    },
    [mark, onIngested],
  );

  if (!open) return null;

  function addFiles(incoming: FileList | null) {
    // One ingest at a time: concurrent uploads would race the BM25 rebuild.
    if (!incoming || busy) return;
    const seen = new Set(items.map((i) => keyOf(i.file)));
    const fresh = Array.from(incoming).filter((f) => !seen.has(keyOf(f)));
    if (fresh.length === 0) return;
    setItems((prev) => [...prev, ...fresh.map((file) => ({ file, status: "uploading" as const }))]);
    void ingest(fresh);
  }

  function retry() {
    const failed = items.filter((i) => i.status === "failed").map((i) => i.file);
    if (failed.length === 0 || busy) return;
    mark(failed, "uploading");
    void ingest(failed);
  }

  const hasFailures = items.some((i) => i.status === "failed");
  const indexed = items.filter((i) => i.status === "done").length;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/70" onClick={onClose} aria-hidden="true" />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Upload documents"
        className="relative w-full max-w-md rounded-2xl border border-border bg-background p-5 shadow-2xl"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-sm font-semibold">Upload documents</h2>
            <p className="mt-0.5 text-[12px] leading-relaxed text-muted-foreground">
              Indexing starts as soon as you add a file. Re-uploading one replaces its
              chunks.
            </p>
          </div>
          <Button size="icon" onClick={onClose} aria-label="Close">
            <X className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            addFiles(e.dataTransfer.files);
          }}
          className={cn(
            "mt-4 rounded-xl border border-dashed px-4 py-7 text-center transition-colors duration-200",
            dragging ? "border-accent bg-accent/5" : "border-border bg-surface/40",
            busy && "opacity-60",
          )}
        >
          <CloudUpload className="mx-auto h-6 w-6 text-muted-foreground" aria-hidden="true" />
          <p className="mt-2 text-sm">Drop files here</p>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            PDF, DOCX, MD, HTML, TXT, CSV, JSON, XML, images (OCR)
          </p>
          <Button
            variant="secondary"
            size="sm"
            className="mt-3"
            disabled={busy}
            onClick={() => inputRef.current?.click()}
          >
            Browse files
          </Button>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept={ACCEPT}
            className="sr-only"
            onChange={(e) => {
              addFiles(e.target.files);
              e.target.value = "";
            }}
          />
        </div>

        {items.length > 0 ? (
          <ul className="scrollbar-thin mt-3 max-h-40 space-y-1.5 overflow-y-auto">
            {items.map(({ file, status }) => (
              <li
                key={keyOf(file)}
                className="flex items-center gap-2 rounded-lg border border-border bg-surface/50 px-2.5 py-1.5"
              >
                <span className="shrink-0" aria-hidden="true">
                  {status === "uploading" ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
                  ) : status === "done" ? (
                    <CheckCircle2 className="h-3.5 w-3.5" />
                  ) : (
                    <AlertCircle className="h-3.5 w-3.5 text-destructive" />
                  )}
                </span>
                <span className="min-w-0 flex-1 truncate font-mono text-[11px]">
                  {file.name}
                </span>
                <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">
                  {status === "uploading"
                    ? "indexing…"
                    : status === "failed"
                      ? "failed"
                      : formatBytes(file.size)}
                </span>
              </li>
            ))}
          </ul>
        ) : null}

        {error ? (
          <p className="mt-3 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-[12px] text-destructive">
            {error}
          </p>
        ) : null}

        {indexed > 0 && !busy ? (
          <p className="mt-3 flex items-start gap-2 rounded-lg border border-accent/30 bg-accent/10 px-3 py-2 text-[12px] text-accent">
            <FileText className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            Indexed {indexed} document{indexed === 1 ? "" : "s"} into {chunks} chunks.
          </p>
        ) : null}

        {busy ? (
          /* Scanned pages go through OCR on the CPU, which is slow enough that
             silence reads as a hang. Say so instead of spinning wordlessly. */
          <p className="mt-3 text-[11px] leading-relaxed text-muted-foreground">
            Extracting text, then embedding each chunk. Scanned pages are OCR&rsquo;d,
            which can take up to a minute per page — large or image-heavy PDFs take a
            while.
          </p>
        ) : null}

        <div className="mt-4 flex gap-2">
          {hasFailures ? (
            <Button variant="secondary" size="md" onClick={retry} disabled={busy} className="flex-1">
              Retry
            </Button>
          ) : null}
          <Button variant="primary" size="md" onClick={onClose} className="flex-1">
            Done
          </Button>
        </div>
      </div>
    </div>
  );
}
