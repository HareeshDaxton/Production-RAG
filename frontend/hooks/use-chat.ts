"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, askStream, generateTitle } from "@/lib/api";
import { createConversation, loadConversations, saveConversations } from "@/lib/storage";
import type { ChatMessage, Conversation, RetrievalMode } from "@/lib/types";
import { createId, deriveTitle } from "@/lib/utils";

export function useChat() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [busy, setBusy] = useState(false);
  const [mode] = useState<RetrievalMode>("hybrid");
  // Uploaded files waiting to be sent — they ride along with the next message,
  // the way an attachment does in ChatGPT, rather than hanging over the composer.
  const [staged, setStaged] = useState<string[]>([]);

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

  /** Everything this chat answers from: already attached + about to be sent. */
  const scope = [...new Set([...(active?.attachments ?? []), ...staged])];

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
    async (
      conversationId: string,
      prompt: string,
      assistantId: string,
      sources: string[] = [],
    ) => {
      const controller = new AbortController();
      abortRef.current = controller;
      setBusy(true);
      try {
        await askStream(
          // Attached files scope the search: without this a question about an
          // uploaded CSV loses to whatever prose is already in the corpus.
          { query: prompt, mode, ...(sources.length ? { filters: { source: sources } } : {}) },
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

  /**
   * Replace the placeholder title with a summarised one, ChatGPT-style — the raw
   * question is only a stand-in until this lands. Fire-and-forget: it runs beside
   * the answer stream and a failure just leaves the placeholder in place.
   */
  const nameConversation = useCallback((conversationId: string, question: string) => {
    void generateTitle(question)
      .then(({ title }) => {
        if (!title) return;
        setConversations((prev) =>
          prev.map((c) => (c.id === conversationId ? { ...c, title } : c)),
        );
      })
      .catch(() => {
        // Titling is cosmetic — never surface it as a chat error.
      });
  }, []);

  const send = useCallback(
    (query: string) => {
      if (busy) return;
      const now = Date.now();
      const assistantId = createId();
      const existing = conversations.find((c) => c.id === activeId);
      // Everything the answer may draw on: this chat's files plus the ones being sent.
      const sources = [...new Set([...(existing?.attachments ?? []), ...staged])];
      const turn: ChatMessage[] = [
        {
          id: createId(),
          role: "user",
          content: query,
          createdAt: now,
          // Only the newly staged files ride on this bubble — earlier ones are
          // already shown on the message they arrived with.
          ...(staged.length ? { attachments: staged } : {}),
        },
        {
          id: assistantId,
          role: "assistant",
          content: "",
          createdAt: now,
          streaming: true,
          prompt: query,
        },
      ];
      setStaged([]);

      if (!existing) {
        // No active chat (fresh load, after New chat, or after deleting the last
        // one) — the conversation is created here, on the first real message.
        const fresh = createConversation();
        setConversations((prev) => [
          { ...fresh, title: deriveTitle(query), messages: turn, updatedAt: now, attachments: sources },
          ...prev,
        ]);
        setActiveId(fresh.id);
        nameConversation(fresh.id, query);
        void runStream(fresh.id, query, assistantId, sources);
        return;
      }

      const opening = existing.messages.length === 0; // an untitled chat, if one survives
      setConversations((prev) =>
        prev.map((c) =>
          c.id === existing.id
            ? {
                ...c,
                title: opening ? deriveTitle(query) : c.title,
                messages: [...c.messages, ...turn],
                attachments: sources,
                updatedAt: now,
              }
            : c,
        ),
      );
      if (opening) nameConversation(existing.id, query);
      void runStream(existing.id, query, assistantId, sources);
    },
    [activeId, busy, conversations, nameConversation, runStream, staged],
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
      // Replay against the same files the chat is scoped to.
      void runStream(activeId, message.prompt, message.id, active?.attachments ?? []);
    },
    [active, activeId, busy, patchMessage, runStream],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  /** Just detaches from the current chat — nothing is stored until a message is sent. */
  const newChat = useCallback(() => {
    setActiveId(null);
    setStaged([]); // a new chat starts with nothing attached
  }, []);

  /** Open an existing chat; anything staged but unsent is dropped. */
  const selectChat = useCallback((id: string) => {
    setActiveId(id);
    setStaged([]);
  }, []);

  /** Stage freshly ingested files for the next message. */
  const attach = useCallback((sources: string[]) => {
    if (sources.length === 0) return;
    setStaged((prev) => [...new Set([...prev, ...sources])]);
  }, []);

  /** Deleting a document is index-wide, so drop it from every chat that lists it. */
  const detach = useCallback((source: string) => {
    setStaged((prev) => prev.filter((s) => s !== source));
    setConversations((prev) =>
      prev.map((c) =>
        c.attachments.includes(source)
          ? { ...c, attachments: c.attachments.filter((s) => s !== source) }
          : c,
      ),
    );
  }, []);

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
    (messageId: string, rating: "up" | "down" | null) => {
      // null = the user un-clicked; `undefined` is how "no rating" is stored.
      if (activeId) patchMessage(activeId, messageId, { feedback: rating ?? undefined });
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
    selectChat,
    setFeedback,
    staged,
    scope,
    attach,
    detach,
  };
}
