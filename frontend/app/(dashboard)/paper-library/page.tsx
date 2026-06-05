"use client";

import { useEffect, useMemo, useState } from "react";
import {
  fetchProjectsWithQuestions,
  deleteQuestion,
  fetchJson,
} from "@/lib/api-client";
import { ListChecks, Trash2, Search, FileText } from "lucide-react";
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
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useEditorStore } from "@/store/editor-store";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

/* -------------------------------------------------------------------------- */
/*  Types                                                                       */
/* -------------------------------------------------------------------------- */

type Question = {
  id: string;
  content: string;
  answer?: string;
  options?: string[];
  type: string;
  marks: number;
  // Backend-supplied metadata. These were dropped from the search index
  // before Cluster D, which made "Math" or "Class 10" queries useless on
  // any project whose name didn't already contain those tokens.
  grade_class?: string | null;
  subject?: string | null;
  inferred_topic?: string | null;
  inferred_chapter?: string | null;
  source_pdf?: string | null;
  bloom_taxonomy?: string | null;
  difficulty?: string | null;
};

type Project = {
  id: string;
  name: string;
  questions: Question[];
};

type SavedQuestion = Question & {
  projectId: string;
  projectName: string;
  classLabel: string;
  subjectLabel: string;
};

/* -------------------------------------------------------------------------- */
/*  Helpers                                                                     */
/* -------------------------------------------------------------------------- */

/** Parse `"class 9 — social — frenchie"` → { classLabel: "class 9", subjectLabel: "social" } */
function parseProjectName(name: string): {
  classLabel: string;
  subjectLabel: string;
} {
  // Tolerate any of: em-dash, en-dash, hyphen, or no delimiter, since the
  // project name is user-supplied free text. Whatever does not parse cleanly
  // still goes into the haystack via raw `projectName`.
  const cleaned = (name || "").trim();
  const parts = cleaned.split(/\s*[—–\-]\s*/).filter(Boolean);
  return {
    classLabel: parts[0]?.trim() ?? cleaned,
    subjectLabel: parts[1]?.trim() ?? "",
  };
}

function flattenProjects(projects: Project[]): SavedQuestion[] {
  return projects.flatMap((project) => {
    const { classLabel, subjectLabel } = parseProjectName(project.name);
    return (project.questions ?? []).map((q) => ({
      ...q,
      projectId: project.id,
      projectName: project.name,
      classLabel,
      subjectLabel,
    }));
  });
}

/* -------------------------------------------------------------------------- */
/*  Page                                                                        */
/* -------------------------------------------------------------------------- */

