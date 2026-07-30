import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { Conversation } from "@/lib/types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function createId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export function deriveTitle(question: string): string {
  const clean = question.trim().replace(/\s+/g, " ");
  return clean.length <= 44 ? clean : `${clean.slice(0, 44).trimEnd()}…`;
}

export function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

export function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** Bands mirror the backend: idk_threshold 0.45, auto-eval flag 0.6. */
export function confidenceTone(confidence: number): "high" | "medium" | "low" {
  if (confidence >= 0.75) return "high";
  if (confidence >= 0.45) return "medium";
  return "low";
}

export function formatRelativeTime(timestamp: number): string {
  const seconds = Math.round((Date.now() - timestamp) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days}d ago`;
  const weeks = Math.round(days / 7);
  if (weeks < 5) return `${weeks}w ago`;
  return new Date(timestamp).toLocaleDateString();
}

/**
 * The doc chips on a history card. Files actually attached to the chat win — they
 * are what the user chose. Citations are only a fallback for chats recorded before
 * attachments existed, where they'd otherwise show nothing.
 */
export function conversationDocuments(conversation: Conversation): string[] {
  if (conversation.attachments?.length) return conversation.attachments;
  const sources = new Set<string>();
  for (const message of conversation.messages) {
    for (const citation of message.response?.citations ?? []) {
      if (citation.source) sources.add(citation.source);
    }
  }
  return [...sources];
}

/** The question that opened a conversation, used as the card preview. */
export function firstQuestion(conversation: Conversation): string {
  return conversation.messages.find((m) => m.role === "user")?.content ?? "";
}
