"use client";

import { useState } from "react";
import { Check, Copy, RefreshCw, ThumbsDown, ThumbsUp, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { sendFeedback } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Copy / regenerate / rate. Thumbs post to /v1/feedback, which records the vote and
 * — on a thumbs-down — enqueues an auto-eval candidate for human review.
 */
export function MessageActions({
  answer,
  query,
  feedback,
  onFeedback,
  onRegenerate,
  disabled,
  cached,
}: {
  answer: string;
  query: string;
  feedback?: "up" | "down";
  onFeedback: (rating: "up" | "down") => void;
  onRegenerate: () => void;
  disabled?: boolean;
  cached?: boolean;
}) {
  const [copied, setCopied] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  async function copy() {
    try {
      await navigator.clipboard.writeText(answer);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setNote("Clipboard unavailable");
    }
  }

  async function rate(rating: "up" | "down") {
    if (feedback) return;
    onFeedback(rating); // optimistic — a vote shouldn't block on the network
    try {
      await sendFeedback(query, rating);
      setNote(rating === "down" ? "Queued for review" : "Thanks");
      window.setTimeout(() => setNote(null), 2400);
    } catch {
      setNote("Feedback not recorded");
    }
  }

  return (
    <div className="flex items-center gap-0.5">
      <Button size="icon" onClick={copy} aria-label="Copy answer" title="Copy">
        {copied ? (
          <Check className="h-3.5 w-3.5 text-foreground" aria-hidden="true" />
        ) : (
          <Copy className="h-3.5 w-3.5" aria-hidden="true" />
        )}
      </Button>

      <Button
        size="icon"
        onClick={onRegenerate}
        disabled={disabled}
        aria-label="Regenerate answer"
        title="Regenerate"
      >
        <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
      </Button>

      <Button
        size="icon"
        onClick={() => rate("up")}
        disabled={Boolean(feedback)}
        aria-label="Good answer"
        aria-pressed={feedback === "up"}
        title="Good answer"
      >
        <ThumbsUp
          className={cn("h-3.5 w-3.5", feedback === "up" && "fill-current text-foreground")}
          aria-hidden="true"
        />
      </Button>

      <Button
        size="icon"
        onClick={() => rate("down")}
        disabled={Boolean(feedback)}
        aria-label="Bad answer"
        aria-pressed={feedback === "down"}
        title="Needs work — queues an eval candidate"
        className="mr-1"
      >
        <ThumbsDown
          className={cn("h-3.5 w-3.5", feedback === "down" && "fill-current text-foreground")}
          aria-hidden="true"
        />
      </Button>

      {cached ? (
        <span
          className="flex items-center gap-1 text-[11px] text-muted-foreground"
          title="Served from the semantic cache"
        >
          <Zap className="h-3 w-3" aria-hidden="true" />
          cached
        </span>
      ) : null}

      {note ? <span className="ml-1 text-[11px] text-muted-foreground">{note}</span> : null}
    </div>
  );
}
