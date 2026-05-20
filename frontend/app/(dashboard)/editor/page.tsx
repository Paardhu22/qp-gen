"use client";

import { GeneratorForm } from "@/components/generator-form";
import { TiptapEditor } from "@/components/tiptap-editor";
import { useEditorStore } from "@/store/editor-store";
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
import { Loader2 } from "lucide-react";
import {
  savePaperAction,
  updatePaperAction,
  getPaperAction,
} from "@/actions/savePaper";
import {
  saveQuestionsToBank,
  getQuestionsFromBank,
} from "@/actions/saveQuestions";

export default function EditorPage() {
  const router = useRouter();

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
  const editorContent = useEditorStore((state) => state.editorContent);

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

  useEffect(() => {
    let active = true;

    if (!paperId) {
      setPaperContent("");
      setLoadedPaperTitle(null);
      setPaperError(null);
      setCurrentPaperId(null);
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
        setLoadedPaperTitle(paper.examName || "Saved Paper");
        setPaperExamName(paper.examName || "");
        setPaperClass(paper.class || "");
        setPaperSubject(paper.subject || "");
        setCurrentPaperId(paper.id);
        setPaperError(null);
      })
      .catch((error) => {
        if (!active) return;
        console.error(error);
        setPaperError("Failed to load saved paper. Please try again.");
        setPaperContent("");
        toast.error(error?.message || "Failed to load saved paper.");
      })
      .finally(() => {
        if (active) setPaperLoading(false);
      });

    return () => {
      active = false;
    };
  }, [paperId]);

  const handleSavePaper = async () => {
    if (!paperClass.trim() || !paperSubject.trim() || !paperExamName.trim()) {
      toast.error("Please fill in all fields: Class, Subject, Exam Name.");
      return;
    }

    setIsSaving(true);
    try {
      const payload = {
        class: paperClass.trim(),
        subject: paperSubject.trim(),
        examName: paperExamName.trim(),
        content: editorContent,
        questionRefs: [], // Can implement question refs extracting later if needed
      };

      if (currentPaperId) {
        await updatePaperAction(currentPaperId, payload);
      } else {
        const result = await savePaperAction(payload);
        router.replace(`/editor?paperId=${result.paperId}`);
        setCurrentPaperId(result.paperId);
      }

      setLoadedPaperTitle(paperExamName.trim());
      setSavePaperModalOpen(false);
      toast.success(`Paper "${paperExamName.trim()}" saved successfully!`);
    } catch (error: any) {
      console.error(error);
      toast.error(error?.message || "Failed to save paper.");
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
        `Saved ${res.count} question(s) to the Question Bank successfully!`,
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
    <div className="flex h-[calc(100vh-4.5rem)] w-full overflow-hidden bg-white dark:bg-zinc-950">
      {/* Left Panel: Generator Form */}
      <div
        className="flex-shrink-0 bg-white dark:bg-zinc-950 flex flex-col h-full overflow-hidden"
        style={{ width: sidebarWidth }}
      >
        <GeneratorForm />
      </div>

      {/* Drag handle */}
      <div
        onMouseDown={onDragStart}
        className="flex-shrink-0 w-px h-full cursor-col-resize group relative z-20 bg-zinc-200 dark:bg-zinc-800 hover:bg-indigo-500 transition-colors"
        title="Drag to resize"
      >
        <div className="absolute inset-y-0 -left-2 -right-2 z-0" />
        <div className="z-10 w-1.5 h-12 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 group-hover:border-indigo-500 group-hover:bg-indigo-600 transition-all flex flex-col items-center justify-center gap-1 shadow-sm pointer-events-none">
          <div className="w-0.5 h-0.5 rounded-full bg-zinc-300 dark:bg-zinc-700 group-hover:bg-indigo-200" />
          <div className="w-0.5 h-0.5 rounded-full bg-zinc-300 dark:bg-zinc-700 group-hover:bg-indigo-200" />
          <div className="w-0.5 h-0.5 rounded-full bg-zinc-300 dark:bg-zinc-700 group-hover:bg-indigo-200" />
        </div>
      </div>

      {/* Right Panel: Tiptap Editor */}
      <div className="flex-1 min-w-0 bg-zinc-100 dark:bg-zinc-900 h-full flex flex-col overflow-hidden">
        <div className="h-10 min-h-10 px-4 flex items-center border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-950 text-[10px] uppercase tracking-wider font-medium text-zinc-500 flex-shrink-0">
          {paperLoading ? (
            <span className="inline-flex items-center gap-2">
              <span className="h-3 w-24 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse" />
            </span>
          ) : paperError ? (
            <span className="text-red-400">{paperError}</span>
          ) : loadedPaperTitle ? (
            <>
              <span className="text-zinc-400 mr-2">Editing:</span>
              <span className="text-zinc-800 dark:text-zinc-200">
                {loadedPaperTitle}
              </span>
            </>
          ) : (
            "New Document"
          )}
        </div>
        <TiptapEditor initialContent={paperContent} />
      </div>

      {/* Save Paper Modal */}
      <Dialog
        open={savePaperModalOpen}
        onOpenChange={(open) => {
          if (!isSaving) setSavePaperModalOpen(open);
        }}
      >
        <DialogContent className="bg-popover border-border text-popover-foreground sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Save Paper</DialogTitle>
            <DialogDescription className="text-muted-foreground">
              {currentPaperId
                ? "Update your saved paper."
                : "Save this paper to the Paper Library."}
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
              {isSaving
                ? "Saving..."
                : currentPaperId
                  ? "Update Paper"
                  : "Save Paper"}
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
            <DialogTitle>Save to Question Bank</DialogTitle>
            <DialogDescription className="text-muted-foreground">
              Save {questionsToSave.length} question(s) to the reusable Question
              Bank.
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
      {/* Question Bank Browser Modal */}
      <Dialog
        open={questionBankBrowserOpen}
        onOpenChange={setQuestionBankBrowserOpen}
      >
        <DialogContent className="bg-popover border-border text-popover-foreground sm:max-w-[700px] max-h-[85vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>Question Bank Browser</DialogTitle>
            <DialogDescription className="text-muted-foreground">
              Search and select existing questions to add to your current paper.
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
    </div>
  );
}
