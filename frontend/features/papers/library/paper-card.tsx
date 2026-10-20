"use client";

import { useEffect, useRef, useState } from "react";
import { Key, Layers, MoreHorizontal, Pencil, FileDown, Trash2 } from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

import { formatRelative } from "./format";
import { usePaperPreview } from "./use-paper-preview";

export interface PaperCardData {
  id: string;
  title: string;
  subjectLabel: string;
  classLabel: string;
  boardLabel: string;
  created_at?: string;
  updated_at?: string;
  answerScriptId?: string | null;
  sets?: unknown[];
}

interface PaperCardProps {
  paper: PaperCardData;
  deleting?: boolean;
  onOpen: () => void;
  onEdit: () => void;
  onExport: (format: "pdf" | "docx") => void;
  onDelete: () => void;
}

const dash = (v: string) => (v === "—" ? "" : v);

/**
 * One paper in the library.
 *
 * The top band previews the paper's first questions as plain text rather than
 * a rendered thumbnail: a TipTap document per card would cost a full editor
 * instance each. The text comes from `usePaperPreview`, loaded lazily.
 *
 * The whole card opens the detail view through an overlay button; the menu
 * sits above it (`z-10`) so it never triggers an open.
 */
export function PaperCard({
  paper,
  deleting,
  onOpen,
  onEdit,
  onExport,
  onDelete,
}: PaperCardProps) {
  const subject = dash(paper.subjectLabel);
  const cls = dash(paper.classLabel);
  const board = dash(paper.boardLabel);
  const setCount = paper.sets?.length ?? 0;

  // Fetch the preview only once the card is near the viewport.
  const ref = useRef<HTMLElement>(null);
  const [near, setNear] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || near) return;
    if (typeof IntersectionObserver === "undefined") {
      setNear(true);
      return;
    }
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setNear(true);
          io.disconnect();
        }
      },
      { rootMargin: "200px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [near]);
  const preview = usePaperPreview(paper.id, paper.updated_at, near);

  return (
    <article
      ref={ref}
      className={cn(
        "group relative flex flex-col overflow-hidden rounded-2xl border border-border bg-card",
        "transition-[border-color,box-shadow,transform] duration-200 ease-[var(--ease)]",
        "hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md hover:shadow-primary/5",
        "focus-within:border-primary/50 motion-reduce:transition-none motion-reduce:hover:translate-y-0",
        deleting && "pointer-events-none opacity-40",
      )}
    >
      {/* A miniature of the paper itself: its first questions, set in the
          paper's own serif, fading out at the bottom edge like a page that
          carries on. While the text loads (or if there is none to show) it
          falls back to a plain sheet of ruled lines. */}
      <div
        aria-hidden
        className="relative h-44 overflow-hidden border-b border-border/60 bg-brand-sand/70"
      >
        <div className="absolute inset-x-5 top-10 bottom-0 overflow-hidden rounded-t-lg bg-card px-4 pt-3.5 shadow-sm ring-1 ring-foreground/5 transition-transform duration-300 ease-[var(--ease)] group-hover:-translate-y-1 motion-reduce:transition-none">
          {preview.status === "ready" && preview.questions.length > 0 ? (
            <div className="space-y-2 font-serif">
              {preview.questions.map((q) => (
                <p
                  key={q.number}
                  className="line-clamp-2 text-[11px] leading-[1.4] text-foreground/80"
                >
                  <span className="mr-1 font-semibold text-foreground">
                    {q.number}.
                  </span>
                  {q.text}
                </p>
              ))}
            </div>
          ) : (
            <div
              className={cn(
                "space-y-1.5",
                preview.status === "loading" && "animate-pulse",
              )}
            >
              <div className="h-1.5 w-2/3 rounded-full bg-primary/25" />
              <div className="h-1 w-full rounded-full bg-muted" />
              <div className="h-1 w-5/6 rounded-full bg-muted" />
              <div className="h-1 w-full rounded-full bg-muted" />
              <div className="h-1 w-3/5 rounded-full bg-muted" />
              <div className="h-1 w-full rounded-full bg-muted" />
              <div className="h-1 w-4/5 rounded-full bg-muted" />
            </div>
          )}
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-10 bg-gradient-to-t from-card to-transparent" />
        </div>
        {cls && (
          <span className="absolute right-3 top-3 rounded-full bg-card/90 px-2.5 py-0.5 text-[11px] font-medium text-foreground ring-1 ring-foreground/10 backdrop-blur-sm">
            {/^class\b/i.test(cls) ? cls : `Class ${cls}`}
          </span>
        )}
      </div>

      <div className="flex flex-1 flex-col gap-3 p-4">
        <div className="min-w-0 pr-8">
          <h3 className="font-heading text-[15px] font-medium leading-snug tracking-[-0.01em] text-foreground">
            <button
              type="button"
              onClick={onOpen}
              className="line-clamp-2 break-words text-left outline-none"
            >
              {paper.title || "Untitled paper"}
            </button>
          </h3>
          <p className="mt-1 truncate text-xs text-muted-foreground">
            {[subject, board].filter(Boolean).join(" · ") || "No subject or board"}
          </p>
        </div>

        <div className="mt-auto flex items-center gap-3 text-[11px] text-muted-foreground">
          <span className="tabular-nums">
            {formatRelative(paper.updated_at ?? paper.created_at)}
          </span>
          {setCount > 1 && (
            <span className="inline-flex items-center gap-1">
              <Layers className="h-3 w-3" aria-hidden /> {setCount} sets
            </span>
          )}
          {paper.answerScriptId && (
            <span className="inline-flex items-center gap-1 text-primary">
              <Key className="h-3 w-3" aria-hidden /> Answer key
            </span>
          )}
        </div>
      </div>

      {/* The whole card opens the paper. A real absolutely positioned button
          rather than a `::after` stretched from the title: Firefox does not
          deliver clicks to a button for a pseudo-element that spills outside
          the button's own box, so only the title text opened the card. The
          title button stays for keyboard and screen-reader users. */}
      <button
        type="button"
        tabIndex={-1}
        aria-hidden
        onClick={onOpen}
        className="absolute inset-0 rounded-2xl"
      />

      {/* Actions — above the overlay */}
      <div className="absolute right-2 bottom-2 z-10">
        <DropdownMenu>
          <DropdownMenuTrigger
            aria-label={`Actions for ${paper.title || "paper"}`}
            className="flex h-11 w-11 items-center justify-center rounded-lg text-muted-foreground outline-none transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/20 sm:h-8 sm:w-8"
          >
            <MoreHorizontal className="h-4 w-4" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" side="top" className="w-48">
            <DropdownMenuItem onClick={onEdit}>
              <Pencil /> Open in editor
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => onExport("pdf")}>
              <FileDown /> Export PDF
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => onExport("docx")}>
              <FileDown /> Export Word
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" onClick={onDelete}>
              <Trash2 /> Move to recycle bin
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </article>
  );
}
