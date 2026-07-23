"use client";

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchPapers,
  deletePaper,
  fetchJson,
  generateAnswerScript,
} from "@/lib/api-client";
import {
  BookOpen,
  FileText,
  Search,
  Trash2,
  Loader2,
  MoreHorizontal,
  Eye,
  Key,
  RefreshCcw,
  FileDown,
  Printer,
  X,
  AlertTriangle,
  ChevronRight,
  ArrowUp,
  ArrowDown,
  ChevronsUpDown,
} from "lucide-react";
import { Input } from "@/components/ui/input";
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
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { useSession } from "@/lib/auth-client";
import {
  deleteLiveDocument,
  clearLiveDocumentsForUser,
  getLiveDocumentId,
} from "@/lib/live-document-db";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type PaperSet = {
  id: string;
  label: string;
  order?: number;
};

type Paper = {
  id: string;
  title: string;
  projectName?: string;
  subject?: string | null;
  gradeClass?: string | null;
  board?: string | null;
  answerScriptId?: string | null;
  created_at?: string;
  updated_at?: string;
  sets?: PaperSet[];
};

type NormalizedSet = { id: string; label: string };

type ParsedPaper = Paper & {
  classLabel: string;
  subjectLabel: string;
  boardLabel: string;
  setList: NormalizedSet[];
};

type SortKey = "title" | "class" | "subject" | "board" | "sets" | "updated";

type SortState = {
  sortKey: SortKey;
  sortDir: "asc" | "desc";
  onToggle: (col: SortKey) => void;
};

// Module-scope so it is never redefined during render (react-hooks/static-components).
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
        "select-none px-3 py-2 font-semibold text-muted-foreground",
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

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function normalizeSetLabel(label: string, index: number): string {
  const trailing = (label || "").trim().match(/([A-Za-z])$/);
  if (trailing) return trailing[1].toUpperCase();
  return String.fromCharCode(65 + index); // A, B, C…
}

/** Legacy single-content papers have no PaperSet rows — treat them as Set A. */
function paperSetList(paper: Paper): NormalizedSet[] {
  const sets = paper.sets ?? [];
  if (sets.length === 0) return [{ id: `${paper.id}-A`, label: "A" }];
  return [...sets]
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
    .map((s, i) => ({ id: s.id, label: normalizeSetLabel(s.label, i) }));
}

function parsePaper(paper: Paper): ParsedPaper {
  let c = (paper.gradeClass || "").trim();
  let s = (paper.subject || "").trim();
  if (!c && !s && paper.projectName) {
    const parts = paper.projectName.trim().split(/\s*[—–\-]\s*/).filter(Boolean);
    c = parts[0]?.trim() || "";
    s = parts[1]?.trim() || "";
  }
  return {
    ...paper,
    classLabel: c || "—",
    subjectLabel: s || "—",
    boardLabel: (paper.board || "").trim() || "—",
    setList: paperSetList(paper),
  };
}

function formatDateTime(value?: string): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

/** Answer scripts are stored as separate papers; exclude them from the list. */
function isAnswerScriptPaper(paper: Paper): boolean {
  return /answer[\s\-_]*key|answer[\s\-_]*script/i.test(paper.title ?? "");
}

// ---------------------------------------------------------------------------
// Actions Modal (paper-level actions)
// ---------------------------------------------------------------------------

interface ActionsModalProps {
  paper: ParsedPaper;
  answerScriptId: string | null;
  isGenerating: boolean;
  generationError?: string;
  onClose: () => void;
  onViewPaper: () => void;
  onGenerateAnswerScript: () => void;
  onViewAnswerScript: () => void;
  onExportPDF: () => void;
  onExportWord: () => void;
  onExportAnswerScriptPDF: () => void;
  onDelete: () => void;
}

