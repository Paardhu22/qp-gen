"use client";

import { GeneratorForm } from "@/components/generator-form";
import { TiptapEditor, normalizeInitialContent } from "@/components/tiptap-editor";
import { ComparisonWorkspace } from "@/components/comparison-workspace";
import { useEditorStore } from "@/store/editor-store";
import { type AppliedHsatSource } from "@/components/hsat-source-picker";
import { fetchJson } from "@/lib/api-client";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useState, useEffect, useRef, useCallback } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import { Loader2, PanelLeftOpen, Zap, X } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  savePaperAction,
  updatePaperAction,
  getPaperAction,
} from "@/actions/savePaper";
import { getQuestionsFromBank } from "@/actions/saveQuestions";
import { useSession } from "@/lib/auth-client";
import {
  deleteLiveDocument,
  deleteLiveDocumentsForPaper,
  getLiveDocumentId,
  getLatestLiveDocumentForUser,
  getLiveDocument,
  saveLiveDocument,
} from "@/lib/live-document-db";
import {
  basePaperId,
  withSetSuffix,
  isDraftPaperId,
  newLocalDraftId,
  persistablePaperId,
  DRAFT_PAPER_ID,
} from "@/lib/paper-id";
import { draftScopeOfDocument } from "@/lib/drafts";
import { resolveTabContent } from "@/lib/set-content";

