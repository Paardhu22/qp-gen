"use client";

import { useEffect, useMemo, useState } from "react";
import {
  fetchProjectsWithQuestions,
  deleteQuestion,
  fetchJson,
  fetchQuestionTypes,
} from "@/lib/api-client";
import {
  ListChecks,
  Trash2,
  Search,
  FileText,
  ArrowUp,
  ArrowDown,
  ChevronsUpDown,
  X,
} from "lucide-react";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
  grade_class?: string | null;
  subject?: string | null;
  inferred_topic?: string | null;
  inferred_chapter?: string | null;
  source_pdf?: string | null;
  bloom_taxonomy?: string | null;
  difficulty?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

type QuestionType = {
  code: string;
  name: string;
  family: any;
  description: string;
  is_container: boolean;
  requires_stimulus: boolean;
  is_auto_markable: boolean;
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
  chapterLabel: string;
};

type SortKey =
  | "content"
  | "type"
  | "marks"
  | "class"
  | "subject"
  | "chapter"
  | "difficulty"
  | "bloom"
  | "date";

const PAGE_SIZE = 100;

/* -------------------------------------------------------------------------- */
/*  Sortable table header (module-scope component — never redefined in render) */
/* -------------------------------------------------------------------------- */

type SortState = {
  sortKey: SortKey;
  sortDir: "asc" | "desc";
  onToggle: (col: SortKey) => void;
};

function SortHeader({
  label,
  col,
  sort,
  className,
  align = "left",
}: {
  label: string;
  col: SortKey;
  sort: SortState;
  className?: string;
  align?: "left" | "right" | "center";
}) {
  const active = sort.sortKey === col;
  return (
    <th
      className={cn(
        "select-none px-2.5 py-2 font-semibold text-muted-foreground",
        align === "right" && "text-right",
        align === "center" && "text-center",
        className,
      )}
    >
      <button
        type="button"
        onClick={() => sort.onToggle(col)}
        className={cn(
          "inline-flex items-center gap-1 hover:text-foreground transition-colors",
          active && "text-foreground",
          align === "right" && "flex-row-reverse",
        )}
      >
        {label}
        {active ? (
          sort.sortDir === "asc" ? (
            <ArrowUp className="h-3 w-3" />
          ) : (
            <ArrowDown className="h-3 w-3" />
          )
        ) : (
          <ChevronsUpDown className="h-3 w-3 opacity-40" />
        )}
      </button>
    </th>
  );
}

/* -------------------------------------------------------------------------- */
/*  Helpers                                                                     */
/* -------------------------------------------------------------------------- */

function parseProjectName(name: string): {
  classLabel: string;
  subjectLabel: string;
} {
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
      // Prefer the native columns; fall back to the parsed project name.
      classLabel: (q.grade_class || classLabel || "").trim(),
      subjectLabel: (q.subject || subjectLabel || "").trim(),
      chapterLabel: (q.inferred_chapter || q.inferred_topic || "").trim(),
    }));
  });
}

function formatShortDate(value?: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "2-digit",
  });
}

/** Subtle, enterprise-grade tint for the difficulty badge — no loud fills. */
function difficultyTint(value?: string | null): string {
  switch ((value || "").toLowerCase()) {
    case "easy":
      return "text-emerald-700 dark:text-emerald-400 bg-emerald-500/10 border-emerald-500/20";
    case "hard":
      return "text-rose-700 dark:text-rose-400 bg-rose-500/10 border-rose-500/20";
    case "medium":
      return "text-amber-700 dark:text-amber-400 bg-amber-500/10 border-amber-500/20";
    default:
      return "text-muted-foreground bg-muted border-border";
  }
}

const ALL = "__all__";

function distinct(values: (string | null | undefined)[]): string[] {
  return Array.from(
    new Set(
      values
        .map((v) => (v ?? "").trim())
        .filter((v): v is string => v.length > 0),
    ),
  ).sort((a, b) => a.localeCompare(b));
}

/* -------------------------------------------------------------------------- */
/*  Page                                                                        */
/* -------------------------------------------------------------------------- */

