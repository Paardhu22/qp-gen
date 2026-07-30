"use client";

/**
 * Step 3 of the Blueprint Builder — the questions themselves.
 *
 * Two controls that look separate but write to the same place:
 *
 *   * the **source split** at the top, which is a bulk edit over every slot; and
 *   * each slot's own type / marks / source.
 *
 * Storing the split per slot rather than as a paper-level ratio is deliberate
 * (see backend `services/templates.py`): one representation cannot disagree
 * with itself. Dragging the slider to "12 from bank" just marks the first
 * twelve slots, and a teacher who then flips slot 3 back to Generated gets 11
 * — which is what they asked for, with nothing to reconcile.
 *
 * Slots are grouped by section for scanning. A CBSE paper is 38 rows, and an
 * ungrouped list of 38 identical selects is not something a teacher can read.
 */

import * as React from "react";
import { Plus, Trash2, Database } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type {
  Blueprint,
  BlueprintSlot,
  QuestionTypeOption,
  SlotSource,
} from "@/lib/api-client";

interface Props {
  slots: BlueprintSlot[];
  questionTypes: QuestionTypeOption[];
  totals: Pick<
    Blueprint,
    "totalQuestions" | "totalMarks" | "savedCount" | "generatedCount"
  >;
  onChange: (slots: BlueprintSlot[]) => void;
}

/** Recompute indices so they always match position. */
function reindex(slots: BlueprintSlot[]): BlueprintSlot[] {
  return slots.map((slot, i) => ({ ...slot, index: i + 1 }));
}

