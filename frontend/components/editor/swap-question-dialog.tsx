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
 * the running total is stated in the footer at all times rather than being
 * discovered after the swap. Changing the total is allowed — a teacher
 * restructuring a section is doing something legitimate — but it is never
 * allowed to happen quietly.
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
  QuestionTypePicker,
  findTypeOption,
} from "@/components/question-type-picker";
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
import type { QuestionTypeOption } from "@/lib/api-client";

/** What a swap asks for: the new type as shape and catalogue code, and marks. */
export interface SwapChoice {
  type: string;
  typeCode: string;
  marks: number;
}

export interface SwapDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The types this slot's generator can write. Empty while loading. */
  options: QuestionTypeOption[];
  loadingOptions: boolean;
  /** The question being changed, so the teacher can confirm the target. */
  questionText: string;
  /** Its catalogue code, or its shape for a question from before the catalogue. */
  currentType: string;
  currentMarks: number;
  /** What the paper adds up to right now, OR branches counted once. */
  paperTotal: number;
  /** True when this question is one branch of an OR choice. */
  isOrBranch: boolean;
  swapping: boolean;
  onSwap: (choice: SwapChoice) => void;
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
  const current = React.useMemo(
    () => findTypeOption(options, currentType),
    [options, currentType],
  );
  const [choice, setChoice] = React.useState<QuestionTypeOption | undefined>(current);
  const [marks, setMarks] = React.useState(currentMarks);

  // Reset to the question's own type and marks each time the dialog opens.
  // A remembered choice would quietly apply the previous question's answer to
  // this one — the same reasoning as the image style picker.
  React.useEffect(() => {
    if (open) {
      setChoice(current);
      setMarks(currentMarks);
    }
  }, [open, current, currentMarks]);

  const pickType = (option: QuestionTypeOption) => {
    setChoice(option);
    // Move the marks to the type's usual weight, because that is what the
    // teacher almost always means. They can still overrule it below — which is
    // why this is a default and not a lock.
    setMarks(option.code === current?.code ? currentMarks : option.defaultMarks);
  };

  const delta = marks - currentMarks;
  const newTotal = paperTotal + delta;
  const changed =
    (choice?.code ?? "") !== (current?.code ?? "") || marks !== currentMarks;

  const swap = () =>
    onSwap(
      choice
        ? { type: choice.shape, typeCode: choice.code, marks }
        : { type: currentType, typeCode: "", marks },
    );

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
          <QuestionTypePicker
            variant="inline"
            value={choice?.code ?? currentType}
            options={options}
            onChange={pickType}
            disabled={swapping}
            aria-label="Question type"
          />
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
            onClick={swap}
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
