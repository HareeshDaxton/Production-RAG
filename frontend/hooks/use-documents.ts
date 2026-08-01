"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, deleteDocument, getDocuments, getSystemInfo, uploadDocuments } from "@/lib/api";
import type { IndexedDocument, SystemInfo } from "@/lib/types";

/** `ingest_files` flattens uploads to their basename — that becomes the `source`. */
const sourceOf = (file: File) => file.name.split(/[\\/]/).pop() || file.name;

/**
 * The indexed corpus, shared by the sidebar counters and the composer's file
 * chips. Both read the same state so an upload can never update one and leave
 * the other showing stale numbers.
 */
export function useDocuments() {
  const [documents, setDocuments] = useState<IndexedDocument[]>([]);
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [uploading, setUploading] = useState<string[]>([]);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [docs, info] = await Promise.all([getDocuments(), getSystemInfo()]);
      setDocuments(docs.documents);
      setSystem(info);
    } catch {
      // Backend unreachable — leave the last known values rather than blanking out.
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  /** Ingest picked/dropped files immediately; returns the sources that landed. */
  const upload = useCallback(
    async (files: File[]): Promise<string[]> => {
      if (files.length === 0) return [];
      const sources = files.map(sourceOf);
      setUploadError(null);
      setUploading((prev) => [...prev, ...sources]);
      try {
        await uploadDocuments(files, false);
        await refresh();
        return sources;
      } catch (err) {
        setUploadError(err instanceof ApiError ? err.message : "Upload failed");
        return [];
      } finally {
        setUploading((prev) => prev.filter((s) => !sources.includes(s)));
      }
    },
    [refresh],
  );

  const remove = useCallback(
    async (source: string) => {
      await deleteDocument(source);
      await refresh();
    },
    [refresh],
  );

  return { documents, system, uploading, uploadError, refresh, upload, remove };
}
