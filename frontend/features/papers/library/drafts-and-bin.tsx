"use client";

import { ChevronRight, FileText, PencilLine, Trash2, Undo2 } from "lucide-react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { cn } from "@/lib/utils";
import {
  daysUntilExpiry,
  DRAFT_RETENTION_DAYS,
  type DraftSummary,
} from "@/features/papers/drafts";

import { formatRelative } from "./format";

/**
 * Unsaved drafts. Papers live on the server; drafts do not — until saved, a
 * draft exists only as an IndexedDB document in this browser, which is why the
 * retention window has to be on the card. A draft vanishing on day 10 with no
 * warning is indistinguishable from data loss.
 *
 * Dashed border: a draft is "not yet a paper", and the library's solid cards
 * are papers.
 */
export function DraftsRail({
  drafts,
  onOpen,
  onDelete,
}: {
  drafts: DraftSummary[];
  onOpen: (draft: DraftSummary) => void;
  onDelete: (draft: DraftSummary) => void;
}) {
  if (drafts.length === 0) return null;
  return (
    <section aria-labelledby="drafts-heading" className="space-y-3">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2
          id="drafts-heading"
          className="font-heading text-base font-medium tracking-[-0.02em]"
        >
          Pick up where you left off
        </h2>
        <p className="text-xs text-muted-foreground">
          Unsaved · kept {DRAFT_RETENTION_DAYS} days in this browser
        </p>
      </div>

      <div className="-mx-4 flex gap-3 overflow-x-auto px-4 pb-2 custom-scrollbar sm:mx-0 sm:px-0">
        {drafts.map((draft) => {
          const daysLeft = daysUntilExpiry(draft.expiresAt);
          const title = draft.title || "Untitled draft";
          return (
            <div
              key={draft.id}
              className="group relative w-64 shrink-0 rounded-2xl border border-dashed border-border bg-card/60 p-4 transition-colors hover:border-primary/50 hover:bg-card"
            >
              <div className="flex items-start gap-3 pr-8">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-warning/15 text-warning">
                  <PencilLine className="h-4 w-4" aria-hidden />
                </span>
                <div className="min-w-0">
                  <button
                    type="button"
                    onClick={() => onOpen(draft)}
                    className="block max-w-full truncate text-left text-sm font-medium text-foreground outline-none"
                  >
                    {title}
                  </button>
                  <p className="mt-0.5 truncate text-xs text-muted-foreground">
                    {[draft.className, draft.subject].filter(Boolean).join(" · ") ||
                      "No class or subject yet"}
                  </p>
                </div>
              </div>

              <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground">
                {draft.questionCount > 0 && (
                  <span className="tabular-nums">
                    {draft.questionCount} questions · {draft.totalMarks} marks
                  </span>
                )}
                {draft.setLabels.length > 1 && (
                  <span>Sets {draft.setLabels.join("/")}</span>
                )}
              </div>
              <p
                className={cn(
                  "mt-1.5 text-[11px]",
                  daysLeft <= 2 ? "font-medium text-destructive" : "text-muted-foreground/80",
                )}
              >
                {formatRelative(new Date(draft.updatedAt).toISOString())} ·{" "}
                {daysLeft === 0
                  ? "deletes today unless saved"
                  : `deletes in ${daysLeft} day${daysLeft === 1 ? "" : "s"} unless saved`}
              </p>

              {/* Whole-card open target: a real overlay button, not a ::after
                  (Firefox ignores clicks on a button's out-of-box pseudo). */}
              <button
                type="button"
                tabIndex={-1}
                aria-hidden
                onClick={() => onOpen(draft)}
                className="absolute inset-0 rounded-2xl"
              />

              <button
                type="button"
                aria-label={`Delete draft ${title}`}
                onClick={() => onDelete(draft)}
                className="delete-icon-button absolute right-2 top-2 z-10 opacity-0 focus-visible:opacity-100 group-hover:opacity-100 group-focus-within:opacity-100 [@media(pointer:coarse)]:opacity-100"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          );
        })}
      </div>
    </section>
  );
}

/**
 * The recycle bin, collapsed by default. A bin that is always open is a second
 * papers list competing with the real one; the count on the toggle is what
 * makes it worth reading — the day a teacher needs it, they need to know at a
 * glance that the paper is in there.
 */
export function RecycleBin({
  papers,
  open,
  onToggle,
  retentionDays,
  onRestore,
  onPurge,
  onEmpty,
}: {
  papers: {
    id: string;
    title: string;
    gradeClass?: string | null;
    subject?: string | null;
    answerScriptId?: string | null;
  }[];
  open: boolean;
  onToggle: () => void;
  retentionDays: number;
  onRestore: (id: string, answerScriptId?: string | null) => void;
  onPurge: (id: string) => void;
  onEmpty: () => void;
}) {
  if (papers.length === 0) return null;
  return (
    <section className="rounded-2xl border border-border bg-muted/30">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          className="flex min-h-8 items-center gap-2 rounded-lg text-sm font-medium text-foreground outline-none focus-visible:ring-[3px] focus-visible:ring-ring/20"
        >
          <Trash2 className="h-4 w-4 text-muted-foreground" aria-hidden />
          Recycle bin
          <span className="rounded-full bg-background px-2 py-0.5 text-[11px] font-medium tabular-nums text-muted-foreground ring-1 ring-border">
            {papers.length}
          </span>
          <ChevronRight
            className={cn("h-3.5 w-3.5 text-muted-foreground transition-transform", open && "rotate-90")}
            aria-hidden
          />
        </button>
        <span className="text-xs text-muted-foreground">
          Kept {retentionDays} days, then removed for good
        </span>
        {open && (
          <AlertDialog>
            <AlertDialogTrigger className="destructive-action ml-auto rounded-lg text-xs underline underline-offset-2">
              Empty bin
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Empty the recycle bin?</AlertDialogTitle>
                <AlertDialogDescription>
                  This permanently deletes all {papers.length} papers in the bin,
                  along with their questions and answer keys. This cannot be
                  undone.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  onClick={onEmpty}
                >
                  Empty bin
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        )}
      </div>

      {open && (
        <ul className="divide-y divide-border border-t border-border">
          {papers.map((paper) => (
            <li
              key={paper.id}
              className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-2.5"
            >
              <FileText className="h-4 w-4 shrink-0 text-muted-foreground/60" aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm text-foreground">
                  {paper.title || "Untitled paper"}
                </p>
                <p className="truncate text-xs text-muted-foreground">
                  {[paper.gradeClass, paper.subject].filter(Boolean).join(" · ") ||
                    "No class or subject"}
                </p>
              </div>
              {/* Restore leads: the reason to open a bin is to get something
                  back, not to finish destroying it. */}
              <button
                type="button"
                onClick={() => onRestore(paper.id, paper.answerScriptId)}
                className="inline-flex min-h-8 items-center gap-1.5 rounded-lg border border-border bg-background px-3 text-xs font-medium text-foreground transition-colors hover:bg-accent"
              >
                <Undo2 className="h-3.5 w-3.5" aria-hidden /> Restore
              </button>
              <button
                type="button"
                aria-label={`Permanently delete ${paper.title || "this paper"}`}
                onClick={() => onPurge(paper.id)}
                className="destructive-action inline-flex min-h-8 items-center gap-1 rounded-lg px-2 text-xs"
              >
                <Trash2 className="h-3.5 w-3.5" aria-hidden /> Delete for good
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