export default function EditorPage() {
  const router = useRouter();
  const { data: sessionData } = useSession();

  const [hsatSources, setHsatSources] = useState<AppliedHsatSource[]>([]);
  const [uploadedDocs, setUploadedDocs] = useState<{ id: string; name: string; size: number }[]>([]);

  // Modals state from store
  const savePaperModalOpen = useEditorStore(
    (state) => state.savePaperModalOpen,
  );
  const setSavePaperModalOpen = useEditorStore(
    (state) => state.setSavePaperModalOpen,
  );

  // NOTE: `editorContent` is intentionally NOT subscribed here any more —
  // the TipTap editor used to push it into the store on every keystroke,
  // which re-rendered the whole EditorPage tree on each one. Save reads
  // the live editor via `window.__activeEditorBuildContent` instead, so
  // we only re-render when something we actually display changes.

  // Paper Form state
  const [paperClass, setPaperClass] = useState("");
  const [paperSubject, setPaperSubject] = useState("");
  const [paperExamName, setPaperExamName] = useState("");

  // Question Bank Browser state
  const questionBankBrowserOpen = useEditorStore(
    (state) => state.questionBankBrowserOpen,
  );
  const setQuestionBankBrowserOpen = useEditorStore(
    (state) => state.setQuestionBankBrowserOpen,
  );
  const appendQuestions = useEditorStore((state) => state.appendQuestions);
  const comparisonSets = useEditorStore((state) => state.comparisonSets);
  // Sets the teacher approved in the review workspace. Each one becomes the
  // content of its own tab — the reason there is no "Insert set" button any
  // more. `approvedAt` changes on every approval and is what tells the editor
  // this content supersedes whatever draft is in IndexedDB for that tab.
  const approvedSets = useEditorStore((state) => state.approvedSets);
  const approvedAt = useEditorStore((state) => state.approvedAt);

  const [activeSetTab, setActiveSetTab] = useState("A");
  const [loadedSets, setLoadedSets] = useState<any[]>([]);

  const [browserSearchQuery, setBrowserSearchQuery] = useState("");
  const [browserQuestions, setBrowserQuestions] = useState<any[]>([]);
  const [browserLoading, setBrowserLoading] = useState(false);
  const [selectedBankQuestions, setSelectedBankQuestions] = useState<
    Set<string>
  >(new Set());

  const [isSaving, setIsSaving] = useState(false);
  const [paperContent, setPaperContent] = useState<string | undefined>(
    undefined,
  );
  const [loadedPaperTitle, setLoadedPaperTitle] = useState<string | null>(null);
  const [paperUpdatedAt, setPaperUpdatedAt] = useState<string | null>(null);
  const [paperLoading, setPaperLoading] = useState(false);
  const [paperError, setPaperError] = useState<string | null>(null);
  const [currentPaperId, setCurrentPaperId] = useState<string | null>(null);

  // Mirrors currentPaperId so the reset routine can read the latest value
  // without being re-created (and re-firing the load effect) on every change.
  const currentPaperIdRef = useRef<string | null>(null);
  useEffect(() => {
    currentPaperIdRef.current = currentPaperId;
  }, [currentPaperId]);

  // Bumped to force a brand-new TiptapEditor instance (fresh ProseMirror doc +
  // cleared undo/redo history + reset save state) — see the `key` prop below.
  const [editorInstanceKey, setEditorInstanceKey] = useState(0);

  const clearComparisonSets = useEditorStore((s) => s.clearComparisonSets);
  const setGlobalSaveState = useEditorStore((s) => s.setSaveState);
  const awaitingGeneratedPaper = useEditorStore((s) => s.awaitingGeneratedPaper);
  const consumeGeneratedPaperHandoff = useEditorStore(
    (s) => s.consumeGeneratedPaperHandoff,
  );

  // ── "New Paper" reset ─────────────────────────────────────────────────
  // A brand-new paper must start with EVERY set empty and hold no reference
  // to the paper that was open before. The previous reset only cleared the
  // inputs that feed Set A (paperContent + metadata), so Sets B/C — whose
  // content comes from `comparisonSets`/`loadedSets` and their own per-set
  // IndexedDB drafts (`current_B`, `current_C`, …) — kept rendering the old
  // paper. This purges all three sources, in order, and forces a fresh editor
  // instance so switching tabs afterwards can never rehydrate stale content.
  const resetToNewPaper = useCallback(async () => {
    const userId = sessionData?.user?.id;

    // 1. Purge only the LEGACY shared draft scope. Every unsaved paper used to
    //    write to `current_A|B|C`, so starting a new one had to delete those
    //    keys or the fresh editor would rehydrate the old paper — which meant
    //    "New paper" destroyed unsaved work. Drafts now get an id of their own
    //    (`newLocalDraftId`), so there is nothing to clear: the previous draft
    //    stays put under its own keys and is listed on the Papers page. Only
    //    the shared `current` scope still needs clearing, and only because
    //    drafts written before this change live there.
    //
    //    A per-draft scope is deliberately NOT deleted, including the paper
    //    that was open a moment ago.
    if (userId) {
      await deleteLiveDocumentsForPaper(userId, DRAFT_PAPER_ID);
    }

    // 2. Drop the multi-set references so the Set B/C tabs disappear and their
    //    initialContent can no longer resolve to the old paper.
    clearComparisonSets();
    setLoadedSets([]);
    setActiveSetTab("A");

    // 3. Reset paper identity, metadata, content and save state.
    setCurrentPaperId(null);
    setPaperContent("");
    setLoadedPaperTitle(null);
    setPaperUpdatedAt(null);
    setPaperError(null);
    setPaperClass("");
    setPaperSubject("");
    setPaperExamName("");
    setHsatSources([]);
    setUploadedDocs([]);
    setGlobalSaveState("saved");

    // 4. Force a fresh TiptapEditor (empty doc, cleared undo/redo history).
    setEditorInstanceKey((k) => k + 1);
  }, [sessionData?.user?.id, clearComparisonSets, setGlobalSaveState]);

  // Resizable sidebar
  const SIDEBAR_MIN = 260;
  const SIDEBAR_MAX = 600;
  const SIDEBAR_DEFAULT = 360;
  const STORAGE_KEY = "editor-sidebar-width";

  const [sidebarWidth, setSidebarWidth] = useState<number>(() => {
    if (typeof window === "undefined") return SIDEBAR_DEFAULT;
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      const n = parseInt(saved, 10);
      if (!isNaN(n) && n >= SIDEBAR_MIN && n <= SIDEBAR_MAX) return n;
    }
    return SIDEBAR_DEFAULT;
  });

  // Mobile (< lg): the generator panel is an off-canvas left drawer toggled
  // from the editor status bar instead of an inline resizable sidebar.
  const [genDrawerOpen, setGenDrawerOpen] = useState(false);
  useEffect(() => {
    if (!genDrawerOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setGenDrawerOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
    };
  }, [genDrawerOpen]);

  const isDragging = useRef(false);
  const dragStartX = useRef(0);
  const dragStartWidth = useRef(0);

  const onDragStart = useCallback(
    (e: React.MouseEvent) => {
      isDragging.current = true;
      dragStartX.current = e.clientX;
      dragStartWidth.current = sidebarWidth;
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    },
    [sidebarWidth],
  );

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!isDragging.current) return;
      const delta = e.clientX - dragStartX.current;
      const next = Math.min(
        SIDEBAR_MAX,
        Math.max(SIDEBAR_MIN, dragStartWidth.current + delta),
      );
      setSidebarWidth(next);
    };
    const onMouseUp = () => {
      if (!isDragging.current) return;
      isDragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      setSidebarWidth((prev) => {
        localStorage.setItem(STORAGE_KEY, String(prev));
        return prev;
      });
    };
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, []);

  const searchParams = useSearchParams();
  // The URL must only ever carry a BASE paper id. A set suffix reaching it
  // (via a live document written before this normalisation, or a hand-edited
  // link) would be re-suffixed on every render pass and autosave would PUT a
  // non-existent "{id}_A_A" row. Strip it here and heal the URL below.
  const rawPaperIdParam = searchParams.get("paperId");
  const paperId = rawPaperIdParam
    ? basePaperId(rawPaperIdParam) ?? DRAFT_PAPER_ID
    : null;
  const isNew = searchParams.get("new") === "true";
  const actionParam = searchParams.get("action"); // e.g. "export-pdf" | "export-docx"
  // exportTypeParam lets the question-bank page signal that an answer script is being exported.
  const exportTypeParam = (searchParams.get("exportType") ?? "question_paper") as
    | "question_paper"
    | "answer_script"
    | "question_bank";

  // Heal a URL that already carries a set suffix (written by a live document
  // saved before the suffix leak was fixed). Left alone it keeps growing a
  // suffix per visit and every autosave 404s.
  useEffect(() => {
    if (rawPaperIdParam && paperId && rawPaperIdParam !== paperId) {
      router.replace(`/editor?paperId=${paperId}`);
    }
  }, [rawPaperIdParam, paperId, router]);

  // Deep-link to a specific set (A/B/C) from the Papers page's per-set
  // Preview / Export / Print actions. Only re-applies on an actual navigation
  // (searchParams identity change), so it never fights a manual tab click.
  const setParam = searchParams.get("set");
  useEffect(() => {
    const s = (setParam || "").toUpperCase();
    if (s === "A" || s === "B" || s === "C") setActiveSetTab(s);
  }, [setParam]);

  // Auto-trigger export when the action param is present (set by the
  // question-paper page Actions modal). We fire after the paper finishes
  // loading and immediately strip the param from the URL.
  useEffect(() => {
    if (!actionParam || paperLoading || paperError) return;
    const IMPORT_TIMEOUT = 800; // ms — give the editor time to hydrate
    const t = setTimeout(async () => {
      if (actionParam === "export-pdf") {
        try {
          const { exportToPDF } = await import("@/lib/export-pdf");
          const defaultName = `paper-${Date.now()}.pdf`;
          const rawName = window.prompt("Enter a filename for the PDF", defaultName);
          if (rawName) {
            const filename = rawName.trim().endsWith(".pdf")
              ? rawName.trim()
              : `${rawName.trim()}.pdf`;
            const blob = await exportToPDF("tiptap-paper-container", filename);
            toast.success("PDF downloaded!");
            const realPaperId = paperId && paperId !== "current" ? paperId : null;
            if (realPaperId) {
              const { uploadExportToS3 } = await import("@/lib/s3-upload");
              uploadExportToS3(blob, {
                exportType: exportTypeParam,
                fileFormat: "pdf",
                paperId: realPaperId,
              })
                .then(() => toast.success("Saved to cloud.", { duration: 2000 }))
                .catch((err) => console.error("[S3 upload]", err));
            }
          }
        } catch {
          toast.error("PDF export failed. Please try from the toolbar.");
        }
      } else if (actionParam === "export-docx") {
        try {
          const { exportToDocx } = await import("@/lib/export-docx");
          const defaultName = `paper-${Date.now()}.docx`;
          const rawName = window.prompt("Enter a filename for the DOCX", defaultName);
          if (rawName) {
            const trimmed = rawName.trim();
            const filename = /\.docx$/i.test(trimmed) ? trimmed : `${trimmed}.docx`;
            const container = document.getElementById("tiptap-paper-container");
            if (container) {
              const blob = await exportToDocx(container, filename);
              toast.success("DOCX downloaded!");
              const realPaperId = paperId && paperId !== "current" ? paperId : null;
              if (realPaperId) {
                const { uploadExportToS3 } = await import("@/lib/s3-upload");
                uploadExportToS3(blob, {
                  exportType: exportTypeParam,
                  fileFormat: "docx",
                  paperId: realPaperId,
                })
                  .then(() => toast.success("Saved to cloud.", { duration: 2000 }))
                  .catch((err) => console.error("[S3 upload]", err));
              }
            }
          }
        } catch {
          toast.error("DOCX export failed. Please try from the toolbar.");
        }
      } else if (actionParam === "print") {
        // Per-set print: the active set tab is already selected via ?set=,
        // and the editor's @media print rules isolate #tiptap-paper-container,
        // so the browser dialog prints only this set's A4 pages.
        try {
          window.print();
        } catch {
          toast.error("Print failed. Please try again from the editor.");
        }
      }
      // Remove the action param from the URL so refresh doesn't re-trigger
      const url = new URL(window.location.href);
      url.searchParams.delete("action");
      router.replace(url.pathname + url.search);
    }, IMPORT_TIMEOUT);
    return () => clearTimeout(t);
    // Deliberately narrow deps: this fires an export/print once, then strips
    // `action` from the URL so it cannot re-trigger.
  }, [actionParam, paperLoading, paperError]);

  // Guards the open-a-document effect below so it runs once per mount.
  const [checkedResume, setCheckedResume] = useState(false);

  // ── Open the right document, without asking ───────────────────────────
  // Opening `/editor` with no `?paperId=` used to pop "Resume previous paper?"
  // whenever the latest draft came from a different browser session. A word
  // processor does not interrogate you about your own unsaved work: it opens it.
  // So this always resolves silently — the drafts themselves are now listed,
  // openable and deletable on the Papers page, which is where a teacher chooses
  // between them deliberately instead of in a modal they did not ask for.
  useEffect(() => {
    if (!sessionData?.user?.id || paperId || checkedResume || isNew) return;

    // A paper generated on the dashboard arrives here with no `?paperId=`, which
    // is the same shape as "wandered back to the editor". Redirecting to the
    // previous draft would load its content and metadata over the paper that was
    // just generated. The generation is the intent; there is nothing to resume.
    if (awaitingGeneratedPaper) {
      consumeGeneratedPaperHandoff();
      setCheckedResume(true);
      return;
    }

    let active = true;
    (async () => {
      try {
        const latestDoc = await getLatestLiveDocumentForUser(
          sessionData.user.id,
        );
        if (!active) return;
        // Older live documents stored the composed "{id}_A" form in `paperId`.
        // No draft at all: mint an id for this one so it becomes a draft of its
        // own rather than sharing the single legacy `current` scope with every
        // other unsaved paper the teacher will ever start.
        const target = latestDoc
          ? (basePaperId(latestDoc.paperId) ??
            draftScopeOfDocument(latestDoc) ??
            DRAFT_PAPER_ID)
          : newLocalDraftId();
        router.replace(`/editor?paperId=${target}`);
      } catch (error) {
        console.error("Failed to resolve the draft to open:", error);
      } finally {
        if (active) setCheckedResume(true);
      }
    })();
    return () => {
      active = false;
    };
  }, [
    sessionData?.user?.id,
    paperId,
    checkedResume,
    isNew,
    router,
    awaitingGeneratedPaper,
    consumeGeneratedPaperHandoff,
  ]);

  useEffect(() => {
    let active = true;

    if (isNew) {
      setCheckedResume(true);
      // Give the new paper a scope of its own and land on it. Nothing is
      // deleted: the previous draft keeps its own ids and shows up under Saved
      // Drafts on the Papers page. That is what replaced the old archive dance
      // — "New paper" used to purge the `current_*` keys outright, which was
      // the only copy of whatever the teacher had not saved.
      (async () => {
        await resetToNewPaper();
        if (!active) return;
        const newDraftId = newLocalDraftId();
        // The blank draft only starts existing in IndexedDB once the editor's
        // debounced sync fires on a real edit. If the teacher clicks "New
        // Paper" and closes the tab before typing anything, that write never
        // happens — so the bare-`/editor` resume effect above still finds the
        // OLD draft (with its uploaded PDFs) as "latest" and reopens THAT,
        // making the new paper look like it never took. Seed an empty row
        // immediately so the new paper is the latest draft from the moment
        // it's created, not from the moment it's first edited.
        const userId = sessionData?.user?.id;
        if (userId) {
          const now = Date.now();
          try {
            await saveLiveDocument({
              id: getLiveDocumentId(userId, newDraftId),
              userId,
              paperId: newDraftId,
              title: "Untitled Paper",
              template: "cbse",
              editorJSON: normalizeInitialContent(undefined),
              pages: [],
              metadata: {
                title: "Untitled Paper",
                className: "",
                subject: "",
                template: "cbse",
                updatedAt: now,
                hsatSources: [],
                uploadedDocs: [],
              },
              layout: {
                pageSize: "A4",
                orientation: "portrait",
                template: "cbse",
                pages: [],
              },
              sync: { status: "synced", lastSyncedAt: now, error: null },
              updatedAt: now,
            });
          } catch (error) {
            console.warn("Failed to seed the new draft:", error);
          }
        }
        if (active) router.replace(`/editor?paperId=${newDraftId}`);
      })();
      return () => {
        active = false;
      };
    }

    if (!paperId) {
      setPaperContent("");
      setLoadedPaperTitle(null);
      setPaperError(null);
      setPaperUpdatedAt(null);
      setCurrentPaperId(null);
      setHsatSources([]);
      setUploadedDocs([]);
      return () => {
        active = false;
      };
    }

    // `isDraftPaperId`, not `startsWith("current")`: per-draft ids (`draft-…`)
    // are local-only too and must take the IndexedDB path, not be sent to
    // `getPaperAction` as if they were backend rows.
    if (paperId && isDraftPaperId(paperId)) {
      const loadLocalDraft = async () => {
        const userId = sessionData?.user?.id;
        if (!userId) return;
        try {
          // The editor writes one draft per set tab under "{id}_A|B|C"; the
          // un-suffixed key only exists for pre-set-tabs drafts. Read the
          // legacy key first, then Set A, so the page still recovers the
          // draft's title/class/subject instead of showing "Unsaved Draft".
          const draft =
            (await getLiveDocument(getLiveDocumentId(userId, paperId))) ??
            (await getLiveDocument(
              getLiveDocumentId(userId, withSetSuffix(paperId, "A")),
            ));
          if (draft && active) {
            setPaperContent(
              draft.editorJSON ? JSON.stringify(draft.editorJSON) : "",
            );
            setLoadedPaperTitle(draft.metadata?.title || "Unsaved Draft");
            setPaperExamName(draft.metadata?.title || "");
            setPaperClass(draft.metadata?.className || "");
            setPaperSubject(draft.metadata?.subject || "");
            setPaperUpdatedAt(new Date(draft.updatedAt).toISOString());
            setCurrentPaperId(paperId);
            setPaperError(null);
            setHsatSources(draft.metadata?.hsatSources || []);
            setUploadedDocs(draft.metadata?.uploadedDocs || []);
          } else if (active) {
            setPaperContent("");
            setLoadedPaperTitle("Unsaved Draft");
            setPaperExamName("");
            setPaperClass("");
            setPaperSubject("");
            setPaperUpdatedAt(null);
            setCurrentPaperId(paperId);
            setPaperError(null);
            setHsatSources([]);
            setUploadedDocs([]);
          }
        } catch (error) {
          console.error("Failed to load local draft metadata:", error);
        } finally {
          if (active) setPaperLoading(false);
        }
      };

      setPaperLoading(true);
      loadLocalDraft();
      return () => {
        active = false;
      };
    }

    setPaperLoading(true);
    setPaperError(null);
    setPaperContent(undefined);

    getPaperAction(paperId)
      .then((paper) => {
        if (!active) return;
        setPaperContent(paper.content || "");
        setLoadedPaperTitle(paper.examName || "Untitled Paper");
        setPaperExamName(paper.examName || "");
        setPaperClass(paper.class || "");
        setPaperSubject(paper.subject || "");
        setPaperUpdatedAt(paper.updatedAt || null);
        setCurrentPaperId(paper.id);
        setLoadedSets(paper.sets || []);
        setPaperError(null);

        // Fetch applied HSAT sources for this paper
        fetchJson<{ sources: any[] }>(`/api/hsat/papers/${paperId}/sources/`)
          .then((data) => {
            if (!active) return;
            const mapped = data.sources.map((s: any) => ({
              id: s.hsat_source_id,
              grade: s.grade,
              subject: s.subject,
              book: s.book,
              status: s.status,
              chunkCount: s.chunk_count,
            }));
            setHsatSources(mapped);
          })
          .catch((err) => {
            console.error("Failed to load applied HSAT sources:", err);
          });
      })
      .catch((error) => {
        if (!active) return;
        console.error(error);

        const is404 =
          error &&
          (error.status === 404 ||
            String(error.message || "")
              .toLowerCase()
              .includes("not found"));

        if (is404) {
          toast.error("This paper no longer exists. Opening a fresh paper...");
          setPaperContent("");
          setLoadedPaperTitle(null);
          setPaperError(null);
          setPaperUpdatedAt(null);
          setCurrentPaperId(null);
          setHsatSources([]);
          setUploadedDocs([]);

          router.replace("/editor");

          const userId = sessionData?.user?.id;
          if (userId && paperId) {
            deleteLiveDocumentsForPaper(userId, paperId);
          }
        } else {
          setPaperError("Failed to load paper. Please try again.");
          setPaperContent("");
          toast.error(error?.message || "Failed to load paper.");
        }
      })
      .finally(() => {
        if (active) setPaperLoading(false);
      });

    return () => {
      active = false;
    };
  }, [paperId, isNew, sessionData?.user?.id, router, resetToNewPaper]);

  // Once a draft has been saved it IS a paper, and papers are listed from the
  // backend. Its draft-scoped IndexedDB rows have to go, or the Papers page
  // shows the same work twice — once as a saved paper and once as an unsaved
  // draft that can never be reconciled with it. Only ever called after the
  // backend row exists, so this is not the last copy of anything.
  const discardDraftScope = useCallback(
    async (scope: string | null) => {
      const uid = sessionData?.user?.id;
      if (!uid || !scope || !isDraftPaperId(scope)) return;
      await deleteLiveDocumentsForPaper(uid, scope);
    },
    [sessionData?.user?.id],
  );

  const handleLivePaperCreated = useCallback(
    (newPaperId: string) => {
      const previousScope = basePaperId(currentPaperIdRef.current);
      setCurrentPaperId(newPaperId);
      setLoadedPaperTitle(
        (title) => title || paperExamName.trim() || "Untitled Paper",
      );
      setPaperUpdatedAt(new Date().toISOString());
      router.replace(`/editor?paperId=${newPaperId}`);
      void discardDraftScope(previousScope);
    },
    [paperExamName, router, discardDraftScope],
  );

  const handleSavePaper = async () => {
    if (!paperClass.trim() || !paperSubject.trim() || !paperExamName.trim()) {
      toast.error("Please fill in all fields: Class, Subject, Exam Name.");
      return;
    }

    setIsSaving(true);
    try {
      const trimmedClass = paperClass.trim();
      const trimmedSubject = paperSubject.trim();
      const trimmedExamName = paperExamName.trim();
      const updatedAt = new Date().getTime();

      // PERF: build the persisted content payload from the LIVE editor at
      // click time instead of from a per-keystroke store mirror. See the
      // matching `__activeEditorBuildContent` in tiptap-editor.tsx for the
      // motivation (full-doc serialize on every keystroke).
      const builder = (window as any).__activeEditorBuildContent as
        | ((meta?: any) => string)
        | undefined;
      let contentToSave = "";
      if (typeof builder === "function") {
        contentToSave = builder({
          examName: trimmedExamName,
          className: trimmedClass,
          subject: trimmedSubject,
        });
      }
      // Inject final metadata + updatedAt (the builder uses prop metadata,
      // which may lag the form values the user just typed into this modal).
      try {
        const parsed = contentToSave ? JSON.parse(contentToSave) : null;
        if (parsed && typeof parsed === "object") {
          parsed.metadata = {
            ...(parsed.metadata || {}),
            title: trimmedExamName,
            className: trimmedClass,
            subject: trimmedSubject,
            updatedAt,
          };
          parsed.updatedAt = updatedAt;
          contentToSave = JSON.stringify(parsed);
        }
      } catch {
        // Older shape — fall through with raw stringified content.
      }

      let setsPayload: any[] = [];
      const { comparisonSets } = useEditorStore.getState();
      const activeSets = comparisonSets && comparisonSets.length > 0 ? comparisonSets : loadedSets;

      if (activeSets && activeSets.length > 0) {
        setsPayload = await Promise.all(activeSets.map(async (s, idx) => {
          const labelNormalized = s.label.replace("Set ", "");
          let setContent = "";
          
          if (labelNormalized === activeSetTab) {
             setContent = contentToSave;
          } else {
             // withSetSuffix, not string concatenation: composing inline is
             // what let the suffix compound into "{id}_A_A" and 404 autosave.
             const draftId = getLiveDocumentId(
               sessionData?.user?.id || "",
               withSetSuffix(currentPaperId, labelNormalized),
             );
             const draft = await getLiveDocument(draftId);
             if (draft && draft.editorJSON) {
               setContent = JSON.stringify(draft.editorJSON);
             } else {
               const raw = typeof s.result !== "undefined" ? 
                  (typeof s.result === "string" ? s.result : JSON.stringify(s.result)) : 
                  s.content;
               setContent = JSON.stringify(normalizeInitialContent(raw));
             }
          }
          
          return {
            label: `Set ${labelNormalized}`,
            order: idx + 1,
            content: setContent,
            answers: "",
            metadata: s.result?.meta || s.metadata || {},
          };
        }));
      } else {
        // Just the single set from the editor
        setsPayload = [{
          label: "Set A",
          order: 1,
          content: contentToSave,
          answers: "",
          metadata: {}
        }];
      }

      const payload = {
        class: trimmedClass,
        subject: trimmedSubject,
        examName: trimmedExamName,
        content: contentToSave,
        questionRefs: [], // Can implement question refs extracting later if needed
        hsatSourceIds: hsatSources.map((s) => s.id),
        sets: setsPayload,
      };

      // `persistablePaperId`, not a bare `!== "current"` check: an unsaved paper
      // now carries a per-draft id (`draft-…`) as well, and PUTting that would
      // 404 against a row that never existed.
      const realPaperId = persistablePaperId(currentPaperId);
      if (realPaperId) {
        await updatePaperAction(realPaperId, payload);
      } else {
        const previousScope = basePaperId(currentPaperId);
        const result = await savePaperAction(payload);
        router.replace(`/editor?paperId=${result.paperId}`);
        setCurrentPaperId(result.paperId);
        void discardDraftScope(previousScope);
      }

      setLoadedPaperTitle(paperExamName.trim());
      setPaperUpdatedAt(new Date().toISOString());
      setSavePaperModalOpen(false);
      toast.success(`Paper details updated.`);
    } catch (error: any) {
      console.error(error);
      toast.error(error?.message || "Failed to update paper details.");
    } finally {
      setIsSaving(false);
    }
  };

  useEffect(() => {
    let active = true;
    if (questionBankBrowserOpen) {
      setBrowserLoading(true);
      getQuestionsFromBank(browserSearchQuery)
        .then((data) => {
          if (active) setBrowserQuestions(data);
        })
        .catch((error) => {
          if (active) toast.error("Failed to fetch questions from bank.");
        })
        .finally(() => {
          if (active) setBrowserLoading(false);
        });
    }
    return () => {
      active = false;
    };
  }, [questionBankBrowserOpen, browserSearchQuery]);

  const toggleQuestionSelection = (questionId: string) => {
    setSelectedBankQuestions((prev) => {
      const next = new Set(prev);
      if (next.has(questionId)) {
        next.delete(questionId);
      } else {
        next.add(questionId);
      }
      return next;
    });
  };

  const handleInsertSelectedQuestions = () => {
    const toInsert = browserQuestions.filter((q) =>
      selectedBankQuestions.has(q.id),
    );
    if (toInsert.length === 0) return;

    // Convert from Django API format to Editor format.
    // The Django API returns `type` (not `questionType`).
    const formattedQuestions = toInsert.map((q) => ({
      content: q.content,
      type: q.type || "short",
      marks: q.marks || 1,
      options: q.options || [],
      // A banked composite (unseen passage, grammar task set) must still split
      // into paginatable blocks when re-inserted. See `Question.metadata`.
      metadata: q.metadata ?? null,
    }));

    appendQuestions(formattedQuestions);
    setQuestionBankBrowserOpen(false);
    setSelectedBankQuestions(new Set());
    toast.success(
      `Inserted ${formattedQuestions.length} question(s) into the paper.`,
    );
  };

  return (
    <div className="flex h-full min-h-0 w-full overflow-hidden bg-background">
      {/* Comparison Workspace — full-screen overlay for multi-set review.
          Self-gates on store state (comparisonOpen && >=2 sets); inserts route
          through the same store append plumbing as the editor below. */}
      <ComparisonWorkspace />

      {/* Mobile backdrop for the generator drawer */}
      {genDrawerOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm lg:hidden"
          onClick={() => setGenDrawerOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Left Panel: Generator Form — inline resizable sidebar on lg+,
          off-canvas drawer below lg. The dynamic px width is applied via a
          CSS var (`--sb-w`) so the `lg:` width utility wins without an inline
          `width` clobbering the mobile `w-[88%]`. */}
      <div
        className={cn(
          "bg-background flex flex-col overflow-hidden",
          "fixed inset-y-0 left-0 z-50 w-[88%] max-w-sm shadow-2xl transition-transform duration-300 ease-out pt-safe pb-safe",
          genDrawerOpen ? "translate-x-0" : "-translate-x-full",
          "lg:static lg:z-auto lg:h-full lg:w-[var(--sb-w)] lg:max-w-none lg:flex-shrink-0 lg:translate-x-0 lg:shadow-none lg:pt-0 lg:pb-0",
        )}
        style={{ "--sb-w": `${sidebarWidth}px` } as React.CSSProperties}
      >
        {/* Mobile-only drawer header with close */}
        <div className="flex items-center justify-between gap-2 border-b border-border px-4 h-14 shrink-0 lg:hidden">
          <span className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <Zap className="h-4 w-4 text-primary" />
            Generate &amp; Sources
          </span>
          <button
            type="button"
            onClick={() => setGenDrawerOpen(false)}
            aria-label="Close generator panel"
            className="inline-flex items-center justify-center h-10 w-10 -mr-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="flex-1 min-h-0">
          <GeneratorForm
            uploadedDocs={uploadedDocs}
            setUploadedDocs={setUploadedDocs}
            hsatSources={hsatSources}
            setHsatSources={setHsatSources}
          />
        </div>
      </div>

      {/* Drag handle — desktop only */}
      <div
        onMouseDown={onDragStart}
        className="hidden lg:block flex-shrink-0 w-px h-full cursor-col-resize group relative z-20 bg-border hover:bg-primary/50 transition-colors"
        title="Drag to resize"
      >
        <div className="absolute inset-y-0 -left-2 -right-2 z-0" />
        <div className="z-10 w-1.5 h-8 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-border/50 opacity-0 group-hover:opacity-100 group-hover:bg-primary/50 transition-all pointer-events-none" />
      </div>

      {/* Right Panel: Tiptap Editor */}
      <div className="flex-1 min-w-0 bg-muted/30 h-full flex flex-col overflow-hidden">
        <div className="h-10 min-h-10 px-2 sm:px-4 flex items-center gap-2 border-b border-border bg-muted/50 text-[10px] uppercase tracking-wider font-medium text-muted-foreground flex-shrink-0">
          {/* Mobile: open the generator/sources drawer */}
          <button
            type="button"
            onClick={() => setGenDrawerOpen(true)}
            className="lg:hidden inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md border border-border bg-background px-2.5 text-[11px] font-semibold normal-case tracking-normal text-primary dark:text-primary hover:bg-accent"
          >
            <PanelLeftOpen className="h-3.5 w-3.5" />
            Generate
          </button>
          <span className="truncate min-w-0">
          {paperLoading ? (
            <span className="inline-flex items-center gap-2">
              <span className="h-3 w-24 bg-muted rounded animate-pulse" />
            </span>
          ) : paperError ? (
            <span className="text-destructive">{paperError}</span>
          ) : loadedPaperTitle ? (
            <>
              <span className="text-muted-foreground mr-2">Editing:</span>
              <span className="text-foreground">
                {loadedPaperTitle}
              </span>
            </>
          ) : (
            "New Document"
          )}
          </span>
        </div>
        
        {(() => {
          const activeSets = comparisonSets.length > 0 ? comparisonSets : loadedSets;
          if (activeSets.length > 1) {
            return (
              <div className="flex items-center gap-2 px-2 bg-muted/20 border-b border-border overflow-x-auto custom-scrollbar flex-shrink-0">
                {activeSets.map(set => {
                  const labelNormalized = set.label.replace("Set ", "");
                  return (
                    <button
                      key={labelNormalized}
                      onClick={() => setActiveSetTab(labelNormalized)}
                      className={cn(
                        "px-4 py-2 text-[13px] font-semibold border-b-2 transition-colors",
                        activeSetTab === labelNormalized ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
                      )}
                    >
                      Set {labelNormalized}
                    </button>
                  );
                })}
              </div>
            );
          }
          return null;
        })()}

        <TiptapEditor
          // `approvedAt` is part of the key so approving a NEW generation
          // remounts the editor. Without it the tab keeps the previous
          // paper's document and the approval appears to do nothing.
          key={`${editorInstanceKey}-${activeSetTab}-${approvedAt}`}
          // Precedence lives in `lib/set-content.ts` — see the note there on
          // why an approved set is the only source that carries Set A.
          initialContent={resolveTabContent({
            activeSetTab,
            approvedSets,
            comparisonSets,
            loadedSets,
            paperContent,
          })}
          paperId={withSetSuffix(currentPaperId, activeSetTab)}
          // Approving is an explicit "use this paper" instruction, so it has to
          // beat the IndexedDB draft the tab may already hold from an earlier
          // generation. Anything else and a second approval silently no-ops.
          forceInitialContent={Boolean(approvedSets?.[activeSetTab])}
          contentVersion={approvedAt}
          serverUpdatedAt={paperUpdatedAt}
          paperMetadata={{
            examName: paperExamName,
            className: paperClass,
            subject: paperSubject,
          }}
          hsatSources={hsatSources}
          uploadedDocs={uploadedDocs}
          onPaperCreatedAction={handleLivePaperCreated}
          exportType={exportTypeParam}
        />
      </div>

      {/* Paper Details Modal */}
      <Dialog
        open={savePaperModalOpen}
        onOpenChange={(open) => {
          if (!isSaving) setSavePaperModalOpen(open);
        }}
      >
        <DialogContent className="bg-popover border-border text-popover-foreground sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Paper Details</DialogTitle>
            <DialogDescription className="text-muted-foreground">
              Update the paper metadata. Document content is saved
              automatically.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="space-y-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="paperClass">
                  Class <span className="text-red-400">*</span>
                </Label>
                <Input
                  id="paperClass"
                  placeholder="e.g. Class 10"
                  value={paperClass}
                  disabled={isSaving}
                  onChange={(e) => setPaperClass(e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="paperSubject">
                  Subject <span className="text-red-400">*</span>
                </Label>
                <Input
                  id="paperSubject"
                  placeholder="e.g. Mathematics"
                  value={paperSubject}
                  disabled={isSaving}
                  onChange={(e) => setPaperSubject(e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="paperExamName">
                  Exam Name <span className="text-red-400">*</span>
                </Label>
                <Input
                  id="paperExamName"
                  placeholder="e.g. Mid-Term Examination"
                  value={paperExamName}
                  disabled={isSaving}
                  onChange={(e) => setPaperExamName(e.target.value)}
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button
              disabled={isSaving}
              onClick={handleSavePaper}
              className="bg-primary hover:bg-primary/90 text-white w-full gap-2"
            >
              {isSaving ? "Updating..." : "Update Details"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Question Bank Browser Modal */}
      <Dialog
        open={questionBankBrowserOpen}
        onOpenChange={setQuestionBankBrowserOpen}
      >
        <DialogContent className="bg-popover border-border text-popover-foreground sm:max-w-[700px] max-h-[85dvh] flex flex-col">
          <DialogHeader>
            <DialogTitle>Question Bank</DialogTitle>
            <DialogDescription className="text-muted-foreground">
              Search and select questions from the bank to add to your current paper.
            </DialogDescription>
          </DialogHeader>
          <div className="flex-shrink-0 py-2">
            <Input
              placeholder="Search by topic, subject, or content..."
              value={browserSearchQuery}
              onChange={(e) => setBrowserSearchQuery(e.target.value)}
              className="w-full"
            />
          </div>
          <div className="flex-1 overflow-y-auto min-h-[300px] pr-2 space-y-3">
            {browserLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className="p-3 border border-border rounded-md animate-pulse"
                  >
                    <div className="flex justify-between mb-2">
                      <div className="flex gap-2">
                        <div className="h-4 w-12 bg-zinc-200 dark:bg-zinc-800 rounded"></div>
                        <div className="h-4 w-16 bg-zinc-200 dark:bg-zinc-800 rounded"></div>
                        <div className="h-4 w-20 bg-primary/10 dark:bg-primary/30 rounded"></div>
                      </div>
                      <div className="h-4 w-10 bg-zinc-200 dark:bg-zinc-800 rounded"></div>
                    </div>
                    <div className="h-3 w-full bg-zinc-100 dark:bg-zinc-800 rounded mt-1"></div>
                    <div className="h-3 w-5/6 bg-zinc-100 dark:bg-zinc-800 rounded mt-1"></div>
                  </div>
                ))}
              </div>
            ) : browserQuestions.length === 0 ? (
              <div className="flex items-center justify-center h-full text-zinc-500">
                No questions found.
              </div>
            ) : (
              browserQuestions.map((q) => {
                const isSelected = selectedBankQuestions.has(q.id);
                return (
                  <div
                    key={q.id}
                    onClick={() => toggleQuestionSelection(q.id)}
                    className={`p-3 border rounded-md cursor-pointer transition-colors ${
                      isSelected
                        ? "border-primary bg-primary/10 dark:bg-primary/10"
                        : "border-border hover:border-zinc-400"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2 text-xs font-medium text-zinc-500">
                        <span className="bg-zinc-100 dark:bg-zinc-800 px-2 py-0.5 rounded">
                          {q.class}
                        </span>
                        <span className="bg-zinc-100 dark:bg-zinc-800 px-2 py-0.5 rounded">
                          {q.subject}
                        </span>
                        <span className="bg-primary/10 dark:bg-primary/30 text-primary dark:text-primary px-2 py-0.5 rounded">
                          {q.topic}
                        </span>
                      </div>
                      <span className="text-xs font-bold text-zinc-400">
                        {q.marks} Marks
                      </span>
                    </div>
                    <p className="text-sm text-foreground line-clamp-3">
                      {q.content}
                    </p>
                  </div>
                );
              })
            )}
          </div>
          <DialogFooter className="pt-4 border-t border-border mt-auto">
            <Button
              variant="outline"
              onClick={() => setQuestionBankBrowserOpen(false)}
            >
              Cancel
            </Button>
            <Button
              onClick={handleInsertSelectedQuestions}
              disabled={selectedBankQuestions.size === 0}
              className="bg-emerald-600 hover:bg-emerald-700 text-white"
            >
              Insert{" "}
              {selectedBankQuestions.size > 0 &&
                `(${selectedBankQuestions.size})`}{" "}
              Questions
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

    </div>
  );
}
