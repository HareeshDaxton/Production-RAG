"use client";

import {
  ChevronLeft,
  ChevronRight,
  History,
  Moon,
  MessageSquare,
  Sun,
} from "lucide-react";
import type { SystemInfo } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useTheme } from "@/hooks/use-theme";

export type View = "chat" | "history";

const NAV: { id: View; label: string; icon: typeof MessageSquare }[] = [
  { id: "chat", label: "Chat", icon: MessageSquare },
  { id: "history", label: "History", icon: History },
];

export function Sidebar({
  view,
  onView,
  collapsed,
  onToggleCollapse,
  mobileOpen,
  onCloseMobile,
  system,
}: {
  view: View;
  onView: (view: View) => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
  mobileOpen: boolean;
  onCloseMobile: () => void;
  /** Shared with the composer's chips so the counts can never disagree. */
  system: SystemInfo | null;
}) {
  const { theme, toggle } = useTheme();

  // The toggle is labelled with the mode it switches TO.
  const nextThemeLabel = theme === "dark" ? "Light Mode" : "Dark Mode";
  const ThemeIcon = theme === "dark" ? Sun : Moon;

  return (
    <>
      {mobileOpen ? (
        <div
          className="fixed inset-0 z-30 bg-black/60 md:hidden"
          onClick={onCloseMobile}
          aria-hidden="true"
        />
      ) : null}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex shrink-0 flex-col border-r border-border bg-sidebar",
          "transition-[width,transform] duration-300 md:static md:translate-x-0",
          collapsed ? "w-16" : "w-64",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        {/* Wordmark */}
        <div
          className={cn(
            "flex h-16 items-center gap-2.5 px-4",
            collapsed && "justify-center px-0",
          )}
        >
          <span
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-accent"
            aria-hidden="true"
          >
            <svg viewBox="0 0 24 24" className="h-7 w-7" fill="none">
              <circle cx="12" cy="7" r="3.4" fill="currentColor" opacity="0.95" />
              <circle cx="6.6" cy="16" r="3.4" fill="currentColor" opacity="0.7" />
              <circle cx="17.4" cy="16" r="3.4" fill="currentColor" opacity="0.5" />
            </svg>
          </span>
          {!collapsed ? (
            /* Wraps rather than truncates — the name is too long for one line at
               the sidebar's width, and "Medical Research As…" would read as a bug. */
            <span className="text-[13px] font-semibold leading-tight tracking-tight">
              Medical Research Assistant
            </span>
          ) : null}
        </div>

        {/* Primary nav */}
        <nav className="space-y-1 px-2" aria-label="Sections">
          {NAV.map(({ id, label, icon: Icon }) => {
            const active = view === id;
            return (
              <button
                key={id}
                onClick={() => {
                  onView(id);
                  onCloseMobile();
                }}
                aria-current={active ? "page" : undefined}
                title={collapsed ? label : undefined}
                className={cn(
                  "flex w-full cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5",
                  "text-sm transition-colors duration-200",
                  collapsed && "justify-center px-0",
                  active
                    ? "bg-surface font-medium text-foreground"
                    : "text-muted-foreground hover:bg-surface/60 hover:text-foreground",
                )}
              >
                <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                {!collapsed ? <span>{label}</span> : null}
              </button>
            );
          })}
        </nav>

        <div className="flex-1" />

        {/* System panel — real model wiring from GET /v1/system */}
        {!collapsed && system ? (
          <div className="mx-3 mb-3 rounded-xl border border-border bg-surface/50 p-3">
            <p className="mb-2 text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
              System
            </p>
            <dl className="space-y-1.5">
              {[
                { label: system.generation_model, hint: "generation" },
                { label: system.embedding_model, hint: "embeddings" },
              ].map(({ label, hint }) => (
                <div key={hint} className="flex items-center gap-2">
                  <dt
                    className="min-w-0 flex-1 truncate font-mono text-[11px] text-foreground/80"
                    title={`${label} · ${hint}`}
                  >
                    {label}
                  </dt>
                  <dd
                    className="h-1.5 w-1.5 shrink-0 rounded-full bg-success"
                    aria-label="ready"
                  />
                </div>
              ))}
            </dl>
            <p className="mt-2 border-t border-border pt-2 text-[11px] text-muted-foreground">
              {system.documents} doc{system.documents === 1 ? "" : "s"} · {system.chunks} chunks
            </p>
          </div>
        ) : null}

        {/* Footer controls */}
        <div className={cn("space-y-1 border-t border-border p-2", collapsed && "px-1")}>
          <button
            onClick={toggle}
            title={collapsed ? nextThemeLabel : undefined}
            className={cn(
              "flex w-full cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-sm",
              "text-muted-foreground transition-colors duration-200 hover:bg-surface/60 hover:text-foreground",
              collapsed && "justify-center px-0",
            )}
          >
            <ThemeIcon className="h-4 w-4 shrink-0" aria-hidden="true" />
            {!collapsed ? <span>{nextThemeLabel}</span> : null}
          </button>

          <button
            onClick={onToggleCollapse}
            title={collapsed ? "Expand sidebar" : undefined}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className={cn(
              "flex w-full cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-sm",
              "text-muted-foreground transition-colors duration-200 hover:bg-surface/60 hover:text-foreground",
              collapsed && "justify-center px-0",
            )}
          >
            {collapsed ? (
              <ChevronRight className="h-4 w-4 shrink-0" aria-hidden="true" />
            ) : (
              <>
                <ChevronLeft className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span>Collapse</span>
              </>
            )}
          </button>
        </div>
      </aside>
    </>
  );
}
