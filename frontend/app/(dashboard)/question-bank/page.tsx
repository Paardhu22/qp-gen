"use client";

import { useEffect, useMemo, useState } from "react";
import {
  fetchPapers,
  deletePaper,
  fetchJson,
  generateAnswerScript,
} from "@/lib/api-client";
// getPaperAction unwraps the paper's `sets[]` array to the Set A content the
// preview needs (the pool refactor moved content out of a top-level field).
import { getPaperAction } from "@/actions/savePaper";
import {
  BookOpen,
  FileText,
  Search,
  Trash2,
  Loader2,
  Eye,
  Key,
  RefreshCcw,
  FileDown,
  AlertTriangle,
  ArrowLeft,
  Pencil,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { PaperFromBank } from "@/components/paper-from-bank";
import { PaperPreview } from "@/components/paper-preview";
import {
  computePaperBreakdown,
  questionTypeLabel,
  type PaperBreakdown,
} from "@/lib/paper-breakdown";
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
  answerScriptId?: string | null; // DB-stored link to the answer script paper
  created_at?: string;
  updated_at?: string;
};

type ParsedPaper = Paper & { classLabel: string; subjectLabel: string };

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function parsePaper(paper: Paper): ParsedPaper {
  // Use native fields if available; fallback to parsing projectName
  let c = (paper as any).gradeClass || "";
  let s = (paper as any).subject || "";
  if (!c && !s && paper.projectName) {
    const cleaned = paper.projectName.trim();
    const parts = cleaned.split(/\s*[—–\-]\s*/).filter(Boolean);
    c = parts[0]?.trim() || "—";
    s = parts[1]?.trim() || "—";
  }
  return {
    ...paper,
    classLabel: c || "—",
    subjectLabel: s || "—",
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
// Split view — breakdown (left) + preview (right)
// ---------------------------------------------------------------------------

interface PaperDetailSplitProps {
  paper: ParsedPaper;
  isGenerating: boolean;
  generationError?: string;
  onBack: () => void;
  onOpenEditor: () => void;
  onGenerateAnswerScript: () => void;
  onViewAnswerScript: () => void;
  onExportPDF: () => void;
  onExportWord: () => void;
  onExportAnswerScriptPDF: () => void;
  onDelete: () => void;
}

function StatTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-border bg-card px-3 py-2.5">
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="text-xl font-semibold leading-tight text-foreground">
        {value}
      </div>
    </div>
  );
}

