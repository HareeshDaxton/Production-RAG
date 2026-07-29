"use client";

import { Children, isValidElement, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";

// Two regexes on purpose: `split` needs the /g capture form, while `test` must be
// non-global — a /g regex keeps `lastIndex` between calls and would alternate results.
const CITATION_SPLIT_RE = /(\[\d+\])/g;
const CITATION_TEST_RE = /^\[\d+\]$/;

/** Tint inline [n] markers so sourced claims are visible at a glance. */
function highlightCitations(children: ReactNode): ReactNode {
  return Children.map(children, (child) => {
    if (typeof child === "string") {
      const parts = child.split(CITATION_SPLIT_RE);
      if (parts.length === 1) return child;
      return parts.map((part, i) =>
        CITATION_TEST_RE.test(part) ? (
          <span
            key={i}
            className="mx-0.5 rounded bg-accent/15 px-1 font-medium text-accent tabular-nums"
          >
            {part}
          </span>
        ) : (
          part
        ),
      );
    }
    if (isValidElement(child)) return child;
    return child;
  });
}

export function Markdown({ content, className }: { content: string; className?: string }) {
  return (
    <div className={cn("prose-answer", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p>{highlightCitations(children)}</p>,
          li: ({ children }) => <li>{highlightCitations(children)}</li>,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