export default function SavedQuestionsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [questionTypes, setQuestionTypes] = useState<QuestionType[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set());
  const [isClearing, setIsClearing] = useState(false);

  // Filters
  const [fSubject, setFSubject] = useState(ALL);
  const [fClass, setFClass] = useState(ALL);
  const [fType, setFType] = useState(ALL);
  const [fChapter, setFChapter] = useState(ALL);
  const [fDifficulty, setFDifficulty] = useState(ALL);
  const [fBloom, setFBloom] = useState(ALL);

  // Sorting + progressive rendering
  const [sortKey, setSortKey] = useState<SortKey>("date");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  /* -------------------------------------------------------------------- */
  /*  Data                                                                 */
  /* -------------------------------------------------------------------- */

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    Promise.all([
      fetchProjectsWithQuestions<Project[]>(),
      fetchQuestionTypes<QuestionType[]>()
    ])
      .then(([projData, typesData]) => {
        if (!cancelled) {
          setProjects(projData ?? []);
          setQuestionTypes(typesData ?? []);
        }
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

  const allQuestions = useMemo(() => flattenProjects(projects), [projects]);

  // Distinct filter option lists, derived from the whole dataset.
  const subjectOptions = useMemo(
    () => distinct(allQuestions.map((q) => q.subjectLabel)),
    [allQuestions],
  );
  const classOptions = useMemo(
    () => distinct(allQuestions.map((q) => q.classLabel)),
    [allQuestions],
  );
  // We map the underlying raw codes to their descriptive names using the fetched QuestionTypes.
  const typeMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const qt of questionTypes) {
      m.set(qt.code, qt.name);
    }
    return m;
  }, [questionTypes]);

  const typeOptions = useMemo(
    () => distinct(allQuestions.map((q) => q.type)),
    [allQuestions],
  );
  const chapterOptions = useMemo(
    () => distinct(allQuestions.map((q) => q.chapterLabel)),
    [allQuestions],
  );
  const difficultyOptions = useMemo(
    () => distinct(allQuestions.map((q) => q.difficulty)),
    [allQuestions],
  );
  const bloomOptions = useMemo(
    () => distinct(allQuestions.map((q) => q.bloom_taxonomy)),
    [allQuestions],
  );

  const filtered = useMemo<SavedQuestion[]>(() => {
    const term = search.trim().toLowerCase();
    const eq = (a: string, b: string) =>
      a.trim().toLowerCase() === b.trim().toLowerCase();

    return allQuestions.filter((q) => {
      if (fSubject !== ALL && !eq(q.subjectLabel, fSubject)) return false;
      if (fClass !== ALL && !eq(q.classLabel, fClass)) return false;
      if (fType !== ALL && !eq(q.type, fType)) return false;
      if (fChapter !== ALL && !eq(q.chapterLabel, fChapter)) return false;
      if (fDifficulty !== ALL && !eq(q.difficulty || "", fDifficulty))
        return false;
      if (fBloom !== ALL && !eq(q.bloom_taxonomy || "", fBloom)) return false;
      if (!term) return true;
      const haystack = [
        q.content,
        q.answer,
        q.type,
        q.projectName,
        q.classLabel,
        q.subjectLabel,
        q.chapterLabel,
        q.bloom_taxonomy,
        q.difficulty,
        ...(q.options ?? []),
      ]
        .filter((v): v is string => typeof v === "string" && v.length > 0)
        .join(" · ")
        .toLowerCase();
      return haystack.includes(term);
    });
  }, [
    allQuestions,
    search,
    fSubject,
    fClass,
    fType,
    fChapter,
    fDifficulty,
    fBloom,
  ]);

  const sorted = useMemo<SavedQuestion[]>(() => {
    const dir = sortDir === "asc" ? 1 : -1;
    const val = (q: SavedQuestion): string | number => {
      switch (sortKey) {
        case "content":
          return q.content?.toLowerCase() ?? "";
        case "type":
          return q.type?.toLowerCase() ?? "";
        case "marks":
          return q.marks ?? 0;
        case "class":
          return q.classLabel.toLowerCase();
        case "subject":
          return q.subjectLabel.toLowerCase();
        case "chapter":
          return q.chapterLabel.toLowerCase();
        case "difficulty":
          return (q.difficulty || "").toLowerCase();
        case "bloom":
          return (q.bloom_taxonomy || "").toLowerCase();
        case "date":
          return new Date(q.updated_at ?? q.created_at ?? 0).getTime();
      }
    };
    return [...filtered].sort((a, b) => {
      const av = val(a);
      const bv = val(b);
      if (av < bv) return -1 * dir;
      if (av > bv) return 1 * dir;
      return 0;
    });
  }, [filtered, sortKey, sortDir]);

  const visible = useMemo(
    () => sorted.slice(0, visibleCount),
    [sorted, visibleCount],
  );

  // Reset the render window whenever the result set changes shape.
  useEffect(() => {
    setVisibleCount(PAGE_SIZE);
  }, [search, fSubject, fClass, fType, fChapter, fDifficulty, fBloom, sortKey, sortDir]);

  const activeFilterCount =
    [fSubject, fClass, fType, fChapter, fDifficulty, fBloom].filter(
      (v) => v !== ALL,
    ).length + (search.trim() ? 1 : 0);

  /* -------------------------------------------------------------------- */
  /*  Handlers                                                             */
  /* -------------------------------------------------------------------- */

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      // Sensible default direction per column type.
      setSortDir(key === "date" || key === "marks" ? "desc" : "asc");
    }
  };

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const allVisibleSelected =
    visible.length > 0 && visible.every((q) => selectedIds.has(q.id));

  const toggleSelectAllVisible = () => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (allVisibleSelected) {
        visible.forEach((q) => next.delete(q.id));
      } else {
        visible.forEach((q) => next.add(q.id));
      }
      return next;
    });
  };

  const clearFilters = () => {
    setSearch("");
    setFSubject(ALL);
    setFClass(ALL);
    setFType(ALL);
    setFChapter(ALL);
    setFDifficulty(ALL);
    setFBloom(ALL);
  };

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
      setSelectedIds((prev) => {
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
      action: { label: "Delete", onClick: () => void deleteQuestionById(id) },
    });
  };

  const handleClearAll = async () => {
    setIsClearing(true);
    try {
      await fetchJson("/api/projects/questions/clear", { method: "DELETE" });
      setProjects([]);
      setSelectedIds(new Set());
      toast.success("All saved questions cleared.");
    } catch {
      toast.error("Failed to clear questions. Please try again.");
    } finally {
      setIsClearing(false);
    }
  };

  const handleInsertSelected = () => {
    const selected = allQuestions.filter((q) => selectedIds.has(q.id));
    const questions = selected.map((q) => ({
      content: q.content,
      type: q.type,
      options: q.options ?? [],
      answer: q.answer ?? "",
      marks: q.marks,
    }));
    useEditorStore.getState().appendQuestions(questions);
    toast.success(`Inserted ${questions.length} question(s) into the editor.`);
    setSelectedIds(new Set());
  };

  /* -------------------------------------------------------------------- */
  /*  Render                                                               */
  /* -------------------------------------------------------------------- */

  const sortState = { sortKey, sortDir, onToggle: toggleSort };

  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      {/* ── Header + toolbar ──────────────────────────────────────────── */}
      <div className="shrink-0 border-b border-border px-4 py-3 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <ListChecks className="h-5 w-5 text-indigo-500" />
            <h1 className="text-lg font-semibold tracking-tight">
              Saved Questions
            </h1>
            <span className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium tabular-nums text-muted-foreground">
              {isLoading ? "…" : allQuestions.length}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                className="h-8 w-56 pl-8 text-sm"
                placeholder="Search questions…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            {allQuestions.length > 0 && !isLoading && (
              <AlertDialog>
                <AlertDialogTrigger
                  className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border border-destructive/40 bg-background px-2.5 text-xs font-medium text-destructive transition-colors hover:bg-destructive/10 disabled:opacity-50"
                  disabled={isClearing}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  {isClearing ? "Clearing…" : "Clear all"}
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
                      onClick={() => void handleClearAll()}
                    >
                      Yes, clear all
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            )}
          </div>
        </div>

        {/* Filter row */}
        <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
          <FilterSelect
            label="Subject"
            value={fSubject}
            onChange={setFSubject}
            options={subjectOptions}
          />
          <FilterSelect
            label="Class"
            value={fClass}
            onChange={setFClass}
            options={classOptions}
          />
          <FilterSelect
            label="Type"
            value={fType}
            onChange={setFType}
            options={typeOptions}
            mapOption={(val) => typeMap.get(val) || val}
          />
          <FilterSelect
            label="Chapter"
            value={fChapter}
            onChange={setFChapter}
            options={chapterOptions}
          />
          <FilterSelect
            label="Difficulty"
            value={fDifficulty}
            onChange={setFDifficulty}
            options={difficultyOptions}
          />
          <FilterSelect
            label="Bloom"
            value={fBloom}
            onChange={setFBloom}
            options={bloomOptions}
          />
          {activeFilterCount > 0 && (
            <button
              type="button"
              onClick={clearFilters}
              className="inline-flex h-7 items-center gap-1 rounded-md px-2 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              <X className="h-3 w-3" />
              Clear ({activeFilterCount})
            </button>
          )}
          <span className="ml-auto text-xs tabular-nums text-muted-foreground">
            {isLoading
              ? ""
              : `${sorted.length} result${sorted.length === 1 ? "" : "s"}`}
          </span>
        </div>
      </div>

      {/* ── Selection action bar ──────────────────────────────────────── */}
      {selectedIds.size > 0 && (
        <div className="flex shrink-0 items-center gap-3 border-b border-indigo-200 bg-indigo-50 px-4 py-2 text-sm dark:border-indigo-900 dark:bg-indigo-950/40 sm:px-6">
          <FileText className="h-4 w-4 text-indigo-500" />
          <span className="text-indigo-700 dark:text-indigo-300">
            {selectedIds.size} selected
          </span>
          <button
            type="button"
            onClick={() => setSelectedIds(new Set())}
            className="text-xs text-indigo-600/70 hover:text-indigo-600 dark:text-indigo-400/70 dark:hover:text-indigo-400"
          >
            Clear
          </button>
          <button
            type="button"
            onClick={handleInsertSelected}
            className="ml-auto inline-flex items-center gap-1.5 rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700"
          >
            <FileText className="h-3.5 w-3.5" />
            Insert into Editor ({selectedIds.size})
          </button>
        </div>
      )}

      {/* ── Table ─────────────────────────────────────────────────────── */}
      <div className="min-h-0 flex-1 overflow-auto">
        {isLoading ? (
          <div className="space-y-px p-4">
            {Array.from({ length: 12 }).map((_, i) => (
              <div key={i} className="h-8 animate-pulse rounded bg-muted/40" />
            ))}
          </div>
        ) : sorted.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-3 py-24 text-center">
            <ListChecks className="h-10 w-10 opacity-30" />
            <p className="text-sm font-medium">
              {activeFilterCount > 0
                ? "No questions match your filters."
                : "No saved questions yet."}
            </p>
            {activeFilterCount > 0 ? (
              <button
                type="button"
                onClick={clearFilters}
                className="text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400"
              >
                Clear filters
              </button>
            ) : (
              <p className="max-w-xs text-xs text-muted-foreground">
                Generate and save questions from the Editor to see them here.
              </p>
            )}
          </div>
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead className="sticky top-0 z-10 bg-muted/80 backdrop-blur">
              <tr className="border-b border-border text-left text-xs">
                <th className="w-9 px-2.5 py-2">
                  <input
                    type="checkbox"
                    aria-label="Select all visible"
                    checked={allVisibleSelected}
                    onChange={toggleSelectAllVisible}
                    className="h-3.5 w-3.5 cursor-pointer accent-indigo-600"
                  />
                </th>
                <SortHeader label="Question" col="content" sort={sortState} className="min-w-[22rem]" />
                <SortHeader label="Type" col="type" sort={sortState} />
                <SortHeader label="Marks" col="marks" sort={sortState} align="right" />
                <SortHeader label="Class" col="class" sort={sortState} />
                <SortHeader label="Subject" col="subject" sort={sortState} />
                <SortHeader label="Chapter" col="chapter" sort={sortState} />
                <SortHeader label="Difficulty" col="difficulty" sort={sortState} />
                <SortHeader label="Bloom" col="bloom" sort={sortState} />
                <SortHeader label="Date" col="date" sort={sortState} align="right" />
                <th className="w-9 px-2.5 py-2" />
              </tr>
            </thead>
            <tbody>
              {visible.map((q) => {
                const isSelected = selectedIds.has(q.id);
                const isDeleting = deletingIds.has(q.id);
                return (
                  <tr
                    key={q.id}
                    onClick={() => toggleSelect(q.id)}
                    className={cn(
                      "cursor-pointer border-b border-border/60 transition-colors hover:bg-muted/40",
                      isSelected && "bg-indigo-50/60 dark:bg-indigo-950/30",
                      isDeleting && "pointer-events-none opacity-40",
                    )}
                  >
                    <td className="px-2.5 py-1.5 align-top">
                      <input
                        type="checkbox"
                        aria-label="Select question"
                        checked={isSelected}
                        onChange={() => toggleSelect(q.id)}
                        onClick={(e) => e.stopPropagation()}
                        className="mt-0.5 h-3.5 w-3.5 cursor-pointer accent-indigo-600"
                      />
                    </td>
                    <td className="px-2.5 py-1.5 align-top">
                      <span className="line-clamp-2 leading-snug text-foreground">
                        {q.content}
                      </span>
                    </td>
                    <td className="px-2.5 py-1.5 align-top">
                      <span className="inline-flex items-center rounded border border-border bg-muted/60 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground whitespace-nowrap">
                        {q.type ? (typeMap.get(q.type) || q.type) : "—"}
                      </span>
                    </td>
                    <td className="px-2.5 py-1.5 text-right align-top tabular-nums text-muted-foreground">
                      {q.marks}
                    </td>
                    <td className="px-2.5 py-1.5 align-top whitespace-nowrap text-muted-foreground">
                      {q.classLabel || "—"}
                    </td>
                    <td className="px-2.5 py-1.5 align-top whitespace-nowrap text-muted-foreground">
                      {q.subjectLabel || "—"}
                    </td>
                    <td className="px-2.5 py-1.5 align-top text-muted-foreground">
                      <span className="line-clamp-1">{q.chapterLabel || "—"}</span>
                    </td>
                    <td className="px-2.5 py-1.5 align-top">
                      {q.difficulty ? (
                        <span
                          className={cn(
                            "inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-medium capitalize",
                            difficultyTint(q.difficulty),
                          )}
                        >
                          {q.difficulty}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="px-2.5 py-1.5 align-top">
                      {q.bloom_taxonomy ? (
                        <span className="inline-flex items-center rounded border border-border bg-muted/60 px-1.5 py-0.5 text-[10px] font-medium capitalize text-muted-foreground whitespace-nowrap">
                          {q.bloom_taxonomy}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="px-2.5 py-1.5 text-right align-top whitespace-nowrap tabular-nums text-muted-foreground">
                      {formatShortDate(q.updated_at ?? q.created_at)}
                    </td>
                    <td className="px-2.5 py-1.5 align-top">
                      <button
                        type="button"
                        aria-label="Delete question"
                        disabled={isDeleting}
                        onClick={(e) => handleDeleteQuestion(q.id, e)}
                        className="flex h-6 w-6 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive disabled:pointer-events-none disabled:opacity-40"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}

        {/* Progressive rendering — keep large banks responsive. */}
        {!isLoading && visible.length < sorted.length && (
          <div className="flex items-center justify-center gap-3 py-4 text-xs text-muted-foreground">
            <span className="tabular-nums">
              Showing {visible.length} of {sorted.length}
            </span>
            <button
              type="button"
              onClick={() => setVisibleCount((c) => c + PAGE_SIZE)}
              className="rounded-md border border-border bg-background px-3 py-1.5 font-medium text-foreground hover:bg-accent"
            >
              Load {Math.min(PAGE_SIZE, sorted.length - visible.length)} more
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Compact filter select                                                       */
/* -------------------------------------------------------------------------- */

function FilterSelect({
  label,
  value,
  onChange,
  options,
  mapOption,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
  mapOption?: (opt: string) => string;
}) {
  const active = value !== ALL;
  return (
    <Select value={value} onValueChange={(v) => onChange(v ?? ALL)}>
      <SelectTrigger
        className={cn(
          "h-7 w-auto gap-1 px-2 text-xs",
          active && "border-indigo-500/60 text-foreground",
        )}
      >
        <span className="text-muted-foreground">{label}:</span>
        <SelectValue>{(v: string) => (v && v !== ALL ? (mapOption ? mapOption(v) : v) : "All")}</SelectValue>
      </SelectTrigger>
      <SelectContent className="max-h-72">
        <SelectItem value={ALL}>All</SelectItem>
        {options.map((opt) => (
          <SelectItem key={opt} value={opt}>
            {mapOption ? mapOption(opt) : opt}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
