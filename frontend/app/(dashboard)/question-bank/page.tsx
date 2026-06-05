"use client";

import { useEffect, useMemo, useState } from "react";
import {
  fetchPapers,
  deletePaper,
  fetchJson,
  generateAnswerScript,
} from "@/lib/api-client";
import { BookOpen, FileText, Search, Trash2, Loader2 } from "lucide-react";
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

type Paper = {
  id: string;
  title: string;
  projectName?: string;
  created_at?: string;
  updated_at?: string;
};

type ParsedPaper = Paper & { classLabel: string; subjectLabel: string };

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function parsePaper(paper: Paper): ParsedPaper {
  // Tolerate any delimiter style — em-dash, en-dash, hyphen — since the
  // project name is user-supplied free text. Whatever does not parse cleanly
  // still goes into the search haystack via raw `projectName`.
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

  // Answer script generation state per paper card
  const [generatingIds, setGeneratingIds] = useState<Set<string>>(new Set());
  const [generationErrors, setGenerationErrors] = useState<
    Record<string, string>
  >({});

  // ---- fetch on mount ----
  useEffect(() => {
    setIsLoading(true);
    fetchPapers<Paper[]>()
      .then((data) => setPapers(data ?? []))
      .catch(() => toast.error("Failed to load saved papers."))
      .finally(() => setIsLoading(false));
  }, []);

  // ---- derived ----
  const parsedPapers = useMemo<ParsedPaper[]>(
    () => papers.map(parsePaper),
    [papers],
  );

  const filteredPapers = useMemo<ParsedPaper[]>(() => {
    const term = paperSearch.trim().toLowerCase();
    if (!term) return parsedPapers;
    // Cluster D — match against every searchable field on the paper card.
    // The pre-fix filter only indexed title + parsed class/subject, so
    // queries like "Math" or the raw project name failed when the parser
    // didn't find the expected " — " delimiter. Building a single haystack
    // makes the search robust to project-naming inconsistencies.
    return parsedPapers.filter((p) => {
      const haystack = [p.title, p.projectName, p.classLabel, p.subjectLabel]
        .filter((v): v is string => typeof v === "string" && v.length > 0)
        .join(" · ")
        .toLowerCase();
      return haystack.includes(term);
    });
  }, [parsedPapers, paperSearch]);

  // ---- actions ----
  async function deletePaperById(id: string) {
    setDeletingIds((prev) => new Set(prev).add(id));
    try {
      await deletePaper(id);
      setPapers((prev) => prev.filter((p) => p.id !== id));

      const userId = sessionData?.user?.id;
      if (userId) {
        await deleteLiveDocument(getLiveDocumentId(userId, id)).catch((err) =>
          console.error("Failed to delete local autosave:", err),
        );
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

  function handleDeletePaper(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    toast.warning("Delete this paper?", {
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

      const userId = sessionData?.user?.id;
      if (userId) {
        await clearLiveDocumentsForUser(userId).catch((err) =>
          console.error("Failed to clear local autosaves:", err),
        );
      }

      toast.success("All papers cleared.");
    } catch {
      toast.error("Failed to clear papers.");
    } finally {
      setIsClearing(false);
    }
  }

  async function handleGenerateAnswerScript(
    paperId: string,
    e: React.MouseEvent,
  ) {
    e.stopPropagation();

    // Clear any previous error
    setGenerationErrors((prev) => {
      const next = { ...prev };
      delete next[paperId];
      return next;
    });

    // Set loading state
    setGeneratingIds((prev) => new Set(prev).add(paperId));

    try {
      const result = await generateAnswerScript(paperId);
      toast.success("Answer script generated successfully!");
      // Navigate to the editor with the new answer script
      router.push(result.editor_url);
    } catch (err: any) {
      const errorMessage =
        err?.message || "Failed to generate. Please try again.";
      setGenerationErrors((prev) => ({
        ...prev,
        [paperId]: errorMessage,
      }));
    } finally {
      setGeneratingIds((prev) => {
        const next = new Set(prev);
        next.delete(paperId);
        return next;
      });
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="p-8 space-y-6 bg-background min-h-full">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        {/* Left: title block */}
        <div>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-3xl font-bold leading-tight">
                Question Paper
              </h1>
              {!isLoading && papers.length > 0 && (
                <span className="inline-flex items-center justify-center h-6 min-w-6 px-2 rounded-full bg-indigo-100 text-indigo-600 text-xs font-bold dark:bg-indigo-950 dark:text-indigo-400">
                  {papers.length}
                </span>
              )}
            </div>
            <p className="text-sm text-muted-foreground mt-0.5">
              Browse and open your saved exam papers in the editor.
            </p>
          </div>
        </div>

        {/* Right: search + clear */}
        <div className="flex items-center gap-3">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
            <Input
              className="w-64 pl-9"
              placeholder="Search papers…"
              value={paperSearch}
              onChange={(e) => setPaperSearch(e.target.value)}
            />
          </div>

          {/* Clear All — only when there are papers and not loading */}
          {!isLoading && papers.length > 0 && (
            <AlertDialog>
              <AlertDialogTrigger
                className="inline-flex items-center gap-1.5 rounded-lg border border-destructive/40 px-3 py-2 text-sm font-medium text-destructive hover:bg-destructive/10 transition-colors disabled:opacity-50"
                disabled={isClearing}
              >
                <Trash2 className="h-4 w-4" />
                Clear All
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Clear all saved papers?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This will permanently delete every saved paper. This action
                    cannot be undone.
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

      {/* ── Loading skeletons ───────────────────────────────────────────────── */}
      {isLoading && (
        <div className="grid gap-5 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="animate-pulse h-44 rounded-xl border bg-muted/40"
            />
          ))}
        </div>
      )}

      {/* ── Empty state ─────────────────────────────────────────────────────── */}
      {!isLoading && filteredPapers.length === 0 && (
        <div className="flex flex-col items-center justify-center gap-4 rounded-xl border border-dashed py-20 text-center">
          <BookOpen className="h-10 w-10 opacity-30" />
          <div>
            <p className="font-semibold text-foreground">
              No saved papers yet.
            </p>
            <p className="text-sm text-muted-foreground mt-1">
              Save a paper from the Editor to see it here.
            </p>
          </div>
        </div>
      )}

      {/* ── Paper grid ──────────────────────────────────────────────────────── */}
      {!isLoading && filteredPapers.length > 0 && (
        <div className="grid gap-5 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
          {filteredPapers.map((paper) => {
            const isDeleting = deletingIds.has(paper.id);
            const isGenerating = generatingIds.has(paper.id);
            const generationError = generationErrors[paper.id];

            return (
              <div
                key={paper.id}
                role="button"
                tabIndex={0}
                onClick={() => router.push(`/editor?paperId=${paper.id}`)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    router.push(`/editor?paperId=${paper.id}`);
                  }
                }}
                className={cn(
                  "group relative bg-card border border-border rounded-xl p-5 flex flex-col gap-4",
                  "cursor-pointer transition-all hover:border-primary/50 hover:shadow-md",
                  isDeleting && "opacity-50 pointer-events-none",
                )}
              >
                {/* Top row: icon + delete button */}
                <div className="flex items-center justify-between">
                  <div className="p-2 rounded-lg bg-indigo-500/10">
                    <FileText className="h-5 w-5 text-indigo-500" />
                  </div>
                  <button
                    type="button"
                    aria-label="Delete paper"
                    onClick={(e) => handleDeletePaper(paper.id, e)}
                    className={cn(
                      "opacity-0 group-hover:opacity-100 transition-opacity",
                      "p-1.5 rounded-lg text-muted-foreground hover:text-red-500 hover:bg-red-500/10",
                    )}
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>

                {/* Exam name */}
                <p className="text-base font-bold text-foreground line-clamp-2 leading-snug">
                  {paper.title}
                </p>

                {/* Metadata badges */}
                <div className="flex flex-wrap gap-1.5">
                  <span className="bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 text-[11px] px-2 py-0.5 rounded font-medium">
                    {paper.classLabel}
                  </span>
                  <span className="bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 text-[11px] px-2 py-0.5 rounded font-medium">
                    {paper.subjectLabel}
                  </span>
                </div>

                {/* Footer row */}
                <div className="mt-auto flex items-center justify-between gap-2">
                  <span className="text-xs text-indigo-500 font-medium">
                    Open in Editor →
                  </span>
                  <span className="text-[10px] text-muted-foreground bg-muted/50 px-1.5 py-0.5 rounded border">
                    {formatDate(paper.updated_at ?? paper.created_at)}
                  </span>
                </div>

                {/* Generate Answer Script button */}
                <button
                  type="button"
                  disabled={isGenerating}
                  onClick={(e) => handleGenerateAnswerScript(paper.id, e)}
                  className={cn(
                    "w-full flex items-center justify-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium transition-all",
                    isGenerating
                      ? "border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-700 dark:bg-amber-950/30 dark:text-amber-400 cursor-wait"
                      : "border-border bg-background text-muted-foreground hover:border-indigo-400 hover:text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-950/30 dark:hover:text-indigo-400",
                  )}
                >
                  {isGenerating ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      Generating answer script…
                    </>
                  ) : (
                    "Generate Answer Script"
                  )}
                </button>

                {/* Error state */}
                {generationError && !isGenerating && (
                  <p className="text-[11px] text-red-500 dark:text-red-400 leading-snug">
                    {generationError}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

