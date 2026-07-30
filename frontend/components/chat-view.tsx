"use client";

import { useEffect, useRef } from "react";
import { FileText, Lightbulb, MessageSquare, Plus, Search } from "lucide-react";
import { Composer } from "@/components/composer";
import { AssistantBubble, UserBubble } from "@/components/message";
import { Button } from "@/components/ui/button";
import type { ChatMessage, Conversation, IndexedDocument } from "@/lib/types";

const SUGGESTIONS = [
  { icon: FileText, text: "Summarize the key findings in my uploaded research papers" },
  { icon: Search, text: "What does my documentation say about authentication flows?" },
  { icon: Lightbulb, text: "Compare the methodologies across the papers I uploaded" },
  { icon: MessageSquare, text: "Extract all action items from my meeting notes" },
];

export function ChatView({
  conversation,
  busy,
  onSend,
  onStop,
  onRegenerate,
  onFeedback,
  onNewChat,
  onOpenUpload,
  ready,
  documents,
  onRemoveDocument,
  scope,
}: {
  conversation: Conversation | null;
  busy: boolean;
  onSend: (query: string) => void;
  onStop: () => void;
  onRegenerate: (message: ChatMessage) => void;
  onFeedback: (messageId: string, rating: "up" | "down" | null) => void;
  onNewChat: () => void;
  onOpenUpload: () => void;
  ready: boolean;
  /** Staged uploads — chips above the composer until the next message carries them. */
  documents: IndexedDocument[];
  onRemoveDocument: (source: string) => Promise<void>;
  /** Every file this chat answers from, for the composer's scope line. */
  scope: string[];
}) {
  const messages = conversation?.messages ?? [];
  const bottomRef = useRef<HTMLDivElement>(null);
  // Streamed tokens change the last message's length, so track that too.
  const lastLength = messages[messages.length - 1]?.content.length ?? 0;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, lastLength]);

  const empty = messages.length === 0;

  return (
    <>
      <header className="flex h-16 items-center gap-3 border-b border-border px-4 md:px-6">
        {/* Auto-named from the first question once a conversation starts. */}
        <h1 className="min-w-0 flex-1 truncate text-[15px] font-semibold tracking-tight">
          {conversation?.title ?? "New Conversation"}
        </h1>
        {!empty ? (
          <span className="hidden shrink-0 font-mono text-[11px] text-muted-foreground sm:inline">
            {messages.length} msgs
          </span>
        ) : null}
        <Button variant="secondary" size="md" onClick={onNewChat} className="shrink-0">
          <Plus className="h-4 w-4" aria-hidden="true" />
          <span className="hidden sm:inline">New Chat</span>
        </Button>
      </header>

      <main className="scrollbar-thin flex-1 overflow-y-auto">
        {!ready ? null : empty ? (
          <div className="mx-auto flex h-full max-w-2xl flex-col items-center justify-center px-4 py-10 text-center">
            <span className="flex h-14 w-14 items-center justify-center rounded-2xl border border-border bg-surface">
              <MessageSquare className="h-6 w-6" aria-hidden="true" />
            </span>
            <h2 className="mt-6 text-[28px] font-semibold tracking-tight">
              Chat with your knowledge
            </h2>
            <p className="mt-3 max-w-md text-[15px] leading-relaxed text-muted-foreground">
              Upload a PDF, DOCX, or image and ask anything. Aether answers with citations
              pointing to the exact page and section.
            </p>

            <div className="mt-9 grid w-full gap-3 sm:grid-cols-2">
              {SUGGESTIONS.map(({ icon: Icon, text }) => (
                <button
                  key={text}
                  onClick={() => onSend(text)}
                  className="group cursor-pointer rounded-xl border border-border bg-surface/50 p-4 text-left transition-colors duration-200 hover:bg-surface-hover"
                >
                  <Icon
                    className="h-4 w-4 text-muted-foreground transition-colors duration-200 group-hover:text-accent"
                    aria-hidden="true"
                  />
                  <span className="mt-3 block text-[13px] leading-relaxed text-muted-foreground">
                    {text}
                  </span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="mx-auto max-w-3xl space-y-7 px-4 py-6 md:px-6">
            {messages.map((message) =>
              message.role === "user" ? (
                <UserBubble
                  key={message.id}
                  content={message.content}
                  attachments={message.attachments}
                />
              ) : (
                <AssistantBubble
                  key={message.id}
                  message={message}
                  busy={busy}
                  onFeedback={(rating) => onFeedback(message.id, rating)}
                  onRegenerate={() => onRegenerate(message)}
                />
              ),
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </main>

      <Composer
        onSubmit={onSend}
        onStop={onStop}
        onOpenUpload={onOpenUpload}
        busy={busy}
        disabled={!ready}
        documents={documents}
        onRemoveDocument={onRemoveDocument}
        scope={scope}
      />
    </>
  );
}
