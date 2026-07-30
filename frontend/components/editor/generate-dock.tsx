"use client";

/**
 * Paper Studio — generation, docked to the right of the document.
 *
 * ## Why it is on the right, and why it is a dock
 *
 * The left of an editor belongs to the document (`document-outline.tsx`). The
 * right is where every word processor puts the thing that acts *on* the
 * document — Docs' Gemini panel, Word's Editor pane, Notion's AI sidebar. This
 * is that surface: the one place a paper is generated.
 *
 * It is a dock rather than a floating button because generation is not a
 * moment, it is a session. A run takes minutes and streams; a control that
 * opens a modal and vanishes leaves the teacher with no idea whether anything
 * is happening. Collapsed it is a 48px rail — a tab in the margin. Expanded it
 * is a panel that pushes the canvas over rather than covering it, so the page
 * stays visible while questions land in it.
 *
 * ## Two ways in, deliberately
 *
 * - **Say what you want.** One field. It hands the text to the Blueprint
 *   Builder's "Describe It Yourself" template, which is exactly what that
 *   template is for — the teacher lands on a resolved blueprint instead of an
 *   empty picker.
 * - **Open the builder.** The full three-step flow, for a teacher who wants to
 *   choose a board template and edit slots.
 *
 * Neither generates behind the teacher's back: both land in the Builder, which
 * is where the paper is confirmed. The dock's job is to make starting obvious
 * and progress legible, not to hide the decisions.
 */

import * as React from "react";
import { ArrowUp, PanelRightClose } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Open the Builder, optionally seeded with a plain-English brief. */
  onOpenBuilder: (instructions?: string) => void;
  generating: boolean;
  /** Live line from the pool pipeline ("Writing questions 12/40"). */
  status?: string;
  /** Questions inserted into the page so far this run. */
  insertedCount?: number;
  /** Uploads + library books currently attached to this paper. */
  sourceCount?: number;
  /**
   * The review tray, when a single-set run has questions waiting on a
   * decision. It belongs in this panel rather than in a corner of the screen:
   * it is the tail of the run that started here, and as a floating overlay it
   * used to land on top of this dock. The page forces the dock open while it
   * has something to show, so it cannot be reviewed-and-forgotten behind a
   * collapsed rail.
   */
  review?: React.ReactNode;
}

const EXAMPLES = [
  "Class 10 Science half-yearly, 80 marks",
  "Weekly test on photosynthesis, 20 marks",
  "Class 9 Maths, mostly application questions",
];

