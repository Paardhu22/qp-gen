"use client";

/**
 * "Add a picture" → what kind of figure is this, actually?
 *
 * The dialog opens on that question rather than on the style picker, because
 * the two answers want completely different controls. A question about data —
 * a pie chart, a bar graph, a histogram — is drawn exactly by the server from
 * numbers read out of the question, and the only thing worth a teacher's
 * attention is whether those numbers are right. A question about a beaker or
 * a ray diagram is drawn by an image model, and the only choice is how it
 * should look.
 *
 * Offering "line art / realistic / cartoon" for a bar graph was the old bug in
 * miniature: three adjectives that mean nothing for a chart, attached to a
 * model that could not count. Those styles now appear only when the figure is
 * genuinely an illustration.
 *
 * The style previews are inline SVG, not sample renders. A sample render would
 * be a network request per card on open, would need storing somewhere, and
 * would go stale the moment the prompt changed. These are cheap, offline, and
 * honest about being schematic.
 */

import * as React from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Spinner } from "@/components/ui/spinner";
import type {
  ChartSpec,
  QuestionImageStyle,
  QuestionImageStyleOption,
} from "@/lib/api-client";
import { ChartFigureEditor } from "./chart-figure-editor";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  styles: QuestionImageStyleOption[];
  /** The question the image is for, shown so the teacher can confirm the target. */
  questionText: string;
  generating: boolean;
  onGenerate: (style: QuestionImageStyle) => void;
  /** True while the backend is working out what kind of figure this is. */
  loadingSpec: boolean;
  /** Non-null when this question wants a chart rather than an illustration. */
  chartSpec: ChartSpec | null;
  onChartSpecChange: (spec: ChartSpec) => void;
  /** Insert the chart already drawn at this URL. */
  onInsertChart: (imageUrl: string) => void;
}

/** Schematic previews. Deliberately crude — they show a look, not a result. */
function StylePreview({ style }: { style: QuestionImageStyle }) {
  const common = { width: 64, height: 48, viewBox: "0 0 64 48" } as const;

  if (style === "realistic") {
    return (
      <svg {...common} aria-hidden="true">
        <defs>
          <linearGradient id="qi-real" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#93c5fd" />
            <stop offset="100%" stopColor="#1e3a5f" />
          </linearGradient>
        </defs>
        <rect width="64" height="48" rx="4" fill="url(#qi-real)" />
        <circle cx="22" cy="17" r="7" fill="#fde68a" />
        <path d="M0 36 L18 22 L32 33 L46 20 L64 34 L64 48 L0 48 Z" fill="#334155" />
        <path d="M0 41 L20 30 L38 40 L64 28 L64 48 L0 48 Z" fill="#0f172a" opacity="0.7" />
      </svg>
    );
  }

  if (style === "cartoon") {
    return (
      <svg {...common} aria-hidden="true">
        <rect width="64" height="48" rx="4" fill="#fef9c3" />
        <circle cx="32" cy="24" r="13" fill="#fbbf24" stroke="#78350f" strokeWidth="2" />
        <circle cx="27" cy="21" r="2" fill="#78350f" />
        <circle cx="37" cy="21" r="2" fill="#78350f" />
        <path
          d="M26 29 Q32 34 38 29"
          fill="none"
          stroke="#78350f"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </svg>
    );
  }

  return (
    <svg {...common} aria-hidden="true">
      <rect width="64" height="48" rx="4" fill="#ffffff" stroke="#e5e7eb" />
      <circle
        cx="26"
        cy="24"
        r="11"
        fill="none"
        stroke="#111827"
        strokeWidth="1.5"
      />
      <circle cx="26" cy="24" r="4" fill="none" stroke="#111827" strokeWidth="1.5" />
      <line x1="37" y1="24" x2="52" y2="14" stroke="#111827" strokeWidth="1" />
      <line x1="46" y1="14" x2="54" y2="14" stroke="#111827" strokeWidth="1" />
      <line x1="26" y1="35" x2="26" y2="42" stroke="#111827" strokeWidth="1" />
      <line x1="18" y1="42" x2="34" y2="42" stroke="#111827" strokeWidth="1" />
    </svg>
  );
}

