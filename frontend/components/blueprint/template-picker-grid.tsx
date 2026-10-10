"use client";

/**
 * Step 1 of the Blueprint Builder — choose what to start from.
 *
 * This grid is where "QP Type" went. A teacher used to tick *board* or
 * *general instructions* before they could describe anything, and the two
 * behaved like different products. Now both are cards: "CBSE Class 10 Science
 * — Sample Paper 2025-26" sits beside "Describe It Yourself", and picking
 * either just fills the next step with a starting blueprint they can change.
 *
 * Saved templates come first when they exist. A teacher who made "My Midterm"
 * last week is far likelier to want it again than to browse thirty board
 * papers, and burying it under the catalog is how a saved template stops being
 * worth saving.
 *
 * The ready-made papers are browsed one class at a time. Every subject has at
 * least two for every class — a short test and a full exam, plus the CBSE
 * board card in Class 10 — so laid out on one page they ran to eighty cards.
 * The class and subject chosen on the previous step open the browser; the
 * tabs move it anywhere else.
 */

import * as React from "react";
import {
  ArrowRight,
  BookOpen,
  Check,
  ClipboardList,
  FilePlus2,
  MessageSquareText,
  Trash2,
} from "lucide-react";

import { SkeletonCards } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { BuiltinTemplate, PaperTemplate } from "@/lib/api-client";
import { PAPER_CLASSES, PAPER_SUBJECTS, paperSubjectEntry } from "@/lib/subject";

interface Props {
  builtin: BuiltinTemplate[];
  saved: PaperTemplate[];
  selectedId: string | null;
  /** `academicClass` is the class being browsed when a ready-made paper is
   *  picked: a Class 3–5 test chosen under the Class 3 tab is a Class 3 paper. */
  onSelect: (id: string, kind: string, options?: { academicClass?: string }) => void;
  onDelete?: (template: PaperTemplate) => void;
  loading?: boolean;
  /** The paper's class and subject, which open the browser. */
  academicClass?: string;
  subject?: string;
}

/** Every subject, in the picker's order. */
const ALL_SUBJECTS = "all";

function iconFor(kind: string) {
  if (kind === "instructions") return MessageSquareText;
  if (kind === "blank") return FilePlus2;
  if (kind === "starter") return ClipboardList;
  return BookOpen;
}

/** Whether a ready-made paper suits a class: a starter by its band, a board
 *  card by its one class. Universal templates fit none. */
export function fitsClass(template: BuiltinTemplate, classNum: number) {
  if (template.classRange) {
    return classNum >= template.classRange[0] && classNum <= template.classRange[1];
  }
  return template.academicClass === String(classNum);
}

