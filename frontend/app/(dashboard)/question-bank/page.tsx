"use client";

import { useEffect, useMemo, useRef, useState } from "react";
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
  X,
  AlertTriangle,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { PaperFromBank } from "@/components/paper-from-bank";
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

type Paper = {
  id: string;
  title: string;
  projectName?: string;
  answerScriptId?: string | null;   // DB-stored link to the answer script paper
  created_at?: string;
  updated_at?: string;
};

type ParsedPaper = Paper & { classLabel: string; subjectLabel: string };

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function parsePaper(paper: Paper): ParsedPaper {
  const cleaned = (paper.projectName || "").trim();
  const parts = cleaned.split(/\s*[—–\-]\s*/).filter(Boolean);
  return {
    ...paper,
    classLabel: parts[0]?.trim() || "—",
    subjectLabel: parts[1]?.trim() || "—",
  };
}

function formatDate(value?: string): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatTime(value?: string): string {
  if (!value) return "";
  return new Date(value).toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
}

function dateBucketLabel(value?: string): string {
  if (!value) return "Undated";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "Undated";
  const startOfDay = (x: Date) =>
    new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const today = startOfDay(new Date());
  const that = startOfDay(d);
  const diffDays = Math.round((today - that) / 86400000);
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  return d.toLocaleDateString(undefined, {
    weekday: "long",
    month: "short",
    day: "numeric",
    year: today - that > 365 * 86400000 ? "numeric" : undefined,
  });
}