function PaperDetailSplit({
  paper,
  isGenerating,
  generationError,
  onBack,
  onOpenEditor,
  onGenerateAnswerScript,
  onViewAnswerScript,
  onExportPDF,
  onExportWord,
  onExportAnswerScriptPDF,
  onDelete,
}: PaperDetailSplitProps) {
  const hasAnswerScript = Boolean(paper.answerScriptId);

  // Preview can show the question paper or (if generated) its answer script.
  const [previewTarget, setPreviewTarget] = useState<"paper" | "answer">("paper");

  // Content caches keyed by the paper we fetch (question paper + answer script).
  const [paperContent, setPaperContent] = useState<string | undefined>(undefined);
  const [answerContent, setAnswerContent] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Load the question paper's content when the selected paper changes.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    setPreviewTarget("paper");
    setAnswerContent(undefined);
    getPaperAction(paper.id)
      .then((data) => {
        if (!cancelled) setPaperContent(data?.content ?? "");
      })
      .catch(() => {
        if (!cancelled) setLoadError("Failed to load paper content.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [paper.id]);

  // Lazily load the answer script content the first time it's previewed.
  useEffect(() => {
    if (previewTarget !== "answer" || !paper.answerScriptId) return;
    if (answerContent !== undefined) return;
    let cancelled = false;
    getPaperAction(paper.answerScriptId)
      .then((data) => {
        if (!cancelled) setAnswerContent(data?.content ?? "");
      })
      .catch(() => {
        if (!cancelled) toast.error("Failed to load answer script.");
      });
    return () => {
      cancelled = true;
    };
  }, [previewTarget, paper.answerScriptId, answerContent]);

  // The breakdown always describes the QUESTION paper, not the answer script.
  const breakdown: PaperBreakdown = useMemo(
    () => computePaperBreakdown(paperContent),
    [paperContent],
  );

  const previewContent = previewTarget === "answer" ? answerContent : paperContent;

  const typeEntries = Object.entries(breakdown.typeDistribution).sort(
    (a, b) => b[1] - a[1],
  );

  return (
    <div className="flex h-full flex-col bg-background">
      {/* Top bar */}
      <div className="flex shrink-0 items-center gap-3 border-b border-border px-4 py-3 sm:px-6">
        <button
          type="button"
          onClick={onBack}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-2.5 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-accent"
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </button>
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-base font-semibold leading-tight text-foreground">
            {paper.title}
          </h1>
          <p className="truncate text-xs text-muted-foreground">
            {paper.classLabel} · {paper.subjectLabel}
          </p>
        </div>
        <button
          type="button"
          onClick={onOpenEditor}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
        >
          <Pencil className="h-4 w-4" />
          Open in editor
        </button>
      </div>

      {/* Body: breakdown (left) + preview (right) */}
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        {/* Left — breakdown */}
        <aside className="w-full shrink-0 space-y-5 overflow-y-auto border-b border-border p-4 sm:p-5 lg:w-[38%] lg:max-w-md lg:border-b-0 lg:border-r">
          {generationError && !isGenerating && (
            <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2.5">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" />
              <p className="text-xs text-destructive">{generationError}</p>
            </div>
          )}

          {/* At-a-glance */}
          <section className="space-y-2">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Overview
            </h2>
            <div className="grid grid-cols-2 gap-2">
              <StatTile label="Questions" value={breakdown.totalQuestions} />
              <StatTile label="Total marks" value={breakdown.totalMarks} />
              <StatTile label="Sections" value={breakdown.sectionCount} />
              <StatTile
                label="Updated"
                value={formatDate(paper.updated_at ?? paper.created_at)}
              />
            </div>
          </section>

          {/* Section breakdown */}
          {breakdown.sections.length > 0 && (
            <section className="space-y-2">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Sections
              </h2>
              <div className="divide-y divide-border rounded-lg border border-border">
                {breakdown.sections.map((s, i) => (
                  <div
                    key={`${s.title}-${i}`}
                    className="flex items-center justify-between gap-3 px-3 py-2"
                  >
                    <span className="min-w-0 truncate text-sm font-medium text-foreground">
                      {s.title}
                    </span>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {s.questionCount} Q · {s.marks} m
                    </span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Question type distribution */}
          {typeEntries.length > 0 && (
            <section className="space-y-2">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Question types
              </h2>
              <div className="flex flex-wrap gap-1.5">
                {typeEntries.map(([code, count]) => (
                  <span
                    key={code}
                    className="inline-flex items-center gap-1 rounded-full border border-border bg-muted/50 px-2.5 py-1 text-xs text-foreground"
                  >
                    {questionTypeLabel(code)}
                    <span className="font-semibold text-muted-foreground">{count}</span>
                  </span>
                ))}
              </div>
            </section>
          )}

          {/* Answer script */}
          <section className="space-y-2">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Answer script
            </h2>
            {hasAnswerScript ? (
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1 rounded-full border border-success/30 bg-success/10 px-2.5 py-1 text-xs font-medium text-success">
                  <Key className="h-3 w-3" />
                  Ready
                </span>
                <button
                  type="button"
                  onClick={() =>
                    setPreviewTarget((t) => (t === "answer" ? "paper" : "answer"))
                  }
                  className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-accent"
                >
                  <Eye className="h-3.5 w-3.5" />
                  {previewTarget === "answer" ? "Show question paper" : "Preview answer script"}
                </button>
                <button
                  type="button"
                  onClick={onGenerateAnswerScript}
                  disabled={isGenerating}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-accent disabled:opacity-50"
                >
                  {isGenerating ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <RefreshCcw className="h-3.5 w-3.5" />
                  )}
                  Regenerate
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={onGenerateAnswerScript}
                disabled={isGenerating}
                className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
              >
                {isGenerating ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Key className="h-3.5 w-3.5" />
                )}
                {isGenerating ? "Generating…" : "Generate answer script"}
              </button>
            )}
          </section>

          {/* Actions */}
          <section className="space-y-2">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Actions
            </h2>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={onExportPDF}
                className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-border bg-background px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-accent"
              >
                <FileDown className="h-3.5 w-3.5" />
                Export PDF
              </button>
              <button
                type="button"
                onClick={onExportWord}
                className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-border bg-background px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-accent"
              >
                <FileDown className="h-3.5 w-3.5" />
                Export Word
              </button>
              <button
                type="button"
                onClick={onExportAnswerScriptPDF}
                disabled={!hasAnswerScript || isGenerating}
                className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-border bg-background px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-accent disabled:opacity-40"
              >
                <FileDown className="h-3.5 w-3.5" />
                Answer PDF
              </button>
              <button
                type="button"
                onClick={onViewAnswerScript}
                disabled={!hasAnswerScript || isGenerating}
                className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-border bg-background px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-accent disabled:opacity-40"
              >
                <Pencil className="h-3.5 w-3.5" />
                Edit answers
              </button>
            </div>
            <button
              type="button"
              onClick={onDelete}
              className="mt-1 inline-flex w-full items-center justify-center gap-1.5 rounded-lg border border-destructive/40 px-3 py-2 text-xs font-medium text-destructive transition-colors hover:bg-destructive/10"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Delete paper
            </button>
          </section>
        </aside>

        {/* Right — preview */}
        <div className="relative min-h-0 flex-1">
          {loading ? (
            <div className="flex h-full items-center justify-center">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : loadError ? (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              {loadError}
            </div>
          ) : (
            <PaperPreview key={previewTarget} content={previewContent} />
          )}
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

  // Which paper's split preview is open
  const [selectedPaperId, setSelectedPaperId] = useState<string | null>(null);

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

  // Only show question papers in the list (answer scripts are accessed via the split view)
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

      setPapers((prev) => prev.filter((p) => p.id !== id && p.id !== asId));

      // If the deleted paper was open in the split view, return to the list.
      setSelectedPaperId((cur) => (cur === id ? null : cur));

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
      action: {
        label: "Delete",
        onClick: () => deletePaperById(id),
      },
    });
  }

  async function handleClearAll() {
    setIsClearing(true);
    try {
      await fetchJson("/api/projects/papers/clear", { method: "DELETE" });
      setPapers([]);
      setSelectedPaperId(null);

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

  // ---- render ----
  const selectedPaper = selectedPaperId
    ? (parsedPapers.find((p) => p.id === selectedPaperId) ?? null)
    : null;

  // Split preview replaces the list once a paper is selected.
  if (selectedPaper) {
    return (
      <div className="h-full min-h-0 bg-background">
        <PaperDetailSplit
          paper={selectedPaper}
          isGenerating={generatingIds.has(selectedPaper.id)}
          generationError={generationErrors[selectedPaper.id]}
          onBack={() => setSelectedPaperId(null)}
          onOpenEditor={() =>
            router.push(`/editor?paperId=${selectedPaper.id}`)
          }
          onGenerateAnswerScript={() =>
            handleGenerateAnswerScript(selectedPaper.id)
          }
          onViewAnswerScript={() => {
            if (selectedPaper.answerScriptId) {
              router.push(`/editor?paperId=${selectedPaper.answerScriptId}`);
            }
          }}
          onExportPDF={() =>
            router.push(`/editor?paperId=${selectedPaper.id}&action=export-pdf`)
          }
          onExportWord={() =>
            router.push(
              `/editor?paperId=${selectedPaper.id}&action=export-docx`,
            )
          }
          onExportAnswerScriptPDF={() => {
            if (selectedPaper.answerScriptId) {
              router.push(
                `/editor?paperId=${selectedPaper.answerScriptId}&action=export-pdf&exportType=answer_script`,
              );
            }
          }}
          onDelete={() => handleDeletePaper(selectedPaper.id)}
        />
      </div>
    );
  }

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-6 bg-background min-h-full">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-bold leading-tight">Question Paper</h1>
            {!isLoading && questionPapers.length > 0 && (
              <span className="inline-flex items-center justify-center h-6 min-w-6 px-2 rounded-full bg-primary/10 text-primary text-xs font-bold">
                {questionPapers.length}
              </span>
            )}
          </div>
          <p className="text-sm text-muted-foreground mt-0.5">
            Browse, preview, and open your saved exam papers.
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
                      {/* Left: icon + text (clickable to open preview) */}
                      <div
                        className="flex items-start gap-3 flex-1 min-w-0 cursor-pointer hover:opacity-80 transition-opacity"
                        onClick={() => setSelectedPaperId(paper.id)}
                      >
                        <div className="p-2 rounded-lg bg-primary/10 shrink-0">
                          <FileText className="h-5 w-5 text-primary" />
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
                            <span className="inline-flex items-center gap-1 mt-1.5 text-[10px] font-semibold uppercase tracking-wide text-success bg-success/10 border border-success/30 rounded px-1.5 py-0.5">
                              <Key className="h-2.5 w-2.5" />
                              Answer Script Ready
                            </span>
                          )}
                          {isGenerating && (
                            <span className="inline-flex items-center gap-1 mt-1.5 text-[10px] font-semibold uppercase tracking-wide text-warning bg-warning/10 border border-warning/30 rounded px-1.5 py-0.5">
                              <Loader2 className="h-2.5 w-2.5 animate-spin" />
                              Generating Answer Script…
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Right: Preview + Delete */}
                      <div className="flex items-center gap-2 shrink-0">
                        <button
                          type="button"
                          onClick={() => setSelectedPaperId(paper.id)}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent hover:border-primary/40 transition-all"
                        >
                          <Eye className="h-3.5 w-3.5" />
                          Preview
                        </button>

                        <button
                          type="button"
                          aria-label="Delete paper"
                          onClick={() => handleDeletePaper(paper.id)}
                          className="p-1.5 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
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
    </div>
  );
}
