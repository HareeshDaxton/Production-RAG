"use client";

import { useEffect, useRef, useState } from "react";
import { Paperclip, SendHorizonal, Square } from "lucide-react";
import { DocumentChips } from "@/components/document-chips";
import { Button } from "@/components/ui/button";
import type { IndexedDocument } from "@/lib/types";
import { cn } from "@/lib/utils";

const MAX_HEIGHT_PX = 200;

/** Mirrors the backend allowlist (`ingestion.formats.enabled` -> allowed_suffixes()). */
const ACCEPT = [
  ".pdf", ".docx", ".md", ".markdown", ".txt", ".html", ".htm",
  ".csv", ".json", ".xml",
  ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp", ".gif",
].join(",");

export function Composer({
  onSubmit,
  onStop,
  onFiles,
  busy,
  disabled,
  documents,
  uploading,
  uploadError,
  onRemoveDocument,
  scope,
}: {
  onSubmit: (query: string) => void;
  onStop: () => void;
  /** Picked or dropped files — ingestion starts immediately, no confirmation step. */
  onFiles: (files: FileList | null) => void;
  busy: boolean;
  disabled?: boolean;
  documents: IndexedDocument[];
  uploading: string[];
  uploadError: string | null;
  onRemoveDocument: (source: string) => Promise<void>;
  scope: string[];
}) {
  const [value, setValue] = useState("");
  const [dragging, setDragging] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT_PX)}px`;
  }, [value]);

  // The backend enforces min_length=3 on the query.
  const canSend = value.trim().length >= 3 && !busy && !disabled;

  function submit() {
    if (!canSend) return;
    onSubmit(value.trim());
    setValue("");
  }

  return (
    <div className="px-4 pb-4 md:px-6">
      <div className="mx-auto max-w-3xl">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            onFiles(e.dataTransfer.files);
          }}
          className={cn(
            "rounded-2xl border bg-surface px-3 py-2.5 transition-colors duration-200",
            dragging ? "border-accent" : "border-border focus-within:border-accent/50",
          )}
        >
          {/* Attachments live inside the box, above the input — they belong to the
              message you are about to send, not to the page. */}
          <DocumentChips
            documents={documents}
            uploading={uploading}
            onRemove={onRemoveDocument}
          />

          <div className="flex items-end gap-2">
            <Button
              size="icon"
              onClick={() => fileRef.current?.click()}
              aria-label="Attach a file"
              title="Attach a file"
              className="mb-0.5"
            >
              <Paperclip className="h-4 w-4" aria-hidden="true" />
            </Button>
            <input
              ref={fileRef}
              type="file"
              multiple
              accept={ACCEPT}
              className="sr-only"
              onChange={(e) => {
                onFiles(e.target.files);
                e.target.value = ""; // let the same file be picked again
              }}
            />

            <textarea
              ref={ref}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  submit();
                }
              }}
              rows={1}
              disabled={disabled}
              placeholder="Ask a question about your documents…"
              aria-label="Message"
              className="scrollbar-thin flex-1 resize-none bg-transparent py-1.5 text-[15px] leading-relaxed placeholder:text-muted-foreground/70 focus:outline-none disabled:opacity-50"
            />

            {busy ? (
              <Button
                variant="secondary"
                size="icon"
                onClick={onStop}
                aria-label="Stop generating"
                title="Stop"
                className="mb-0.5"
              >
                <Square className="h-3 w-3 fill-current" aria-hidden="true" />
              </Button>
            ) : (
              <Button
                variant="primary"
                size="icon"
                onClick={submit}
                disabled={!canSend}
                aria-label="Send message"
                className="mb-0.5"
              >
                <SendHorizonal className="h-4 w-4" aria-hidden="true" />
              </Button>
            )}
          </div>
        </div>

        {uploadError ? (
          <p
            role="alert"
            className="mt-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-[12px] text-destructive"
          >
            {uploadError}
          </p>
        ) : null}

        {/* Attaching files narrows retrieval to them — say so, rather than letting
            the scope change silently. */}
        <p className="mt-2 text-center text-[11px] text-muted-foreground/70">
          {scope.length === 1
            ? `Answering from ${scope[0]}`
            : scope.length > 1
              ? `Answering from ${scope.length} attached files`
              : "Retrieves from indexed documents only"}{" "}
          · Shift+Enter for newline
        </p>
      </div>
    </div>
  );
}