function Card({
  title,
  description,
  icon: Icon,
  selected,
  badge,
  index = 0,
  onClick,
  onDelete,
}: {
  title: string;
  description: string;
  icon?: React.ElementType;
  selected: boolean;
  badge?: string;
  /** Position in its section — drives the entrance stagger. */
  index?: number;
  onClick: () => void;
  onDelete?: () => void;
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
      style={{ "--i": index } as React.CSSProperties}
      className={cn(
        "builder-card group relative flex min-h-36 cursor-pointer flex-col overflow-hidden border p-5 text-left",
        "transition-[transform,box-shadow,border-color,background-color] duration-300 ease-[var(--ease)]",
        "hover:-translate-y-1 hover:border-primary/60 hover:shadow-lg hover:shadow-primary/10 active:translate-y-0 active:scale-[0.99]",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        selected
          ? "border-primary bg-primary/[0.06] shadow-md shadow-primary/15"
          : "border-border bg-card",
      )}
    >
      {/* Accent bar: grows down the left edge on hover, stays when chosen. */}
      <span
        aria-hidden
        className={cn(
          "absolute inset-y-0 left-0 w-1 origin-top bg-primary transition-transform duration-300 ease-[var(--ease)]",
          selected ? "scale-y-100" : "scale-y-0 group-hover:scale-y-100",
        )}
      />
      {/* Soft wash that sweeps in from the corner on hover. */}
      <span
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_100%_0%,color-mix(in_srgb,var(--primary)_12%,transparent),transparent_60%)] opacity-0 transition-opacity duration-300 group-hover:opacity-100"
      />

      <div className={cn("relative flex items-start gap-4", onDelete && "pr-10")}>
        {Icon ? (
          <span
            className={cn(
              "flex size-11 shrink-0 items-center justify-center transition-all duration-300 ease-[var(--ease)]",
              "group-hover:-rotate-6 group-hover:scale-110",
              selected
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground group-hover:bg-primary group-hover:text-primary-foreground",
            )}
          >
            <Icon className="size-5" />
          </span>
        ) : null}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h4 className="line-clamp-2 text-[0.95rem] font-semibold leading-snug">
              {title}
            </h4>
            {badge ? (
              <span className="shrink-0 bg-accent px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-accent-foreground">
                {badge}
              </span>
            ) : null}
          </div>
          {description ? (
            <p className="mt-1.5 line-clamp-3 text-xs leading-relaxed text-muted-foreground">
              {description}
            </p>
          ) : null}
        </div>
      </div>

      <div
        className={cn(
          "relative mt-auto flex items-center gap-1.5 pt-3 text-xs font-semibold transition-all duration-300 ease-[var(--ease)]",
          selected
            ? "text-primary"
            : "translate-x-[-6px] text-primary opacity-0 group-hover:translate-x-0 group-hover:opacity-100 group-focus-visible:translate-x-0 group-focus-visible:opacity-100",
        )}
      >
        {selected ? (
          <>
            <Check className="size-3.5" /> Selected
          </>
        ) : (
          <>
            Use this <ArrowRight className="size-3.5" />
          </>
        )}
      </div>

      {onDelete ? (
        <button
          type="button"
          aria-label={`Delete ${title}`}
          onClick={(e) => {
            // Without this the card's own onClick fires too and the teacher
            // both deletes the template and selects it on the way out.
            e.stopPropagation();
            onDelete();
          }}
          className="delete-icon-button absolute right-2 top-2 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 focus-visible:opacity-100 [@media(pointer:coarse)]:opacity-100"
        >
          <Trash2 className="size-3.5" />
        </button>
      ) : null}
    </div>
  );
}

