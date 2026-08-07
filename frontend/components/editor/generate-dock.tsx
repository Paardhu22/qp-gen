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
import { ArrowUp, BookMarked, LayoutTemplate, PanelRightClose } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

/** "SHORT_ANSWER" → "Short Answer", "mcq" → "MCQ". A heuristic, not a lookup
 *  against the type menu — this line is a passing detail, not a place a
 *  wrong capitalization is worth a network round trip to get exactly right. */
function humanizeType(code: string): string {
  if (!code) return "";
  return code
    .toLowerCase()
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((w) => (w.length <= 3 ? w.toUpperCase() : w[0].toUpperCase() + w.slice(1)))
    .join(" ");
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Open the Builder, optionally seeded with a plain-English brief. */
  onOpenBuilder: (instructions?: string) => void;
  /** Assemble a paper from already-saved questions, skipping generation
   *  entirely. Optional so surfaces that have no bank access can omit it. */
  onBuildFromBank?: () => void;
  /** Open the manual template builder — the same section-by-section slot
   *  editor as the Templates page's New Template, without generating a
   *  paper. Optional so surfaces without template management can omit it. */
  onNewTemplate?: () => void;
  generating: boolean;
  /** Live line from the pool pipeline ("Writing questions 12/40"). */
  status?: string;
  /** Questions inserted into the page so far this run. */
  insertedCount?: number;
  /** The blueprint's slot count once the plan resolves; 0 while still unknown. */
  plannedTotal?: number;
  /** Questions streamed so far this run, counted the moment each arrives —
   *  advances during review-mode runs too, unlike `insertedCount`. */
  generatedCount?: number;
  /** The most recently streamed question, for a live "just written" line. */
  lastQuestion?: { section: string; type: string; marks: number } | null;
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
  onBuildFromBank,
  onNewTemplate,
  generating,
  status,
  insertedCount = 0,
  plannedTotal = 0,
  generatedCount = 0,
  lastQuestion = null,
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
          {generating
            ? plannedTotal > 0
              ? `${generatedCount} / ${plannedTotal}`
              : "Generating"
            : "Generate paper"}
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
              A count against the blueprint's own slot total once it is known
              (from the `plan` event — the one number in this stream that is
              an actual target, not an over-generated pool size), and an
              indeterminate sweep before that. Below it, the most recent
              question to land, so the panel reads as work happening rather
              than a spinner that might be stuck. */}
          {generating ? (
            <div className="mb-3 rounded-lg border border-border bg-muted/40 p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[13px] font-medium text-foreground">
                  Writing your paper
                </span>
                {plannedTotal > 0 ? (
                  <span className="text-[12px] tabular-nums text-muted-foreground">
                    {generatedCount} / {plannedTotal}
                  </span>
                ) : null}
              </div>

              {plannedTotal > 0 ? (
                <Progress
                  value={Math.min(generatedCount, plannedTotal)}
                  max={plannedTotal}
                  className="mt-2 [&_[data-slot=progress-track]]:h-1"
                />
              ) : (
                <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-muted">
                  <div className="h-full w-2/5 rounded-full bg-primary animate-[loading-bar_1.6s_ease-in-out_infinite]" />
                </div>
              )}

              <p className="mt-2 text-[12px] leading-relaxed text-muted-foreground">
                {status || "Planning the blueprint…"}
              </p>

              {lastQuestion ? (
                <p
                  key={generatedCount}
                  className="mt-1.5 truncate text-[12px] text-foreground/80 animate-in fade-in slide-in-from-bottom-1 duration-300"
                >
                  Just written — {lastQuestion.section}
                  {lastQuestion.type ? ` · ${humanizeType(lastQuestion.type)}` : ""}
                  {lastQuestion.marks ? ` · ${lastQuestion.marks} mk` : ""}
                </p>
              ) : insertedCount > 0 ? (
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
                className="rounded-full border border-border px-3 py-1 text-[11px] text-muted-foreground transition-colors hover:border-foreground/30 hover:bg-muted hover:text-foreground"
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

          {/* ── Or build a reusable template, not a paper ─────────────── */}
          {onNewTemplate ? (
            <div className="mt-4">
              <Button
                type="button"
                variant="ghost"
                onClick={onNewTemplate}
                className="w-full justify-start gap-2 text-[13px]"
              >
                <LayoutTemplate className="h-3.5 w-3.5" />
                New template
              </Button>
              <p className="mt-1.5 px-0.5 text-[12px] leading-relaxed text-muted-foreground">
                Define sections and question slots by hand, to reuse the next
                time you generate a paper — nothing is written now.
              </p>
            </div>
          ) : null}

          {/* ── Or don't write anything at all ────────────────────────── */}
          {onBuildFromBank ? (
            <div className="mt-4">
              <Button
                type="button"
                variant="ghost"
                onClick={onBuildFromBank}
                className="w-full justify-start gap-2 text-[13px]"
              >
                <BookMarked className="h-3.5 w-3.5" />
                Build from my question bank
              </Button>
              <p className="mt-1.5 px-0.5 text-[12px] leading-relaxed text-muted-foreground">
                Re-paper chapters you have already generated. Nothing new is
                written, so it costs nothing and finishes in seconds.
              </p>
            </div>
          ) : null}

          {/* Questions waiting on a decision, from the run that started here. */}
          {review}
        </div>
      </aside>
    </>
  );
}