export default function SavedQuestionsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [questionSearch, setQuestionSearch] = useState("");
  const [selectedQuestionIds, setSelectedQuestionIds] = useState<Set<string>>(
    new Set(),
  );
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set());
  const [isClearingQuestions, setIsClearingQuestions] = useState(false);

  /* ---------------------------------------------------------------------- */
  /*  Data fetching                                                           */
  /* ---------------------------------------------------------------------- */

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    fetchProjectsWithQuestions<Project[]>()
      .then((data) => {
        if (!cancelled) setProjects(data ?? []);
      })
      .catch(() => {
        if (!cancelled)
          toast.error("Failed to load saved questions. Please refresh.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  /* ---------------------------------------------------------------------- */
  /*  Derived state                                                           */
  /* ---------------------------------------------------------------------- */

  const allQuestions = useMemo(() => flattenProjects(projects), [projects]);

  const filteredQuestions = useMemo<SavedQuestion[]>(() => {
    const term = questionSearch.trim().toLowerCase();
    if (!term) return allQuestions;
    // Cluster D — every field the user might reasonably look for joins
    // the search index. Building a single haystack per question keeps
    // the filter O(N) and treats every token equally, so "Math",
    // "Class 10", "BPT", "trigonometry", "MCQ" all match the right rows.
    const matches = (q: SavedQuestion) => {
      const haystack = [
        q.content,
        q.answer,
        q.type,
        q.projectName,
        q.classLabel,
        q.subjectLabel,
        q.grade_class,
        q.subject,
        q.inferred_topic,
        q.inferred_chapter,
        q.source_pdf,
        q.bloom_taxonomy,
        q.difficulty,
        ...(q.options ?? []),
      ]
        .filter((v): v is string => typeof v === "string" && v.length > 0)
        .join(" · ")
        .toLowerCase();
      return haystack.includes(term);
    };
    return allQuestions.filter(matches);
  }, [allQuestions, questionSearch]);

  /* ---------------------------------------------------------------------- */
  /*  Handlers                                                                */
  /* ---------------------------------------------------------------------- */

  const deleteQuestionById = async (id: string) => {
    setDeletingIds((prev) => new Set(prev).add(id));
    try {
      await deleteQuestion(id);
      setProjects((prev) =>
        prev.map((p) => ({
          ...p,
          questions: p.questions.filter((q) => q.id !== id),
        })),
      );
      setSelectedQuestionIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
      toast.success("Question deleted.");
    } catch {
      toast.error("Failed to delete question. Please try again.");
    } finally {
      setDeletingIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  };

  const handleDeleteQuestion = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    toast.warning("Delete this question?", {
      description: "This cannot be undone.",
      action: {
        label: "Delete",
        onClick: () => void deleteQuestionById(id),
      },
    });
  };

  const handleClearAllQuestions = async () => {
    setIsClearingQuestions(true);
    try {
      await fetchJson("/api/projects/questions/clear", { method: "DELETE" });
      setProjects([]);
      setSelectedQuestionIds(new Set());
      toast.success("All saved questions cleared.");
    } catch {
      toast.error("Failed to clear questions. Please try again.");
    } finally {
      setIsClearingQuestions(false);
    }
  };

  const handleInsertSelectedQuestions = () => {
    const selected = allQuestions.filter((q) => selectedQuestionIds.has(q.id));
    const questions = selected.map((q) => ({
      content: q.content,
      type: q.type,
      options: q.options ?? [],
      answer: q.answer ?? "",
      marks: q.marks,
    }));
    useEditorStore.getState().appendQuestions(questions);
    toast.success(`Inserted ${questions.length} question(s) into the editor.`);
    setSelectedQuestionIds(new Set());
  };

  const toggleQuestionSelection = (id: string) => {
    setSelectedQuestionIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  /* ---------------------------------------------------------------------- */
  /*  Render                                                                  */
  /* ---------------------------------------------------------------------- */

  return (
    <div className="p-8 space-y-6 bg-background min-h-full">
      {/* ------------------------------------------------------------------ */}
      {/* Header                                                              */}
      {/* ------------------------------------------------------------------ */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        {/* Left — icon + title + subtitle */}
        <div className="flex items-start gap-3">
          <ListChecks className="mt-1 h-7 w-7 shrink-0 text-indigo-500" />
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-3xl font-bold tracking-tight">
                Saved Questions
              </h1>
              {!isLoading && allQuestions.length > 0 && (
                <span className="inline-flex items-center justify-center h-6 min-w-6 px-2 rounded-full bg-indigo-100 text-indigo-600 text-xs font-bold dark:bg-indigo-950 dark:text-indigo-400">
                  {allQuestions.length}
                </span>
              )}
            </div>
            <p className="text-sm text-muted-foreground mt-1">
              Browse and insert your saved exam questions.
            </p>
          </div>
        </div>

        {/* Right — search + clear all */}
        <div className="flex items-center gap-2 shrink-0">
          {/* Search input */}
          <div className="relative w-64">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              className="pl-9"
              placeholder="Search questions…"
              value={questionSearch}
              onChange={(e) => setQuestionSearch(e.target.value)}
            />
          </div>

          {/* Clear All — only when there are questions */}
          {allQuestions.length > 0 && !isLoading && (
            <AlertDialog>
              <AlertDialogTrigger
                className="inline-flex h-9 items-center justify-center rounded-md border border-destructive/40 bg-background px-3 text-sm font-medium text-destructive transition-colors hover:bg-destructive/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50"
                disabled={isClearingQuestions}
              >
                {isClearingQuestions ? "Clearing…" : "Clear All"}
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>
                    Clear all saved questions?
                  </AlertDialogTitle>
                  <AlertDialogDescription>
                    This will permanently delete every saved question. This
                    action cannot be undone.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction
                    className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                    onClick={() => void handleClearAllQuestions()}
                  >
                    Yes, clear all
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
        </div>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Insert selected bar                                                 */}
      {/* ------------------------------------------------------------------ */}
      {selectedQuestionIds.size > 0 && (
        <div className="flex items-center gap-3 rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-2.5 dark:border-indigo-800 dark:bg-indigo-950/40">
          <FileText className="h-4 w-4 text-indigo-500 shrink-0" />
          <span className="text-sm text-indigo-700 dark:text-indigo-300 flex-1">
            {selectedQuestionIds.size} question
            {selectedQuestionIds.size !== 1 ? "s" : ""} selected
          </span>
          <button
            type="button"
            onClick={handleInsertSelectedQuestions}
            className="inline-flex items-center gap-1.5 rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 transition-colors"
          >
            <FileText className="h-3.5 w-3.5" />
            Insert Selected ({selectedQuestionIds.size}) into Editor
          </button>
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Loading skeletons                                                   */}
      {/* ------------------------------------------------------------------ */}
      {isLoading && (
        <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="animate-pulse h-36 rounded-xl border bg-muted/40"
            />
          ))}
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Empty state                                                         */}
      {/* ------------------------------------------------------------------ */}
      {!isLoading && filteredQuestions.length === 0 && (
        <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed py-20 text-center">
          <ListChecks className="h-12 w-12 opacity-30 text-foreground" />
          <p className="text-sm font-medium text-foreground">
            {questionSearch.trim()
              ? "No questions match your search."
              : "No saved questions yet."}
          </p>
          {!questionSearch.trim() && (
            <p className="max-w-xs text-xs text-muted-foreground">
              Generate and save questions from the Editor to see them here.
            </p>
          )}
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Questions grid                                                      */}
      {/* ------------------------------------------------------------------ */}
      {!isLoading && filteredQuestions.length > 0 && (
        <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
          {filteredQuestions.map((question) => {
            const isSelected = selectedQuestionIds.has(question.id);
            const isDeleting = deletingIds.has(question.id);

            return (
              <div
                key={question.id}
                onClick={() => toggleQuestionSelection(question.id)}
                className={cn(
                  "bg-card border rounded-xl p-4 flex flex-col gap-3 cursor-pointer transition-all hover:shadow-sm",
                  isSelected && "border-primary/60 bg-primary/5",
                )}
              >
                {/* Top row: type badge (left) | marks badge + delete (right) */}
                <div className="flex items-center justify-between gap-2">
                  <Badge
                    variant="outline"
                    className="border-indigo-300 text-indigo-600 dark:border-indigo-700 dark:text-indigo-400 uppercase text-[10px] tracking-wide px-1.5 py-0"
                  >
                    {question.type}
                  </Badge>

                  <div className="flex items-center gap-1.5">
                    <Badge
                      variant="secondary"
                      className="text-[10px] px-1.5 py-0"
                    >
                      {question.marks} {question.marks === 1 ? "mark" : "marks"}
                    </Badge>
                    <button
                      type="button"
                      aria-label="Delete question"
                      disabled={isDeleting}
                      onClick={(e) => handleDeleteQuestion(question.id, e)}
                      className={cn(
                        "flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground transition-colors",
                        "hover:bg-destructive/10 hover:text-destructive",
                        "disabled:pointer-events-none disabled:opacity-40",
                      )}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>

                {/* Question content */}
                <p className="text-sm text-card-foreground line-clamp-3 flex-1 leading-relaxed">
                  {question.content}
                </p>

                {/* Class + subject metadata */}
                <p className="text-[11px] text-zinc-500 dark:text-zinc-400">
                  {question.classLabel}
                  {question.subjectLabel ? (
                    <>
                      <span className="mx-1.5">·</span>
                      {question.subjectLabel}
                    </>
                  ) : null}
                </p>

                {/* Select / Selected toggle */}
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleQuestionSelection(question.id);
                  }}
                  className={cn(
                    "w-full rounded-md border px-3 py-1.5 text-xs font-medium transition-colors",
                    isSelected
                      ? "border-primary bg-primary text-primary-foreground hover:bg-primary/90"
                      : "border-border bg-background text-foreground hover:bg-muted",
                  )}
                >
                  {isSelected ? "Selected ✓" : "Select"}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
