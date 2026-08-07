"use client";

/**
 * A live mock-up of the paper a template will produce, rendered from the
 * exact same state the editor form (`template-editor-panel.tsx`) edits — no
 * fetch, no debounce, so every keystroke and slot edit recomputes it for
 * free as a pure render.
 *
 * This mirrors structure only: sections, question count, type and marks.
 * Question text does not exist until generation, so there is nothing honest
 * to preview there — placeholder question text would look like a real paper
 * and read as a lie.
 */

import * as React from "react";
import type { Blueprint, BlueprintSlot, QuestionTypeOption } from "@/lib/api-client";

interface Props {
  name: string;
  subject: string;
  academicClass: string;
  difficulty: string;
  instructions: string;
  slots: BlueprintSlot[];
  totals: Blueprint;
  questionTypes: QuestionTypeOption[];
}

function typeLabel(code: string, options: QuestionTypeOption[]): string {
  const match = options.find((o) => o.code === code);
  if (match) return match.label;
  return code
    .toLowerCase()
    .split("_")
    .filter(Boolean)
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(" ");
}

export function TemplatePreviewPaper({
  name,
  subject,
  academicClass,
  difficulty,
  instructions,
  slots,
  totals,
  questionTypes,
}: Props) {
  // Preserve section order as it appears, mirroring SlotEditor's own grouping
  // — Section E must not sort above Section A.
  const sections = React.useMemo(() => {
    const order: string[] = [];
    const grouped = new Map<string, BlueprintSlot[]>();
    slots.forEach((slot) => {
      if (!grouped.has(slot.sectionTitle)) {
        grouped.set(slot.sectionTitle, []);
        order.push(slot.sectionTitle);
      }
      grouped.get(slot.sectionTitle)!.push(slot);
    });
    return order.map((title) => ({ title, slots: grouped.get(title)! }));
  }, [slots]);

  const isStructured = slots.length > 0;

  return (
    <div className="flex w-full max-w-lg flex-col items-center gap-3">
      <div className="flex aspect-[210/297] w-full flex-col overflow-hidden rounded-sm bg-white text-neutral-900 shadow-2xl ring-1 ring-black/10">
        <div className="flex flex-1 flex-col overflow-y-auto px-6 py-6 font-serif">
          <div className="mb-4 space-y-1 border-b border-neutral-300 pb-3 text-center">
            <p className="text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
              {academicClass ? `Class ${academicClass}` : "Class —"}
              {" · "}
              {subject || "Subject"}
            </p>
            <h3 className="text-base font-bold leading-tight text-neutral-900">
              {name.trim() || "Untitled template"}
            </h3>
            <div className="flex items-center justify-center gap-3 text-[10px] text-neutral-500">
              <span>Max Marks: {totals.totalMarks || "—"}</span>
              <span aria-hidden="true">·</span>
              <span className="capitalize">{difficulty}</span>
            </div>
          </div>

          {instructions.trim() ? (
            <div className="mb-4 rounded border border-dashed border-neutral-300 bg-neutral-50 px-3 py-2">
              <p className="text-[9px] font-semibold uppercase tracking-wide text-neutral-500">
                General Instructions
              </p>
              <p className="mt-0.5 line-clamp-3 text-[10px] leading-relaxed text-neutral-600">
                {instructions}
              </p>
            </div>
          ) : null}

          {isStructured ? (
            <div className="space-y-4">
              {sections.map(({ title, slots: sectionSlots }) => {
                const marks = sectionSlots.reduce((sum, s) => sum + s.marks, 0);
                return (
                  <div key={title}>
                    <div className="mb-1 flex items-baseline justify-between border-b border-neutral-200 pb-0.5">
                      <span className="text-[11px] font-bold text-neutral-800">
                        {title}
                      </span>
                      <span className="text-[9px] text-neutral-500">
                        {sectionSlots.length} q · {marks} mk
                      </span>
                    </div>
                    <div className="space-y-1">
                      {sectionSlots.map((slot) => (
                        <div
                          key={slot.index}
                          className="flex items-baseline justify-between gap-2 text-[10px] text-neutral-700"
                        >
                          <span className="flex-1 truncate">
                            {slot.index}. {typeLabel(slot.questionType, questionTypes)}
                            {slot.choiceRequired ? "  (OR)" : ""}
                          </span>
                          <span className="shrink-0 text-neutral-400">
                            [{slot.marks}]
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center gap-2 px-2 py-10 text-center">
              {[0, 1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="h-1.5 w-full rounded-full bg-neutral-100"
                  style={{ opacity: 1 - i * 0.18 }}
                />
              ))}
              <p className="mt-3 max-w-[85%] text-[10px] leading-relaxed text-neutral-400">
                {instructions.trim()
                  ? "No fixed structure — this paper is rebuilt from the instructions above each time it's used."
                  : "Add question slots, or write instructions, to preview this template's paper."}
              </p>
            </div>
          )}
        </div>
      </div>

      <p className="text-xs text-muted-foreground">
        Live preview · {totals.totalQuestions} question
        {totals.totalQuestions === 1 ? "" : "s"} · {totals.totalMarks} marks
      </p>
    </div>
  );
}
