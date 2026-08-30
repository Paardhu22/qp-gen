"use client";

/**
 * Build a paper from questions already in the bank — no chapter, no upload, no
 * model call to write anything.
 *
 * This is the capability that used to be the whole `/build-paper` page. That
 * page was labelled "Builder" and sat in the nav beside the real one, which made
 * two quite different things look like the same thing: one configures a paper
 * and generates it, the other assembles a paper out of questions that already
 * exist. Only the second is here, and it lives next to Generate in the Studio
 * dock because that is where a teacher decides how a paper gets filled.
 *
 * The backend path is `POST /api/generation/paper-from-bank`
 * (`services/pool/from_bank.py`), which skips Model 1 entirely. Deleting the old
 * page without moving this would have orphaned that pipeline.
 */

import * as React from "react";
import { createPortal } from "react-dom";
import { toast } from "sonner";
import { errorWithRetry } from "@/lib/toasts";
import { BookMarked, RefreshCcw, Search, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SkeletonRows } from "@/components/ui/skeleton";
import {
  fetchBankSummary,
  streamPaperFromBank,
  type BankChapter,
} from "@/lib/api-client";
import { useEditorStore } from "@/store/editor-store";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";

const chapterKey = (row: BankChapter) => row.chapter || row.projectName;

const DIFFICULTIES = ["easy", "medium", "hard"];

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called once the paper has been staged into the editor document. */
  onBuilt?: () => void;
}