export function FigureDialog({
  open,
  onOpenChange,
  styles,
  questionText,
  generating,
  onGenerate,
  loadingSpec,
  chartSpec,
  onChartSpecChange,
  onInsertChart,
}: Props) {
  const [selected, setSelected] = React.useState<QuestionImageStyle>("line_art");
  const [chartUrl, setChartUrl] = React.useState<string | null>(null);

  // Line art every time the dialog opens, not whatever was picked last. The
  // right style depends on the question, and a remembered choice quietly
  // applies the previous question's answer to this one.
  React.useEffect(() => {
    if (open) {
      setSelected("line_art");
      setChartUrl(null);
    }
  }, [open]);

  const preview = questionText.trim().replace(/\s+/g, " ");
  const isChart = Boolean(chartSpec);

  return (
    <Dialog open={open} onOpenChange={generating ? () => {} : onOpenChange}>
      <DialogContent className={isChart ? "sm:max-w-2xl" : "sm:max-w-lg"}>
        <DialogHeader>
          <DialogTitle>Add a figure to this question</DialogTitle>
          <DialogDescription>
            {isChart
              ? "Check the numbers we read from your question, then insert the chart."
              : "We will draw something that fits what the question is about."}
          </DialogDescription>
        </DialogHeader>

        {preview ? (
          <p className="line-clamp-2 rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs italic text-muted-foreground">
            “{preview}”
          </p>
        ) : null}

        {loadingSpec ? (
          <div className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground">
            <Spinner className="size-4" />
            Reading the question…
          </div>
        ) : chartSpec ? (
          <ChartFigureEditor
            spec={chartSpec}
            onSpecChange={onChartSpecChange}
            onPreviewChange={setChartUrl}
          />
        ) : (
          <div className="grid gap-2 sm:grid-cols-3">
            {styles.map((style) => {
              const active = selected === style.value;
              return (
                <button
                  key={style.value}
                  type="button"
                  disabled={generating}
                  onClick={() => setSelected(style.value)}
                  className={cn(
                    "flex flex-col items-center gap-2 rounded-xl border p-3 text-center transition-all",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                    "disabled:cursor-not-allowed disabled:opacity-60",
                    active
                      ? "border-primary bg-primary/5 ring-1 ring-primary"
                      : "border-border hover:border-primary/40 hover:bg-muted/40",
                  )}
                >
                  <StylePreview style={style.value} />
                  <span className="text-sm font-semibold">{style.label}</span>
                  <span className="text-[11px] leading-snug text-muted-foreground">
                    {style.description}
                  </span>
                </button>
              );
            })}
          </div>
        )}

        <DialogFooter className="sm:justify-between">
          <p className="hidden text-[11px] text-muted-foreground sm:block">
            {isChart
              ? "Drawn from these numbers exactly. Nothing is billed for redrawing."
              : "Takes up to a minute. Check the picture before using the paper."}
          </p>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={generating}
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            {isChart ? (
              <Button
                type="button"
                size="sm"
                // Disabled until a drawing exists: the button inserts the
                // chart that is on screen, so there is nothing to insert
                // while the current values are mid-redraw or unrenderable.
                disabled={!chartUrl}
                onClick={() => chartUrl && onInsertChart(chartUrl)}
              >
                Insert figure
              </Button>
            ) : (
              <Button
                type="button"
                size="sm"
                disabled={generating || loadingSpec || styles.length === 0}
                onClick={() => onGenerate(selected)}
              >
                {generating ? (
                  <>
                    <Spinner className="size-3.5" />
                    Drawing…
                  </>
                ) : (
                  <>Generate</>
                )}
              </Button>
            )}
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
