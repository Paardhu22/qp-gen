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
 * ungrouped list of 38 identical controls is not something a teacher can read.
 *
 * Each row stays one line. The type comes from the question type catalogue
 * through a picker that opens on the types this subject sets most in this
 * class, and a new row repeats the type and marks of the row before it. The two
 * slot attributes most slots never use — higher-order thinking and real-world
 * framing — sit behind one small menu rather than adding two controls to every
 * row.
 */

import * as React from "react";
import { Database, Plus, SlidersHorizontal, Trash2 } from "lucide-react";

import { QuestionTypePicker } from "@/components/question-type-picker";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { questionTypeInfo } from "@/lib/question-types";
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
  /** The class the paper is for. Drives suggestions and the class-fit note. */
  academicClass?: string;
  onChange: (slots: BlueprintSlot[]) => void;
}

/**
 * The next unused section heading: one letter past the highest already in use,
 * not one past whichever section happens to sit last. Sections carrying prose
 * headings (language papers) are ignored for lettering.
 */
function nextSectionTitle(titles: string[]): string {
  let highest = 0;
  for (const title of titles) {
    const match = /^Section\s+([A-Za-z])$/.exec(title.trim());
    if (match) {
      highest = Math.max(highest, match[1].toUpperCase().charCodeAt(0) - 64);
    }
  }
  if (highest === 0) return "Section A";
  // Past Z there is no next letter; number it rather than emit punctuation.
  return highest >= 26
    ? `Section ${highest + 1}`
    : `Section ${String.fromCharCode(65 + highest)}`;
}

/** Recompute indices so they always match position. */
function reindex(slots: BlueprintSlot[]): BlueprintSlot[] {
  return slots.map((slot, i) => ({ ...slot, index: i + 1 }));
}

/** The catalogue type a slot holds, whether it stores a code or only a shape. */
function slotTypeCode(slot: BlueprintSlot): string {
  return (
    slot.typeCode || questionTypeInfo(slot.questionType)?.code || slot.questionType
  );
}

/** A note when the type is usually set to other classes; null when it fits. */
function classFitNote(code: string, academicClass?: string): string | null {
  const classNum = Number.parseInt(String(academicClass ?? ""), 10);
  const info = questionTypeInfo(code);
  if (!info || !Number.isFinite(classNum)) return null;
  const [first, last] = info.classes;
  if (classNum < first) return `${info.label} is usually set from Class ${first}.`;
  if (classNum > last) return `${info.label} is usually set up to Class ${last}.`;
  return null;
}