export function GenerateDock({
  open,
  onOpenChange,
  onOpenBuilder,
  generating,
  status,
  insertedCount = 0,
  sourceCount = 0,
  review,
}: Props) {
  const [brief, setBrief] = React.useState("");
  const fieldRef = React.useRef<HTMLTextAreaElement | null>(null);

  const submit = () => {
    const text = brief.trim();
    if (!text) return;
    onOpenBuilder(text);
  };

  // Enter sends, Shift+Enter breaks the line — the convention every prompt
  // field on the web now shares, and the field is one or two lines of prose.
  const onKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  // A phone has no room for a 320px panel beside a 794px page, so below `lg`
  // the rail is the whole feature: it goes straight to the Builder, which is
  // full-screen there anyway. Resolved at click time rather than with a
  // breakpoint hook, so it cannot disagree with the CSS that hides the panel.
  const enterStudio = () => {
    const roomForPanel =
      typeof window !== "undefined" &&
      window.matchMedia("(min-width: 1024px)").matches;
    if (roomForPanel) onOpenChange(true);
    else onOpenBuilder();
  };

  return (
    <>
      {/* ── The rail ──────────────────────────────────────────────────────
          Always present on small screens; on desktop it is what the panel
          collapses to. Both states are rendered and toggled in CSS so the
          component never has to know the viewport width to lay itself out. */}
      <div
        className={cn(
          "flex w-12 flex-shrink-0 flex-col items-center gap-3 border-l border-border bg-background py-3 print:hidden",
          open && "lg:hidden",
        )}
      >
        <button
          type="button"
          onClick={enterStudio}
          title="Open Paper Studio"
          aria-label="Open Paper Studio"
          className={cn(
            "relative flex h-9 w-9 items-center justify-center rounded-full",
            "bg-primary text-primary-foreground transition-transform",
            "hover:scale-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
          )}
        >
          <span className="text-xs font-bold leading-none">PS</span>
          {generating ? (
            <span className="absolute -right-0.5 -top-0.5 flex h-2.5 w-2.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500 ring-2 ring-background" />
            </span>
          ) : null}
        </button>

        {/* The rail reads as a labelled tab rather than a mystery icon. */}
        <button
          type="button"
          onClick={enterStudio}
          tabIndex={-1}
          aria-hidden="true"
          className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground transition-colors hover:text-foreground [writing-mode:vertical-rl]"
        >
          {generating ? "Generating" : "Generate paper"}
        </button>
      </div>

      {/* ── The panel ─────────────────────────────────────────────────── */}
      <aside
        className={cn(
          "hidden w-[320px] flex-shrink-0 flex-col border-l border-border bg-background print:hidden xl:w-[360px]",
          open && "lg:flex",
        )}
      >
        {/* Header */}
        <div className="flex h-11 flex-shrink-0 items-center gap-2 border-b border-border px-3">
          <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-foreground">
            Paper Studio
          </span>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            title="Hide Paper Studio"
            aria-label="Hide Paper Studio"
            className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <PanelRightClose className="h-[18px] w-[18px]" />
          </button>
        </div>

        <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto p-3">
          {/* ── While a run is in flight ──────────────────────────────────
              Generation goes genuinely silent for minutes at a time (a Model 1
              batch emits nothing until it finishes), so this reports the last
              thing that happened rather than pretending to a percentage. */}
          {generating ? (
            <div className="mb-3 rounded-lg border border-border bg-muted/40 p-3">
              <div className="flex items-center gap-2">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
                </span>
                <span className="text-[13px] font-medium text-foreground">
                  Writing your paper
                </span>
              </div>
              <p className="mt-1.5 text-[12px] leading-relaxed text-muted-foreground">
                {status || "Planning the blueprint…"}
              </p>
              {insertedCount > 0 ? (
                <p className="mt-1.5 text-[12px] tabular-nums text-muted-foreground">
                  {insertedCount} question{insertedCount === 1 ? "" : "s"} placed
                  on the page
                </p>
              ) : null}
              <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground/80">
                This takes a few minutes. You can keep editing while it runs.
              </p>
            </div>
          ) : null}

          {/* ── Say what you want ─────────────────────────────────────── */}
          <label
            htmlFor="paper-brief"
            className="block px-0.5 text-[13px] font-medium text-foreground"
          >
            Describe the paper
          </label>
          <p className="mt-0.5 px-0.5 text-[12px] leading-relaxed text-muted-foreground">
            Plain English is enough — class, subject, marks, what to emphasise.
          </p>

          <div className="mt-2 rounded-lg border border-input bg-background transition-colors focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/40">
            <textarea
              id="paper-brief"
              ref={fieldRef}
              value={brief}
              onChange={(event) => setBrief(event.target.value)}
              onKeyDown={onKeyDown}
              rows={3}
              placeholder="e.g. Class 10 Science mid-term, 80 marks, one set"
              className="w-full resize-none bg-transparent px-3 pt-2.5 text-[13px] leading-relaxed outline-none placeholder:text-muted-foreground/70"
            />
            <div className="flex items-center justify-between gap-2 px-2 pb-2">
              <span className="pl-1 text-[11px] text-muted-foreground">
                {sourceCount > 0
                  ? `${sourceCount} source${sourceCount === 1 ? "" : "s"} attached`
                  : "No sources attached"}
              </span>
              <button
                type="button"
                onClick={submit}
                disabled={!brief.trim()}
                title="Plan this paper"
                aria-label="Plan this paper"
                className={cn(
                  "flex h-7 w-7 items-center justify-center rounded-full transition-colors",
                  brief.trim()
                    ? "bg-primary text-primary-foreground hover:bg-primary/90"
                    : "bg-muted text-muted-foreground",
                )}
              >
                <ArrowUp className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Examples double as documentation: they show the shape of a brief
              that produces a good blueprint. */}
          <div className="mt-2 flex flex-wrap gap-1.5">
            {EXAMPLES.map((example) => (
              <button
                key={example}
                type="button"
                onClick={() => {
                  setBrief(example);
                  fieldRef.current?.focus();
                }}
                className="rounded-full border border-border px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:border-foreground/30 hover:bg-muted hover:text-foreground"
              >
                {example}
              </button>
            ))}
          </div>

          {/* ── Or configure it properly ──────────────────────────────── */}
          <div className="mt-5 border-t border-border pt-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenBuilder()}
              className="w-full justify-start gap-2 text-[13px]"
            >
              Open the paper builder
            </Button>
            <p className="mt-1.5 px-0.5 text-[12px] leading-relaxed text-muted-foreground">
              Pick a board template, attach chapters, and edit the paper section
              by section before anything is written.
            </p>
          </div>

          {/* Questions waiting on a decision, from the run that started here. */}
          {review}
        </div>
      </aside>
    </>
  );
}
