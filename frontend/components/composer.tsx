"use client";

import { useEffect, useRef, useState } from "react";
import { Paperclip, SendHorizonal, Square } from "lucide-react";
import { Button } from "@/components/ui/button";

const MAX_HEIGHT_PX = 200;

export function Composer({
  onSubmit,
  onStop,
  onOpenUpload,
  busy,
  disabled,
}: {
  onSubmit: (query: string) => void;
  onStop: () => void;
  onOpenUpload: () => void;
  busy: boolean;
  disabled?: boolean;
}) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

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
        <div className="flex items-end gap-2 rounded-2xl border border-border bg-surface px-3 py-2.5 transition-colors duration-200 focus-within:border-accent/50">
          <Button
            size="icon"
            onClick={onOpenUpload}
            aria-label="Upload a document"
            title="Upload a document"
            className="mb-0.5"
          >
            <Paperclip className="h-4 w-4" aria-hidden="true" />
          </Button>

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

        <p className="mt-2 text-center text-[11px] text-muted-foreground/70">
          Retrieves from indexed documents only · Shift+Enter for newline
        </p>
      </div>
    </div>
  );
}
