"use client";

import { useState } from "react";
import { FileText, Loader2, X } from "lucide-react";
import type { IndexedDocument } from "@/lib/types";

/** Human label under the filename, the way a file manager names a type. */
const KIND: Record<string, string> = {
  pdf: "PDF",
  docx: "Document",
  markdown: "Document",
  txt: "Text",
  html: "Web page",
  csv: "Spreadsheet",
  json: "Data",
  xml: "Data",
  image: "Image",
};

interface Chip {
  key: string;
  name: string;
  kind: string;
  busy: boolean;
}

/**
 * Attached files, rendered inside the composer box above the input — the same
 * place ChatGPT puts them, so it reads as "these ride with my next message".
 *
 * Files are indexed corpus-wide, so dismissing one really deletes it; the control
 * is a deliberate click rather than a passive dismiss for that reason.
 */
export function DocumentChips({
  documents,
  uploading,
  onRemove,
}: {
  documents: IndexedDocument[];
  /** Sources still being ingested — shown with a spinner and no dismiss. */
  uploading: string[];
  onRemove: (source: string) => Promise<void>;
}) {
  const [removing, setRemoving] = useState<string | null>(null);

  const chips: Chip[] = [
    ...uploading.map((name) => ({ key: `up:${name}`, name, kind: "Uploading…", busy: true })),
    ...documents.map((doc) => ({
      key: doc.source,
      name: doc.source,
      kind: KIND[doc.file_type] ?? "File",
      busy: removing === doc.source,
    })),
  ];

  if (chips.length === 0) return null;

  async function remove(source: string) {
    setRemoving(source);
    try {
      await onRemove(source);
    } finally {
      setRemoving(null);
    }
  }

  return (
    <ul className="mb-2.5 flex flex-wrap gap-2 pr-1 pt-1">
      {chips.map(({ key, name, kind, busy }) => {
        const pending = kind === "Uploading…";
        return (
          <li
            key={key}
            title={name}
            className="relative flex items-center gap-2.5 rounded-xl border border-border bg-background py-1.5 pl-2 pr-3"
          >
            <span
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border bg-surface"
              aria-hidden="true"
            >
              {busy ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
              ) : (
                <FileText className="h-3.5 w-3.5" />
              )}
            </span>
            <span className="min-w-0">
              <span className="block max-w-[13rem] truncate text-[12px] font-medium leading-tight">
                {name}
              </span>
              <span className="block text-[11px] leading-tight text-muted-foreground">
                {kind}
              </span>
            </span>
            {pending ? null : (
              <button
                onClick={() => remove(name)}
                disabled={busy}
                aria-label={`Remove ${name} from the index`}
                title="Remove from index"
                className="absolute -right-1.5 -top-1.5 flex h-5 w-5 cursor-pointer items-center justify-center rounded-full border border-border bg-background text-muted-foreground transition-colors duration-200 hover:text-foreground disabled:opacity-50"
              >
                <X className="h-3 w-3" aria-hidden="true" />
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}
