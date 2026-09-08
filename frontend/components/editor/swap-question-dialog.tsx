"use client";

/**
 * "Swap this question — and make it a different kind of question."
 *
 * The one-click Swap on the hover menu answers "give me another one of these".
 * This answers the other complaint: the teacher likes the paper but wants
 * question 7 to stop being a 1-mark MCQ. Both go through the same endpoint —
 * the slot travels in the request rather than being looked up — so the only
 * thing this dialog really has to get right is what it lets a teacher pick.
 *
 * ## Why the marks are the headline, not a detail
 *
 * A question paper that does not add up to its stated total is not a paper. So
 * the types are split by whether they keep the total intact, and the running
 * total is stated in the footer at all times rather than being discovered
 * after the swap. Changing the total is allowed — a teacher restructuring a
 * section is doing something legitimate — but it is never allowed to happen
 * quietly.
 *
 * ## Why some types are missing
 *
 * The menu is served per generator. A slot the blueprint routed to the Reading
 * generator can only ever hold a Reading asset, so offering "Short Answer" on
 * it would offer a choice that fails after a spinner. See
 * `question_types_for`.
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";
import type { QuestionTypeOption } from "@/lib/api-client";

export interface SwapDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The types this slot's generator can write. Empty while loading. */
  options: QuestionTypeOption[];
  loadingOptions: boolean;
  /** The question being changed, so the teacher can confirm the target. */
  questionText: string;
  currentType: string;
  currentMarks: number;
  /** What the paper adds up to right now, OR branches counted once. */
  paperTotal: number;
  /** True when this question is one branch of an OR choice. */
  isOrBranch: boolean;
  swapping: boolean;
  onSwap: (overrides: { type: string; marks: number }) => void;
}

/** Catalog order, but grouped — a flat list of twenty types does not scan. */
function byGroup(options: QuestionTypeOption[]) {
  const groups: Array<{ name: string; options: QuestionTypeOption[] }> = [];
  for (const option of options) {
    const existing = groups.find((g) => g.name === option.group);
    if (existing) existing.options.push(option);
    else groups.push({ name: option.group, options: [option] });
  }
  return groups;
}

export function SwapQuestionDialog({
  open,
  onOpenChange,
  options,
  loadingOptions,
  questionText,
  currentType,
  currentMarks,
  paperTotal,
  isOrBranch,
  swapping,
  onSwap,
}: SwapDialogProps) {
  const [type, setType] = React.useState(currentType);
  const [marks, setMarks] = React.useState(currentMarks);

  // Reset to the question's own type and marks each time the dialog opens.
  // A remembered choice would quietly apply the previous question's answer to
  // this one — the same reasoning as the image style picker.
  React.useEffect(() => {
    if (open) {
      setType(currentType);
      setMarks(currentMarks);
    }
  }, [open, currentType, currentMarks]);

  const pickType = (option: QuestionTypeOption) => {
    setType(option.code);
    // Move the marks to the type's usual weight, because that is what the
    // teacher almost always means. They can still overrule it below — which is
    // why this is a default and not a lock.
    setMarks(option.code === currentType ? currentMarks : option.defaultMarks);
  };

  const delta = marks - currentMarks;
  const newTotal = paperTotal + delta;
  const changed = type !== currentType || marks !== currentMarks;

  return (
    <Dialog open={open} onOpenChange={swapping ? () => {} : onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Change this question&rsquo;s type</DialogTitle>
          <DialogDescription>
            We will write a new question of the kind you pick, in this same
            position on the paper.
          </DialogDescription>
        </DialogHeader>

        {questionText.trim() ? (
          <p className="line-clamp-2 rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs italic text-muted-foreground">
            &ldquo;{questionText.trim().replace(/\s+/g, " ")}&rdquo;
          </p>
        ) : null}

        {loadingOptions ? (
          <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
            <Spinner className="size-4" />
            Loading the types this section can use&hellip;
          </div>
        ) : options.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            This section&rsquo;s questions can only be written as one kind, so
            there is nothing to change. Use Swap to get a different question.
          </p>
        ) : (
          <div className="max-h-[46vh] space-y-3 overflow-y-auto pr-1">
            {byGroup(options).map((group) => (
              <div key={group.name}>
                <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  {group.name}
                </p>
                <div className="grid gap-1.5 sm:grid-cols-2">
                  {group.options.map((option) => {
                    const active = type === option.code;
                    const keepsTotal = option.defaultMarks === currentMarks;
                    return (
                      <button
                        key={option.code}
                        type="button"
                        disabled={swapping}
                        onClick={() => pickType(option)}
                        className={cn(
                          "flex items-center justify-between gap-2 rounded-lg border px-3 py-2 text-left transition-colors",
                          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                          "disabled:cursor-not-allowed disabled:opacity-60",
                          active
                            ? "border-primary bg-primary/5 ring-1 ring-primary"
                            : "border-border hover:border-primary/40 hover:bg-muted/40",
                        )}
                      >
                        <span className="text-sm">
                          {option.label}
                          {option.code === currentType ? (
                            <span className="ml-1.5 text-[10px] text-muted-foreground">
                              current
                            </span>
                          ) : null}
                        </span>
                        <span
                          className={cn(
                            "shrink-0 text-[11px] tabular-nums",
                            keepsTotal
                              ? "text-muted-foreground"
                              : "font-medium text-amber-600 dark:text-amber-500",
                          )}
                        >
                          {option.defaultMarks}m
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}

        {options.length > 0 ? (
          <div className="flex items-end justify-between gap-4 rounded-lg border border-border bg-muted/30 px-3 py-2.5">
            <div className="space-y-1">
              <Label htmlFor="swap-marks" className="text-[11px]">
                Marks
              </Label>
              <Input
                id="swap-marks"
                type="number"
                min={1}
                max={20}
                value={marks}
                disabled={swapping}
                onChange={(event) => {
                  const next = Number(event.target.value);
                  setMarks(Number.isFinite(next) && next > 0 ? next : 1);
                }}
                className="h-8 w-20 tabular-nums"
              />
            </div>
            <p className="pb-1 text-right text-[11px] leading-snug">
              <span className="text-muted-foreground">Paper total </span>
              <span className="tabular-nums">{paperTotal}</span>
              {delta !== 0 ? (
                <>
                  <span className="text-muted-foreground"> &rarr; </span>
                  <span className="font-semibold tabular-nums text-amber-600 dark:text-amber-500">
                    {newTotal}
                  </span>
                </>
              ) : (
                <span className="text-muted-foreground"> &mdash; unchanged</span>
              )}
            </p>
          </div>
        ) : null}

        {isOrBranch && changed ? (
          <p className="text-[11px] leading-snug text-muted-foreground">
            This question is one branch of an <strong>OR</strong> choice. Both
            branches will be rewritten, because a student choosing between them
            has to be choosing between two questions of the same kind.
          </p>
        ) : null}

        <DialogFooter className="sm:justify-end">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={swapping}
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <Button
            type="button"
            size="sm"
            disabled={swapping || !changed || options.length === 0}
            onClick={() => onSwap({ type, marks })}
          >
            {swapping ? (
              <>
                <Spinner className="size-3.5" />
                Writing&hellip;
              </>
            ) : (
              "Swap"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
