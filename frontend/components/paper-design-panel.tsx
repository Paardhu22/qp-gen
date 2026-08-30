"use client";

/**
 * "Here is the paper your instructions describe."
 *
 * General Instructions Mode lets a teacher type whatever they want, which
 * means what they type is routinely incomplete — no difficulty, no set count,
 * sometimes no subject. The old behaviour was to quietly default all of it and
 * find out three minutes later, from the finished paper, what had been assumed.
 *
 * So this shows the structure BEFORE generation, and splits what is missing in
 * two:
 *
 *   assumed   filled with a stated default, rendered as a chip the teacher can
 *             change. Never blocks. Forgetting to set difficulty is not a
 *             reason to stop someone generating a paper.
 *   required  genuinely un-inferable — subject, class, and something to write
 *             questions FROM. Rendered as a question with tap-able answers,
 *             and generation waits.
 *
 * Rendered identically in the editor sidebar and the dashboard, because the
 * teacher's question ("what am I about to get?") is identical in both.
 */

import type { DesignGap, PaperDesign } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { AlertTriangle, Check } from "lucide-react";
import { Spinner } from "@/components/ui/spinner";

const TYPE_LABELS: Record<string, string> = {
  MCQ: "MCQ",
  ASSERTION_REASON: "Assertion–Reason",
  SHORT_ANSWER: "Short answer",
  LONG_ANSWER: "Long answer",
  CASE_STUDY: "Case study",
  FILL_BLANK: "Fill in the blank",
  TRUE_FALSE: "True / false",
  MATCH_FOLLOWING: "Match the following",
  DIAGRAM: "Figure-based",
};

function typeLabel(raw: string): string {
  return TYPE_LABELS[raw] ?? raw.replace(/_/g, " ").toLowerCase();
}

export interface PaperDesignPanelProps {
  design: PaperDesign | null;
  gaps: DesignGap[];
  loading?: boolean;
  /** Answer a gap. `field` is a generator-form field name. */
  onResolve: (field: string, value: string) => void;
  /** Rendered under the required gaps — e.g. the editor's source picker. */
  sourceAction?: React.ReactNode;
  className?: string;
}

export function PaperDesignPanel({
  design,
  gaps,
  loading = false,
  onResolve,
  sourceAction,
  className,
}: PaperDesignPanelProps) {
  const assumed = gaps.filter((g) => g.kind === "assumed");
  const required = gaps.filter((g) => g.kind === "required");

  if (loading && !design) {
    return (
      <div
        className={cn(
          "flex items-center gap-2 rounded-lg border border-border bg-muted/30 p-3 text-xs text-muted-foreground",
          className,
        )}
      >
        <Spinner className="size-3.5" />
        Working out the paper…
      </div>
    );
  }

  if (!design || design.sections.length === 0) return null;

  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-muted/20 text-sm",
        loading && "opacity-60 transition-opacity",
        className,
      )}
    >
      {/* Totals first: the one thing a teacher checks at a glance. */}
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-border px-3 py-2">
        <span className="font-medium text-foreground">
          {design.title || "Your paper"}
        </span>
        <span className="text-xs tabular-nums text-muted-foreground">
          {design.totalQuestions} question{design.totalQuestions === 1 ? "" : "s"} ·{" "}
          {design.totalMarks} mark{design.totalMarks === 1 ? "" : "s"}
          {design.duration ? ` · ${design.duration}` : ""}
        </span>
      </div>

      <div className="space-y-2.5 px-3 py-2.5">
        {design.sections.map((section, index) => (
          <div key={`${section.title}-${index}`}>
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-[13px] font-medium text-foreground">
                {section.title}
              </span>
              <span className="text-[11px] tabular-nums text-muted-foreground">
                {section.totalMarks}m
              </span>
            </div>
            <ul className="mt-0.5 space-y-0.5">
              {section.groups.map((group, groupIndex) => (
                <li
                  key={groupIndex}
                  className="flex items-baseline justify-between gap-2 text-[12px] text-muted-foreground"
                >
                  <span className="min-w-0 truncate">
                    {group.count} × {typeLabel(group.type)}
                    {group.topic ? ` — ${group.topic}` : ""}
                    {group.choice ? " (with choice)" : ""}
                  </span>
                  <span className="shrink-0 tabular-nums">
                    {group.marks}m each
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      {/* Corrections. A paper that quietly came out 3 marks short is worse
          than one that says it did. */}
      {design.corrections.length > 0 && (
        <div className="flex gap-2 border-t border-border px-3 py-2">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
          <ul className="space-y-0.5 text-[11.5px] text-muted-foreground">
            {design.corrections.map((correction, index) => (
              <li key={index}>{correction}</li>
            ))}
          </ul>
        </div>
      )}

      {assumed.length > 0 && (
        <div className="border-t border-border px-3 py-2">
          <p className="mb-1.5 text-[10.5px] font-medium uppercase tracking-wide text-muted-foreground">
            Assumed
          </p>
          <div className="flex flex-wrap gap-1.5">
            {assumed.map((gap) => (
              <AssumedChip key={gap.field} gap={gap} onResolve={onResolve} />
            ))}
          </div>
        </div>
      )}

      {required.length > 0 && (
        <div className="space-y-2.5 border-t border-border px-3 py-2.5">
          <p className="text-[10.5px] font-medium uppercase tracking-wide text-muted-foreground">
            Needs you
          </p>
          {required.map((gap) => (
            <div key={gap.field}>
              <p className="text-[12.5px] text-foreground">{gap.label}</p>
              {gap.note && (
                <p className="mt-0.5 text-[11px] text-muted-foreground">
                  {gap.note}
                </p>
              )}
              {gap.options.length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {gap.options.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => onResolve(gap.field, option.value)}
                      className="rounded-full border border-border px-3 py-1 text-[11.5px] text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              )}
              {gap.field === "sources" && sourceAction}
            </div>
          ))}
        </div>
      )}

      {required.length === 0 && (
        <div className="flex items-center gap-1.5 border-t border-border px-3 py-2 text-[11.5px] text-muted-foreground">
          <Check className="h-3.5 w-3.5 text-success" />
          Ready to generate.
        </div>
      )}
    </div>
  );
}

/**
 * An assumption, shown as what it is. Clicking cycles to the next option —
 * a select for three values is more chrome than the decision deserves, and
 * the current value stays legible either way.
 */
function AssumedChip({
  gap,
  onResolve,
}: {
  gap: DesignGap;
  onResolve: (field: string, value: string) => void;
}) {
  const current =
    gap.options.find((option) => option.value === gap.value)?.label || gap.value;

  if (gap.options.length === 0) {
    return (
      <span className="rounded-full border border-dashed border-border px-3 py-1 text-[11.5px] text-muted-foreground">
        {gap.label}: {current}
      </span>
    );
  }

  const cycle = () => {
    const index = gap.options.findIndex((option) => option.value === gap.value);
    const next = gap.options[(index + 1) % gap.options.length];
    onResolve(gap.field, next.value);
  };

  return (
    <button
      type="button"
      onClick={cycle}
      title={`${gap.label} — click to change`}
      className="group rounded-full border border-dashed border-border px-3 py-1 text-[11.5px] text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
    >
      {current}
      <span className="ml-1 text-[10px] opacity-0 transition-opacity group-hover:opacity-70">
        change
      </span>
    </button>
  );
}