function TypeSelect({
  value,
  options,
  onChange,
}: {
  value: string;
  options: QuestionTypeOption[];
  onChange: (code: string) => void;
}) {
  // Grouped <optgroup> rather than a custom popover: 22 options in a native
  // select is scannable, keyboard-navigable and type-ahead searchable for free,
  // and on a phone it becomes the platform picker.
  const groups = React.useMemo(() => {
    const byGroup = new Map<string, QuestionTypeOption[]>();
    for (const option of options) {
      const list = byGroup.get(option.group) ?? [];
      list.push(option);
      byGroup.set(option.group, list);
    }
    return Array.from(byGroup.entries());
  }, [options]);

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="h-8 w-full rounded-md border border-input bg-transparent px-2 text-xs shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
    >
      {/* A type the server no longer offers must still render, or editing any
          other field on this slot would silently rewrite its type. */}
      {!options.some((o) => o.code === value) && value ? (
        <option value={value}>{value}</option>
      ) : null}
      {groups.map(([group, groupOptions]) => (
        <optgroup key={group} label={group}>
          {groupOptions.map((option) => (
            <option key={option.code} value={option.code}>
              {option.label}
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  );
}

function SourceToggle({
  value,
  onChange,
}: {
  value: SlotSource;
  onChange: (source: SlotSource) => void;
}) {
  return (
    <div className="inline-flex overflow-hidden rounded-md border border-input">
      {(
        [
          ["generate", "New", null],
          ["saved", "Bank", Database],
        ] as const
      ).map(([key, label, Icon]) => (
        <button
          key={key}
          type="button"
          onClick={() => onChange(key)}
          title={
            key === "generate"
              ? "Write a fresh question for this slot"
              : "Reuse a question from your saved bank"
          }
          className={cn(
            "flex items-center gap-1 px-2 py-1 text-[11px] font-medium transition-colors",
            value === key
              ? "bg-primary text-primary-foreground"
              : "bg-transparent text-muted-foreground hover:bg-muted",
          )}
        >
          {Icon && <Icon className="size-3" />}
          {label}
        </button>
      ))}
    </div>
  );
}

function SourceSplit({
  total,
  savedCount,
  onChange,
}: {
  total: number;
  savedCount: number;
  onChange: (saved: number) => void;
}) {
  const generated = total - savedCount;
  return (
    <div className="rounded-xl border border-border bg-muted/30 p-4">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h4 className="text-sm font-semibold">Where do questions come from?</h4>
          <p className="text-xs text-muted-foreground">
            Reusing saved questions is instant and free. New ones are written
            from your chapters.
          </p>
        </div>
        <div className="flex items-center gap-3 text-xs font-medium">
          <span className="flex items-center gap-1.5">
            <Database className="size-3.5 text-muted-foreground" />
            {savedCount} from bank
          </span>
          <span className="flex items-center gap-1.5">
            {generated} newly written
          </span>
        </div>
      </div>

      <input
        type="range"
        min={0}
        max={total}
        value={savedCount}
        disabled={total === 0}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-label="How many questions to take from your saved bank"
        className="w-full accent-[var(--primary)] disabled:opacity-40"
      />
      <div className="mt-1 flex justify-between text-[10px] uppercase tracking-wide text-muted-foreground">
        <span>All newly written</span>
        <span>All from bank</span>
      </div>
    </div>
  );
}

export function SlotEditor({ slots, questionTypes, totals, onChange }: Props) {
  const typeByCode = React.useMemo(
    () => new Map(questionTypes.map((o) => [o.code, o])),
    [questionTypes],
  );

  const update = (index: number, patch: Partial<BlueprintSlot>) => {
    onChange(
      slots.map((slot, i) => (i === index ? { ...slot, ...patch } : slot)),
    );
  };

  const changeType = (index: number, code: string) => {
    // Marks follow the type unless the teacher has already overridden them —
    // switching MCQ → Long Answer and leaving it at 1 mark is a wrong paper,
    // but silently resetting a deliberate 4 is worse. "Already overridden"
    // means the current marks differ from the outgoing type's default.
    const slot = slots[index];
    const outgoingDefault = typeByCode.get(slot.questionType)?.defaultMarks;
    const incomingDefault = typeByCode.get(code)?.defaultMarks;
    const untouched = outgoingDefault !== undefined && slot.marks === outgoingDefault;
    update(index, {
      questionType: code,
      ...(untouched && incomingDefault !== undefined
        ? { marks: incomingDefault }
        : {}),
    });
  };

  const removeSlot = (index: number) => {
    onChange(reindex(slots.filter((_, i) => i !== index)));
  };

  const addSlot = (sectionTitle: string) => {
    const fallback = questionTypes[0];
    const next: BlueprintSlot = {
      index: slots.length + 1,
      sectionTitle,
      questionType: fallback?.code ?? "SHORT_ANSWER",
      marks: fallback?.defaultMarks ?? 2,
      source: "generate",
      choiceRequired: false,
    };
    // Insert at the end of its own section rather than the end of the paper,
    // or "add a question to Section A" drops it after Section E.
    const lastOfSection = slots.reduce(
      (found, slot, i) => (slot.sectionTitle === sectionTitle ? i : found),
      -1,
    );
    const copy = [...slots];
    copy.splice(lastOfSection + 1, 0, next);
    onChange(reindex(copy));
  };

  const applySplit = (saved: number) => {
    onChange(
      slots.map((slot, i) => ({
        ...slot,
        source: i < saved ? "saved" : "generate",
      })),
    );
  };

  // Preserve section order as it appears, not alphabetically — Section E must
  // not sort above Section A, and language papers use prose headings.
  const sections = React.useMemo(() => {
    const order: string[] = [];
    const grouped = new Map<string, { slot: BlueprintSlot; index: number }[]>();
    slots.forEach((slot, index) => {
      if (!grouped.has(slot.sectionTitle)) {
        grouped.set(slot.sectionTitle, []);
        order.push(slot.sectionTitle);
      }
      grouped.get(slot.sectionTitle)!.push({ slot, index });
    });
    return order.map((title) => ({ title, entries: grouped.get(title)! }));
  }, [slots]);

  if (slots.length === 0) {
    return (
      <div className="space-y-4">
        <div className="rounded-xl border border-dashed border-border py-12 text-center">
          <p className="text-sm font-medium">No questions yet</p>
          <p className="mx-auto mt-1 max-w-sm text-xs text-muted-foreground">
            Add your first question below, or go back and pick a board paper to
            start from a ready-made structure.
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-4"
            onClick={() => addSlot("Section A")}
          >
            <Plus className="size-3.5" />
            Add a question
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <SourceSplit
        total={totals.totalQuestions}
        savedCount={totals.savedCount}
        onChange={applySplit}
      />

      {sections.map(({ title, entries }) => {
        const sectionMarks = entries.reduce((sum, e) => sum + e.slot.marks, 0);
        return (
          <section key={title} className="space-y-2">
            <div className="flex items-baseline justify-between gap-2">
              <h4 className="text-sm font-semibold">{title}</h4>
              <span className="text-xs text-muted-foreground">
                {entries.length} question{entries.length === 1 ? "" : "s"} ·{" "}
                {sectionMarks} marks
              </span>
            </div>

            <div className="overflow-hidden rounded-lg border border-border">
              {entries.map(({ slot, index }, position) => (
                <div
                  key={`${title}-${index}`}
                  className={cn(
                    "grid grid-cols-[2rem_1fr_4.5rem_auto_2rem] items-center gap-2 px-3 py-2",
                    position % 2 === 1 && "bg-muted/30",
                  )}
                >
                  <span className="text-xs font-medium tabular-nums text-muted-foreground">
                    {slot.index}
                  </span>

                  <TypeSelect
                    value={slot.questionType}
                    options={questionTypes}
                    onChange={(code) => changeType(index, code)}
                  />

                  <div className="flex items-center gap-1">
                    <Input
                      type="number"
                      min={1}
                      max={20}
                      value={slot.marks}
                      onChange={(e) =>
                        update(index, {
                          marks: Math.max(
                            1,
                            Math.min(20, Number(e.target.value) || 1),
                          ),
                        })
                      }
                      aria-label={`Marks for question ${slot.index}`}
                      className="h-8 w-12 px-1.5 text-center text-xs"
                    />
                    <span className="text-[10px] text-muted-foreground">mk</span>
                  </div>

                  <SourceToggle
                    value={slot.source}
                    onChange={(source) => update(index, { source })}
                  />

                  <button
                    type="button"
                    aria-label={`Remove question ${slot.index}`}
                    onClick={() => removeSlot(index)}
                    className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
              ))}
            </div>

            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 text-xs text-muted-foreground"
              onClick={() => addSlot(title)}
            >
              <Plus className="size-3" />
              Add to {title}
            </Button>
          </section>
        );
      })}
    </div>
  );
}
