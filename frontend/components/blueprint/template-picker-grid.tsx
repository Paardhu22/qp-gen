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
 */

import * as React from "react";
import {
  BookOpen,
  FilePlus2,
  MessageSquareText,
  Trash2,
} from "lucide-react";

import { SkeletonCards } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { BuiltinTemplate, PaperTemplate } from "@/lib/api-client";

interface Props {
  builtin: BuiltinTemplate[];
  saved: PaperTemplate[];
  selectedId: string | null;
  onSelect: (id: string, kind: string) => void;
  onDelete?: (template: PaperTemplate) => void;
  loading?: boolean;
}

function iconFor(kind: string) {
  if (kind === "instructions") return MessageSquareText;
  if (kind === "blank") return FilePlus2;
  return BookOpen;
}

function Card({
  title,
  description,
  icon: Icon,
  selected,
  badge,
  onClick,
  onDelete,
}: {
  title: string;
  description: string;
  icon?: React.ElementType;
  selected: boolean;
  badge?: string;
  onClick: () => void;
  onDelete?: () => void;
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
      className={cn(
        "group relative flex cursor-pointer flex-col gap-2 rounded-xl border p-4 text-left transition-all",
        "hover:border-primary/50 hover:shadow-sm focus-visible:outline-none",
        "focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        selected
          ? "border-primary bg-primary/5 ring-1 ring-primary"
          : "border-border bg-card",
      )}
    >
      <div className="flex items-start gap-3">
        {Icon ? (
          <span
            className={cn(
              "mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg",
              selected
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground",
            )}
          >
            <Icon className="size-4" />
          </span>
        ) : null}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h4 className="truncate text-sm font-semibold leading-tight">
              {title}
            </h4>
            {badge ? (
              <span className="shrink-0 rounded-full bg-accent px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-accent-foreground">
                {badge}
              </span>
            ) : null}
          </div>
          {description ? (
            <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
              {description}
            </p>
          ) : null}
        </div>
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
          className="absolute right-2 top-2 rounded-lg p-1.5 text-muted-foreground opacity-0 transition-opacity hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100 focus-visible:opacity-100"
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
      <div className="flex items-baseline gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {label}
        </h3>
        {hint ? (
          <span className="text-xs text-muted-foreground/70">{hint}</span>
        ) : null}
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{children}</div>
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
}: Props) {
  // "Describe It Yourself" and "Blank" are not board papers and should not be
  // buried among thirty of them — they are the two ways to start from nothing.
  const quickStarts = builtin.filter((t) => t.kind !== "cbse_blueprint");
  const boardPapers = builtin.filter((t) => t.kind === "cbse_blueprint");

  if (loading) {
    return <SkeletonCards cards={6} />;
  }

  return (
    <div className="space-y-7">
      {saved.length > 0 ? (
        <Section label="Your templates" hint="the ones you saved">
          {saved.map((template) => (
            <Card
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
          {quickStarts.map((template) => (
            <Card
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

      {boardPapers.length > 0 ? (
        <Section
          label="Board papers"
          hint="official CBSE patterns, ready to edit"
        >
          {boardPapers.map((template) => (
            <Card
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

      {builtin.length === 0 && saved.length === 0 ? (
        <p className="py-12 text-center text-sm text-muted-foreground">
          No templates available. Check your connection and try again.
        </p>
      ) : null}
    </div>
  );
}