export function BuildFromBankDialog({ open, onOpenChange, onBuilt }: Props) {
  const [mounted, setMounted] = React.useState(false);
  const [chapters, setChapters] = React.useState<BankChapter[]>([]);
  const [isLoading, setIsLoading] = React.useState(true);
  const [search, setSearch] = React.useState("");
  const [selected, setSelected] = React.useState<Set<string>>(new Set());
  const [difficulty, setDifficulty] = React.useState("medium");
  const [numSets, setNumSets] = React.useState(1);
  const [isBuilding, setIsBuilding] = React.useState(false);
  const [status, setStatus] = React.useState("");

  React.useEffect(() => {
    setMounted(true);
  }, []);

  const load = React.useCallback(async function load() {
    setIsLoading(true);
    try {
      const data = await fetchBankSummary();
      setChapters(data.chapters || []);
    } catch (error: any) {
      errorWithRetry(error?.message || "Could not load your question bank.", load);
    } finally {
      setIsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    if (open) void load();
  }, [open, load]);

  const filtered = React.useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return chapters;
    return chapters.filter((row) =>
      [row.chapter, row.projectName, row.subject, row.gradeClass]
        .filter((v): v is string => typeof v === "string" && v.length > 0)
        .join(" · ")
        .toLowerCase()
        .includes(term),
    );
  }, [chapters, search]);

  const selectedRows = React.useMemo(
    () => chapters.filter((row) => selected.has(chapterKey(row))),
    [chapters, selected],
  );

  const totalSelected = selectedRows.reduce((sum, row) => sum + row.count, 0);

  // A paper is compiled from exactly one subject and one class. Mixing them
  // would ask the assembler to satisfy a blueprint that no single board pattern
  // describes, so it is refused rather than silently resolved.
  const subjects = new Set(selectedRows.map((r) => r.subject || ""));
  const classes = new Set(selectedRows.map((r) => r.gradeClass || ""));
  const isMixed = subjects.size > 1 || classes.size > 1;

  const toggle = (key: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const handleBuild = async () => {
    if (selectedRows.length === 0) {
      toast.error("Pick at least one chapter from your bank.");
      return;
    }
    if (isMixed) {
      toast.error(
        "Those chapters span more than one subject or class. Pick from a single subject and class.",
      );
      return;
    }

    const first = selectedRows[0];
    const classNumber = parseInt(
      (first.gradeClass || "10").replace(/\D/g, "") || "10",
      10,
    );

    setIsBuilding(true);
    setStatus("Loading your question bank…");

    const sections: any[] = [];
    let instructions: string[] = [];
    let doneSets: { label: string; result: any }[] | null = null;
    let failed: string | null = null;

    try {
      await streamPaperFromBank(
        {
          subject: first.subject || "",
          class: classNumber,
          chapters: selectedRows.map((r) => r.chapter).filter(Boolean),
          difficulty,
          count: -1,
          countVariation: "cbse",
          qp_type: "board",
          numberOfSets: numSets,
        },
        (event, data) => {
          if (event === "error") {
            failed = data.error || "Could not build the paper.";
          } else if (event === "status") {
            if (data.message) setStatus(data.message);
          } else if (event === "notice") {
            if (data.message) toast.info(data.message);
          } else if (event === "done" && data.result) {
            instructions = data.result.generalInstructions || [];
            for (const section of data.result.sections || []) {
              sections.push({
                title: section.title,
                questions: (section.questions || []).map((q: any) => ({
                  content: q.content,
                  type: q.type,
                  options: q.options || [],
                  answer: q.answer,
                  marks: q.marks,
                  image_url: q.image_url || q.metadata?.image_url || "",
                })),
              });
            }
            if (Array.isArray(data.sets) && data.sets.length > 1) {
              doneSets = data.sets.map((s: any) => ({
                label: s.label,
                result: s.result,
              }));
            }
          }
        },
      );

      if (failed) {
        toast.error(failed);
        return;
      }
      if (sections.length === 0) {
        toast.error("No questions could be selected for this paper.");
        return;
      }

      const store = useEditorStore.getState();
      // Set A streams into the editor doc via the append plumbing.
      if (instructions.length > 0) store.appendInstructions(instructions);
      store.appendSections(sections);
      // Sets B/C (if any) drive the editor's Set tabs / comparison workspace.
      if (doneSets) store.setComparisonSets(doneSets);
      else store.clearComparisonSets();

      const count = sections.reduce((n, s) => n + s.questions.length, 0);
      toast.success(
        `Built a ${count}-question paper${
          numSets > 1 ? ` (${numSets} sets)` : ""
        } from your question bank.`,
      );
      onOpenChange(false);
      onBuilt?.();
    } catch (error: any) {
      toast.error(error?.message || "Could not build the paper.");
    } finally {
      setIsBuilding(false);
      setStatus("");
    }
  };

  if (!open || !mounted) return null;

  return createPortal(
    <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={isBuilding ? undefined : () => onOpenChange(false)}
        aria-hidden="true"
      />

      <div className="relative z-10 flex max-h-[calc(100dvh-4rem)] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-border bg-background shadow-2xl">
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-border px-5 py-3">
          <div className="min-w-0">
            <h2 className="flex items-center gap-2 text-sm font-semibold">
              <BookMarked className="h-4 w-4 text-primary" />
              Build from my question bank
            </h2>
            <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
              Assembles a paper from questions you already have. Nothing new is
              written, so this costs nothing and finishes in seconds.
            </p>
          </div>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            disabled={isBuilding}
            className="rounded-lg p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-50"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex shrink-0 items-center gap-2 border-b border-border px-5 py-2">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              className="h-8 pl-8 text-sm"
              placeholder="Search chapters"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <button
            type="button"
            onClick={() => void load()}
            title="Refresh"
            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <RefreshCcw className="h-3.5 w-3.5" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-3">
          {isLoading ? (
            <SkeletonRows rows={6} height="h-9" />
          ) : filtered.length === 0 ? (
            <p className="py-12 text-center text-xs leading-relaxed text-muted-foreground">
              {chapters.length === 0
                ? "Your question bank is empty. Every generation saves its questions here, so generate a paper first."
                : "No chapters match that search."}
            </p>
          ) : (
            <ul className="space-y-1">
              {filtered.map((row) => {
                const key = chapterKey(row);
                const isSelected = selected.has(key);
                return (
                  <li key={key}>
                    <button
                      type="button"
                      onClick={() => toggle(key)}
                      className={cn(
                        "flex w-full items-center gap-3 rounded-lg border px-3 py-2 text-left transition-colors",
                        isSelected
                          ? "border-primary/50 bg-primary/5"
                          : "border-border hover:bg-accent",
                      )}
                    >
                      <span
                        className={cn(
                          "flex h-4 w-4 shrink-0 items-center justify-center rounded border",
                          isSelected
                            ? "border-primary bg-primary text-primary-foreground"
                            : "border-input",
                        )}
                        aria-hidden="true"
                      >
                        {isSelected ? "✓" : ""}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm">{key}</span>
                        <span className="block truncate text-xs text-muted-foreground">
                          {[row.subject, row.gradeClass && `Class ${row.gradeClass}`]
                            .filter(Boolean)
                            .join(" · ")}
                        </span>
                      </span>
                      <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                        {row.count}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div className="shrink-0 space-y-3 border-t border-border bg-muted/20 px-5 py-3">
          {isMixed ? (
            <p className="rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive">
              Those chapters span more than one subject or class. A paper is
              compiled from exactly one of each.
            </p>
          ) : null}

          <div className="flex flex-wrap items-center gap-4">
            <label className="flex items-center gap-2 text-xs">
              <span className="text-muted-foreground">Difficulty</span>
              <select
                value={difficulty}
                onChange={(e) => setDifficulty(e.target.value)}
                className="h-8 rounded-lg border border-input bg-transparent px-2 text-xs shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
              >
                {DIFFICULTIES.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>

            <label className="flex items-center gap-2 text-xs">
              <span className="text-muted-foreground">Sets</span>
              <select
                value={numSets}
                onChange={(e) => setNumSets(Number(e.target.value))}
                className="h-8 rounded-lg border border-input bg-transparent px-2 text-xs shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
              >
                {[1, 2, 3].map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>

            <span className="ml-auto text-xs tabular-nums text-muted-foreground">
              {selectedRows.length} chapter
              {selectedRows.length === 1 ? "" : "s"} · {totalSelected} questions
            </span>
          </div>

          <div className="flex items-center justify-between gap-3">
            <p className="min-h-[1rem] text-xs text-muted-foreground">
              {status}
            </p>
            <Button
              size="sm"
              onClick={() => void handleBuild()}
              disabled={isBuilding || selectedRows.length === 0 || isMixed}
              className="gap-1.5"
            >
              {isBuilding ? (
                <Spinner />
              ) : null}
              {isBuilding ? "Building…" : "Build paper"}
            </Button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
