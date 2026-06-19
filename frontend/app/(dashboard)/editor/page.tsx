"use client";

import { GeneratorForm } from "@/components/generator-form";
import { TiptapEditor } from "@/components/tiptap-editor";
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
import { Loader2, PanelLeftOpen, Sparkles, X } from "lucide-react";
import { cn } from "@/lib/utils";
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
  getLiveDocumentId,
  getLatestLiveDocumentForUser,
  getLiveDocument,
} from "@/lib/live-document-db";

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

  // Question Paper Browser state
  const questionBankBrowserOpen = useEditorStore(
    (state) => state.questionBankBrowserOpen,
  );
  const setQuestionBankBrowserOpen = useEditorStore(
    (state) => state.setQuestionBankBrowserOpen,
  );
  const appendQuestions = useEditorStore((state) => state.appendQuestions);

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
  const paperId = searchParams.get("paperId");
  const isNew = searchParams.get("new") === "true";
  const actionParam = searchParams.get("action"); // e.g. "export-pdf" | "export-docx"
  // exportTypeParam lets the question-bank page signal that an answer script is being exported.
  const exportTypeParam = (searchParams.get("exportType") ?? "question_paper") as
    | "question_paper"
    | "answer_script"
    | "question_bank";

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
      }
      // Remove the action param from the URL so refresh doesn't re-trigger
      const url = new URL(window.location.href);
      url.searchParams.delete("action");
      router.replace(url.pathname + url.search);
    }, IMPORT_TIMEOUT);
    return () => clearTimeout(t);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [actionParam, paperLoading, paperError]);

  const [resumeDoc, setResumeDoc] = useState<any>(null);
  const [showResumePrompt, setShowResumePrompt] = useState(false);
  const [checkedResume, setCheckedResume] = useState(false);

  // ISSUE 1: Resolve the current browser-session id so we can tell in-app
  // nav (same session) apart from a genuine "previous browser session"
  // resume. The TipTap editor writes the same id into every IDB save
  // (see browserSessionIdRef in tiptap-editor.tsx). We compute it inside
  // a useEffect (not useMemo) so the impure Date.now/Math.random calls
  // don't run during render.
  const [browserSessionId, setBrowserSessionId] = useState<string>("");
  useEffect(() => {
    if (typeof window === "undefined") return;
    const KEY = "qp-gen:editor-session-id";
    let id = sessionStorage.getItem(KEY);
    if (!id) {
      id = `sess-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
      sessionStorage.setItem(KEY, id);
    }
    setBrowserSessionId(id);
  }, []);

  // Check for resume doc on mount if no explicit paperId is selected and not creating a new paper
  useEffect(() => {
    // Wait until the browser-session id is resolved — otherwise the
    // session-match check below would always fail and the resume modal
    // would pop on in-app navigation.
    if (!browserSessionId) return;
    if (!sessionData?.user?.id || paperId || checkedResume || isNew) return;

    const checkResume = async () => {
      try {
        const latestDoc = await getLatestLiveDocumentForUser(
          sessionData.user.id,
        );
        if (!latestDoc) {
          setCheckedResume(true);
          return;
        }

        // ISSUE 1: if the latest live doc was written by THIS browser
        // session (i.e. the user just left the editor and came back),
        // restore silently — no modal, no friction. Only show the
        // "Resume previous paper?" prompt when the latest doc was
        // written in a different session.
        if (latestDoc.sessionId && latestDoc.sessionId === browserSessionId) {
          if (latestDoc.paperId) {
            router.replace(`/editor?paperId=${latestDoc.paperId}`);
          } else {
            router.replace(`/editor?paperId=current`);
          }
          setCheckedResume(true);
          return;
        }

        setResumeDoc(latestDoc);
        setShowResumePrompt(true);
      } catch (error) {
        console.error("Failed to check for resume doc:", error);
      } finally {
        setCheckedResume(true);
      }
    };

    checkResume();
  }, [
    sessionData?.user?.id,
    paperId,
    checkedResume,
    isNew,
    browserSessionId,
    router,
  ]);

  const handleContinueEditing = () => {
    setShowResumePrompt(false);
    if (resumeDoc) {
      if (resumeDoc.paperId) {
        router.replace(`/editor?paperId=${resumeDoc.paperId}`);
      } else {
        // No backend paper id yet — load the local "current" draft, which
        // the editor's load effect rehydrates from IndexedDB.
        router.replace(`/editor?paperId=current`);
      }
    }
  };

  const handleCreateNewPaper = async () => {
    setShowResumePrompt(false);
    // ISSUE 1: "Create New Paper" must NEVER silently destroy unsaved
    // work — the old behaviour `deleteLiveDocument(resumeDoc.id)` deleted
    // the only copy of an unsaved draft. Instead, archive the draft by
    // re-saving it under an `archived:{userId}:{ts}` id so it stays in
    // IndexedDB (and out of `getLatestLiveDocumentForUser`'s "latest"
    // result, since it goes through the same store but the user can
    // recover it through the paper library if it had a backend paperId).
    if (sessionData?.user?.id && resumeDoc) {
      try {
        const archivedId = `archived:${sessionData.user.id}:${Date.now()}`;
        const { saveLiveDocument: saveLD } = await import(
          "@/lib/live-document-db"
        );
        await saveLD({ ...resumeDoc, id: archivedId });
        await deleteLiveDocument(resumeDoc.id);
        toast.message("Previous draft archived. It's still in your browser.");
      } catch (err) {
        console.error("Failed to archive previous draft:", err);
        // On failure, keep the original draft alive rather than deleting
        // it — never destroy unsaved work on a best-effort cleanup.
      }
    }
    setPaperExamName("");
    setPaperClass("");
    setPaperSubject("");
    setLoadedPaperTitle(null);
    setCurrentPaperId(null);
    setPaperContent("");
  };

  useEffect(() => {
    let active = true;

    if (isNew) {
      setPaperContent("");
      setLoadedPaperTitle(null);
      setPaperError(null);
      setPaperUpdatedAt(null);
      setCurrentPaperId(null);
      setPaperClass("");
      setPaperSubject("");
      setPaperExamName("");
      setHsatSources([]);
      setUploadedDocs([]);
      setCheckedResume(true); // Bypass resume prompt for explicitly new papers
      router.replace("/editor");
      return;
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

    if (paperId === "current") {
      const loadLocalDraft = async () => {
        const userId = sessionData?.user?.id;
        if (!userId) return;
        try {
          const draft = await getLiveDocument(
            getLiveDocumentId(userId, "current"),
          );
          if (draft && active) {
            setPaperContent(
              draft.editorJSON ? JSON.stringify(draft.editorJSON) : "",
            );
            setLoadedPaperTitle(draft.metadata?.title || "Unsaved Draft");
            setPaperExamName(draft.metadata?.title || "");
            setPaperClass(draft.metadata?.className || "");
            setPaperSubject(draft.metadata?.subject || "");
            setPaperUpdatedAt(new Date(draft.updatedAt).toISOString());
            setCurrentPaperId("current");
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
            setCurrentPaperId("current");
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
            deleteLiveDocument(getLiveDocumentId(userId, paperId)).catch(
              (err) => console.error("Failed to delete stale autosave:", err),
            );
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
  }, [paperId, isNew, sessionData?.user?.id, router]);

  const handleLivePaperCreated = useCallback(
    (newPaperId: string) => {
      setCurrentPaperId(newPaperId);
      setLoadedPaperTitle(
        (title) => title || paperExamName.trim() || "Untitled Paper",
      );
      setPaperUpdatedAt(new Date().toISOString());
      router.replace(`/editor?paperId=${newPaperId}`);
    },
    [paperExamName, router],
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

      const payload = {
        class: trimmedClass,
        subject: trimmedSubject,
        examName: trimmedExamName,
        content: contentToSave,
        questionRefs: [], // Can implement question refs extracting later if needed
        hsatSourceIds: hsatSources.map((s) => s.id),
      };

      // "current" is a sentinel for an unsaved local draft; treat it as null
      // so we create a real backend paper instead of trying to PUT /papers/current/.
      const realPaperId =
        currentPaperId && currentPaperId !== "current" ? currentPaperId : null;
      if (realPaperId) {
        await updatePaperAction(realPaperId, payload);
      } else {
        const result = await savePaperAction(payload);
        router.replace(`/editor?paperId=${result.paperId}`);
        setCurrentPaperId(result.paperId);
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
        `Saved ${res.count} question(s) to the Question Paper successfully!`,
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

  return (
    <div className="flex h-full min-h-0 w-full overflow-hidden bg-background">
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
            <Sparkles className="h-4 w-4 text-indigo-500" />
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
            className="lg:hidden inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md border border-border bg-background px-2.5 text-[11px] font-semibold normal-case tracking-normal text-indigo-600 dark:text-indigo-400 hover:bg-accent"
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
        <TiptapEditor
          initialContent={paperContent}
          paperId={currentPaperId}
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
              className="bg-indigo-600 hover:bg-indigo-700 text-white w-full gap-2"
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
            <DialogTitle>Save to Question Paper</DialogTitle>
            <DialogDescription className="text-muted-foreground">
              Save {questionsToSave.length} question(s) to the Question Paper
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
              className="bg-indigo-600 hover:bg-indigo-700 text-white w-full gap-2"
            >
              {isSaving ? "Saving..." : "Save Questions"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {/* Question Paper Browser Modal */}
      <Dialog
        open={questionBankBrowserOpen}
        onOpenChange={setQuestionBankBrowserOpen}
      >
        <DialogContent className="bg-popover border-border text-popover-foreground sm:max-w-[700px] max-h-[85dvh] flex flex-col">
          <DialogHeader>
            <DialogTitle>Question Paper Browser</DialogTitle>
            <DialogDescription className="text-muted-foreground">
              Search and select saved questions to add to your current paper.
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
                        <div className="h-4 w-20 bg-indigo-100 dark:bg-indigo-900/30 rounded"></div>
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
                        ? "border-indigo-500 bg-indigo-50 dark:bg-indigo-500/10"
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
                        <span className="bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-400 px-2 py-0.5 rounded">
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

      {/* Resume Session Dialog */}
      <Dialog
        open={showResumePrompt}
        onOpenChange={(open) => {
          if (!open) {
            setShowResumePrompt(false);
          }
        }}
      >
        <DialogContent className="bg-popover border-border text-popover-foreground sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Resume previous paper?</DialogTitle>
            <DialogDescription className="text-muted-foreground">
              We found a previous active paper session. Would you like to
              continue editing it?
            </DialogDescription>
          </DialogHeader>
          {resumeDoc && (
            <div className="py-4 px-4 bg-muted/30 border border-border rounded-lg space-y-1 my-2">
              <p className="text-sm font-semibold text-foreground">
                {resumeDoc.metadata?.title ||
                  resumeDoc.title ||
                  "Untitled Paper"}
              </p>
              <p className="text-[11px] text-muted-foreground">
                Class: {resumeDoc.metadata?.className || "Not set yet"} |{" "}
                Subject: {resumeDoc.metadata?.subject || "Not set yet"}
              </p>
              {(() => {
                // Surface marks/questions if we can extract them from the
                // saved doc — gives the user a real signal about which
                // paper this resume points at.
                let questionCount = 0;
                let totalMarks = 0;
                try {
                  const visit = (node: any) => {
                    if (!node) return;
                    if (
                      node.type === "questionBlock" ||
                      node.type === "groupedQuestionBlock"
                    ) {
                      questionCount += 1;
                      totalMarks += Number(node.attrs?.marks) || 0;
                    }
                    (node.content || []).forEach(visit);
                  };
                  visit(resumeDoc.editorJSON);
                } catch {
                  /* old/legacy doc shapes — skip the count */
                }
                if (questionCount > 0) {
                  return (
                    <p className="text-[11px] text-muted-foreground">
                      {questionCount} question{questionCount === 1 ? "" : "s"} ·{" "}
                      {totalMarks} mark{totalMarks === 1 ? "" : "s"}
                    </p>
                  );
                }
                return null;
              })()}
              <p className="text-[11px] text-muted-foreground">
                Last active: {new Date(resumeDoc.updatedAt).toLocaleString()}
              </p>
            </div>
          )}
          <DialogFooter className="grid grid-cols-1 sm:grid-cols-2 gap-2 sm:space-x-0">
            <Button
              variant="outline"
              onClick={handleCreateNewPaper}
              className="w-full border-border text-foreground hover:bg-muted"
            >
              Create New Paper
            </Button>
            <Button
              onClick={handleContinueEditing}
              className="bg-indigo-600 hover:bg-indigo-700 text-white w-full"
            >
              Continue Editing
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
