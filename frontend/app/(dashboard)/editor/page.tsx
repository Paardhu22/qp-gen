"use client";

import { BlueprintModal, type BlueprintSubmission } from "@/components/blueprint/blueprint-modal";
import { ReviewTray } from "@/components/review-tray";
import { DocumentOutline } from "@/components/editor/document-outline";
import { GenerateDock } from "@/components/editor/generate-dock";
import { HsatSourcePicker } from "@/components/hsat-source-picker";
import { usePaperGeneration } from "@/lib/use-paper-generation";
import { useSourceUploads } from "@/lib/use-source-uploads";
import { useHsatReadiness } from "@/lib/use-hsat-readiness";
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
import { Skeleton } from "@/components/ui/skeleton";
import { useState, useEffect, useRef, useCallback } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import { X } from "lucide-react";
import {
  savePaperAction,
  updatePaperAction,
  getPaperAction,
} from "@/actions/savePaper";
import {
  saveQuestionsToBank,
  getQuestionsFromBank,
} from "@/actions/saveQuestions";
import { useSession } from "@/lib/auth-client";
import {
  deleteLiveDocument,
  deleteLiveDocumentsForPaper,
  getLiveDocumentId,
  getLatestLiveDocumentForUser,
  getLiveDocument,
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

  const hsatSources = useEditorStore((state) => state.hsatSources);
  const setHsatSources = useEditorStore((state) => state.setHsatSources);
  const uploadedDocs = useEditorStore((state) => state.uploadedDocs);
  const setUploadedDocs = useEditorStore((state) => state.setUploadedDocs);

  // Modals state from store
  const savePaperModalOpen = useEditorStore(
    (state) => state.savePaperModalOpen,
  );
  const setSavePaperModalOpen = useEditorStore(
    (state) => state.setSavePaperModalOpen,
  );

  const saveQuestionModalOpen = useEditorStore(
    (state) => state.saveQuestionModalOpen,
  );
  const setSaveQuestionModalOpen = useEditorStore(
    (state) => state.setSaveQuestionModalOpen,
  );

  const questionsToSave = useEditorStore((state) => state.questionsToSave);
  // NOTE: `editorContent` is intentionally NOT subscribed here any more —
  // the TipTap editor used to push it into the store on every keystroke,
  // which re-rendered the whole EditorPage tree on each one. Save reads
  // the live editor via `window.__activeEditorBuildContent` instead, so
  // we only re-render when something we actually display changes.

  // Paper Form state
  const [paperClass, setPaperClass] = useState("");
  const [paperSubject, setPaperSubject] = useState("");
  const [paperExamName, setPaperExamName] = useState("");

  // Question Form state
  const [questionClass, setQuestionClass] = useState("");
  const [questionSubject, setQuestionSubject] = useState("");
  const [questionTopic, setQuestionTopic] = useState("");

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
  const comparisonSetsPaperId = useEditorStore((s) => s.comparisonSetsPaperId);
  const setActiveEditorPaperId = useEditorStore((s) => s.setActiveEditorPaperId);
  // Drives the review tray's visibility. Read here rather than inside the tray
  // so an empty tray costs nothing to render.
  const insertionMode = useEditorStore((s) => s.insertionMode);
  const generatedTray = useEditorStore((s) => s.generatedTray);
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

  // ── The Blueprint Builder ─────────────────────────────────────────────
  // The resizable generator sidebar and its mobile drawer are gone: paper
  // configuration is a modal over the editor now, so the page below is full
  // width and there is exactly one place a paper is set up.
  const [blueprintOpen, setBlueprintOpen] = useState(false);
  const [hsatPickerOpen, setHsatPickerOpen] = useState(false);
  // A plain-English brief typed into the Studio dock, handed to the Builder so
  // it opens on a resolved blueprint instead of an empty template picker.
  const [builderBrief, setBuilderBrief] = useState("");

  // ── Panel state ───────────────────────────────────────────────────────
  // Held here, not inside the panels: the editor remounts on every set-tab
  // switch and would otherwise reset them. Both default open — the point of
  // the layout is that the document's structure and the way to generate one
  // are visible without hunting.
  const [outlineOpen, setOutlineOpen] = useState(true);
  const [dockOpen, setDockOpen] = useState(true);

  const openBuilder = useCallback((brief?: string) => {
    setBuilderBrief(brief ?? "");
    setBlueprintOpen(true);
  }, []);

  // Uploads live on the page, not in the modal: a teacher who starts a large
  // upload and closes the Builder must come back to a finished upload.
  const uploads = useSourceUploads(uploadedDocs, setUploadedDocs);

  // Same reason, other source kind: the library picker applies a book and
  // closes instead of blocking on its ingest, so the page is what watches a
  // still-indexing book turn ready.
  useHsatReadiness(hsatSources, setHsatSources);

  const generation = usePaperGeneration({
    onSourcesNotReady: uploads.reconcileNotReady,
  });

  // Streamed questions waiting on a decision. They render inside the Studio
  // dock (see its `review` prop) rather than in a floating panel, so the
  // effect below opens the dock — otherwise a run that finishes while the
  // rail is collapsed would stage questions into a surface nobody can see.
  // Multi-set runs review in the Comparison Workspace instead, so the two
  // never compete for the screen.
  const reviewPending =
    insertionMode === "review" &&
    !generation.multiSetMode &&
    generatedTray.length > 0;

  useEffect(() => {
    if (reviewPending) setDockOpen(true);
  }, [reviewPending]);

  const handleGenerate = useCallback(
    async (submission: BlueprintSubmission) => {
      if (uploads.isBusy) {
        toast.error(
          "A source is still being prepared. Wait for it to finish, then generate.",
        );
        return;
      }
      const notReadyHsat = hsatSources.find((s) => s.status !== "ready");
      if (notReadyHsat) {
        toast.error(
          `${notReadyHsat.book} is still being prepared. Wait for it to finish, then generate.`,
        );
        return;
      }

      // Close before streaming, not after: generation runs for minutes and
      // the questions land in the editor behind the modal. Holding the
      // overlay open would hide the very thing the teacher is waiting for.
      setBlueprintOpen(false);

      await generation.generate({
        pdfSourceIds: uploadedDocs.map((d) => d.id),
        hsatSourceIds: hsatSources.map((s) => s.id),
        subject: submission.settings.subject,
        academicClass: submission.settings.academicClass,
        board: submission.settings.board,
        difficulty: submission.settings.difficulty,
        numberOfSets: submission.settings.numberOfSets,
        mathLevel: submission.settings.mathLevel,
        instructions: submission.instructions,
        blueprint: { slots: submission.blueprint.slots },
        templateId: submission.templateId,
      });
    },
    [generation, hsatSources, uploadedDocs, uploads.isBusy],
  );


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

  // Sync the currently open paperId so generated sets get stamped with it.
  useEffect(() => {
    setActiveEditorPaperId(paperId);
  }, [paperId, setActiveEditorPaperId]);

  // Prevent volatile generated sets from bleeding into another paper if the teacher
  // generates sets for paper A, navigates away without approving, and opens paper B.
  // We also clear if comparisonSetsPaperId is missing (legacy sets from before this fix).
  useEffect(() => {
    if (paperId && comparisonSets.length > 0 && comparisonSetsPaperId !== paperId) {
      clearComparisonSets();
    }
  }, [paperId, comparisonSets.length, comparisonSetsPaperId, clearComparisonSets]);

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

  // ── Is the document target still undecided? ───────────────────────────
  // Arriving at `/editor` with no `?paperId=` (the nav bar links there
  // bare) leaves `paperId` null until the resume effect below reads
  // IndexedDB and redirects. During that window nothing has decided which
  // document this tab shows, and the editor must be told exactly that.
  //
  // The distinction is load-bearing and documented in `lib/set-content.ts`:
  // `undefined` means "no content decided here", so `TiptapEditor` bails out
  // of its load effect and leaves `documentLoadedRef` false; `""` means "an
  // empty document", which it will happily load. The `!paperId` branch of the
  // load effect below sets `paperContent` to `""` — correct once the resume
  // check has finished and there is genuinely nothing to open, but fatal
  // before it has: the editor loads a blank page, flips `documentLoadedRef`
  // true, and the pending `sectionsToAppend` / `questionsToAppend` queued by a
  // generation drain into that blank page and are cleared. The redirect then
  // lands, the editor reloads the pre-insertion draft from IndexedDB, and the
  // questions are gone. (Worse, the post-insert `debouncedLiveSync.flush()`
  // writes them under the legacy `current_A` key — `withSetSuffix(null, "A")`
  // — which nothing reads back, so they are orphaned rather than merely raced.)
  //
  // `checkedResume` is set in every path out of the resume effect, so this can
  // never latch on: the redirect path sets it in `finally`, the
  // dashboard-handoff path sets it inline, and `isNew` sets it directly.
  const documentTargetUnresolved = !isNew && !paperId && !checkedResume;

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
        if (active) router.replace(`/editor?paperId=${newLocalDraftId()}`);
      })();
      return () => {
        active = false;
      };
    }

    if (!paperId) {
      // `""` (an empty document), NOT `undefined` — this branch is also the
      // dashboard-handoff landing, where the editor must load a blank page so
      // the generated sections have somewhere to be inserted. It is only wrong
      // BEFORE the resume check has decided whether to redirect, and that
      // window is held open by `documentTargetUnresolved` at the call site
      // rather than by second-guessing the value here.
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

  const handleSaveQuestions = async () => {
    if (
      !questionClass.trim() ||
      !questionSubject.trim() ||
      !questionTopic.trim()
    ) {
      toast.error("Please fill in all fields: Class, Subject, Topic.");
      return;
    }

    if (questionsToSave.length === 0) {
      toast.error("No questions found to save.");
      return;
    }

    setIsSaving(true);
    try {
      const payload = {
        class: questionClass.trim(),
        subject: questionSubject.trim(),
        topic: questionTopic.trim(),
        questions: questionsToSave,
      };

      const res = await saveQuestionsToBank(payload);
      setSaveQuestionModalOpen(false);
      toast.success(
        `Saved ${res.count} question(s) to the Paper successfully!`,
      );

      // Reset form
      setQuestionTopic("");
    } catch (error: any) {
      console.error(error);
      toast.error(error?.message || "Failed to save questions.");
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
    }));

    appendQuestions(formattedQuestions);
    setQuestionBankBrowserOpen(false);
    setSelectedBankQuestions(new Set());
    toast.success(
      `Inserted ${formattedQuestions.length} question(s) into the paper.`,
    );
  };

  // ── Document tabs ─────────────────────────────────────────────────────
  // The A/B/C sets, as the document panel lists them. Always at least one:
  // a single-set paper still has a tab, exactly as a Docs document does, so
  // the panel never renders a heading over nothing.
  const setTabs = (() => {
    const activeSets =
      comparisonSets.length > 0 ? comparisonSets : loadedSets;
    if (activeSets.length > 1) {
      return activeSets.map((set: any) => {
        const id = set.label.replace("Set ", "");
        return { id, label: `Set ${id}` };
      });
    }
    return [{ id: "A", label: "Set A" }];
  })();

  return (
    <div className="relative isolate flex h-full min-h-0 w-full overflow-hidden bg-background">
      {/* Comparison Workspace — full-screen overlay for multi-set review.
          Self-gates on store state (comparisonOpen && >=2 sets); inserts route
          through the same store append plumbing as the editor below. */}
      <ComparisonWorkspace />

      {/* The review tray's small-screen home. Below `lg` the Studio dock is a
          rail with no panel to hold it (there is no room for one beside a
          794px page), so it falls back to the docked sheet it used to be.
          `ReviewTray` reads the store and runs no mount effects, so having it
          in both places costs nothing but the markup — and exactly one of them
          is ever visible. */}
      {reviewPending ? (
        <aside className="fixed bottom-0 right-0 z-40 flex max-h-[70vh] w-full flex-col overflow-y-auto border-l border-t border-border bg-background shadow-2xl sm:w-[380px] sm:rounded-tl-xl lg:hidden">
          <ReviewTray />
        </aside>
      ) : null}

      {/* The Blueprint Builder — the one place a paper is configured.
          Mounted here rather than inside the editor so it survives the editor
          remounting between set tabs, and so an upload started inside it
          continues when it closes. */}
      <BlueprintModal
        open={blueprintOpen}
        onOpenChange={setBlueprintOpen}
        initialInstructions={builderBrief}
        onGenerate={handleGenerate}
        generating={generation.isGenerating}
        uploadedDocs={uploadedDocs}
        uploadingDocs={uploads.uploadingDocs}
        hsatSources={hsatSources}
        onFiles={uploads.uploadFiles}
        onRemoveDoc={uploads.removeDoc}
        onDismissUpload={uploads.dismissUpload}
        onRemoveHsat={(id) =>
          setHsatSources((prev) => prev.filter((s) => s.id !== id))
        }
        onOpenHsatPicker={() => setHsatPickerOpen(true)}
      />

      {/* The library picker, opened from inside the Builder's Sources step.
          It is no longer a top-level toolbar button: an HSAT book and an
          uploaded PDF both end up as DocumentChunk rows, so presenting them
          as different kinds of action made one thing look like two. */}
      <HsatSourcePicker
        open={hsatPickerOpen}
        onOpenChange={setHsatPickerOpen}
        paperId={currentPaperId}
        appliedIds={hsatSources.map((s) => s.id)}
        onApply={(source) =>
          setHsatSources((prev) => [
            ...prev.filter((s) => s.id !== source.id),
            source,
          ])
        }
      />

      {/* The editor. A document window, in the order a word processor builds
          one: the document's name, then the toolbar (rendered inside
          TiptapEditor), then the page flanked by its panels. */}
      <div className="relative z-10 flex h-full min-w-0 flex-1 flex-col overflow-hidden">
        {/* Document name. Its own row above the toolbar, the way every editor
            does it — not a status line squeezed into small caps. */}
        <div className="flex h-11 min-h-11 flex-shrink-0 items-center gap-2 border-b border-border bg-background px-3 sm:px-4">
          <span className="min-w-0 truncate text-[14px]">
            {paperLoading ? (
              <Skeleton className="block h-3.5 w-40" />
            ) : paperError ? (
              <span className="text-destructive">{paperError}</span>
            ) : (
              <span className="font-medium text-foreground">
                {loadedPaperTitle || "Untitled paper"}
              </span>
            )}
          </span>
        </div>

        <TiptapEditor
          leftPanel={
            <DocumentOutline
              tabs={setTabs}
              activeTab={activeSetTab}
              onSelectTab={setActiveSetTab}
              open={outlineOpen}
              onOpenChange={setOutlineOpen}
            />
          }
          rightPanel={
            <GenerateDock
              open={dockOpen}
              onOpenChange={setDockOpen}
              onOpenBuilder={openBuilder}
              generating={generation.isGenerating}
              status={generation.poolStatus}
              insertedCount={generation.liveInsertedCount}
              sourceCount={uploadedDocs.length + hsatSources.length}
              review={reviewPending ? <ReviewTray /> : null}
            />
          }
          // `approvedAt` is part of the key so approving a NEW generation
          // remounts the editor. Without it the tab keeps the previous
          // paper's document and the approval appears to do nothing.
          key={`${editorInstanceKey}-${activeSetTab}-${approvedAt}`}
          // Precedence lives in `lib/set-content.ts` — see the note there on
          // why an approved set is the only source that carries Set A.
          //
          // `undefined` while the document target is undecided: it holds the
          // editor's load effect (and therefore any pending question
          // insertion) until we know which document this tab is showing. See
          // `documentTargetUnresolved` above.
          initialContent={
            documentTargetUnresolved
              ? undefined
              : resolveTabContent({
                  activeSetTab,
                  approvedSets,
                  comparisonSets,
                  loadedSets,
                  paperContent,
                })
          }
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

      {/* Save Questions Modal */}
      <Dialog
        open={saveQuestionModalOpen}
        onOpenChange={(open) => {
          if (!isSaving) setSaveQuestionModalOpen(open);
        }}
      >
        <DialogContent className="bg-popover border-border text-popover-foreground sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Save to Paper</DialogTitle>
            <DialogDescription className="text-muted-foreground">
              Save {questionsToSave.length} question(s) to the Paper
              collection.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="space-y-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="questionClass">
                  Class <span className="text-red-400">*</span>
                </Label>
                <Input
                  id="questionClass"
                  placeholder="e.g. Class 10"
                  value={questionClass}
                  disabled={isSaving}
                  onChange={(e) => setQuestionClass(e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="questionSubject">
                  Subject <span className="text-red-400">*</span>
                </Label>
                <Input
                  id="questionSubject"
                  placeholder="e.g. Mathematics"
                  value={questionSubject}
                  disabled={isSaving}
                  onChange={(e) => setQuestionSubject(e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="questionTopic">
                  Topic <span className="text-red-400">*</span>
                </Label>
                <Input
                  id="questionTopic"
                  placeholder="e.g. Probability"
                  value={questionTopic}
                  disabled={isSaving}
                  onChange={(e) => setQuestionTopic(e.target.value)}
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button
              disabled={isSaving}
              onClick={handleSaveQuestions}
              className="bg-primary hover:bg-primary/90 text-white w-full gap-2"
            >
              {isSaving ? "Saving..." : "Save Questions"}
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
              <div role="status" aria-live="polite" aria-label="Loading" className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className="rounded-lg border border-border p-3"
                  >
                    <div className="mb-2 flex justify-between">
                      <div className="flex gap-2">
                        <Skeleton className="h-4 w-12" />
                        <Skeleton className="h-4 w-16" />
                        <Skeleton className="h-4 w-20" />
                      </div>
                      <Skeleton className="h-4 w-10" />
                    </div>
                    <Skeleton className="mt-1 h-3 w-full" />
                    <Skeleton className="mt-1 h-3 w-5/6" />
                  </div>
                ))}
              </div>
            ) : browserQuestions.length === 0 ? (
              <div className="flex items-center justify-center h-full text-muted-foreground">
                No questions found.
              </div>
            ) : (
              browserQuestions.map((q) => {
                const isSelected = selectedBankQuestions.has(q.id);
                return (
                  <div
                    key={q.id}
                    onClick={() => toggleQuestionSelection(q.id)}
                    className={`p-3 border rounded-lg cursor-pointer transition-colors ${
                      isSelected
                        ? "border-primary bg-primary/10 dark:bg-primary/10"
                        : "border-border hover:border-border"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                        <span className="bg-muted px-2 py-0.5 rounded-sm">
                          {q.class}
                        </span>
                        <span className="bg-muted px-2 py-0.5 rounded-sm">
                          {q.subject}
                        </span>
                        <span className="bg-primary/10 dark:bg-primary/30 text-primary dark:text-primary px-2 py-0.5 rounded-sm">
                          {q.topic}
                        </span>
                      </div>
                      <span className="text-xs font-bold text-muted-foreground">
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
