"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, askStream } from "@/lib/api";
import { createConversation, loadConversations, saveConversations } from "@/lib/storage";
import type { ChatMessage, Conversation, RetrievalMode } from "@/lib/types";
import { createId, deriveTitle } from "@/lib/utils";

export function useChat() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [busy, setBusy] = useState(false);
  const [mode] = useState<RetrievalMode>("hybrid");

  const abortRef = useRef<AbortController | null>(null);
  const skipFirstSave = useRef(true);

  // Hydration-safe: first client render matches the server (empty), then load.
  // Conversations only exist once they hold a message, so any empty ones left by
  // an older build are dropped rather than shown as blank history cards.
  useEffect(() => {
    setConversations(loadConversations().filter((c) => c.messages.length > 0));
    setActiveId(null); // always land on a fresh chat, like ChatGPT
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    if (skipFirstSave.current) {
      skipFirstSave.current = false; // don't write the pre-hydration state back
      return;
    }
    saveConversations(conversations);
  }, [conversations, hydrated]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const active = conversations.find((c) => c.id === activeId) ?? null;

  const patchMessage = useCallback(
    (conversationId: string, messageId: string, patch: Partial<ChatMessage>) => {
      setConversations((prev) =>
        prev.map((c) =>
          c.id === conversationId
            ? {
                ...c,
                messages: c.messages.map((m) =>
                  m.id === messageId ? { ...m, ...patch } : m,
                ),
                updatedAt: Date.now(),
              }
            : c,
        ),
      );
    },
    [],
  );

  /** Append streamed text to the in-flight assistant message. */
  const appendDelta = useCallback(
    (conversationId: string, messageId: string, text: string) => {
      setConversations((prev) =>
        prev.map((c) =>
          c.id === conversationId
            ? {
                ...c,
                messages: c.messages.map((m) =>
                  m.id === messageId ? { ...m, content: m.content + text } : m,
                ),
              }
            : c,
        ),
      );
    },
    [],
  );

  const runStream = useCallback(
    async (conversationId: string, prompt: string, assistantId: string) => {
      const controller = new AbortController();
      abortRef.current = controller;
      setBusy(true);
      try {
        await askStream(
          { query: prompt, mode },
          (event) => {
            switch (event.type) {
              case "delta":
                appendDelta(conversationId, assistantId, event.text);
                break;
              case "final":
                // The verified response is authoritative — it replaces the streamed
                // text, which matters when the quality gate swapped in a refusal.
                patchMessage(conversationId, assistantId, {
                  content: event.response.answer,
                  response: event.response,
                  replaced: event.replaced,
                  streaming: false,
                });
                break;
              case "error":
                patchMessage(conversationId, assistantId, {
                  error: event.message,
                  streaming: false,
                });
                break;
            }
          },
          controller.signal,
        );
      } catch (err) {
        if (controller.signal.aborted) {
          patchMessage(conversationId, assistantId, { streaming: false });
        } else {
          patchMessage(conversationId, assistantId, {
            error: err instanceof ApiError ? err.message : "Something went wrong.",
            streaming: false,
          });
        }
      } finally {
        abortRef.current = null;
        setBusy(false);
      }
    },
    [mode, appendDelta, patchMessage],
  );

  const send = useCallback(
    (query: string) => {
      if (busy) return;
      const now = Date.now();
      const assistantId = createId();
      const turn: ChatMessage[] = [
        { id: createId(), role: "user", content: query, createdAt: now },
        {
          id: assistantId,
          role: "assistant",
          content: "",
          createdAt: now,
          streaming: true,
          prompt: query,
        },
      ];

      const existing = conversations.find((c) => c.id === activeId);
      if (!existing) {
        // No active chat (fresh load, after New chat, or after deleting the last
        // one) — the conversation is created here, on the first real message.
        const fresh = createConversation();
        setConversations((prev) => [
          { ...fresh, title: deriveTitle(query), messages: turn, updatedAt: now },
          ...prev,
        ]);
        setActiveId(fresh.id);
        void runStream(fresh.id, query, assistantId);
        return;
      }

      setConversations((prev) =>
        prev.map((c) =>
          c.id === existing.id
            ? {
                ...c,
                title: c.messages.length === 0 ? deriveTitle(query) : c.title,
                messages: [...c.messages, ...turn],
                updatedAt: now,
              }
            : c,
        ),
      );
      void runStream(existing.id, query, assistantId);
    },
    [activeId, busy, conversations, runStream],
  );

  const regenerate = useCallback(
    (message: ChatMessage) => {
      if (!activeId || busy || !message.prompt) return;
      // Reset the existing bubble in place rather than appending a duplicate turn.
      patchMessage(activeId, message.id, {
        content: "",
        response: undefined,
        error: undefined,
        replaced: false,
        feedback: undefined,
        streaming: true,
      });
      void runStream(activeId, message.prompt, message.id);
    },
    [activeId, busy, patchMessage, runStream],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  /** Just detaches from the current chat — nothing is stored until a message is sent. */
  const newChat = useCallback(() => setActiveId(null), []);

  const deleteChat = useCallback(
    (id: string) => {
      setConversations((prev) => prev.filter((c) => c.id !== id));
      // Deleting the open chat drops you onto a fresh one; deleting the last
      // conversation legitimately leaves history empty.
      setActiveId((current) => (current === id ? null : current));
    },
    [],
  );

  const setFeedback = useCallback(
    (messageId: string, rating: "up" | "down") => {
      if (activeId) patchMessage(activeId, messageId, { feedback: rating });
    },
    [activeId, patchMessage],
  );

  return {
    conversations,
    active,
    activeId,
    hydrated,
    busy,
    send,
    regenerate,
    stop,
    newChat,
    deleteChat,
    setActiveId,
    setFeedback,
  };
}