function SourceToggle({
  value,
  onChange,
}: {
  value: SlotSource;
  onChange: (source: SlotSource) => void;
}) {
  return (
    <div className="inline-flex overflow-hidden rounded-lg border border-input">
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

/** Higher-order thinking and real-world framing, for the few slots that ask. */
function AttributesMenu({
  slot,
  onChange,
}: {
  slot: BlueprintSlot;
  onChange: (patch: Partial<BlueprintSlot>) => void;
}) {
  const active = Boolean(slot.hots || slot.competency);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label={`More options for question ${slot.index}`}
        title="Higher-order thinking, real-world framing"
        className={cn(
          "relative rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
          active && "text-primary",
        )}
      >
        <SlidersHorizontal className="size-3.5" />
        {active ? (
          <span
            aria-hidden
            className="absolute right-1 top-1 size-1.5 rounded-full bg-primary"
          />
        ) : null}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuCheckboxItem
          checked={Boolean(slot.hots)}
          onCheckedChange={(checked) => onChange({ hots: Boolean(checked) })}
        >
          Higher-order thinking
        </DropdownMenuCheckboxItem>
        <DropdownMenuCheckboxItem
          checked={Boolean(slot.competency)}
          onCheckedChange={(checked) => onChange({ competency: Boolean(checked) })}
        >
          Real-world framing
        </DropdownMenuCheckboxItem>
      </DropdownMenuContent>
    </DropdownMenu>
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

export function SlotEditor({
  slots,
  questionTypes,
  totals,
  academicClass,
  onChange,
}: Props) {
  const typeByCode = React.useMemo(
    () => new Map(questionTypes.map((o) => [o.code, o])),
    [questionTypes],
  );

  const update = (index: number, patch: Partial<BlueprintSlot>) => {
    onChange(
      slots.map((slot, i) => (i === index ? { ...slot, ...patch } : slot)),
    );
  };

  const defaultMarksOf = (slot: BlueprintSlot): number | undefined => {
    const code = slotTypeCode(slot);
    return typeByCode.get(code)?.defaultMarks ?? questionTypeInfo(code)?.marks;
  };

  const changeType = (index: number, option: QuestionTypeOption) => {
    // Marks follow the type unless the teacher has already overridden them —
    // switching MCQ → Long Answer and leaving it at 1 mark is a wrong paper,
    // but silently resetting a deliberate 4 is worse. "Already overridden"
    // means the current marks differ from the outgoing type's default.
    const slot = slots[index];
    const outgoingDefault = defaultMarksOf(slot);
    const untouched =
      outgoingDefault !== undefined && slot.marks === outgoingDefault;
    update(index, {
      questionType: option.shape,
      typeCode: option.code,
      ...(untouched ? { marks: option.defaultMarks } : {}),
    });
  };

  const removeSlot = (index: number) => {
    onChange(reindex(slots.filter((_, i) => i !== index)));
  };

  const addSlot = (sectionTitle: string) => {
    // Insert at the end of its own section rather than the end of the paper,
    // or "add a question to Section A" drops it after Section E. A section that
    // does not exist yet has no "end" to sit at: reduce() reports -1 for that,
    // and splicing at 0 would file a brand-new Section C above Section A.
    const lastOfSection = slots.reduce(
      (found, slot, i) => (slot.sectionTitle === sectionTitle ? i : found),
      -1,
    );
    // A new question repeats the one before it — a teacher adding to a run of
    // long answers wants another long answer, not an MCQ to change back. That
    // is the last question of its section, or of the paper for a new section.
    // Higher-order and real-world framing are choices about one question, so
    // they are not carried over.
    const previous =
      lastOfSection === -1 ? slots[slots.length - 1] : slots[lastOfSection];
    // Only a paper with no questions yet starts from a type this subject and
    // class are usually set.
    const fallback =
      questionTypes.find((o) => o.common) ??
      questionTypes.find((o) => o.availability === "available");
    const next: BlueprintSlot = previous
      ? {
          index: slots.length + 1,
          sectionTitle,
          questionType: previous.questionType,
          typeCode: previous.typeCode,
          marks: previous.marks,
          source: previous.source,
          choiceRequired: false,
        }
      : {
          index: slots.length + 1,
          sectionTitle,
          questionType: fallback?.shape ?? "SHORT_ANSWER",
          typeCode: fallback?.code,
          marks: fallback?.defaultMarks ?? 2,
          source: "generate",
          choiceRequired: false,
        };
    const copy = [...slots];
    copy.splice(lastOfSection === -1 ? copy.length : lastOfSection + 1, 0, next);
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
              {entries.map(({ slot, index }, position) => {
                const code = slotTypeCode(slot);
                const note = classFitNote(code, academicClass);
                return (
                  <div
                    key={`${title}-${index}`}
                    className={cn(
                      "flex flex-wrap items-center gap-x-2 gap-y-1.5 px-3 py-2 sm:flex-nowrap",
                      position % 2 === 1 && "bg-muted/30",
                    )}
                  >
                    <span className="w-6 shrink-0 text-xs font-medium tabular-nums text-muted-foreground">
                      {slot.index}
                    </span>

                    <div className="flex min-w-0 flex-1 basis-40 items-center gap-1.5">
                      <QuestionTypePicker
                        value={code}
                        options={questionTypes}
                        onChange={(option) => changeType(index, option)}
                        aria-label={`Type of question ${slot.index}`}
                      />
                      {/* The dot's room is kept on every row, so the type
                          column lines up whether or not a row has a note. */}
                      <span
                        role={note ? "img" : undefined}
                        aria-label={note ?? undefined}
                        aria-hidden={note ? undefined : true}
                        title={note ?? undefined}
                        className={cn(
                          "size-1.5 shrink-0 rounded-full",
                          note ? "bg-warning" : "invisible",
                        )}
                      />
                    </div>

                    <div className="flex shrink-0 items-center gap-1">
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

                    {/* On a phone these wrap onto a second line, lined up
                        under the type rather than under the number. */}
                    <div className="flex shrink-0 items-center gap-2 max-sm:ml-8">
                      <SourceToggle
                        value={slot.source}
                        onChange={(source) => update(index, { source })}
                      />

                      <AttributesMenu
                        slot={slot}
                        onChange={(patch) => update(index, patch)}
                      />

                      <button
                        type="button"
                        aria-label={`Remove question ${slot.index}`}
                        onClick={() => removeSlot(index)}
                        className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
                      >
                        <Trash2 className="size-3.5" />
                      </button>
                    </div>
                  </div>
                );
              })}
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

      {sections.length > 0 && (
        <div className="pt-2">
          <Button
            type="button"
            variant="outline"
            className="w-full h-9 border-dashed text-xs text-muted-foreground"
            onClick={() => addSlot(nextSectionTitle(sections.map((s) => s.title)))}
          >
            <Plus className="size-3.5 mr-1.5" />
            Add a section
          </Button>
        </div>
      )}
    </div>
  );
}
