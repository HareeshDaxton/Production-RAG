"use client";

import { useEffect, useMemo, useState } from "react";
import { Clock, ExternalLink, FileText, Filter, MessageSquare, Search, Trash2 } from "lucide-react";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { Button } from "@/components/ui/button";
import { getDocuments } from "@/lib/api";
import type { Conversation, IndexedDocument } from "@/lib/types";
import {
  cn,
  conversationDocuments,
  firstQuestion,
  formatRelativeTime,
} from "@/lib/utils";

function ConversationCard({
  conversation,
  onResume,
  onDelete,
}: {
  conversation: Conversation;
  onResume: () => void;
  onDelete: () => void;
}) {
  const docs = conversationDocuments(conversation);
  const question = firstQuestion(conversation);

  return (
    <article className="group flex flex-col rounded-xl border border-border bg-surface/50 p-4 transition-colors duration-200 hover:bg-surface">
      <div className="flex items-start gap-2">
        <h3 className="min-w-0 flex-1 truncate text-[15px] font-semibold tracking-tight">
          {conversation.title}
        </h3>
        {/* Revealed on hover/focus so the resting card stays calm. */}
        <div className="flex shrink-0 gap-0.5 opacity-0 transition-opacity duration-200 group-hover:opacity-100 focus-within:opacity-100">
          <Button
            size="icon"
            onClick={onResume}
            aria-label={`Open conversation: ${conversation.title}`}
            title="Open"
          >
            <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
          <Button
            size="icon"
            onClick={onDelete}
            aria-label={`Delete conversation: ${conversation.title}`}
            title="Delete"
          >
            <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
        </div>
      </div>

      {question ? (
        <p className="mt-2 line-clamp-2 text-[13px] leading-relaxed text-muted-foreground">
          {question}
        </p>
      ) : (
        <p className="mt-2 text-[13px] italic text-muted-foreground">Empty conversation</p>
      )}

      {docs.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {docs.slice(0, 2).map((doc) => (
            <span
              key={doc}
              title={doc}
              className="flex max-w-[12rem] items-center gap-1.5 rounded-md border border-border bg-background/60 px-2 py-1 font-mono text-[10px] text-muted-foreground"
            >
              <FileText className="h-3 w-3 shrink-0" aria-hidden="true" />
              <span className="truncate">{doc}</span>
            </span>
          ))}
          {docs.length > 2 ? (
            <span className="rounded-md border border-border bg-background/60 px-2 py-1 font-mono text-[10px] text-muted-foreground">
              +{docs.length - 2}
            </span>
          ) : null}
        </div>
      ) : null}

      <div className="mt-auto flex items-center justify-between border-t border-border pt-3 text-[11px] text-muted-foreground [margin-top:0.9rem]">
        <span className="flex items-center gap-1.5 font-mono">
          <MessageSquare className="h-3 w-3" aria-hidden="true" />
          {conversation.messages.length} msgs
        </span>
        <span className="flex items-center gap-1.5 font-mono">
          <Clock className="h-3 w-3" aria-hidden="true" />
          {formatRelativeTime(conversation.updatedAt)}
        </span>
      </div>

      <Button
        variant="secondary"
        size="md"
        onClick={onResume}
        className="mt-3 w-full opacity-0 transition-opacity duration-200 group-hover:opacity-100 focus-visible:opacity-100"
      >
        Resume Conversation
      </Button>
    </article>
  );
}

export function HistoryView({
  conversations,
  onResume,
  onDelete,
}: {
  conversations: Conversation[];
  onResume: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [docFilter, setDocFilter] = useState("");
  const [documents, setDocuments] = useState<IndexedDocument[]>([]);
  const [pendingDelete, setPendingDelete] = useState<Conversation | null>(null);

  // Auto-updates from the index, so newly uploaded files appear in the filter.
  useEffect(() => {
    getDocuments()
      .then((res) => setDocuments(res.documents))
      .catch(() => setDocuments([]));
  }, [conversations.length]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return conversations
      .filter((c) => {
        if (docFilter && !conversationDocuments(c).includes(docFilter)) return false;
        if (!q) return true;
        return (
          c.title.toLowerCase().includes(q) ||
          firstQuestion(c).toLowerCase().includes(q) ||
          conversationDocuments(c).some((d) => d.toLowerCase().includes(q))
        );
      })
      // Title matches rank above body matches; otherwise most recent first.
      .sort((a, b) => {
        if (q) {
          const aTitle = a.title.toLowerCase().includes(q) ? 0 : 1;
          const bTitle = b.title.toLowerCase().includes(q) ? 0 : 1;
          if (aTitle !== bTitle) return aTitle - bTitle;
        }
        return b.updatedAt - a.updatedAt;
      });
  }, [conversations, query, docFilter]);

  return (
    <>
      <div className="scrollbar-thin flex-1 overflow-y-auto px-4 py-6 md:px-6">
        <div className="mx-auto max-w-6xl">
          <h1 className="text-[22px] font-semibold tracking-tight">Conversation History</h1>
          <p className="mt-1 font-mono text-[12px] text-muted-foreground">
            {visible.length} conversation{visible.length === 1 ? "" : "s"} — click any card to
            resume
          </p>

          <div className="mt-5 flex flex-wrap items-center gap-3">
            <div className="relative min-w-[16rem] flex-1 sm:max-w-sm">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden="true"
              />
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search conversations…"
                aria-label="Search conversations"
                className="h-10 w-full rounded-lg border border-border bg-surface pl-9 pr-3 text-sm placeholder:text-muted-foreground focus:border-accent/50 focus:outline-none"
              />
            </div>

            <Filter className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
            <select
              value={docFilter}
              onChange={(e) => setDocFilter(e.target.value)}
              aria-label="Filter by document"
              className="h-10 min-w-[14rem] cursor-pointer rounded-lg border border-border bg-surface px-3 text-sm focus:border-accent/50 focus:outline-none"
            >
              <option value="">All Documents</option>
              {documents.map((doc) => (
                <option key={doc.source} value={doc.source}>
                  {doc.title || doc.source}
                </option>
              ))}
            </select>
          </div>

          {visible.length === 0 ? (
            <p className="mt-16 text-center text-sm text-muted-foreground">
              {conversations.length === 0
                ? "No conversations yet — ask something in Chat to get started."
                : "No conversations match your search."}
            </p>
          ) : (
            <div className={cn("mt-6 grid gap-4", "sm:grid-cols-2 xl:grid-cols-3")}>
              {visible.map((c) => (
                <ConversationCard
                  key={c.id}
                  conversation={c}
                  onResume={() => onResume(c.id)}
                  onDelete={() => setPendingDelete(c)}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete this conversation?"
        description={`“${pendingDelete?.title ?? ""}” and its ${
          pendingDelete?.messages.length ?? 0
        } message(s) will be removed. This cannot be undone.`}
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => {
          if (pendingDelete) onDelete(pendingDelete.id);
          setPendingDelete(null);
        }}
      />
    </>
  );
}
