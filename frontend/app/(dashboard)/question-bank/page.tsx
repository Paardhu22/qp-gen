"use client";

import { useEffect, useMemo, useState } from "react";
import {
  fetchPapers,
  deletePaper,
  fetchJson,
  generateAnswerScript,
} from "@/lib/api-client";
import { getPaperAction, type EditorPaper } from "@/actions/savePaper";
import {
  computePaperBreakdown,
  questionTypeLabel,
  type PaperBreakdown,
} from "@/lib/paper-breakdown";
import { PaperPreview } from "@/components/paper-preview";
import {
  BookOpen,
  FileText,
  Search,
  Trash2,
  Loader2,
  ArrowLeft,
  MoreHorizontal,
  Eye,
  Key,
  RefreshCcw,
  FileDown,
  X,
  AlertTriangle,
  ChevronRight,
  LayoutList,
  Hash,
  Award,
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
  content?: string;
  answers?: string;
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

type ParsedPaper = Paper & {
  classLabel: string;
  subjectLabel: string;
  boardLabel: string;
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function parsePaper(paper: Paper): ParsedPaper {
  let c = (paper.gradeClass || "").trim();
  let s = (paper.subject || "").trim();
  if (!c && !s && paper.projectName) {
    const parts = paper.projectName
      .trim()
      .split(/\s*[—–\-]\s*/)
      .filter(Boolean);
    c = parts[0]?.trim() || "";
    s = parts[1]?.trim() || "";
  }
  return {
    ...paper,
    classLabel: c || "—",
    subjectLabel: s || "—",
    boardLabel: (paper.board || "").trim() || "—",
  };
}

function formatDate(value?: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function isAnswerScriptPaper(paper: Paper): boolean {
  return /answer[\s\-_]*key|answer[\s\-_]*script/i.test(paper.title ?? "");
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function QuestionBankPage() {
  const router = useRouter();
  const { data: sessionData } = useSession();

  const [papers, setPapers] = useState<Paper[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set());
  const [isClearing, setIsClearing] = useState(false);

  // Detail view
  const [selectedPaperId, setSelectedPaperId] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailPaper, setDetailPaper] = useState<EditorPaper | null>(null);

  // Answer script generation
  const [generatingIds, setGeneratingIds] = useState<Set<string>>(new Set());

  // ---- fetch list ----
  useEffect(() => {
    setIsLoading(true);
    fetchPapers<Paper[]>()
      .then((data) => setPapers(data ?? []))
      .catch(() => toast.error("Failed to load saved papers."))
      .finally(() => setIsLoading(false));
  }, []);

  const parsedPapers = useMemo(() => papers.map(parsePaper), [papers]);

  const questionPapers = useMemo(
    () => parsedPapers.filter((p) => !isAnswerScriptPaper(p)),
    [parsedPapers],
  );

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return questionPapers;
    return questionPapers.filter((p) =>
      [p.title, p.classLabel, p.subjectLabel, p.boardLabel]
        .join(" ")
        .toLowerCase()
        .includes(term),
    );
  }, [questionPapers, search]);

  // ---- fetch detail ----
  useEffect(() => {
    if (!selectedPaperId) {
      setDetailPaper(null);
      return;
    }
    setDetailLoading(true);
    getPaperAction(selectedPaperId)
      .then((data) => setDetailPaper(data))
      .catch(() => toast.error("Failed to load paper details."))
      .finally(() => setDetailLoading(false));
  }, [selectedPaperId]);

  const breakdown = useMemo<PaperBreakdown | null>(() => {
    if (!detailPaper?.content) return null;
    return computePaperBreakdown(detailPaper.content);
  }, [detailPaper]);

  const selectedMeta = useMemo(
    () => parsedPapers.find((p) => p.id === selectedPaperId) ?? null,
    [parsedPapers, selectedPaperId],
  );

  // ---- actions ----
  async function deletePaperById(id: string) {
    setDeletingIds((prev) => new Set(prev).add(id));
    const paper = papers.find((p) => p.id === id);
    const asId = paper?.answerScriptId;
    try {
      await deletePaper(id);
      if (asId) await deletePaper(asId).catch(() => {});
      setPapers((prev) => prev.filter((p) => p.id !== id && p.id !== asId));
      if (selectedPaperId === id) setSelectedPaperId(null);
      const userId = sessionData?.user?.id;
      if (userId) {
        await deleteLiveDocument(getLiveDocumentId(userId, id)).catch(() => {});
        if (asId)
          await deleteLiveDocument(getLiveDocumentId(userId, asId)).catch(
            () => {},
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

  function handleDeletePaper(id: string) {
    const paper = papers.find((p) => p.id === id);
    toast.warning("Delete this paper?", {
      description: paper?.answerScriptId
        ? "The linked answer script will also be deleted."
        : undefined,
      action: { label: "Delete", onClick: () => deletePaperById(id) },
    });
  }

  async function handleClearAll() {
    setIsClearing(true);
    try {
      await fetchJson("/api/projects/papers/clear", { method: "DELETE" });
      setPapers([]);
      setSelectedPaperId(null);
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
      toast.success("Answer script generated!");
    } catch (err: any) {
      toast.error(err?.message || "Failed to generate answer script.");
    } finally {
      setGeneratingIds((prev) => {
        const next = new Set(prev);
        next.delete(paperId);
        return next;
      });
    }
  }

  // ---------------------------------------------------------------------------
  // Detail view
  // ---------------------------------------------------------------------------

  if (selectedPaperId) {
    return (
      <div className="flex h-full min-h-0 flex-col bg-background">
        {/* Back bar */}
        <div className="shrink-0 border-b border-border px-4 py-2.5 sm:px-6">
          <button
            type="button"
            onClick={() => setSelectedPaperId(null)}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to papers
          </button>
        </div>

        {detailLoading ? (
          <div className="flex flex-1 items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="flex flex-1 min-h-0">
            {/* ── Left panel: metadata + breakdown (~40%) ──────────── */}
            <div className="w-[40%] min-w-[320px] overflow-y-auto border-r border-border p-5 sm:p-6 space-y-6">
              {/* Metadata card */}
              <div className="rounded-lg border border-border bg-card p-4 space-y-3">
                <h2 className="text-lg font-semibold text-foreground leading-snug">
                  {selectedMeta?.title ?? "Untitled"}
                </h2>
                <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                  <MetaRow label="Subject" value={selectedMeta?.subjectLabel} />
                  <MetaRow label="Class" value={selectedMeta?.classLabel} />
                  <MetaRow label="Board" value={selectedMeta?.boardLabel} />
                  <MetaRow
                    label="Created"
                    value={formatDate(
                      selectedMeta?.created_at ?? selectedMeta?.updated_at,
                    )}
                  />
                </div>
                <div className="flex items-center gap-2 pt-1">
                  <button
                    type="button"
                    onClick={() =>
                      router.push(`/editor?paperId=${selectedPaperId}`)
                    }
                    className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
                  >
                    <Eye className="h-3.5 w-3.5" />
                    Open in Editor
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      router.push(
                        `/editor?paperId=${selectedPaperId}&action=export-pdf`,
                      )
                    }
                    className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent transition-colors"
                  >
                    <FileDown className="h-3.5 w-3.5" />
                    Export PDF
                  </button>
                </div>
              </div>

              {/* Paper Breakdown */}
              {breakdown && breakdown.totalQuestions > 0 && (
                <div className="space-y-4">
                  <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                    <LayoutList className="h-4 w-4 text-primary" />
                    Paper Breakdown
                  </h3>

                  {/* Summary stats */}
                  <div className="grid grid-cols-3 gap-3">
                    <StatCard
                      icon={<LayoutList className="h-4 w-4" />}
                      label="Sections"
                      value={breakdown.sectionCount}
                    />
                    <StatCard
                      icon={<Hash className="h-4 w-4" />}
                      label="Questions"
                      value={breakdown.totalQuestions}
                    />
                    <StatCard
                      icon={<Award className="h-4 w-4" />}
                      label="Total Marks"
                      value={breakdown.totalMarks}
                    />
                  </div>

                  {/* Per-section breakdown */}
                  {breakdown.sections.length > 0 && (
                    <div className="rounded-lg border border-border overflow-hidden">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-border bg-muted/60 text-xs text-muted-foreground">
                            <th className="px-3 py-2 text-left font-medium">
                              Section
                            </th>
                            <th className="px-3 py-2 text-right font-medium">
                              Questions
                            </th>
                            <th className="px-3 py-2 text-right font-medium">
                              Marks
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {breakdown.sections.map((sec, i) => (
                            <tr
                              key={i}
                              className="border-b border-border/50 last:border-0"
                            >
                              <td className="px-3 py-2 text-foreground">
                                {sec.title}
                              </td>
                              <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">
                                {sec.questionCount}
                              </td>
                              <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">
                                {sec.marks}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {/* Question type distribution */}
                  {Object.keys(breakdown.typeDistribution).length > 0 && (
                    <div className="space-y-2">
                      <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                        Question Types
                      </h4>
                      <div className="flex flex-wrap gap-1.5">
                        {Object.entries(breakdown.typeDistribution)
                          .sort(([, a], [, b]) => b - a)
                          .map(([code, count]) => (
                            <span
                              key={code}
                              className="inline-flex items-center gap-1 rounded-md border border-border bg-muted/50 px-2 py-1 text-xs text-muted-foreground"
                            >
                              {questionTypeLabel(code)}
                              <span className="font-semibold tabular-nums text-foreground">
                                {count}
                              </span>
                            </span>
                          ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Answer script section */}
              <div className="space-y-2">
                <h3 className="text-sm font-semibold text-foreground">
                  Answer Script
                </h3>
                {selectedMeta?.answerScriptId ? (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground">
                      Generated
                    </span>
                    <button
                      type="button"
                      onClick={() =>
                        router.push(
                          `/editor?paperId=${selectedMeta.answerScriptId}`,
                        )
                      }
                      className="text-xs font-medium text-primary hover:underline"
                    >
                      View answer script
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    disabled={generatingIds.has(selectedPaperId)}
                    onClick={() => handleGenerateAnswerScript(selectedPaperId)}
                    className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent transition-colors disabled:opacity-50"
                  >
                    {generatingIds.has(selectedPaperId) ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Key className="h-3.5 w-3.5" />
                    )}
                    {generatingIds.has(selectedPaperId)
                      ? "Generating…"
                      : "Generate Answer Script"}
                  </button>
                )}
              </div>
            </div>

            {/* ── Right panel: paper preview (~60%) ─────────────── */}
            <div className="flex-1 min-w-0 overflow-hidden bg-muted/20">
              <PaperPreview content={detailPaper?.content} />
            </div>
          </div>
        )}
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // List view (default)
  // ---------------------------------------------------------------------------

  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      {/* ── Header ──────────────────────────────────────────────── */}
      <div className="shrink-0 border-b border-border px-4 py-3 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <BookOpen className="h-5 w-5 text-primary" />
            <h1 className="text-lg font-semibold tracking-tight">
              Question Bank
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
                      answer scripts. This action cannot be undone.
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

      {/* ── Table ───────────────────────────────────────────────── */}
      <div className="flex-1 min-h-0 overflow-auto">
        {isLoading ? (
          <div className="space-y-px p-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <div
                key={i}
                className="h-12 animate-pulse rounded bg-muted/40 mb-1"
              />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-3 py-24 text-center">
            <div className="rounded-xl border-2 border-dashed border-border p-6">
              <BookOpen className="mx-auto h-10 w-10 text-muted-foreground/40" />
            </div>
            <p className="text-sm font-medium text-foreground">
              {search.trim()
                ? "No papers match your search."
                : "No saved papers yet."}
            </p>
            {!search.trim() && (
              <p className="max-w-xs text-xs text-muted-foreground">
                Create a paper in the Editor and save it to see it here.
              </p>
            )}
            {search.trim() && (
              <button
                type="button"
                onClick={() => setSearch("")}
                className="text-xs font-medium text-primary hover:underline"
              >
                Clear search
              </button>
            )}
          </div>
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead className="sticky top-0 z-10 bg-muted/80 backdrop-blur">
              <tr className="border-b border-border text-left text-xs">
                <th className="px-4 py-2.5 font-semibold text-muted-foreground sm:px-6">
                  Title
                </th>
                <th className="px-3 py-2.5 font-semibold text-muted-foreground">
                  Subject
                </th>
                <th className="px-3 py-2.5 font-semibold text-muted-foreground">
                  Class
                </th>
                <th className="px-3 py-2.5 font-semibold text-muted-foreground">
                  Board
                </th>
                <th className="px-3 py-2.5 font-semibold text-muted-foreground text-right">
                  Created
                </th>
                <th className="w-10 px-3 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((paper) => {
                const isDeleting = deletingIds.has(paper.id);
                return (
                  <tr
                    key={paper.id}
                    onClick={() => setSelectedPaperId(paper.id)}
                    className={cn(
                      "cursor-pointer border-b border-border/60 transition-colors hover:bg-muted/40 group",
                      isDeleting && "pointer-events-none opacity-40",
                    )}
                  >
                    <td className="px-4 py-3 sm:px-6">
                      <div className="flex items-center gap-2">
                        <FileText className="h-4 w-4 shrink-0 text-muted-foreground/60" />
                        <span className="font-medium text-foreground line-clamp-1">
                          {paper.title}
                        </span>
                        <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground/40 opacity-0 group-hover:opacity-100 transition-opacity" />
                      </div>
                    </td>
                    <td className="px-3 py-3 text-muted-foreground whitespace-nowrap">
                      {paper.subjectLabel}
                    </td>
                    <td className="px-3 py-3 text-muted-foreground whitespace-nowrap">
                      {paper.classLabel}
                    </td>
                    <td className="px-3 py-3 text-muted-foreground whitespace-nowrap">
                      {paper.boardLabel}
                    </td>
                    <td className="px-3 py-3 text-right tabular-nums text-muted-foreground whitespace-nowrap">
                      {formatDate(paper.created_at ?? paper.updated_at)}
                    </td>
                    <td className="px-3 py-3">
                      <button
                        type="button"
                        aria-label="Delete paper"
                        disabled={isDeleting}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeletePaper(paper.id);
                        }}
                        className="flex h-7 w-7 items-center justify-center rounded text-muted-foreground/60 transition-colors hover:bg-destructive/10 hover:text-destructive opacity-0 group-hover:opacity-100"
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
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Small components
// ---------------------------------------------------------------------------

function MetaRow({
  label,
  value,
}: {
  label: string;
  value?: string | null;
}) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="font-medium text-foreground">{value || "—"}</dd>
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
}) {
  return (
    <div className="flex flex-col items-center gap-1 rounded-lg border border-border bg-card p-3">
      <span className="text-muted-foreground">{icon}</span>
      <span className="text-lg font-bold tabular-nums text-foreground">
        {value}
      </span>
      <span className="text-[11px] text-muted-foreground">{label}</span>
    </div>
  );
}
