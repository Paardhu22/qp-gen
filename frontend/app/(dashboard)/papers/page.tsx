"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { fetchJson } from "@/lib/api/http";
import {
  fetchPapers,
  fetchTrashedPapers,
  deletePaper,
  restorePaper,
  emptyPaperTrash,
  generateAnswerScript,
} from "@/lib/api/papers";
import { getPaperAction, type EditorPaper } from "@/features/papers/actions/savePaper";
import {
  computePaperBreakdown,
  questionTypeLabel,
  type PaperBreakdown,
} from "@/features/papers/paper-breakdown";
import { PaperPreview } from "@/features/papers/paper-preview";
import { formatDate } from "@/features/papers/library/format";
import { PaperCard } from "@/features/papers/library/paper-card";
import { DraftsRail, RecycleBin } from "@/features/papers/library/drafts-and-bin";
import {
  BookOpen,
  FileText,
  Search,
  Trash2,
  ArrowLeft,
  Pencil,
  Eye,
  Key,
  RefreshCcw,
  FileDown,
  ChevronRight,
  LayoutList,
  Hash,
  Award,
  Plus,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { PageTitle } from "@/components/ui/page-title";
import { Skeleton } from "@/components/ui/skeleton";
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
import { errorWithRetry } from "@/lib/toasts";
import { cn } from "@/lib/utils";
import { useSession } from "@/features/auth/auth-client";
import { deleteServerDraft, pullDrafts } from "@/features/papers/drafts-sync";
import {
  deleteLiveDocument,
  clearLiveDocumentsForUser,
  getLiveDocumentId,
  purgeExpiredDrafts,
} from "@/features/papers/live-document-db";
import {
  summarizeDrafts,
  type DraftSummary,
} from "@/features/papers/drafts";

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
  const [subjectFilter, setSubjectFilter] = useState<string | null>(null);
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set());
  const [isClearing, setIsClearing] = useState(false);

  // Detail view
  const [selectedPaperId, setSelectedPaperId] = useState<string | null>(null);
  const [selectedSetId, setSelectedSetId] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailPaper, setDetailPaper] = useState<EditorPaper | null>(null);

  // Answer script generation
  const [generatingIds, setGeneratingIds] = useState<Set<string>>(new Set());

  // The answer script is read in this page's preview, beside the paper; the
  // editor is only for changing it. Holds the id of the paper whose preview
  // shows its answer script, so a generation that finishes after the teacher
  // has moved to another paper does not flip that paper's preview.
  const [answerPreviewFor, setAnswerPreviewFor] = useState<string | null>(null);
  // Answer scripts fetched for the preview, by id. "error" when one could not
  // be loaded: the request failed, or the answer script is in the bin.
  const [answerDocs, setAnswerDocs] = useState<
    Record<string, EditorPaper | "error">
  >({});

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
  // Named rather than inline so the failure toast has something to retry.
  const loadPapers = useCallback(function loadPapers() {
    setIsLoading(true);
    return fetchPapers<Paper[]>()
      .then((data) => setPapers(data ?? []))
      .catch(() =>
        errorWithRetry("Could not load your saved papers.", loadPapers),
      )
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    void loadPapers();
  }, [loadPapers]);

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

  // Subjects present in the library, for the filter chips. Keyed by lowercase:
  // teachers type "ict", "ICT" and "Ict" for the same subject, and three
  // chips for one thing is a filter that looks broken. The label shown is the
  // first spelling with a capital in it, else the first spelling capitalised.
  const subjects = useMemo(() => {
    const byKey = new Map<string, string>();
    for (const { subjectLabel } of questionPapers) {
      if (subjectLabel === "—") continue;
      const key = subjectLabel.toLowerCase();
      const known = byKey.get(key);
      if (!known || (!/[A-Z]/.test(known) && /[A-Z]/.test(subjectLabel))) {
        byKey.set(key, subjectLabel);
      }
    }
    return Array.from(byKey, ([key, label]) => ({
      key,
      label: /[A-Z]/.test(label)
        ? label
        : label.charAt(0).toUpperCase() + label.slice(1),
    })).sort((a, b) => a.label.localeCompare(b.label));
  }, [questionPapers]);

  // Most recently touched first: the paper a teacher wants is almost always
  // the one they were last working on.
  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    const stamp = (p: Paper) =>
      new Date(p.updated_at ?? p.created_at ?? 0).getTime() || 0;
    return questionPapers
      .filter(
        (p) =>
          subjectFilter === null ||
          p.subjectLabel.toLowerCase() === subjectFilter,
      )
      .filter(
        (p) =>
          !term ||
          [p.title, p.classLabel, p.subjectLabel, p.boardLabel]
            .join(" ")
            .toLowerCase()
            .includes(term),
      )
      .sort((a, b) => stamp(b) - stamp(a));
  }, [questionPapers, search, subjectFilter]);

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
      .catch(() => toast.error("Could not load those paper details."))
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

  // The active set's answer script. Each set links its own in its metadata;
  // Set A also has the paper-level link from before there were sets.
  const answerScriptId: string | null =
    activeSet?.metadata?.answer_script_id ||
    (activeSet?.id === detailPaper?.sets?.[0]?.id
      ? selectedMeta?.answerScriptId
      : null) ||
    null;
  const showingAnswer =
    !!answerScriptId && answerPreviewFor === selectedPaperId;
  const answerDoc = answerScriptId ? answerDocs[answerScriptId] : undefined;

  useEffect(() => {
    if (!showingAnswer || !answerScriptId || answerDoc) return;
    let active = true;
    getPaperAction(answerScriptId)
      .then((doc) => {
        if (active) setAnswerDocs((prev) => ({ ...prev, [answerScriptId]: doc }));
      })
      .catch(() => {
        if (active)
          setAnswerDocs((prev) => ({ ...prev, [answerScriptId]: "error" }));
      });
    return () => {
      active = false;
    };
  }, [showingAnswer, answerScriptId, answerDoc]);

  function retryAnswerDoc(id: string) {
    setAnswerDocs((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
  }

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
      toast.error("Could not delete that paper.");
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
      toast.error("Could not clear your papers.");
    } finally {
      setIsClearing(false);
    }
  }

  // Also regenerates: the backend links the new answer script in place of the
  // old one and moves the old one to the recycle bin.
  async function handleGenerateAnswerScript(
    paperId: string,
    setId?: string,
    { replacing = false }: { replacing?: boolean } = {},
  ) {
    const trackingId = setId ? `${paperId}-${setId}` : paperId;
    setGeneratingIds((prev) => new Set(prev).add(trackingId));
    try {
      const result = await generateAnswerScript(paperId, setId);

      // Update local state so UI updates
      setDetailPaper((prev) => {
        if (!prev || prev.id !== paperId) return prev;
        const updatedSets = (prev.sets || []).map((s) =>
          s.id === setId ? { ...s, metadata: { ...(s.metadata || {}), answer_script_id: result.answer_script_paper_id } } : s
        );
        return { ...prev, sets: updatedSets };
      });

      setPapers((prev) =>
        prev.map((p) =>
          p.id === paperId
            ? { ...p, answerScriptId: (!setId || p.sets?.[0]?.id === setId) ? result.answer_script_paper_id : p.answerScriptId }
            : p,
        ),
      );
      // Show what was just made, in the preview beside the paper.
      setAnswerPreviewFor(paperId);
      if (replacing) {
        void loadTrash();
        toast.success("Answer script regenerated.", {
          description: "The previous one is in the recycle bin.",
        });
      } else {
        toast.success("Answer script generated!");
      }
    } catch (err: any) {
      toast.error(err?.message || "Could not generate the answer script.");
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
    const createdOn = formatDate(
      selectedMeta?.created_at ?? selectedMeta?.updated_at,
    );
    const metaChips = [
      selectedMeta?.subjectLabel,
      selectedMeta && selectedMeta.classLabel !== "—"
        ? /^class\b/i.test(selectedMeta.classLabel)
          ? selectedMeta.classLabel
          : `Class ${selectedMeta.classLabel}`
        : null,
      selectedMeta?.boardLabel,
    ].filter((v): v is string => !!v && v !== "—");
    const segmentClass = (active: boolean) =>
      cn(
        "min-h-9 rounded-lg px-3 text-xs font-medium transition-colors sm:min-h-7",
        active
          ? "bg-background text-foreground shadow-sm ring-1 ring-foreground/10"
          : "text-muted-foreground hover:text-foreground",
      );
    const actionClass =
      "inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-border bg-background px-3 text-xs font-medium text-foreground transition-colors hover:bg-accent disabled:opacity-50 sm:min-h-8";

    return (
      <div className="flex h-full min-h-0 flex-col bg-background">
        {/* ── Header ───────────────────────────────────────────── */}
        <header className="shrink-0 border-b border-border px-4 py-4 sm:px-6">
          <nav
            aria-label="Breadcrumb"
            className="mb-2 flex items-center gap-1.5 text-xs text-muted-foreground"
          >
            <button
              type="button"
              onClick={() => setSelectedPaperId(null)}
              className="inline-flex items-center gap-1 rounded-md font-medium transition-colors hover:text-foreground"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              Papers
            </button>
            <ChevronRight className="h-3 w-3 opacity-50" aria-hidden />
            <span className="truncate text-foreground">
              {selectedMeta?.title ?? "Untitled"}
            </span>
          </nav>

          <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
            <div className="min-w-0">
              <PageTitle className="break-words">
                {selectedMeta?.title ?? "Untitled"}
              </PageTitle>
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                {metaChips.map((chip) => (
                  <span
                    key={chip}
                    className="rounded-full bg-brand-sand/60 px-2.5 py-0.5 text-xs font-medium text-foreground"
                  >
                    {chip}
                  </span>
                ))}
                <span className="text-xs text-muted-foreground">
                  Created {createdOn}
                </span>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => router.push(`/editor?paperId=${selectedPaperId}`)}
                className="inline-flex min-h-9 items-center gap-1.5 rounded-lg bg-primary px-3.5 text-xs font-semibold text-primary-foreground shadow-xs transition-colors hover:bg-primary-hover sm:min-h-8"
              >
                <Pencil className="h-3.5 w-3.5" />
                Open in editor
              </button>
              {(["pdf", "docx"] as const).map((format) => (
                <button
                  key={format}
                  type="button"
                  onClick={() =>
                    router.push(
                      `/editor?paperId=${selectedPaperId}&action=export-${format}`,
                    )
                  }
                  className={actionClass}
                >
                  <FileDown className="h-3.5 w-3.5" />
                  {format === "pdf" ? "PDF" : "Word"}
                </button>
              ))}
            </div>
          </div>
        </header>

        {detailLoading ? (
          <Spinner size="page" />
        ) : (
          <div className="flex min-h-0 flex-1 flex-col overflow-y-auto lg:flex-row lg:overflow-hidden">
            {/* ── Left: sets, breakdown, answer script ───────────── */}
            <aside className="shrink-0 space-y-6 border-b border-border p-4 sm:p-6 lg:w-[400px] lg:overflow-y-auto lg:border-b-0 lg:border-r xl:w-[440px]">
              {/* Set selector */}
              {detailPaper?.sets && detailPaper.sets.length > 1 && (
                <div className="space-y-2">
                  <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Set
                  </h3>
                  <div
                    role="tablist"
                    aria-label="Paper set"
                    className="inline-flex gap-0.5 rounded-xl bg-muted p-0.5"
                  >
                    {detailPaper.sets.map((set) => (
                      <button
                        key={set.id}
                        type="button"
                        role="tab"
                        aria-selected={selectedSetId === set.id}
                        onClick={() => setSelectedSetId(set.id || null)}
                        className={segmentClass(selectedSetId === set.id)}
                      >
                        {set.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Paper breakdown */}
              {breakdown && breakdown.totalQuestions > 0 && (
                <div className="space-y-4">
                  <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Breakdown
                  </h3>

                  <div className="grid grid-cols-3 gap-2">
                    <StatTile
                      icon={<LayoutList className="h-3.5 w-3.5" />}
                      label="Sections"
                      value={breakdown.sectionCount}
                    />
                    <StatTile
                      icon={<Hash className="h-3.5 w-3.5" />}
                      label="Questions"
                      value={breakdown.totalQuestions}
                    />
                    <StatTile
                      icon={<Award className="h-3.5 w-3.5" />}
                      label="Marks"
                      value={breakdown.totalMarks}
                    />
                  </div>

                  {breakdown.sections.length > 0 && (
                    <div className="overflow-hidden rounded-2xl border border-border bg-card">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-border text-xs text-muted-foreground">
                            <th className="px-3 py-2 text-left font-medium">
                              Section
                            </th>
                            <th className="px-3 py-2 text-right font-medium">
                              Qs
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
                              <td className="px-3 py-2.5">
                                <span className="text-foreground">
                                  {sec.title}
                                </span>
                                {/* Share of the paper's marks, so lopsided
                                    sections are visible without arithmetic. */}
                                <div
                                  aria-hidden
                                  className="mt-1.5 h-1 overflow-hidden rounded-full bg-muted"
                                >
                                  <div
                                    className="h-full rounded-full bg-primary/60"
                                    style={{
                                      width: `${
                                        breakdown.totalMarks > 0
                                          ? Math.min(
                                              100,
                                              (sec.marks / breakdown.totalMarks) * 100,
                                            )
                                          : 0
                                      }%`,
                                    }}
                                  />
                                </div>
                              </td>
                              <td className="px-3 py-2.5 text-right tabular-nums text-muted-foreground">
                                {sec.questionCount}
                              </td>
                              <td className="px-3 py-2.5 text-right font-medium tabular-nums text-foreground">
                                {sec.marks}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {Object.keys(breakdown.typeDistribution).length > 0 && (
                    <div className="space-y-2">
                      <h4 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        Question types
                      </h4>
                      <div className="flex flex-wrap gap-1.5">
                        {Object.entries(breakdown.typeDistribution)
                          .sort(([, a], [, b]) => b - a)
                          .map(([code, count]) => (
                            <span
                              key={code}
                              className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1 text-xs text-muted-foreground"
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

              {/* Answer script */}
              <div className="space-y-3 rounded-2xl border border-border bg-card p-4">
                <div className="flex items-start gap-3">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-sand/60 text-primary">
                    <Key className="h-4 w-4" aria-hidden />
                  </span>
                  <div className="min-w-0">
                    <h3 className="font-heading text-sm font-medium tracking-[-0.01em] text-foreground">
                      Answer script
                      {activeSet && detailPaper?.sets && detailPaper.sets.length > 1
                        ? ` · ${activeSet.label}`
                        : ""}
                    </h3>
                    <p className="text-xs text-muted-foreground">
                      {answerScriptId
                        ? "Ready. Read it beside the paper, edit it, or download it."
                        : "Generate worked answers and marking points for this paper."}
                    </p>
                  </div>
                </div>
                {(() => {
                  const isGenerating = generatingIds.has(
                    activeSet?.id
                      ? `${selectedPaperId}-${activeSet.id}`
                      : selectedPaperId,
                  );

                  if (answerScriptId) {
                    // `exportType` files the download as an answer script,
                    // not as another question paper.
                    const answerScriptUrl = `/editor?paperId=${answerScriptId}&exportType=answer_script`;
                    return (
                      <div className="flex flex-wrap items-center gap-2">
                        <button
                          type="button"
                          onClick={() => setAnswerPreviewFor(selectedPaperId)}
                          className={cn(actionClass, showingAnswer && "bg-accent")}
                        >
                          <Eye className="h-3.5 w-3.5" />
                          View
                        </button>
                        <button
                          type="button"
                          onClick={() => router.push(answerScriptUrl)}
                          className={actionClass}
                        >
                          <Pencil className="h-3.5 w-3.5" />
                          Edit
                        </button>
                        {(["pdf", "docx"] as const).map((format) => (
                          <button
                            key={format}
                            type="button"
                            onClick={() =>
                              router.push(`${answerScriptUrl}&action=export-${format}`)
                            }
                            className={actionClass}
                          >
                            <FileDown className="h-3.5 w-3.5" />
                            {format === "pdf" ? "PDF" : "Word"}
                          </button>
                        ))}
                        {/* The way back from an answer script that came out
                            wrong or was cleared by mistake. Without it, a set
                            that had an answer script could never get another. */}
                        <AlertDialog>
                          <AlertDialogTrigger
                            className={actionClass}
                            disabled={isGenerating}
                          >
                            {isGenerating ? (
                              <Spinner className="size-3.5" />
                            ) : (
                              <RefreshCcw className="h-3.5 w-3.5" />
                            )}
                            {isGenerating ? "Regenerating…" : "Regenerate"}
                          </AlertDialogTrigger>
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle>
                                Regenerate the answer script
                                {activeSet ? ` for ${activeSet.label}` : ""}?
                              </AlertDialogTitle>
                              <AlertDialogDescription>
                                A new answer script is generated from the
                                paper as it is now. The current one, including
                                any edits made to it, moves to the recycle bin
                                and can be recovered for {trashRetentionDays}{" "}
                                days.
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>Cancel</AlertDialogCancel>
                              <AlertDialogAction
                                onClick={() =>
                                  handleGenerateAnswerScript(
                                    selectedPaperId,
                                    activeSet?.id,
                                    { replacing: true },
                                  )
                                }
                              >
                                Regenerate
                              </AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      </div>
                    );
                  }
                  return (
                    <button
                      type="button"
                      disabled={isGenerating}
                      onClick={() =>
                        handleGenerateAnswerScript(selectedPaperId, activeSet?.id)
                      }
                      className="inline-flex min-h-9 items-center gap-1.5 rounded-lg bg-primary px-3.5 text-xs font-semibold text-primary-foreground shadow-xs transition-colors hover:bg-primary-hover disabled:opacity-50 sm:min-h-8"
                    >
                      {isGenerating ? (
                        <Spinner className="size-3.5" />
                      ) : (
                        <Key className="h-3.5 w-3.5" />
                      )}
                      {isGenerating
                        ? "Generating…"
                        : `Generate answer script${activeSet ? ` for ${activeSet.label}` : ""}`}
                    </button>
                  );
                })()}
              </div>
            </aside>

            {/* ── Right: paper or answer script preview ───────────── */}
            <div className="flex min-h-[70dvh] min-w-0 flex-1 flex-col overflow-hidden bg-muted/30 lg:min-h-0">
              {answerScriptId && (
                <div className="flex shrink-0 items-center border-b border-border bg-background px-4 py-2">
                  <div
                    role="tablist"
                    aria-label="Preview"
                    className="inline-flex gap-0.5 rounded-xl bg-muted p-0.5"
                  >
                    {(
                      [
                        ["paper", "Question paper"],
                        ["answer", "Answer script"],
                      ] as const
                    ).map(([mode, label]) => {
                      const active = (mode === "answer") === showingAnswer;
                      return (
                        <button
                          key={mode}
                          type="button"
                          role="tab"
                          aria-selected={active}
                          onClick={() =>
                            setAnswerPreviewFor(
                              mode === "answer" ? selectedPaperId : null,
                            )
                          }
                          className={segmentClass(active)}
                        >
                          {label}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
              <div className="min-h-0 flex-1">
                {!showingAnswer ? (
                  <PaperPreview
                    content={activeSet?.content || detailPaper?.content}
                    subject={detailPaper?.subject}
                  />
                ) : answerDoc === "error" ? (
                  <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center text-sm text-muted-foreground">
                    <p>
                      Could not load this answer script. If it was deleted,
                      use Regenerate to make a new one.
                    </p>
                    <button
                      type="button"
                      onClick={() =>
                        answerScriptId && retryAnswerDoc(answerScriptId)
                      }
                      className={actionClass}
                    >
                      Try again
                    </button>
                  </div>
                ) : answerDoc ? (
                  <PaperPreview
                    content={answerDoc.content}
                    subject={detailPaper?.subject}
                  />
                ) : (
                  <Spinner size="page" />
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // List view (default)
  // ---------------------------------------------------------------------------

  const hasFilters = search.trim() !== "" || subjectFilter !== null;

  return (
    <div className="h-full min-h-0 overflow-y-auto bg-background">
      <div className="mx-auto w-full max-w-6xl space-y-8 px-4 py-6 pb-safe sm:px-6 sm:py-8">
        {/* ── Header ────────────────────────────────────────────── */}
        <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
          <div>
            {/* This route is the PAPERS list — "Search papers…", "No saved
                papers yet", "Clear all saved papers". It used to live at
                /question-bank while the questions lived at /paper-library,
                so both the URL and the heading described the other page. The
                heading was fixed first; the routes followed. */}
            <PageTitle>Papers</PageTitle>
            <p className="mt-1.5 text-sm text-muted-foreground">
              {isLoading
                ? "Loading your library…"
                : questionPapers.length === 0
                  ? "Everything you save from the editor lands here."
                  : `${questionPapers.length} saved ${questionPapers.length === 1 ? "paper" : "papers"}${
                      drafts.length > 0
                        ? ` · ${drafts.length} unsaved ${drafts.length === 1 ? "draft" : "drafts"}`
                        : ""
                    }`}
            </p>
          </div>

          <Link
            href="/editor?new=true"
            className="inline-flex min-h-10 items-center gap-1.5 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground shadow-xs transition-colors hover:bg-primary-hover sm:min-h-9"
          >
            <Plus className="h-4 w-4" />
            New paper
          </Link>
        </header>

        {/* ── Drafts ────────────────────────────────────────────── */}
        {!draftsLoading && (
          <DraftsRail
            drafts={drafts}
            onOpen={(draft) => router.push(`/editor?paperId=${draft.id}`)}
            onDelete={(draft) => void deleteDraft(draft)}
          />
        )}

        {/* ── Library ───────────────────────────────────────────── */}
        <section aria-labelledby="library-heading" className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <h2
              id="library-heading"
              className="font-heading text-base font-medium tracking-[-0.02em]"
            >
              All papers
            </h2>

            <div className="relative ml-auto w-full min-w-0 sm:w-72">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                className="h-10 rounded-xl pl-9 sm:h-9"
                placeholder="Search papers…"
                aria-label="Search papers"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
          </div>

          {subjects.length > 1 && (
            <div
              role="group"
              aria-label="Filter by subject"
              className="-mx-4 flex gap-1.5 overflow-x-auto px-4 pb-1 no-scrollbar sm:mx-0 sm:flex-wrap sm:px-0"
            >
              {[{ key: null, label: "All" }, ...subjects].map(({ key, label }) => {
                const active = subjectFilter === key;
                return (
                  <button
                    key={key ?? "all"}
                    type="button"
                    aria-pressed={active}
                    onClick={() => setSubjectFilter(key)}
                    className={cn(
                      "min-h-9 shrink-0 rounded-full border px-3.5 text-xs font-medium transition-colors sm:min-h-8",
                      active
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-border bg-card text-muted-foreground hover:border-primary/40 hover:text-foreground",
                    )}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          )}

          {isLoading ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 6 }, (_, i) => (
                <Skeleton key={i} className="h-52 rounded-2xl" />
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-border bg-card/40 px-6 py-20 text-center">
              <div className="rounded-2xl bg-brand-sand/50 p-5">
                <BookOpen className="empty-breathe mx-auto h-9 w-9 text-primary/70" />
              </div>
              <p className="font-heading text-base font-medium tracking-[-0.02em] text-foreground">
                {hasFilters ? "No papers match." : "No saved papers yet."}
              </p>
              {!hasFilters && (
                <>
                  <p className="max-w-xs text-sm text-muted-foreground">
                    Create a paper in the editor and save it to see it here.
                  </p>
                  {/* The copy names the Editor; this opens it. A link rather
                      than a router push, so it behaves like any other link. */}
                  <Link
                    href="/editor"
                    className="mt-1 inline-flex min-h-10 items-center gap-1.5 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground shadow-xs transition-colors hover:bg-primary-hover sm:min-h-9"
                  >
                    <FileText className="h-4 w-4" />
                    Open the editor
                  </Link>
                </>
              )}
              {hasFilters && (
                <button
                  type="button"
                  onClick={() => {
                    setSearch("");
                    setSubjectFilter(null);
                  }}
                  className="text-sm font-medium text-primary hover:underline"
                >
                  Clear filters
                </button>
              )}
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {filtered.map((paper) => (
                <PaperCard
                  key={paper.id}
                  paper={paper}
                  deleting={deletingIds.has(paper.id)}
                  onOpen={() => setSelectedPaperId(paper.id)}
                  onEdit={() => router.push(`/editor?paperId=${paper.id}`)}
                  onExport={(format) =>
                    router.push(
                      `/editor?paperId=${paper.id}&action=export-${format}`,
                    )
                  }
                  onDelete={() => handleDeletePaper(paper.id)}
                />
              ))}
            </div>
          )}
        </section>

        {/* ── Recycle bin ───────────────────────────────────────── */}
        <RecycleBin
          papers={trashed}
          open={showTrash}
          onToggle={() => setShowTrash((v) => !v)}
          retentionDays={trashRetentionDays}
          onRestore={(id, asId) => void restorePaperById(id, asId)}
          onPurge={(id) => void purgePaperById(id)}
          onEmpty={() => void handleEmptyTrash()}
        />

        {/* Rare and destructive, so it lives at the very bottom, quiet. */}
        {!isLoading && papers.length > 0 && (
          <div className="flex justify-center pt-2">
            <AlertDialog>
              <AlertDialogTrigger
                className="destructive-action inline-flex min-h-9 items-center gap-1.5 rounded-lg px-3 text-xs disabled:opacity-50"
                disabled={isClearing}
              >
                <Trash2 className="h-3.5 w-3.5" />
                {isClearing ? "Clearing…" : "Clear all saved papers"}
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
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Small components
// ---------------------------------------------------------------------------

function StatTile({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1 rounded-2xl bg-muted/50 p-3">
      <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
        {icon}
        {label}
      </span>
      <span className="font-heading text-2xl font-semibold tabular-nums tracking-[-0.03em] text-foreground">
        {value}
      </span>
    </div>
  );
}
