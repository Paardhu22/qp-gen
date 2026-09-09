"use client";

/**
 * "Generate image" → which style?
 *
 * One question, three answers, and the answer is shown rather than described:
 * a teacher choosing between "line art" and "realistic" is choosing between
 * two pictures, so each card carries a small drawing of what it produces.
 * Three words of prose cannot do that job.
 *
 * The previews are inline SVG, not sample renders. A sample render would be a
 * network request per card on open, would need storing somewhere, and would go
 * stale the moment the prompt changed. These are cheap, offline, and honest
 * about being schematic.
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
  QuestionImageStyle,
  QuestionImageStyleOption,
} from "@/lib/api-client";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  styles: QuestionImageStyleOption[];
  /** The question the image is for, shown so the teacher can confirm the target. */
  questionText: string;
  generating: boolean;
  onGenerate: (style: QuestionImageStyle) => void;
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

export function ImageStyleDialog({
  open,
  onOpenChange,
  styles,
  questionText,
  generating,
  onGenerate,
}: Props) {
  const [selected, setSelected] = React.useState<QuestionImageStyle>("line_art");

  // Line art every time the dialog opens, not whatever was picked last. The
  // right style depends on the question, and a remembered choice quietly
  // applies the previous question's answer to this one.
  React.useEffect(() => {
    if (open) setSelected("line_art");
  }, [open]);

  const preview = questionText.trim().replace(/\s+/g, " ");

  return (
    <Dialog open={open} onOpenChange={generating ? () => {} : onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Add a picture to this question</DialogTitle>
          <DialogDescription>
            We will draw something that fits what the question is about.
          </DialogDescription>
        </DialogHeader>

        {preview ? (
          <p className="line-clamp-2 rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs italic text-muted-foreground">
            “{preview}”
          </p>
        ) : null}

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

        <DialogFooter className="sm:justify-between">
          <p className="hidden text-[11px] text-muted-foreground sm:block">
            Takes up to a minute. Check the picture before using the paper.
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
            <Button
              type="button"
              size="sm"
              disabled={generating || styles.length === 0}
              onClick={() => onGenerate(selected)}
            >
              {generating ? (
                <>
                  <Spinner className="size-3.5" />
                  Drawing…
                </>
              ) : (
                <>
                  Generate
                </>
              )}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
