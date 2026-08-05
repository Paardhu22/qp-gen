"use client";

/**
 * One template, shown in enough detail to choose between two of them.
 *
 * The old picker card carried a name and a one-line blurb, which is fine when
 * you are picking a starting point and about to see the blueprint anyway. It is
 * not enough when the list is thirty of your own templates and the question is
 * "which of these is the one I use for Friday tests" — so the card leads with
 * the shape of the paper: how many questions, how many marks, how it is split
 * into sections, and where its questions come from.
 *
 * The pinned/instruction-driven distinction is surfaced because it changes what
 * the template *does* on use, not just how it was made: a pinned template
 * reproduces the structure shown here, and an instruction-driven one is
 * re-resolved from its prose every time and may come back different.
 */

import * as React from "react";
import {
  Copy,
  FileText,
  MoreHorizontal,
  Pencil,
  PlayCircle,
  Trash2,
  FolderInput,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import type {
  BuiltinTemplate,
  PaperTemplate,
  TemplateFolder,
} from "@/lib/api-client";

function relativeDay(iso: string | null): string | null {
  if (!iso) return null;
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return null;
  const days = Math.floor((Date.now() - then) / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days} days ago`;
  const months = Math.floor(days / 30);
  return months === 1 ? "a month ago" : `${months} months ago`;
}

function Stat({ value, label }: { value: React.ReactNode; label: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-base font-semibold tabular-nums leading-none">
        {value}
      </span>
      <span className="text-[0.7rem] uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
    </div>
  );
}

export function SavedTemplateCard({
  template,
  folders,
  onEdit,
  onUse,
  onDuplicate,
  onMove,
  onDelete,
}: {
  template: PaperTemplate;
  folders: TemplateFolder[];
  onEdit: () => void;
  onUse: () => void;
  onDuplicate: () => void;
  onMove: (folderId: string | null) => void;
  onDelete: () => void;
}) {
  const { blueprint } = template;
  const lastUsed = relativeDay(template.last_used_at);
  const sections = blueprint.bySection ?? [];

  return (
    <div className="rounded-xl border border-border bg-card p-4 transition-colors hover:border-primary/40">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-semibold">{template.name}</h3>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
            <span
              className={cn(
                "rounded px-1.5 py-0.5 text-[0.65rem] font-medium",
                template.pinned
                  ? "bg-primary/10 text-primary"
                  : "bg-muted text-muted-foreground",
              )}
              title={
                template.pinned
                  ? "Reproduces exactly the structure shown here."
                  : "Re-resolved from its instructions each time it is used, so the structure can change."
              }
            >
              {template.pinned ? "Pinned structure" : "From instructions"}
            </span>
            {template.base_template_id ? (
              <span className="truncate">
                based on {template.base_template_id}
              </span>
            ) : null}
            {lastUsed ? <span>· used {lastUsed}</span> : <span>· never used</span>}
          </p>
        </div>

        <DropdownMenu>
          <DropdownMenuTrigger
            aria-label={`Actions for ${template.name}`}
            className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <MoreHorizontal className="h-4 w-4" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={onEdit}>
              <Pencil className="mr-2 h-3.5 w-3.5" />
              Edit
            </DropdownMenuItem>
            <DropdownMenuItem onClick={onDuplicate}>
              <Copy className="mr-2 h-3.5 w-3.5" />
              Duplicate
            </DropdownMenuItem>
            <DropdownMenuSub>
              <DropdownMenuSubTrigger>
                <FolderInput className="mr-2 h-3.5 w-3.5" />
                Move to
              </DropdownMenuSubTrigger>
              <DropdownMenuSubContent>
                <DropdownMenuItem
                  onClick={() => onMove(null)}
                  disabled={template.folderId === null}
                >
                  Unfiled
                </DropdownMenuItem>
                {folders.length ? <DropdownMenuSeparator /> : null}
                {folders.map((folder) => (
                  <DropdownMenuItem
                    key={folder.id}
                    onClick={() => onMove(folder.id)}
                    disabled={template.folderId === folder.id}
                  >
                    {folder.name}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuSubContent>
            </DropdownMenuSub>
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" onClick={onDelete}>
              <Trash2 className="mr-2 h-3.5 w-3.5" />
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {blueprint.totalQuestions > 0 ? (
        <>
          <div className="mt-3 flex flex-wrap items-end gap-5">
            <Stat value={blueprint.totalQuestions} label="questions" />
            <Stat value={blueprint.totalMarks} label="marks" />
            <Stat value={sections.length} label="sections" />
            {blueprint.savedCount > 0 ? (
              <Stat value={blueprint.savedCount} label="from bank" />
            ) : null}
          </div>

          {sections.length ? (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {sections.map((section) => (
                <span
                  key={section.title}
                  className="rounded-md bg-muted px-1.5 py-0.5 text-[0.7rem] text-muted-foreground"
                >
                  {section.title}
                  <span className="ml-1 tabular-nums opacity-70">
                    {section.questions}q · {section.marks}m
                  </span>
                </span>
              ))}
            </div>
          ) : null}
        </>
      ) : (
        // Instruction-driven with nothing compiled yet. Showing the prose is
        // more useful than showing zeroes for a paper that does have a shape —
        // it just has not been resolved into slots.
        <p className="mt-3 line-clamp-3 text-xs leading-relaxed text-muted-foreground">
          {template.instructions || "No instructions saved."}
        </p>
      )}

      <div className="mt-4 flex items-center gap-2">
        <Button size="sm" className="gap-1.5" onClick={onUse}>
          <PlayCircle className="h-3.5 w-3.5" />
          Use
        </Button>
        <Button size="sm" variant="outline" className="gap-1.5" onClick={onEdit}>
          <Pencil className="h-3.5 w-3.5" />
          Edit
        </Button>
      </div>
    </div>
  );
}

export function BuiltinTemplateCard({
  template,
  onFork,
  onUse,
  isForking,
}: {
  template: BuiltinTemplate;
  onFork: () => void;
  onUse: () => void;
  isForking: boolean;
}) {
  // "Describe It Yourself" and "Blank Paper" resolve to nothing until the
  // teacher says something, so there is no structure to copy. The API refuses
  // to fork them; not offering it is clearer than a button that errors.
  const forkable = template.kind === "cbse_blueprint";

  return (
    <div className="flex flex-col rounded-xl border border-dashed border-border bg-card/50 p-4">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold leading-snug">{template.name}</h3>
          {template.subject || template.academicClass ? (
            <p className="mt-0.5 text-xs text-muted-foreground">
              {[template.board, template.subject, template.academicClass && `Class ${template.academicClass}`]
                .filter(Boolean)
                .join(" · ")}
            </p>
          ) : null}
        </div>
      </div>

      <p className="mt-2 line-clamp-3 flex-1 text-xs leading-relaxed text-muted-foreground">
        {template.description}
      </p>

      <div className="mt-4 flex items-center gap-2">
        <Button size="sm" variant="outline" className="gap-1.5" onClick={onUse}>
          <FileText className="h-3.5 w-3.5" />
          Use
        </Button>
        {forkable ? (
          <Button
            size="sm"
            variant="ghost"
            className="gap-1.5"
            onClick={onFork}
            disabled={isForking}
            title="Copy this into your own templates so you can edit and file it"
          >
            <Copy className="h-3.5 w-3.5" />
            {isForking ? "Copying…" : "Make it mine"}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
