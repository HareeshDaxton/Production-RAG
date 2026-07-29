"use client";

import { AlertCircle, Info } from "lucide-react";
import { Markdown } from "@/components/markdown";
import { MessageActions } from "@/components/message-actions";
import { Sources } from "@/components/sources";
import type { ChatMessage } from "@/lib/types";
import { cn } from "@/lib/utils";

export function UserBubble({ content }: { content: string }) {
  return (
    <div className="flex items-start justify-end gap-3">
      <div className="max-w-[80%] rounded-2xl border border-border bg-surface px-4 py-2.5 text-[15px] leading-relaxed">
        {content}
      </div>
      <span
        className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-border bg-surface text-[11px] font-medium text-muted-foreground"
        aria-hidden="true"
      >
        U
      </span>
    </div>
  );
}

export function AssistantBubble({
  message,
  busy,
  onFeedback,
  onRegenerate,
}: {
  message: ChatMessage;
  busy: boolean;
  onFeedback: (rating: "up" | "down") => void;
  onRegenerate: () => void;
}) {
  const response = message.response;
  const streaming = Boolean(message.streaming);
  const pending = streaming && message.content.length === 0;

  return (
    <div className="flex items-start gap-3">
      <span
        className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-accent/40 bg-accent/10 text-[11px] font-semibold text-accent"
        aria-hidden="true"
      >
        A
      </span>

      <div className="min-w-0 flex-1 space-y-3">
        {message.error ? (
          <div className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2.5">
            <AlertCircle
              className="mt-0.5 h-4 w-4 shrink-0 text-destructive"
              aria-hidden="true"
            />
            <div className="min-w-0">
              <p className="text-sm font-medium text-destructive">Request failed</p>
              <p className="mt-0.5 text-[12px] leading-relaxed text-muted-foreground">
                {message.error}
              </p>
            </div>
          </div>
        ) : pending ? (
          <p className="flex items-center gap-2 py-1.5 text-sm text-muted-foreground">
            <span className="flex gap-1" aria-hidden="true">
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.3s]" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.15s]" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground" />
            </span>
            Searching your documents…
          </p>
        ) : (
          <div className="rounded-2xl border border-border bg-surface/60 px-4 py-3">
            <Markdown content={message.content} className={cn(streaming && "caret")} />
          </div>
        )}

        {message.replaced ? (
          <p className="flex items-start gap-2 rounded-xl border border-warning/30 bg-warning/10 px-3 py-2 text-[12px] leading-relaxed text-warning">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            The draft wasn&rsquo;t sufficiently supported by the sources, so it was replaced
            with an honest refusal.
          </p>
        ) : null}

        {response ? (
          <>
            {/* Hidden entirely when the answer had no grounded sources. */}
            <Sources citations={response.citations} />
            <MessageActions
              answer={response.answer}
              query={response.query}
              feedback={message.feedback}
              onFeedback={onFeedback}
              onRegenerate={onRegenerate}
              disabled={busy}
              cached={response.cached}
            />
          </>
        ) : null}
      </div>
    </div>
  );
}