function ActionsModal({
  paper,
  answerScriptId,
  isGenerating,
  generationError,
  onClose,
  onViewPaper,
  onGenerateAnswerScript,
  onViewAnswerScript,
  onExportPDF,
  onExportWord,
  onExportAnswerScriptPDF,
  onDelete,
}: ActionsModalProps) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const hasAnswerScript = Boolean(answerScriptId);

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === overlayRef.current) onClose();
  };

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  type ActionItem = {
    id: string;
    icon: React.ReactNode;
    label: string;
    sublabel?: string;
    disabled?: boolean;
    danger?: boolean;
    loading?: boolean;
    onClick: () => void;
    dividerAfter?: boolean;
  };

  const actions: ActionItem[] = [
    {
      id: "view",
      icon: <Eye className="h-4 w-4" />,
      label: "View Question Paper",
      sublabel: "Open in editor",
      onClick: onViewPaper,
    },
    {
      id: "generate",
      icon: isGenerating ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : hasAnswerScript ? (
        <RefreshCcw className="h-4 w-4" />
      ) : (
        <Key className="h-4 w-4" />
      ),
      label: hasAnswerScript
        ? "Regenerate Answer Script"
        : "Generate Answer Script",
      sublabel: isGenerating
        ? "Generating, please wait…"
        : hasAnswerScript
        ? "Override existing answer script with a new one"
        : "AI-generate an answer key for this paper",
      disabled: isGenerating,
      loading: isGenerating,
      onClick: onGenerateAnswerScript,
      dividerAfter: true,
    },
    {
      id: "view-answer",
      icon: <Eye className="h-4 w-4" />,
      label: "View Answer Script",
      sublabel: hasAnswerScript
        ? "Open generated answer key"
        : "Generate answer script first",
      disabled: !hasAnswerScript || isGenerating,
      onClick: onViewAnswerScript,
      dividerAfter: true,
    },
    {
      id: "export-pdf",
      icon: <FileDown className="h-4 w-4" />,
      label: "Export as PDF",
      sublabel: "Download question paper as PDF",
      onClick: onExportPDF,
    },
    {
      id: "export-word",
      icon: <FileDown className="h-4 w-4" />,
      label: "Export as Word Document",
      sublabel: "Download question paper as .docx",
      onClick: onExportWord,
    },
    {
      id: "export-answer-pdf",
      icon: <FileDown className="h-4 w-4" />,
      label: "Export Answer Script as PDF",
      sublabel: hasAnswerScript
        ? "Download answer key as PDF"
        : "Generate answer script first",
      disabled: !hasAnswerScript || isGenerating,
      onClick: onExportAnswerScriptPDF,
      dividerAfter: true,
    },
    {
      id: "delete",
      icon: <Trash2 className="h-4 w-4" />,
      label: "Delete Paper",
      sublabel: hasAnswerScript
        ? "Also removes the linked answer script"
        : undefined,
      danger: true,
      onClick: onDelete,
    },
  ];

  return (
    <div
      ref={overlayRef}
      onClick={handleBackdropClick}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
    >
      <div
        className="relative flex max-h-[calc(100dvh-2rem)] w-full max-w-sm flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex shrink-0 items-start justify-between px-5 py-4 border-b border-border">
          <div className="flex-1 min-w-0">
            <h2 className="text-base font-semibold text-foreground">Actions</h2>
            <p className="text-xs text-muted-foreground mt-0.5 truncate">
              {paper.title}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="ml-3 p-1.5 rounded-lg text-muted-foreground hover:bg-accent hover:text-foreground transition-colors shrink-0"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {generationError && !isGenerating && (
          <div className="flex items-start gap-2 mx-4 mt-3 px-3 py-2.5 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg">
            <AlertTriangle className="h-3.5 w-3.5 text-red-500 shrink-0 mt-0.5" />
            <p className="text-xs text-red-600 dark:text-red-400">
              {generationError}
            </p>
          </div>
        )}

        <div className="py-2 flex-1 overflow-y-auto overscroll-contain">
          {actions.map((action) => (
            <div key={action.id}>
              <button
                type="button"
                disabled={action.disabled}
                onClick={() => {
                  if (!action.disabled) {
                    action.onClick();
                    if (action.id !== "generate") onClose();
                  }
                }}
                className={cn(
                  "w-full flex items-center gap-3.5 px-5 py-3 text-left transition-colors",
                  "disabled:opacity-40 disabled:cursor-not-allowed",
                  action.danger
                    ? "text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30 disabled:hover:bg-transparent"
                    : "text-foreground hover:bg-accent disabled:hover:bg-transparent",
                  action.loading && "cursor-wait",
                )}
              >
                <span
                  className={cn(
                    "shrink-0",
                    action.danger
                      ? "text-red-500"
                      : action.disabled
                      ? "text-muted-foreground/50"
                      : "text-muted-foreground",
                  )}
                >
                  {action.icon}
                </span>
                <span className="flex-1 min-w-0">
                  <span
                    className={cn(
                      "block text-sm font-medium leading-snug",
                      action.danger && "text-red-500",
                    )}
                  >
                    {action.label}
                  </span>
                  {action.sublabel && (
                    <span
                      className={cn(
                        "block text-[11px] leading-tight mt-0.5",
                        action.danger
                          ? "text-red-400/80"
                          : "text-muted-foreground",
                      )}
                    >
                      {action.sublabel}
                    </span>
                  )}
                </span>
              </button>
              {action.dividerAfter && (
                <div className="mx-5 border-t border-border/60" />
              )}
            </div>
          ))}
        </div>

        <div className="px-5 py-3 border-t border-border flex justify-end shrink-0">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 text-sm font-medium rounded-lg border border-border bg-background hover:bg-accent text-foreground transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function QuestionPaperPage() {
  const router = useRouter();
  const { data: sessionData } = useSession();

  const [papers, setPapers] = useState<Paper[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set());
  const [isClearing, setIsClearing] = useState(false);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const [activeActionsPaperId, setActiveActionsPaperId] = useState<
    string | null
  >(null);
  const [generatingIds, setGeneratingIds] = useState<Set<string>>(new Set());
  const [generationErrors, setGenerationErrors] = useState<
    Record<string, string>
  >({});

  const [sortKey, setSortKey] = useState<SortKey>("updated");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  // ---- fetch ----
  const loadPapers = () => {
    setIsLoading(true);
    fetchPapers<Paper[]>()
      .then((data) => setPapers(data ?? []))
      .catch(() => toast.error("Failed to load saved papers."))
      .finally(() => setIsLoading(false));
  };

  useEffect(() => {
    loadPapers();
  }, []);

  // ---- derived ----
  const parsedPapers = useMemo<ParsedPaper[]>(
    () => papers.map(parsePaper),
    [papers],
  );

  const questionPapers = useMemo(
    () => parsedPapers.filter((p) => !isAnswerScriptPaper(p)),
    [parsedPapers],
  );

  const filtered = useMemo<ParsedPaper[]>(() => {
    const term = search.trim().toLowerCase();
    if (!term) return questionPapers;
    return questionPapers.filter((p) => {
      const haystack = [
        p.title,
        p.projectName,
        p.classLabel,
        p.subjectLabel,
        p.boardLabel,
      ]
        .filter((v): v is string => typeof v === "string" && v.length > 0)
        .join(" · ")
        .toLowerCase();
      return haystack.includes(term);
    });
  }, [questionPapers, search]);

  const sorted = useMemo<ParsedPaper[]>(() => {
    const dir = sortDir === "asc" ? 1 : -1;
    const val = (p: ParsedPaper): string | number => {
      switch (sortKey) {
        case "title":
          return p.title?.toLowerCase() ?? "";
        case "class":
          return p.classLabel.toLowerCase();
        case "subject":
          return p.subjectLabel.toLowerCase();
        case "board":
          return p.boardLabel.toLowerCase();
        case "sets":
          return p.setList.length;
        case "updated":
          return new Date(p.updated_at ?? p.created_at ?? 0).getTime();
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

  // ---- actions ----
  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortDir(key === "updated" || key === "sets" ? "desc" : "asc");
    }
  };

  const toggleExpand = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  async function deletePaperById(id: string) {
    setDeletingIds((prev) => new Set(prev).add(id));
    const paperToDelete = papers.find((p) => p.id === id);
    const asId = paperToDelete?.answerScriptId;
    try {
      await deletePaper(id);
      if (asId) {
        try {
          await deletePaper(asId);
        } catch {
          /* non-fatal */
        }
      }
      setPapers((prev) => prev.filter((p) => p.id !== id && p.id !== asId));
      const userId = sessionData?.user?.id;
      if (userId) {
        await deleteLiveDocument(getLiveDocumentId(userId, id)).catch(() => {});
        if (asId) {
          await deleteLiveDocument(getLiveDocumentId(userId, asId)).catch(
            () => {},
          );
        }
      }
      toast.success("Paper deleted.");
    } catch {
      toast.error("Failed to delete paper.");
    } finally {
      setDeletingIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  }

  function handleDeletePaper(id: string) {
    const paper = papers.find((p) => p.id === id);
    toast.warning("Delete this paper?", {
      description: paper?.answerScriptId
        ? "The linked answer script will also be deleted."
        : undefined,
      action: { label: "Delete", onClick: () => deletePaperById(id) },
    });
    setActiveActionsPaperId(null);
  }

  async function handleClearAll() {
    setIsClearing(true);
    try {
      await fetchJson("/api/projects/papers/clear", { method: "DELETE" });
      setPapers([]);
      const userId = sessionData?.user?.id;
      if (userId) await clearLiveDocumentsForUser(userId).catch(() => {});
      toast.success("All papers cleared.");
    } catch {
      toast.error("Failed to clear papers.");
    } finally {
      setIsClearing(false);
    }
  }

  async function handleGenerateAnswerScript(paperId: string) {
    setGenerationErrors((prev) => {
      const next = { ...prev };
      delete next[paperId];
      return next;
    });
    setGeneratingIds((prev) => new Set(prev).add(paperId));
    try {
      const result = await generateAnswerScript(paperId);
      setPapers((prev) =>
        prev.map((p) =>
          p.id === paperId
            ? { ...p, answerScriptId: result.answer_script_paper_id }
            : p,
        ),
      );
      toast.success("Answer script generated and saved!");
    } catch (err: any) {
      const errorMessage =
        err?.message || "Failed to generate. Please try again.";
      setGenerationErrors((prev) => ({ ...prev, [paperId]: errorMessage }));
      toast.error(errorMessage);
    } finally {
      setGeneratingIds((prev) => {
        const next = new Set(prev);
        next.delete(paperId);
        return next;
      });
    }
  }

  // Per-set actions all route through the editor, which honours ?set= and
  // ?action= (see editor/page.tsx). Preview opens the set; Export/Print run
  // the existing client-side pipeline against that set's rendered A4 page.
  const openSet = (
    paperId: string,
    label: string,
    action?: "export-pdf" | "print",
  ) => {
    const params = new URLSearchParams({ paperId, set: label });
    if (action) params.set("action", action);
    router.push(`/editor?${params.toString()}`);
  };

  const activePaper = activeActionsPaperId
    ? (parsedPapers.find((p) => p.id === activeActionsPaperId) ?? null)
    : null;

  const sortState = { sortKey, sortDir, onToggle: toggleSort };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      {/* ── Header + toolbar ──────────────────────────────────────────── */}
      <div className="shrink-0 border-b border-border px-4 py-3 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <BookOpen className="h-5 w-5 text-indigo-500" />
            <h1 className="text-lg font-semibold tracking-tight">
              Question Paper
            </h1>
            <span className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium tabular-nums text-muted-foreground">
              {isLoading ? "…" : questionPapers.length}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                className="h-8 w-56 pl-8 text-sm"
                placeholder="Search papers…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            {!isLoading && papers.length > 0 && (
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
                    <AlertDialogTitle>Clear all saved papers?</AlertDialogTitle>
                    <AlertDialogDescription>
                      This will permanently delete every saved paper and its
                      generated answer scripts. This action cannot be undone.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction
                      className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                      onClick={handleClearAll}
                    >
                      Yes, clear all
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            )}
          </div>
        </div>
      </div>

      {/* ── Table ─────────────────────────────────────────────────────── */}
      <div className="min-h-0 flex-1 overflow-auto">
        {isLoading ? (
          <div className="space-y-px p-4">
            {Array.from({ length: 10 }).map((_, i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-muted/40" />
            ))}
          </div>
        ) : sorted.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-3 py-24 text-center">
            <BookOpen className="h-10 w-10 opacity-30" />
            <p className="text-sm font-medium">
              {search.trim()
                ? "No papers match your search."
                : "No saved papers yet."}
            </p>
            {!search.trim() && (
              <p className="max-w-xs text-xs text-muted-foreground">
                Save a paper from the Editor, or assemble one from the Build
                Paper workspace.
              </p>
            )}
          </div>
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead className="sticky top-0 z-10 bg-muted/80 backdrop-blur">
              <tr className="border-b border-border text-left text-xs">
                <th className="w-8 px-2 py-2" />
                <SortHeader label="Title" col="title" sort={sortState} className="min-w-[16rem]" />
                <SortHeader label="Class" col="class" sort={sortState} />
                <SortHeader label="Subject" col="subject" sort={sortState} />
                <SortHeader label="Board" col="board" sort={sortState} />
                <SortHeader label="Sets" col="sets" sort={sortState} />
                <SortHeader label="Last Updated" col="updated" sort={sortState} align="right" />
                <th className="px-3 py-2 text-right font-semibold text-muted-foreground">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((paper) => {
                const isDeleting = deletingIds.has(paper.id);
                const isGenerating = generatingIds.has(paper.id);
                const hasAnswerScript = Boolean(paper.answerScriptId);
                const isExpanded = expandedIds.has(paper.id);
                const stamp = paper.updated_at ?? paper.created_at;

                return (
                  <Fragment key={paper.id}>
                    <tr
                      className={cn(
                        "group border-b border-border/60 transition-colors hover:bg-muted/40",
                        isExpanded && "bg-muted/30",
                        isDeleting && "pointer-events-none opacity-40",
                      )}
                    >
                      {/* Expand toggle */}
                      <td className="px-2 py-2 align-middle">
                        <button
                          type="button"
                          aria-label={isExpanded ? "Collapse" : "Expand sets"}
                          onClick={() => toggleExpand(paper.id)}
                          className="flex h-6 w-6 items-center justify-center rounded text-muted-foreground hover:bg-accent hover:text-foreground"
                        >
                          <ChevronRight
                            className={cn(
                              "h-4 w-4 transition-transform",
                              isExpanded && "rotate-90",
                            )}
                          />
                        </button>
                      </td>

                      {/* Title (opens editor) */}
                      <td className="px-3 py-2 align-middle">
                        <button
                          type="button"
                          onClick={() =>
                            router.push(`/editor?paperId=${paper.id}`)
                          }
                          className="flex items-center gap-2 text-left"
                        >
                          <FileText className="h-4 w-4 shrink-0 text-indigo-500" />
                          <span className="font-medium text-foreground hover:underline">
                            {paper.title}
                          </span>
                          {hasAnswerScript && !isGenerating && (
                            <span
                              title="Answer script ready"
                              className="inline-flex items-center gap-0.5 rounded border border-emerald-500/30 bg-emerald-500/10 px-1 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-emerald-600 dark:text-emerald-400"
                            >
                              <Key className="h-2.5 w-2.5" />
                              Key
                            </span>
                          )}
                          {isGenerating && (
                            <span className="inline-flex items-center gap-0.5 rounded border border-amber-500/30 bg-amber-500/10 px-1 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-amber-600 dark:text-amber-400">
                              <Loader2 className="h-2.5 w-2.5 animate-spin" />
                              Gen…
                            </span>
                          )}
                        </button>
                      </td>

                      <td className="px-3 py-2 align-middle whitespace-nowrap text-muted-foreground">
                        {paper.classLabel}
                      </td>
                      <td className="px-3 py-2 align-middle whitespace-nowrap text-muted-foreground">
                        {paper.subjectLabel}
                      </td>
                      <td className="px-3 py-2 align-middle whitespace-nowrap text-muted-foreground">
                        {paper.boardLabel}
                      </td>

                      {/* Sets — inline badges */}
                      <td className="px-3 py-2 align-middle">
                        <div className="flex items-center gap-1">
                          {paper.setList.map((s) => (
                            <span
                              key={s.id}
                              className="inline-flex h-5 min-w-5 items-center justify-center rounded border border-indigo-500/30 bg-indigo-500/10 px-1.5 text-[10px] font-semibold text-indigo-600 dark:text-indigo-400"
                            >
                              {s.label}
                            </span>
                          ))}
                        </div>
                      </td>

                      <td className="px-3 py-2 text-right align-middle whitespace-nowrap tabular-nums text-muted-foreground">
                        {formatDateTime(stamp)}
                      </td>

                      {/* Actions (paper-level) */}
                      <td className="px-3 py-2 text-right align-middle">
                        <button
                          type="button"
                          onClick={() => setActiveActionsPaperId(paper.id)}
                          className="inline-flex items-center gap-1 rounded-md border border-border bg-background px-2 py-1 text-xs font-medium text-foreground hover:bg-accent hover:border-primary/40"
                        >
                          <MoreHorizontal className="h-3.5 w-3.5" />
                          Actions
                        </button>
                      </td>
                    </tr>

                    {/* Expanded per-set rows */}
                    {isExpanded && (
                      <tr className="border-b border-border/60 bg-muted/20">
                        <td />
                        <td colSpan={7} className="px-3 py-2">
                          <div className="flex flex-col gap-1.5">
                            <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                              {paper.setList.length} set
                              {paper.setList.length === 1 ? "" : "s"} — each with
                              independent preview / export / print
                            </span>
                            {paper.setList.map((s) => (
                              <div
                                key={s.id}
                                className="flex items-center gap-3 rounded-md border border-border bg-background px-3 py-1.5"
                              >
                                <span className="inline-flex h-5 min-w-5 items-center justify-center rounded border border-indigo-500/30 bg-indigo-500/10 px-1.5 text-[10px] font-semibold text-indigo-600 dark:text-indigo-400">
                                  {s.label}
                                </span>
                                <span className="text-xs font-medium text-foreground">
                                  Set {s.label}
                                </span>
                                <div className="ml-auto flex items-center gap-1">
                                  <SetActionButton
                                    icon={<Eye className="h-3.5 w-3.5" />}
                                    label="Preview"
                                    onClick={() => openSet(paper.id, s.label)}
                                  />
                                  <SetActionButton
                                    icon={<FileDown className="h-3.5 w-3.5" />}
                                    label="Export"
                                    onClick={() =>
                                      openSet(paper.id, s.label, "export-pdf")
                                    }
                                  />
                                  <SetActionButton
                                    icon={<Printer className="h-3.5 w-3.5" />}
                                    label="Print"
                                    onClick={() =>
                                      openSet(paper.id, s.label, "print")
                                    }
                                  />
                                </div>
                              </div>
                            ))}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* ── Actions Modal ─────────────────────────────────────────────── */}
      {activePaper && (
        <ActionsModal
          paper={activePaper}
          answerScriptId={activePaper.answerScriptId ?? null}
          isGenerating={generatingIds.has(activePaper.id)}
          generationError={generationErrors[activePaper.id]}
          onClose={() => setActiveActionsPaperId(null)}
          onViewPaper={() => router.push(`/editor?paperId=${activePaper.id}`)}
          onGenerateAnswerScript={() =>
            handleGenerateAnswerScript(activePaper.id)
          }
          onViewAnswerScript={() => {
            if (activePaper.answerScriptId)
              router.push(`/editor?paperId=${activePaper.answerScriptId}`);
          }}
          onExportPDF={() =>
            router.push(`/editor?paperId=${activePaper.id}&action=export-pdf`)
          }
          onExportWord={() =>
            router.push(`/editor?paperId=${activePaper.id}&action=export-docx`)
          }
          onExportAnswerScriptPDF={() => {
            if (activePaper.answerScriptId)
              router.push(
                `/editor?paperId=${activePaper.answerScriptId}&action=export-pdf&exportType=answer_script`,
              );
          }}
          onDelete={() => handleDeletePaper(activePaper.id)}
        />
      )}
    </div>
  );
}

function SetActionButton({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1 rounded-md border border-border bg-background px-2 py-1 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
    >
      {icon}
      {label}
    </button>
  );
}
