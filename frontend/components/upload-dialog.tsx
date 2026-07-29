"use client";

import { useEffect, useRef, useState } from "react";
import { CheckCircle2, CloudUpload, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ApiError, uploadDocuments } from "@/lib/api";
import type { IngestResponse } from "@/lib/types";
import { cn, formatBytes } from "@/lib/utils";

/** Mirrors the backend allowlist (`ingestion.formats.enabled` -> allowed_suffixes()). */
const ACCEPT = [
  ".pdf", ".docx", ".md", ".markdown", ".txt", ".html", ".htm",
  ".csv", ".json", ".xml",
  ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp", ".gif",
].join(",");

export function UploadDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<IngestResponse | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  function addFiles(incoming: FileList | null) {
    if (!incoming) return;
    setResult(null);
    setError(null);
    setFiles((prev) => {
      const seen = new Set(prev.map((f) => `${f.name}:${f.size}`));
      return [...prev, ...Array.from(incoming).filter((f) => !seen.has(`${f.name}:${f.size}`))];
    });
  }

  async function submit() {
    if (files.length === 0 || busy) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await uploadDocuments(files, false));
      setFiles([]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

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
              Indexed into the same pipeline as your corpus. Re-uploading a file replaces
              its chunks.
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

        {files.length > 0 ? (
          <ul className="scrollbar-thin mt-3 max-h-40 space-y-1.5 overflow-y-auto">
            {files.map((file) => (
              <li
                key={`${file.name}:${file.size}`}
                className="flex items-center gap-2 rounded-lg border border-border bg-surface/50 px-2.5 py-1.5"
              >
                <span className="min-w-0 flex-1 truncate font-mono text-[11px]">
                  {file.name}
                </span>
                <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">
                  {formatBytes(file.size)}
                </span>
                <Button
                  size="icon"
                  aria-label={`Remove ${file.name}`}
                  onClick={() => setFiles((prev) => prev.filter((f) => f !== file))}
                >
                  <X className="h-3.5 w-3.5" aria-hidden="true" />
                </Button>
              </li>
            ))}
          </ul>
        ) : null}

        {error ? (
          <p className="mt-3 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-[12px] text-destructive">
            {error}
          </p>
        ) : null}

        {result ? (
          <p className="mt-3 flex items-start gap-2 rounded-lg border border-accent/30 bg-accent/10 px-3 py-2 text-[12px] text-accent">
            <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            Indexed {result.documents_ingested} document
            {result.documents_ingested === 1 ? "" : "s"} into {result.chunks_created} chunks.
          </p>
        ) : null}

        <Button
          variant="primary"
          size="md"
          onClick={submit}
          disabled={files.length === 0 || busy}
          className="mt-4 w-full"
        >
          {busy ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              Ingesting…
            </>
          ) : (
            "Ingest files"
          )}
        </Button>
      </div>
    </div>
  );
}
