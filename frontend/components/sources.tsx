"use client";

import { useState } from "react";
import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  ChevronUp,
  FileText,
  HelpCircle,
} from "lucide-react";
import type { Citation, Verdict } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Monochrome carries the verdict two ways: a distinct icon shape, and a contrast
 * step (full -> dimmed -> faint). Never colour alone — which is also why each chip
 * exposes the verdict as an accessible label.
 */
const VERDICTS: Record<Verdict, { icon: typeof CheckCircle2; label: string; tone: string }> = {
  supported: { icon: CheckCircle2, label: "Supported by this source", tone: "text-foreground" },
  partial: { icon: AlertTriangle, label: "Partially supported", tone: "text-foreground/60" },
  unsupported: { icon: HelpCircle, label: "Not supported", tone: "text-foreground/35" },
};

/** "p.4" for paginated sources, else the structural locator or section. */
function locatorLabel(c: Citation): string | null {
  if (c.page !== null) return `p.${c.page}`;
  if (c.locator) return c.locator;
  return null;
}

/**
 * Where the answer actually came from. Rendered only when the response carries
 * citations — an answer with no grounded sources shows nothing rather than an
 * empty "0 sources" affordance.
 */
export function Sources({ citations }: { citations: Citation[] }) {
  const [open, setOpen] = useState(true);
  const [selected, setSelected] = useState<number | null>(null);

  if (citations.length === 0) return null;

  const active = citations.find((c) => c.number === selected) ?? null;

  return (
    <div className="space-y-2">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex cursor-pointer items-center gap-1.5 text-[12px] text-muted-foreground transition-colors duration-200 hover:text-foreground"
      >
        <BookOpen className="h-3.5 w-3.5" aria-hidden="true" />
        <span>
          {citations.length} source{citations.length === 1 ? "" : "s"}
        </span>
        <ChevronUp
          className={cn("h-3.5 w-3.5 transition-transform duration-200", !open && "rotate-180")}
          aria-hidden="true"
        />
      </button>

      {open ? (
        <>
          <div className="flex flex-wrap gap-1.5">
            {citations.map((c) => {
              const verdict = c.verdict ? VERDICTS[c.verdict] : null;
              const VerdictIcon = verdict?.icon;
              const locator = locatorLabel(c);
              const isSelected = selected === c.number;
              return (
                <button
                  key={c.number}
                  onClick={() => setSelected(isSelected ? null : c.number)}
                  aria-expanded={isSelected}
                  title={c.section ? `${c.source} — ${c.section}` : c.source}
                  className={cn(
                    "flex cursor-pointer items-center gap-1.5 rounded-lg border px-2 py-1",
                    "font-mono text-[11px] transition-colors duration-200",
                    isSelected
                      ? "border-accent/60 bg-accent/10 text-foreground"
                      : "border-border bg-surface text-foreground/80 hover:bg-surface-hover",
                  )}
                >
                  <FileText
                    className="h-3 w-3 shrink-0 text-muted-foreground"
                    aria-hidden="true"
                  />
                  <span className="max-w-[13rem] truncate">{c.source}</span>
                  {locator ? (
                    <span className="shrink-0 text-muted-foreground">{locator}</span>
                  ) : null}
                  {verdict && VerdictIcon ? (
                    <VerdictIcon
                      className={cn("h-3 w-3 shrink-0", verdict.tone)}
                      aria-label={verdict.label}
                    />
                  ) : null}
                </button>
              );
            })}
          </div>

          {active ? (
            <div className="space-y-1.5 rounded-lg border border-border bg-surface/60 px-3 py-2.5">
              <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground">
                <span className="font-mono text-foreground/80">{active.source}</span>
                {active.section ? <span>· {active.section}</span> : null}
                {active.page !== null ? <span>· page {active.page}</span> : null}
              </p>
              <p className="scrollbar-thin max-h-44 overflow-y-auto whitespace-pre-wrap text-[12px] leading-relaxed text-muted-foreground">
                {active.text}
              </p>
              {active.verdict_reason ? (
                <p
                  className={cn(
                    "border-t border-border pt-1.5 text-[11px] leading-relaxed",
                    active.verdict ? VERDICTS[active.verdict].tone : undefined,
                  )}
                >
                  {active.verdict_reason}
                </p>
              ) : null}
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
