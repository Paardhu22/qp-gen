"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  fetchPapers,
  fetchTrashedPapers,
  deletePaper,
  restorePaper,
  emptyPaperTrash,
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
  Undo2,
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
import { SkeletonRows } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
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
import { deleteServerDraft, pullDrafts } from "@/lib/drafts-sync";
import {
  deleteLiveDocument,
  clearLiveDocumentsForUser,
  getLiveDocumentId,
  purgeExpiredDrafts,
} from "@/lib/live-document-db";
import {
  summarizeDrafts,
  daysUntilExpiry,
  DRAFT_RETENTION_DAYS,
  type DraftSummary,
} from "@/lib/drafts";

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
  const [selectedSetId, setSelectedSetId] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailPaper, setDetailPaper] = useState<EditorPaper | null>(null);

  // Answer script generation
  const [generatingIds, setGeneratingIds] = useState<Set<string>>(new Set());

  // Unsaved drafts, read straight from IndexedDB.
  const [drafts, setDrafts] = useState<DraftSummary[]>([]);
  const [draftsLoading, setDraftsLoading] = useState(true);

  // The recycle bin. Deleting a paper destroys a term's worth of work from a
  // button that sits one row away from "open"; the bin is what makes that
  // click survivable. Server-side, unlike drafts — a teacher who deletes a
  // paper on their laptop must be able to get it back on the staffroom PC.
  const [trashed, setTrashed] = useState<Paper[]>([]);
  const [trashRetentionDays, setTrashRetentionDays] = useState(30);
  const [showTrash, setShowTrash] = useState(false);

  // ---- fetch list ----
  useEffect(() => {
    setIsLoading(true);
    fetchPapers<Paper[]>()
      .then((data) => setPapers(data ?? []))
      .catch(() => toast.error("Failed to load saved papers."))
      .finally(() => setIsLoading(false));
  }, []);

  // ---- recycle bin ----
  // Loaded alongside the library rather than behind the toggle: the count is
  // part of the toggle's label, and a "Recycle bin" control that has to be
  // opened before it can say whether it holds anything is a control nobody
  // opens. Listing also purges what has aged out, server-side.
  const loadTrash = useCallback(async () => {
    try {
      const data = await fetchTrashedPapers<Paper>();
      setTrashed(data.papers ?? []);
      setTrashRetentionDays(data.retention_days ?? 30);
    } catch {
      // Non-fatal: the bin is a recovery affordance, not the page.
      setTrashed([]);
    }
  }, []);

  useEffect(() => {
    void loadTrash();
  }, [loadTrash]);

  // ---- drafts: purge what has expired, then list the rest ----
  // Purging here rather than on a timer: this is the one page that shows drafts,
  // so it is also the page where a stale one would be visible. Drafts never
  // reach the backend, so nothing server-side can expire them.
  const userId = sessionData?.user?.id;
  useEffect(() => {
    if (!userId) return;
    let active = true;
    (async () => {
      try {
        await purgeExpiredDrafts(userId);
        // Reconcile with the server first, so a draft started on another
        // device shows up here. Falls back to whatever is local if the server
        // cannot be reached — which is exactly what this page did before
        // drafts had a server copy at all.
        const { documents } = await pullDrafts(userId);
        if (active) setDrafts(summarizeDrafts(documents));
      } catch (error) {
        console.error("Failed to load drafts:", error);
      } finally {
        if (active) setDraftsLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [userId]);

  async function deleteDraft(draft: DraftSummary) {
    setDrafts((prev) => prev.filter((d) => d.id !== draft.id));
    await Promise.all([
      ...draft.documentIds.map((id) =>
        deleteLiveDocument(id).catch((error) =>
          console.error("Failed to delete draft:", id, error),
        ),
      ),
      // The server copy goes too, or the next `pullDrafts` faithfully brings
      // the draft back and the delete looks like it did not work.
      deleteServerDraft(draft.id),
    ]);
    toast.success("Draft deleted.");
  }

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
      setSelectedSetId(null);
      return;
    }
    setDetailLoading(true);
    getPaperAction(selectedPaperId)
      .then((data) => {
        setDetailPaper(data);
        if (data?.sets && data.sets.length > 0) {
          setSelectedSetId(data.sets[0].id || null);
        } else {
          setSelectedSetId(null);
        }
      })
      .catch(() => toast.error("Failed to load paper details."))
      .finally(() => setDetailLoading(false));
  }, [selectedPaperId]);

  const activeSet = useMemo(() => {
    if (!detailPaper?.sets || detailPaper.sets.length === 0) return null;
    return detailPaper.sets.find((s) => s.id === selectedSetId) || detailPaper.sets[0] || null;
  }, [detailPaper, selectedSetId]);

  const breakdown = useMemo<PaperBreakdown | null>(() => {
    const content = activeSet?.content || detailPaper?.content;
    if (!content) return null;
    return computePaperBreakdown(content);
  }, [detailPaper, activeSet]);

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
      await loadTrash();
      // Undo right here, not just in the bin. The moment a teacher realises
      // they deleted the wrong paper is the second after they clicked.
      toast.success("Moved to the recycle bin.", {
        description: `Kept for ${trashRetentionDays} days.`,
        action: { label: "Undo", onClick: () => void restorePaperById(id, asId) },
      });
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

  async function restorePaperById(id: string, answerScriptId?: string | null) {
    try {
      await restorePaper(id);
      if (answerScriptId) await restorePaper(answerScriptId).catch(() => {});
      const [live] = await Promise.all([fetchPapers<Paper[]>(), loadTrash()]);
      setPapers(live ?? []);
      toast.success("Paper restored.");
    } catch {
      toast.error("Could not restore that paper.");
    }
  }

  async function purgePaperById(id: string) {
    try {
      await deletePaper(id, { permanent: true });
      setTrashed((prev) => prev.filter((p) => p.id !== id));
      toast.success("Paper deleted for good.");
    } catch {
      toast.error("Could not delete that paper.");
    }
  }

  async function handleEmptyTrash() {
    try {
      await emptyPaperTrash();
      setTrashed([]);
      toast.success("Recycle bin emptied.");
    } catch {
      toast.error("Could not empty the recycle bin.");
    }
  }

  function handleDeletePaper(id: string) {
    const paper = papers.find((p) => p.id === id);
    toast.warning("Move this paper to the recycle bin?", {
      description: paper?.answerScriptId
        ? "The linked answer script goes with it. Both are recoverable."
        : `Recoverable for ${trashRetentionDays} days.`,
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
      // The server copies go with the local ones. Clearing only locally would
      // leave the drafts on the server, and the next `pullDrafts` would put
      // every one of them straight back — a "clear all" that visibly undoes
      // itself on the next page load.
      await Promise.all(drafts.map((draft) => deleteServerDraft(draft.id)));
      setDrafts([]);
      await loadTrash();
      toast.success("All papers moved to the recycle bin.");
    } catch {
      toast.error("Failed to clear papers.");
    } finally {
      setIsClearing(false);
    }
  }

  async function handleGenerateAnswerScript(paperId: string, setId?: string) {
    const trackingId = setId ? `${paperId}-${setId}` : paperId;
    setGeneratingIds((prev) => new Set(prev).add(trackingId));
    try {
      const result = await generateAnswerScript(paperId, setId);
      
      // Update local state so UI updates
      if (detailPaper && detailPaper.id === paperId) {
        setDetailPaper((prev) => {
          if (!prev) return prev;
          const updatedSets = (prev.sets || []).map((s) => 
            s.id === setId ? { ...s, metadata: { ...(s.metadata || {}), answer_script_id: result.answer_script_paper_id } } : s
          );
          return { ...prev, sets: updatedSets };
        });
      }

      setPapers((prev) =>
        prev.map((p) =>
          p.id === paperId
            ? { ...p, answerScriptId: (!setId || p.sets?.[0]?.id === setId) ? result.answer_script_paper_id : p.answerScriptId }
            : p,
        ),
      );
      toast.success("Answer script generated!");
    } catch (err: any) {
      toast.error(err?.message || "Failed to generate answer script.");
    } finally {
      setGeneratingIds((prev) => {
        const next = new Set(prev);
        next.delete(trackingId);
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
          <Spinner size="page" />
        ) : (
          <div className="flex flex-1 min-h-0">
            {/* ── Left panel: metadata + breakdown (~40%) ──────────── */}
            <div className="w-[40%] min-w-[320px] overflow-y-auto border-r border-border p-4 sm:p-6 space-y-6">
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
                    className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
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
                    className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent transition-colors"
                  >
                    <FileDown className="h-3.5 w-3.5" />
                    Export PDF
                  </button>
                </div>
              </div>

              {/* Set Selector */}
              {detailPaper?.sets && detailPaper.sets.length > 1 && (
                <div className="space-y-2">
                  <h3 className="text-sm font-semibold text-foreground">Select Set</h3>
                  <div className="flex flex-wrap gap-2">
                    {detailPaper.sets.map((set) => (
                      <button
                        key={set.id}
                        type="button"
                        onClick={() => setSelectedSetId(set.id || null)}
                        className={cn(
                          "px-3 py-1.5 text-xs font-medium rounded-lg transition-colors",
                          selectedSetId === set.id
                            ? "bg-primary text-primary-foreground"
                            : "bg-muted text-muted-foreground hover:bg-muted/80"
                        )}
                      >
                        {set.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}

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
                              className="inline-flex items-center gap-1 rounded-lg border border-border bg-muted/50 px-2 py-1 text-xs text-muted-foreground"
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
                {(() => {
                  const setAnswerScriptId = activeSet?.metadata?.answer_script_id || (activeSet?.id === detailPaper?.sets?.[0]?.id ? selectedMeta?.answerScriptId : null);
                  const isGenerating = generatingIds.has(activeSet?.id ? `${selectedPaperId}-${activeSet.id}` : selectedPaperId);
                  
                  if (setAnswerScriptId) {
                    return (
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-muted-foreground">
                          Generated
                        </span>
                        <button
                          type="button"
                          onClick={() =>
                            router.push(
                              `/editor?paperId=${setAnswerScriptId}`,
                            )
                          }
                          className="text-xs font-medium text-primary hover:underline"
                        >
                          View answer script
                        </button>
                      </div>
                    );
                  }
                  return (
                    <button
                      type="button"
                      disabled={isGenerating}
                      onClick={() => handleGenerateAnswerScript(selectedPaperId, activeSet?.id)}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent transition-colors disabled:opacity-50"
                    >
                      {isGenerating ? (
                        <Spinner className="size-3.5" />
                      ) : (
                        <Key className="h-3.5 w-3.5" />
                      )}
                      {isGenerating
                        ? "Generating…"
                        : `Generate Answer Script ${activeSet ? `for ${activeSet.label}` : ''}`}
                    </button>
                  );
                })()}
              </div>
            </div>

            {/* ── Right panel: paper preview (~60%) ─────────────── */}
            <div className="flex-1 min-w-0 overflow-hidden bg-muted/20">
              <PaperPreview
                content={activeSet?.content || detailPaper?.content}
                subject={detailPaper?.subject}
              />
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
            {/* This route is the PAPERS list — "Search papers…", "No saved
                papers yet", "Clear all saved papers". The heading said
                "Question Bank", which is the OTHER page (/paper-library), so
                both pages claimed the same title and the nav item that
                correctly reads "Papers" landed on a screen calling itself
                something else. The route name is the misleading part, not the
                nav label. */}
            <h1 className="text-lg font-semibold tracking-tight">Papers</h1>
            <span className="rounded-sm bg-muted px-1.5 py-0.5 text-xs font-medium tabular-nums text-muted-foreground">
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
                  className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg border border-destructive/40 bg-background px-3 text-xs font-medium text-destructive transition-colors hover:bg-destructive/10 disabled:opacity-50"
                  disabled={isClearing}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  {isClearing ? "Clearing…" : "Clear all"}
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Clear all saved papers?</AlertDialogTitle>
                    <AlertDialogDescription>
                      Every saved paper and its answer scripts move to the
                      recycle bin, where they stay recoverable for{" "}
                      {trashRetentionDays} days. Unsaved drafts are deleted
                      outright.
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

      {/* ── Saved drafts ────────────────────────────────────────────
          Papers live on the server; drafts do not. Until a paper is saved it
          exists only as an IndexedDB document in this browser, which used to
          make it reachable solely through a "Resume previous paper?" modal.
          This is that modal's replacement: the drafts are just listed, and the
          teacher picks one — or none. Scrolls horizontally so it never pushes
          the saved-papers table off screen. */}
      {!draftsLoading && drafts.length > 0 && (
        <div className="shrink-0 border-b border-border bg-muted/20 px-4 py-3 sm:px-6">
          <div className="mb-2 flex items-baseline gap-2">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Saved Drafts
            </h2>
            <span className="rounded-sm bg-muted px-1.5 py-0.5 text-[11px] font-medium tabular-nums text-muted-foreground">
              {drafts.length}
            </span>
            <span className="text-[11px] text-muted-foreground">
              unsaved · kept {DRAFT_RETENTION_DAYS} days in this browser
            </span>
          </div>

          <div className="flex gap-3 overflow-x-auto pb-1 custom-scrollbar">
            {drafts.map((draft) => {
              const daysLeft = daysUntilExpiry(draft.expiresAt);
              return (
                <div
                  key={draft.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => router.push(`/editor?paperId=${draft.id}`)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      router.push(`/editor?paperId=${draft.id}`);
                    }
                  }}
                  className="group relative w-56 shrink-0 cursor-pointer rounded-lg border border-border bg-background p-3 text-left transition-colors hover:border-primary/50 hover:bg-muted/40"
                >
                  <div className="flex items-start gap-2">
                    <FileText className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-foreground">
                        {draft.title || "Untitled draft"}
                      </p>
                      <p className="truncate text-[11px] text-muted-foreground">
                        {[draft.className, draft.subject]
                          .filter(Boolean)
                          .join(" · ") || "No class or subject yet"}
                      </p>
                    </div>
                  </div>

                  <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground">
                    {draft.questionCount > 0 && (
                      <span className="tabular-nums">
                        {draft.questionCount} q · {draft.totalMarks} m
                      </span>
                    )}
                    {draft.setLabels.length > 1 && (
                      <span>Sets {draft.setLabels.join("/")}</span>
                    )}
                    <span className="tabular-nums">
                      {formatDate(new Date(draft.updatedAt).toISOString())}
                    </span>
                  </div>

                  {/* Retention has to be visible. A draft vanishing on day 10
                      with no warning is indistinguishable from data loss. */}
                  <p
                    className={cn(
                      "mt-1.5 text-[10.5px]",
                      daysLeft <= 2 ? "text-destructive" : "text-muted-foreground/70",
                    )}
                  >
                    {daysLeft === 0
                      ? "Deletes today unless saved"
                      : `Deletes in ${daysLeft} day${daysLeft === 1 ? "" : "s"} unless saved`}
                  </p>

                  <button
                    type="button"
                    aria-label={`Delete draft ${draft.title || "Untitled draft"}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      void deleteDraft(draft);
                    }}
                    className="absolute right-1.5 top-1.5 rounded-sm p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-destructive/10 hover:text-destructive focus-visible:opacity-100 group-hover:opacity-100"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Recycle bin ─────────────────────────────────────────────
          Collapsed by default and headed by a count, because a bin that is
          always open is a second papers list competing with the real one. The
          count is what makes the toggle worth reading: "Recycle bin" alone
          gives a teacher no reason to open it, and the day they need it they
          need to know at a glance that the paper is in there. */}
      {trashed.length > 0 && (
        <div className="shrink-0 border-b border-border bg-muted/20 px-4 py-3 sm:px-6">
          <div className="flex flex-wrap items-baseline gap-2">
            <button
              type="button"
              onClick={() => setShowTrash((v) => !v)}
              aria-expanded={showTrash}
              className="flex items-baseline gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground hover:text-foreground"
            >
              <span>Recycle Bin</span>
              <span className="rounded-sm bg-muted px-1.5 py-0.5 text-[11px] font-medium tabular-nums">
                {trashed.length}
              </span>
              <ChevronRight
                className={cn(
                  "h-3.5 w-3.5 self-center transition-transform",
                  showTrash && "rotate-90",
                )}
                aria-hidden
              />
            </button>
            <span className="text-[11px] text-muted-foreground">
              deleted · kept {trashRetentionDays} days, then removed for good
            </span>
            {showTrash && (
              <AlertDialog>
                <AlertDialogTrigger className="ml-auto text-[11px] text-muted-foreground underline underline-offset-2 hover:text-destructive">
                  Empty bin
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Empty the recycle bin?</AlertDialogTitle>
                    <AlertDialogDescription>
                      This permanently deletes all {trashed.length} papers in the
                      bin, along with their questions and answer keys. This cannot
                      be undone.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction onClick={() => void handleEmptyTrash()}>
                      Empty bin
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            )}
          </div>

          {showTrash && (
            <div className="mt-2 flex gap-3 overflow-x-auto pb-1 custom-scrollbar">
              {trashed.map((paper) => (
                <div
                  key={paper.id}
                  className="relative w-56 shrink-0 rounded-lg border border-border bg-background p-3 text-left"
                >
                  <div className="flex items-start gap-2">
                    <FileText className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground/60" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-foreground">
                        {paper.title || "Untitled paper"}
                      </p>
                      <p className="truncate text-[11px] text-muted-foreground">
                        {[paper.gradeClass, paper.subject]
                          .filter(Boolean)
                          .join(" · ") || "No class or subject"}
                      </p>
                    </div>
                  </div>

                  <div className="mt-2 flex items-center gap-2">
                    {/* Restore leads. The reason to open a bin is to get
                        something back, not to finish destroying it. */}
                    <button
                      type="button"
                      onClick={() => void restorePaperById(paper.id, paper.answerScriptId)}
                      className="inline-flex items-center gap-1 rounded-sm border border-border px-2 py-1 text-[11px] font-medium text-foreground hover:bg-muted"
                    >
                      <Undo2 className="h-3 w-3" aria-hidden />
                      Restore
                    </button>
                    <button
                      type="button"
                      aria-label={`Permanently delete ${paper.title || "this paper"}`}
                      onClick={() => void purgePaperById(paper.id)}
                      className="inline-flex items-center gap-1 rounded-sm px-2 py-1 text-[11px] text-muted-foreground hover:text-destructive"
                    >
                      <Trash2 className="h-3 w-3" aria-hidden />
                      Delete for good
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Table ───────────────────────────────────────────────── */}
      <div className="flex-1 min-h-0 overflow-auto">
        {isLoading ? (
          <SkeletonRows rows={8} height="h-12" />
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-3 py-24 text-center">
            <div className="rounded-xl border-2 border-dashed border-border p-6">
              <BookOpen className="empty-breathe mx-auto h-10 w-10 text-muted-foreground/40" />
            </div>
            <p className="text-sm font-medium text-foreground">
              {search.trim()
                ? "No papers match your search."
                : "No saved papers yet."}
            </p>
            {!search.trim() && (
              <>
                <p className="max-w-xs text-xs text-muted-foreground">
                  Create a paper in the Editor and save it to see it here.
                </p>
                {/* The copy names the Editor; this opens it. A link rather
                    than a router push, so it behaves like any other link. */}
                <Link
                  href="/editor"
                  className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
                >
                  <FileText className="h-3.5 w-3.5" />
                  Open the Editor
                </Link>
              </>
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
                        className="flex h-7 w-7 items-center justify-center rounded-sm text-muted-foreground/60 transition-colors hover:bg-destructive/10 hover:text-destructive opacity-0 group-hover:opacity-100"
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
