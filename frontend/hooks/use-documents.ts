"use client";

import { useCallback, useEffect, useState } from "react";
import { deleteDocument, getDocuments, getSystemInfo } from "@/lib/api";
import type { IndexedDocument, SystemInfo } from "@/lib/types";

/**
 * The indexed corpus, shared by the sidebar counters and the composer's file
 * chips. Both read the same state so an upload can never update one and leave
 * the other showing stale numbers.
 */
export function useDocuments() {
  const [documents, setDocuments] = useState<IndexedDocument[]>([]);
  const [system, setSystem] = useState<SystemInfo | null>(null);

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

  const remove = useCallback(
    async (source: string) => {
      await deleteDocument(source);
      await refresh();
    },
    [refresh],
  );

  return { documents, system, refresh, remove };
}
