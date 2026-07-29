/**
 * Conversation history. The backend is stateless — there is no session or thread
 * concept server-side — so history lives in the browser. SSR-safe.
 */
import type { Conversation } from "@/lib/types";
import { createId } from "@/lib/utils";

const STORAGE_KEY = "production-rag.chats.v1";
const MAX_CONVERSATIONS = 50;

export function loadConversations(): Conversation[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return (parsed as Conversation[])
      .filter((c) => c && typeof c.id === "string" && Array.isArray(c.messages))
      .sort((a, b) => b.updatedAt - a.updatedAt);
  } catch {
    return [];
  }
}

export function saveConversations(conversations: Conversation[]): void {
  if (typeof window === "undefined") return;
  try {
    const trimmed = [...conversations]
      .sort((a, b) => b.updatedAt - a.updatedAt)
      .slice(0, MAX_CONVERSATIONS);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
  } catch {
    // Quota exceeded / private mode — history is a convenience, never fail the app.
  }
}

export function createConversation(): Conversation {
  const now = Date.now();
  return { id: createId(), title: "New chat", createdAt: now, updatedAt: now, messages: [] };
}
