"use client";

import { useState } from "react";
import { FileText, Loader2, X } from "lucide-react";
import type { IndexedDocument } from "@/lib/types";

/**
 * Files uploaded from the open chat, shown above the composer. Scoped per chat
 * so a new one starts clean, but the index behind them is corpus-wide — so the
 * dismiss really deletes, and is labelled that way rather than as a soft remove.
 */
export function DocumentChips({
  documents,
  onRemove,
}: {
  documents: IndexedDocument[];
  onRemove: (source: string) => Promise<void>;
}) {
  const [removing, setRemoving] = useState<string | null>(null);

  if (documents.length === 0) return null;

  async function remove(source: string) {
    setRemoving(source);
    try {
      await onRemove(source);
    } finally {
      setRemoving(null);
    }
  }

  return (
    <div className="mx-auto mb-2 flex max-w-3xl flex-wrap gap-2">
      {documents.map((doc) => {
        const busy = removing === doc.source;
        return (
          <span
            key={doc.source}
            title={`${doc.source} · ${doc.chunks} chunks${doc.pages ? ` · ${doc.pages} pages` : ""}`}
            className="flex items-center gap-2 rounded-xl border border-border bg-surface py-1.5 pl-2 pr-1.5"
          >
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-muted">
              <FileText className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
            </span>
            <span className="min-w-0">
              <span className="block max-w-[14rem] truncate text-[12px] leading-tight">
                {doc.source}
              </span>
              <span className="block text-[10px] uppercase leading-tight text-muted-foreground">
                {doc.file_type || "file"} · {doc.chunks} chunks
              </span>
            </span>
            <button
              onClick={() => remove(doc.source)}
              disabled={busy}
              aria-label={`Remove ${doc.source} from the index`}
              title="Remove from index"
              className="flex h-5 w-5 shrink-0 cursor-pointer items-center justify-center rounded-full text-muted-foreground transition-colors duration-200 hover:bg-surface-hover hover:text-foreground disabled:opacity-50"
            >
              {busy ? (
                <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
              ) : (
                <X className="h-3 w-3" aria-hidden="true" />
              )}
            </button>
          </span>
        );
      })}
    </div>
  );
}