function Section({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <h3 className="whitespace-nowrap text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {label}
        </h3>
        {hint ? (
          <span className="text-xs text-muted-foreground/70">{hint}</span>
        ) : null}
      </div>
      {/* An explicit single column on phones: the implicit one grows to a
          truncated title's full width and pushes cards off the screen. */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">{children}</div>
    </section>
  );
}

export function TemplatePickerGrid({
  builtin,
  saved,
  selectedId,
  onSelect,
  onDelete,
  loading,
  academicClass,
  subject,
}: Props) {
  const [browseClass, setBrowseClass] = React.useState(academicClass || "10");
  const [browseSubject, setBrowseSubject] = React.useState(
    paperSubjectEntry(subject) ?? ALL_SUBJECTS,
  );
  // Follow the paper when it changes on the previous step, so the browser
  // always opens where the teacher just said the paper is.
  React.useEffect(() => {
    if (academicClass) setBrowseClass(academicClass);
  }, [academicClass]);
  React.useEffect(() => {
    setBrowseSubject(paperSubjectEntry(subject) ?? ALL_SUBJECTS);
  }, [subject]);

  // "Describe It Yourself" and "Blank" are not papers for a class and should
  // not be buried among them — they are the two ways to start from nothing.
  const quickStarts = builtin.filter(
    (t) => t.kind === "instructions" || t.kind === "blank",
  );

  const classNum = Number.parseInt(browseClass, 10);
  // Board card first (it is the one the year is set to), then from the short
  // test to the full exam.
  const inClass = builtin
    .filter(
      (t) => (t.kind === "starter" || t.kind === "cbse_blueprint") && fitsClass(t, classNum),
    )
    .sort(
      (a, b) =>
        Number(b.kind === "cbse_blueprint") - Number(a.kind === "cbse_blueprint") ||
        (a.totalMarks ?? 0) - (b.totalMarks ?? 0) ||
        a.name.localeCompare(b.name),
    );
  const bySubject = PAPER_SUBJECTS.map((s) => ({
    subject: s,
    templates: inClass.filter((t) => paperSubjectEntry(t.subject) === s),
  })).filter((group) => group.templates.length > 0);
  const shown =
    browseSubject === ALL_SUBJECTS
      ? bySubject
      : bySubject.filter((group) => group.subject === browseSubject);

  if (loading) {
    return <SkeletonCards cards={6} />;
  }

  const readyCard = (template: BuiltinTemplate, i: number) => (
    <Card
      index={i}
      key={template.id}
      title={template.name}
      description={template.description}
      icon={iconFor(template.kind)}
      badge={template.kind === "cbse_blueprint" ? "Board" : undefined}
      selected={selectedId === template.id}
      onClick={() => onSelect(template.id, template.kind, { academicClass: browseClass })}
    />
  );

  return (
    <div className="space-y-7">
      {saved.length > 0 ? (
        <Section label="Your templates" hint="the ones you saved">
          {saved.map((template, i) => (
            <Card
              index={i}
              key={template.id}
              title={template.name}
              description={
                template.pinned
                  ? `${template.blueprint.totalQuestions} questions · ${template.blueprint.totalMarks} marks`
                  : template.instructions || "Re-planned each time you use it"
              }
              badge={template.pinned ? undefined : "Adaptive"}
              selected={selectedId === template.id}
              onClick={() => onSelect(template.id, "saved")}
              onDelete={onDelete ? () => onDelete(template) : undefined}
            />
          ))}
        </Section>
      ) : null}

      {quickStarts.length > 0 ? (
        <Section label="Start from scratch">
          {quickStarts.map((template, i) => (
            <Card
              index={i}
              key={template.id}
              title={template.name}
              description={template.description}
              icon={iconFor(template.kind)}
              selected={selectedId === template.id}
              onClick={() => onSelect(template.id, template.kind)}
            />
          ))}
        </Section>
      ) : null}

      <section className="space-y-4">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <h3 className="whitespace-nowrap text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Ready-made papers
          </h3>
          <span className="text-xs text-muted-foreground/70">
            a structure you can edit, by class
          </span>
        </div>

        {/* Class tabs. A row that scrolls on a phone rather than wrapping
            into a second line of numbers. */}
        <div
          role="tablist"
          aria-label="Class"
          className="-mx-1 flex gap-1 overflow-x-auto border-b border-border px-1"
        >
          {PAPER_CLASSES.map((c) => {
            const active = c === browseClass;
            return (
              <button
                key={c}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setBrowseClass(c)}
                className={cn(
                  "relative -mb-px shrink-0 border-b-2 px-3 py-2 text-sm font-medium tabular-nums whitespace-nowrap transition-colors",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  active
                    ? "border-primary text-primary"
                    : "border-transparent text-muted-foreground hover:border-border hover:text-foreground",
                )}
              >
                Class {c}
                {c === academicClass ? (
                  <span
                    aria-label="this paper's class"
                    className="absolute right-1 top-1.5 size-1.5 rounded-full bg-primary"
                  />
                ) : null}
              </button>
            );
          })}
        </div>

        <div role="radiogroup" aria-label="Subject" className="flex flex-wrap gap-2">
          {[ALL_SUBJECTS, ...bySubject.map((group) => group.subject)].map((s) => {
            const active = s === browseSubject;
            return (
              <button
                key={s}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => setBrowseSubject(s)}
                className={cn(
                  "border px-3 py-1.5 text-xs font-medium transition-all duration-200 ease-[var(--ease)]",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
                  active
                    ? "border-primary bg-primary text-primary-foreground shadow-sm shadow-primary/25"
                    : "border-border bg-background hover:-translate-y-0.5 hover:border-primary/50 hover:text-primary",
                )}
              >
                {s === ALL_SUBJECTS ? "All subjects" : s}
              </button>
            );
          })}
        </div>

        {/* Keyed on the selection so the cards re-run their entrance. */}
        <div key={`${browseClass}|${browseSubject}`} className="space-y-6">
          {shown.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No ready-made papers for this class yet — start from scratch above.
            </p>
          ) : (
            shown.map((group) => (
              <div key={group.subject} className="space-y-3">
                {browseSubject === ALL_SUBJECTS ? (
                  <h4 className="text-sm font-semibold">{group.subject}</h4>
                ) : null}
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {group.templates.map(readyCard)}
                </div>
              </div>
            ))
          )}
        </div>
      </section>

      {builtin.length === 0 && saved.length === 0 ? (
        <p className="py-12 text-center text-sm text-muted-foreground">
          No templates available. Check your connection and try again.
        </p>
      ) : null}
    </div>
  );
}