function bucketSortKey(value?: string): number {
  if (!value) return 0;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return 0;
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

/** Answer scripts are stored as separate papers; exclude them from the main list */
function isAnswerScriptPaper(paper: Paper): boolean {
  return /answer[\s\-_]*key|answer[\s\-_]*script/i.test(paper.title ?? "");
}

// ---------------------------------------------------------------------------
// Actions Modal
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
        {/* Header */}
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

        {/* Generation error banner */}
        {generationError && !isGenerating && (
          <div className="flex items-start gap-2 mx-4 mt-3 px-3 py-2.5 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg">
            <AlertTriangle className="h-3.5 w-3.5 text-red-500 shrink-0 mt-0.5" />
            <p className="text-xs text-red-600 dark:text-red-400">
              {generationError}
            </p>
          </div>
        )}

        {/* Action list */}
        <div className="py-2 flex-1 overflow-y-auto overscroll-contain">
          {actions.map((action) => (
            <div key={action.id}>
              <button
                type="button"
                disabled={action.disabled}
                onClick={() => {
                  if (!action.disabled) {
                    action.onClick();
                    // Close the modal after click unless it's the generate action
                    // (so the user can see the loading state inline)
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

        {/* Footer */}
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

export default function QuestionBankPage() {
  const router = useRouter();
  const { data: sessionData } = useSession();

  const [papers, setPapers] = useState<Paper[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [paperSearch, setPaperSearch] = useState("");
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set());
  const [isClearing, setIsClearing] = useState(false);

  // Which paper's actions modal is open
  const [activeActionsPaperId, setActiveActionsPaperId] = useState<
    string | null
  >(null);

  // Per-paper generation loading / error state (in-flight only — not persisted)
  const [generatingIds, setGeneratingIds] = useState<Set<string>>(new Set());
  const [generationErrors, setGenerationErrors] = useState<
    Record<string, string>
  >({});

  // ---- fetch on mount ----
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

  // Only show question papers in the list (answer scripts are accessed via Actions)
  const questionPapers = useMemo(
    () => parsedPapers.filter((p) => !isAnswerScriptPaper(p)),
    [parsedPapers],
  );

  const filteredPapers = useMemo<ParsedPaper[]>(() => {
    const term = paperSearch.trim().toLowerCase();
    if (!term) return questionPapers;
    return questionPapers.filter((p) => {
      const haystack = [p.title, p.projectName, p.classLabel, p.subjectLabel]
        .filter((v): v is string => typeof v === "string" && v.length > 0)
        .join(" · ")
        .toLowerCase();
      return haystack.includes(term);
    });
  }, [questionPapers, paperSearch]);

  // Group by date bucket
  const groupedPapers = useMemo(() => {
    const buckets = new Map<
      string,
      { label: string; sortKey: number; papers: ParsedPaper[] }
    >();
    for (const paper of filteredPapers) {
      const stamp = paper.updated_at ?? paper.created_at;
      const label = dateBucketLabel(stamp);
      const sortKey = bucketSortKey(stamp);
      if (!buckets.has(label)) {
        buckets.set(label, { label, sortKey, papers: [] });
      }
      buckets.get(label)!.papers.push(paper);
    }
    const groups = Array.from(buckets.values()).sort(
      (a, b) => b.sortKey - a.sortKey,
    );
    for (const group of groups) {
      group.papers.sort((a, b) => {
        const av = new Date(a.updated_at ?? a.created_at ?? 0).getTime();
        const bv = new Date(b.updated_at ?? b.created_at ?? 0).getTime();
        return bv - av;
      });
    }
    return groups;
  }, [filteredPapers]);

  // ---- actions ----
  async function deletePaperById(id: string) {
    setDeletingIds((prev) => new Set(prev).add(id));
    const paperToDelete = papers.find((p) => p.id === id);
    const asId = paperToDelete?.answerScriptId;

    try {
      await deletePaper(id);

      // Also delete the linked answer script stored in the DB
      if (asId) {
        try {
          await deletePaper(asId);
        } catch {
          // non-fatal — answer script might have already been deleted
        }
      }

      setPapers((prev) =>
        prev.filter((p) => p.id !== id && p.id !== asId),
      );

      const userId = sessionData?.user?.id;
      if (userId) {
        await deleteLiveDocument(getLiveDocumentId(userId, id)).catch(() => {});
        if (asId) {
          await deleteLiveDocument(getLiveDocumentId(userId, asId)).catch(() => {});
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
      action: {
        label: "Delete",
        onClick: () => deletePaperById(id),
      },
    });
    setActiveActionsPaperId(null);
  }

  async function handleClearAll() {
    setIsClearing(true);
    try {
      await fetchJson("/api/projects/papers/clear", { method: "DELETE" });
      setPapers([]);

      const userId = sessionData?.user?.id;
      if (userId) {
        await clearLiveDocumentsForUser(userId).catch(() => {});
      }

      toast.success("All papers cleared.");
    } catch {
      toast.error("Failed to clear papers.");
    } finally {
      setIsClearing(false);
    }
  }

  async function handleGenerateAnswerScript(paperId: string) {
    // Clear any previous error for this paper
    setGenerationErrors((prev) => {
      const next = { ...prev };
      delete next[paperId];
      return next;
    });

    setGeneratingIds((prev) => new Set(prev).add(paperId));

    try {
      const result = await generateAnswerScript(paperId);

      // The backend has already saved answerScriptId on the paper row.
      // Update local state so the UI reflects the new link immediately
      // without needing a full refetch.
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

  // ---- render helpers ----
  const activePaper = activeActionsPaperId
    ? (parsedPapers.find((p) => p.id === activeActionsPaperId) ?? null)
    : null;

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-6 bg-background min-h-full">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-bold leading-tight">Question Paper</h1>
            {!isLoading && questionPapers.length > 0 && (
              <span className="inline-flex items-center justify-center h-6 min-w-6 px-2 rounded-full bg-indigo-100 text-indigo-600 text-xs font-bold dark:bg-indigo-950 dark:text-indigo-400">
                {questionPapers.length}
              </span>
            )}
          </div>
          <p className="text-sm text-muted-foreground mt-0.5">
            Browse and open your saved exam papers in the editor.
          </p>
        </div>

        <div className="flex w-full items-center gap-3 sm:w-auto">
          {/* Search */}
          <div className="relative flex-1 sm:flex-none">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
            <Input
              className="w-full sm:w-64 pl-9"
              placeholder="Search papers…"
              value={paperSearch}
              onChange={(e) => setPaperSearch(e.target.value)}
            />
          </div>

          {/* Clear All */}
          {!isLoading && papers.length > 0 && (
            <AlertDialog>
              <AlertDialogTrigger
                className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-destructive/40 px-3 py-2 text-sm font-medium text-destructive hover:bg-destructive/10 transition-colors disabled:opacity-50"
                disabled={isClearing}
              >
                <Trash2 className="h-4 w-4" />
                Clear All
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

      {/* ── Loading skeletons ─────────────────────────────────────────────── */}
      {isLoading && (
        <div className="flex flex-col divide-y divide-border rounded-xl border bg-card">
          {Array.from({ length: 5 }).map((_, i) => (
            <div
              key={i}
              className="animate-pulse flex items-center gap-4 px-5 py-4"
            >
              <div className="h-9 w-9 rounded-lg bg-muted/60 shrink-0" />
              <div className="flex-1 space-y-2">
                <div className="h-4 w-1/2 rounded bg-muted/60" />
                <div className="h-3 w-3/4 rounded bg-muted/40" />
              </div>
              <div className="h-8 w-24 rounded-lg bg-muted/40 shrink-0" />
              <div className="h-8 w-8 rounded-lg bg-muted/40 shrink-0" />
            </div>
          ))}
        </div>
      )}

      {/* ── Empty state ───────────────────────────────────────────────────── */}
      {!isLoading && questionPapers.length === 0 && (
        <div className="flex flex-col items-center justify-center gap-4 rounded-xl border border-dashed py-20 text-center">
          <BookOpen className="h-10 w-10 opacity-30" />
          <div>
            <p className="font-semibold text-foreground">
              {paperSearch.trim()
                ? "No papers match your search."
                : "No saved papers yet."}
            </p>
            {!paperSearch.trim() && (
              <p className="text-sm text-muted-foreground mt-1">
                Save a paper from the Editor to see it here.
              </p>
            )}
          </div>
        </div>
      )}

      {/* Reuse path: build a new paper from questions already banked, without
          re-uploading a chapter or re-generating its questions. */}
      <PaperFromBank />

      {/* ── Paper list ───────────────────────────────────────────────────── */}
      {!isLoading && filteredPapers.length > 0 && (
        <div className="space-y-8">
          {groupedPapers.map((group) => (
            <section key={group.label} className="space-y-3">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {group.label}
              </h2>

              <div className="flex flex-col divide-y divide-border rounded-xl border border-border bg-card">
                {group.papers.map((paper) => {
                  const isDeleting = deletingIds.has(paper.id);
                  const isGenerating = generatingIds.has(paper.id);
                  const hasAnswerScript = Boolean(paper.answerScriptId);
                  const stamp = paper.updated_at ?? paper.created_at;

                  return (
                    <article
                      key={paper.id}
                      className={cn(
                        "group flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:gap-6 transition-colors",
                        isDeleting && "opacity-50 pointer-events-none",
                      )}
                    >
                      {/* Left: icon + text (clickable to open) */}
                      <div
                        className="flex items-start gap-3 flex-1 min-w-0 cursor-pointer hover:opacity-80 transition-opacity"
                        onClick={() =>
                          router.push(`/editor?paperId=${paper.id}`)
                        }
                      >
                        <div className="p-2 rounded-lg bg-indigo-500/10 shrink-0">
                          <FileText className="h-5 w-5 text-indigo-500" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="text-base font-semibold text-foreground truncate leading-snug">
                            {paper.title}
                          </p>
                          <div className="flex items-center flex-wrap text-xs text-muted-foreground mt-0.5">
                            <span className="font-medium text-foreground">
                              {paper.classLabel}
                            </span>
                            <span className="mx-1.5 opacity-50">|</span>
                            <span className="font-medium text-foreground">
                              {paper.subjectLabel}
                            </span>
                            <span className="mx-1.5 opacity-50">|</span>
                            {formatDate(stamp)}
                            {formatTime(stamp) && (
                              <>
                                <span className="mx-1.5 opacity-50">|</span>
                                {formatTime(stamp)}
                              </>
                            )}
                          </div>
                          {/* Answer script status badge */}
                          {hasAnswerScript && !isGenerating && (
                            <span className="inline-flex items-center gap-1 mt-1.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800 rounded px-1.5 py-0.5">
                              <Key className="h-2.5 w-2.5" />
                              Answer Script Ready
                            </span>
                          )}
                          {isGenerating && (
                            <span className="inline-flex items-center gap-1 mt-1.5 text-[10px] font-semibold uppercase tracking-wide text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded px-1.5 py-0.5">
                              <Loader2 className="h-2.5 w-2.5 animate-spin" />
                              Generating Answer Script…
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Right: Actions + Delete */}
                      <div className="flex items-center gap-2 shrink-0">
                        <button
                          type="button"
                          onClick={() => setActiveActionsPaperId(paper.id)}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent hover:border-primary/40 transition-all"
                        >
                          <MoreHorizontal className="h-3.5 w-3.5" />
                          Actions
                        </button>

                        <button
                          type="button"
                          aria-label="Delete paper"
                          onClick={() => handleDeletePaper(paper.id)}
                          className="p-1.5 rounded-lg text-muted-foreground hover:text-red-500 hover:bg-red-500/10 transition-colors"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </article>
                  );
                })}
              </div>
            </section>
          ))}
        </div>
      )}

      {/* ── Actions Modal ─────────────────────────────────────────────────── */}
      {activePaper && (
        <ActionsModal
          paper={activePaper}
          answerScriptId={activePaper.answerScriptId ?? null}
          isGenerating={generatingIds.has(activePaper.id)}
          generationError={generationErrors[activePaper.id]}
          onClose={() => setActiveActionsPaperId(null)}
          onViewPaper={() => {
            router.push(`/editor?paperId=${activePaper.id}`);
          }}
          onGenerateAnswerScript={() => {
            handleGenerateAnswerScript(activePaper.id);
            // Keep modal open — user sees live loading badge on the row
          }}
          onViewAnswerScript={() => {
            if (activePaper.answerScriptId) {
              router.push(`/editor?paperId=${activePaper.answerScriptId}`);
            }
          }}
          onExportPDF={() => {
            router.push(
              `/editor?paperId=${activePaper.id}&action=export-pdf`,
            );
          }}
          onExportWord={() => {
            router.push(
              `/editor?paperId=${activePaper.id}&action=export-docx`,
            );
          }}
          onExportAnswerScriptPDF={() => {
            if (activePaper.answerScriptId) {
              router.push(
                `/editor?paperId=${activePaper.answerScriptId}&action=export-pdf&exportType=answer_script`,
              );
            }
          }}
          onDelete={() => handleDeletePaper(activePaper.id)}
        />
      )}
    </div>
  );
}
