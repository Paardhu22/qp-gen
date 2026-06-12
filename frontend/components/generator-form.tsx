"use client";

import { useState, useRef, useMemo, useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useEditorStore } from "@/store/editor-store";
import { toast } from "sonner";
import { BookOpen, FileCheck, Plus, Trash2, Loader2, AlertCircle } from "lucide-react";
import { fetchForm, fetchJson, streamSse, saveQuestions } from "@/lib/api-client";
import { ReviewTray } from "@/components/review-tray";
import {
  HsatSourcePicker,
  type AppliedHsatSource,
} from "@/components/hsat-source-picker";

const formSchema = z.object({
  qpType: z.enum(["board", "general_instructions"]),
  board: z.string(),
  academicClass: z.string(),
  subject: z.string(),
  // Mathematics Standard (041) vs Basic (241) — same A–E section skeleton,
  // different Bloom-band target. Only meaningful for Maths Class 10; ignored
  // by the backend for every other subject. Defaults to Standard.
  mathLevel: z.enum(["standard", "basic"]),
  difficulty: z.string(),
  questionType: z.string(),
  countType: z.enum(["custom", "cbse"]),
  numberOfQuestions: z.string().optional(),
  marks: z.string().min(1),
  // Cluster C: CBSE Sample Papers include "Visually Impaired alternative"
  // text under any visual question. The user can opt OUT of carrying those
  // alternatives into the generated paper without changing the model's
  // grounding — the backend implements it as a post-generation filter.
  // No .default() here so the inferred type stays `boolean` (not
  // `boolean | undefined`) — the default value is set in `defaultValues`.
  includeViAlternatives: z.boolean(),
});

interface UploadingDoc {
  tempId: string;
  name: string;
  status: "uploading" | "error";
  error?: string;
}

// Values accepted by the Subject / Class dropdowns below. HSAT sources
// carry the same canonical strings ("Mathematics", "Science", …, grade
// "10"), so an applied book can safely auto-select the matching option.
const FORM_SUBJECT_VALUES = [
  "Science",
  "Social Science",
  "Mathematics",
  "English",
  "Hindi",
  "Telugu",
];
const FORM_CLASS_VALUES = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"];

export const GeneratorForm = () => {
  const form = useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      qpType: "board",
      board: "CBSE",
      academicClass: "10",
      subject: "Science",
      mathLevel: "standard",
      difficulty: "medium",
      questionType: "mcq",
      countType: "cbse",
      numberOfQuestions: "5",
      marks: "1",
      includeViAlternatives: true,
    },
  });

  const currentQpType = form.watch("qpType");

  const fileInputRef = useRef<HTMLInputElement>(null);

  const [isGenerating, setIsGenerating] = useState(false);
  const [generatedResult, setGeneratedResult] = useState<any>(null);
  const [uploadedDocs, setUploadedDocs] = useState<
    { id: string; name: string; size: number }[]
  >([]);
  const [uploadingDocs, setUploadingDocs] = useState<UploadingDoc[]>([]);
  const [hsatSources, setHsatSources] = useState<AppliedHsatSource[]>([]);
  const [isHsatPickerOpen, setIsHsatPickerOpen] = useState(false);
  // Issue 3 — the draft instructions live in the zustand store directly so a
  // refresh, route change, or browser-close-and-back doesn't drop what the
  // teacher typed. The store is persisted via zustand `persist`, so the
  // round-trip is automatic.
  const generalInstructions = useEditorStore(
    (s) => s.generalInstructionsDraft,
  );
  const setGeneralInstructions = useEditorStore(
    (s) => s.setGeneralInstructionsDraft,
  );
  const [autoSaveEnabled, setAutoSaveEnabled] = useState(false);
  const [isSavingToBank, setIsSavingToBank] = useState(false);
  const [liveInsertedCount, setLiveInsertedCount] = useState(0);
  const liveInsertedSectionsRef = useRef<Set<string>>(new Set());

  // ── ISSUE 2: insertion mode (review vs auto) ───────────────────────
  const insertionMode = useEditorStore((s) => s.insertionMode);
  const setInsertionMode = useEditorStore((s) => s.setInsertionMode);
  const pushToTray = useEditorStore((s) => s.pushToTray);
  const setGeneratorContext = useEditorStore((s) => s.setGeneratorContext);

  // Keep generator-form selections mirrored to the store so the resume
  // modal / IndexedDB record can show truthful class/subject even before
  // the user opens the Paper Details modal. (ISSUE 1 — empty modal.)
  const formClassValue = form.watch("academicClass");
  const formSubjectValue = form.watch("subject");
  useEffect(() => {
    setGeneratorContext({
      className: formClassValue ? `Class ${formClassValue}` : "",
      subject: formSubjectValue || "",
      lastActiveAt: Date.now(),
    });
  }, [formClassValue, formSubjectValue, setGeneratorContext]);

  const handleAddSourceClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (files.length === 0) return;
    // Reset input so the same file can be selected again if needed
    e.target.value = "";

    const currentTotalSize = uploadedDocs.reduce(
      (acc, doc) => acc + (doc.size || 0),
      0,
    );
    let newTotalSize = currentTotalSize;
    let newDocCount = uploadedDocs.length + uploadingDocs.length;

    for (const file of files) {
      if (newDocCount >= 5) {
        toast.error("Maximum of 5 sources allowed.");
        break;
      }
      if (file.size > 100 * 1024 * 1024) {
        toast.error(`File ${file.name} exceeds 100MB limit.`);
        continue;
      }
      if (newTotalSize + file.size > 500 * 1024 * 1024) {
        toast.error("Total upload size cannot exceed 500MB.");
        continue;
      }

      newTotalSize += file.size;
      newDocCount += 1;

      const tempId = `${Date.now()}-${Math.random()}`;
      setUploadingDocs((prev) => [
        ...prev,
        { tempId, name: file.name, status: "uploading" },
      ]);

      try {
        const formData = new FormData();
        formData.append("file", file);

        const data = await fetchForm<{ pdfSourceId: string }>(
          "/api/documents/upload",
          formData,
        );

        // Upload succeeded — move from uploading to uploaded
        setUploadingDocs((prev) => prev.filter((d) => d.tempId !== tempId));
        setUploadedDocs((prev) => [
          ...prev,
          { id: data.pdfSourceId, name: file.name, size: file.size },
        ]);
      } catch (err: any) {
        setUploadingDocs((prev) =>
          prev.map((d) =>
            d.tempId === tempId
              ? { ...d, status: "error", error: err.message || "Upload failed" }
              : d,
          ),
        );
      }
    }
  };

  const dismissUploadError = (tempId: string) => {
    setUploadingDocs((prev) => prev.filter((d) => d.tempId !== tempId));
  };

  const removeDoc = (id: string) => {
    setUploadedDocs((prev) => prev.filter((d) => d.id !== id));
  };

  const handleHsatApply = (source: AppliedHsatSource) => {
    setHsatSources((prev) => {
      if (prev.some((s) => s.id === source.id)) return prev;
      return [...prev, source];
    });
    // The paper config must match the book that was just applied — leaving
    // Subject on its previous value (e.g. "Science" with an HSAT
    // Mathematics book) generates a paper whose blueprint and retrieval
    // disagree. HSAT catalog subjects/grades use the same canonical strings
    // as the form options, but guard against future drift: only overwrite
    // when the value is a known option.
    if (FORM_SUBJECT_VALUES.includes(source.subject)) {
      form.setValue("subject", source.subject);
    }
    if (FORM_CLASS_VALUES.includes(source.grade)) {
      form.setValue("academicClass", source.grade);
    }
    toast.success(`${source.book} added to sources`);
  };

  // Self-heal applied-source status: a source can be applied while its
  // ingest is still running (or the picker's completion poll can be cut
  // short by closing the dialog). The chip status and onSubmit's readiness
  // guard would then stay "processing" forever without a page refresh.
  // While any applied source is not terminal, poll the catalog and fold
  // fresh status/chunk counts back into state; stop as soon as everything
  // is ready or errored.
  const hasPendingHsat = hsatSources.some(
    (s) => s.status !== "ready" && s.status !== "error",
  );
  useEffect(() => {
    if (!hasPendingHsat) return;
    let cancelled = false;

    const refresh = async () => {
      try {
        const data = await fetchJson<{
          tree?: Record<
            string,
            Record<
              string,
              Record<
                string,
                { status: AppliedHsatSource["status"]; chunk_count: number }
              >
            >
          >;
        }>("/api/hsat/catalog/");
        if (cancelled) return;
        setHsatSources((prev) => {
          let changed = false;
          const next = prev.map((s) => {
            const entry = data.tree?.[s.grade]?.[s.subject]?.[s.book];
            if (!entry) return s;
            if (
              entry.status !== s.status ||
              (entry.chunk_count ?? s.chunkCount) !== s.chunkCount
            ) {
              changed = true;
              return {
                ...s,
                status: entry.status,
                chunkCount: entry.chunk_count ?? s.chunkCount,
              };
            }
            return s;
          });
          return changed ? next : prev;
        });
      } catch {
        // Transient network/catalog failure — the next tick retries.
      }
    };

    void refresh();
    const interval = setInterval(refresh, 5_000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [hasPendingHsat]);

  const removeHsatSource = (id: string) => {
    setHsatSources((prev) => prev.filter((s) => s.id !== id));
  };

  const appendQuestionToResult = (
    current: any,
    sectionTitle: string,
    question: any,
  ) => {
    const next = current
      ? {
          ...current,
          sections: (current.sections || []).map((section: any) => ({
            ...section,
            questions: [...(section.questions || [])],
          })),
        }
      : { sections: [] };

    let section = next.sections.find((item: any) => item.title === sectionTitle);
    if (!section) {
      section = { title: sectionTitle, questions: [] };
      next.sections.push(section);
    }
    section.questions.push(question);
    return next;
  };

  const appendQuestionToEditor = (sectionTitle: string, question: any) => {
    const store = useEditorStore.getState();
    const editorQuestion = {
      content: question.content,
      type: question.type,
      options: question.options || [],
      answer: question.answer,
      marks: question.marks,
      image_url: question.image_url || question.metadata?.image_url || "",
    };

    if (!liveInsertedSectionsRef.current.has(sectionTitle)) {
      liveInsertedSectionsRef.current.add(sectionTitle);
      store.appendSections([{ title: sectionTitle, questions: [editorQuestion] }]);
    } else {
      store.appendQuestions([editorQuestion]);
    }
    setLiveInsertedCount((count) => count + 1);
  };

  /** Stage a streamed question for review. Used when `insertionMode==="review"`. */
  const stageQuestionForReview = (sectionTitle: string, question: any) => {
    const sourceType =
      (question?.sourceType as "rag" | "curriculum_fallback" | undefined) ||
      (question?.metadata?.sourceType as "rag" | "curriculum_fallback" | undefined) ||
      "unknown";

    pushToTray({
      sectionTitle,
      sourceType,
      question: {
        content: question.content,
        type: question.type,
        options: question.options || [],
        answer: question.answer,
        marks: question.marks,
        image_url: question.image_url || question.metadata?.image_url || "",
        metadata: question.metadata || {},
        bloom: question.bloom,
        or_choice: question.or_choice,
        vi_alternative: question.vi_alternative,
      },
    });
  };

  const onSubmit = async (values: z.infer<typeof formSchema>) => {
    if (uploadedDocs.length === 0 && hsatSources.length === 0) {
      toast.error("Add at least one source file or HSAT book first.");
      return;
    }
    const notReadyHsat = hsatSources.find((s) => s.status !== "ready");
    if (notReadyHsat) {
      toast.error(
        `${notReadyHsat.book} is still being prepared. Wait for it to finish, then generate again.`,
      );
      return;
    }

    if (values.qpType === "general_instructions" && !generalInstructions.trim()) {
      toast.error("Please describe what questions you want in the instructions box.");
      return;
    }

    try {
      setIsGenerating(true);
      setGeneratedResult(null);
      setLiveInsertedCount(0);
      liveInsertedSectionsRef.current = new Set();

      let generationError: string | null = null;

      const isGIM = values.qpType === "general_instructions";

      await streamSse(
        "/api/generation/questions/stream",
        {
          pdfSourceIds: uploadedDocs.map((d) => d.id),
          hsatSourceIds: hsatSources.map((s) => s.id),
          count: isGIM
            ? parseInt(values.numberOfQuestions || "10", 10)
            : values.countType === "cbse"
              ? -1
              : parseInt(values.numberOfQuestions || "5", 10),
          countType: isGIM ? "custom" : values.countType,
          countVariation: isGIM ? "custom" : values.countType,
          difficulty: values.difficulty,
          instructions: generalInstructions || "",
          board: isGIM ? "" : values.board,
          subject: values.subject,
          class: values.academicClass,
          qp_type: values.qpType,
          mathLevel: values.mathLevel,
          include_vi_alternatives: values.includeViAlternatives,
        },
        (event, data) => {
          if (event === "error") {
            generationError = data.error || "Generation failed";
          } else if (event === "plan") {
            const generalInstructions = data.generalInstructions || [];
            setGeneratedResult({ sections: [], generalInstructions });
            // Only auto-insert the general-instructions block when the
            // teacher has opted into auto-insert. In review mode, the
            // instructions are rebuilt from the realized (inserted) set
            // by the editor's `updateSectionSummaries`, so dumping the
            // planned 38-question header in front of a 0-question paper
            // would mislead.
            if (
              insertionMode === "auto" &&
              Array.isArray(generalInstructions) &&
              generalInstructions.length > 0
            ) {
              useEditorStore.getState().appendInstructions(generalInstructions);
            }
          } else if (event === "question") {
            setGeneratedResult((current: any) =>
              appendQuestionToResult(current, data.section, data.question),
            );
            if (insertionMode === "auto") {
              appendQuestionToEditor(data.section, data.question);
            } else {
              stageQuestionForReview(data.section, data.question);
            }
          } else if (event === "update" || event === "message") {
            setGeneratedResult(data);
          } else if (event === "done" && data.result) {
            setGeneratedResult(data.result);
          }
        },
      );

      if (generationError) {
        toast.error(generationError);
      }
    } catch (error: any) {
      console.error(error);
      toast.error(
        error?.message ||
          "Failed to generate questions. Check whether your source files contain relevant content.",
      );
    } finally {
      setIsGenerating(false);
    }
  };

  const handleAddToEditor = async () => {
    if (!generatedResult) return;
    if (liveInsertedCount > 0) {
      toast.success(`${liveInsertedCount} generated question(s) already inserted into the editor.`);
      return;
    }

    const hasSections =
      generatedResult.sections && generatedResult.sections.length > 0;

    let allQuestions: any[] = [];
    if (hasSections) {
      const sections = generatedResult.sections.map((section: any) => {
        section.questions.forEach((q: any) => {
          allQuestions.push({
            content: q.content,
            type: q.type,
            options: q.options,
            answer: q.answer,
            marks: q.marks,
            metadata: q.metadata,
            image_url: q.image_url || q.metadata?.image_url || "",
          });
        });
        return {
          title: section.title,
          questions: section.questions.map((q: any) => ({
            content: q.content,
            type: q.type,
            options: q.options,
            answer: q.answer,
            marks: q.marks,
            image_url: q.image_url || q.metadata?.image_url || "",
          })),
        };
      });
      useEditorStore.getState().appendSections(sections);
      // Bug 5: surface backend `meta.footerNotes` (curriculum-fallback
      // disclosure) as instruction lines at the bottom of the doc so the
      // teacher and the rendered PDF both show which questions came from
      // curriculum knowledge instead of the uploaded sources.
      const footerNotes: string[] = Array.isArray(generatedResult?.meta?.footerNotes)
        ? generatedResult.meta.footerNotes
        : [];
      if (footerNotes.length > 0) {
        useEditorStore.getState().appendInstructions(footerNotes);
      }
      toast.success("Inserted generated sections into the editor.");
    } else {
      (generatedResult.questions || []).forEach((q: any) => {
        allQuestions.push({
          content: q.content,
          type: q.type,
          options: q.options,
          answer: q.answer,
          marks: q.marks,
          metadata: q.metadata,
          image_url: q.image_url || q.metadata?.image_url || "",
        });
      });
      useEditorStore.getState().appendQuestions(allQuestions);
      toast.success("Inserted generated questions into the editor.");
    }

    if (autoSaveEnabled && allQuestions.length > 0) {
      setIsSavingToBank(true);
      try {
        const questionsPayload = allQuestions.map((q) => ({
          type: q.type || "short",
          content: q.content,
          answer: q.answer || "",
          options: q.options || [],
          marks: Number(q.marks) || 1,
          grade_class: q.metadata?.gradeClass || form.getValues().academicClass,
          subject: q.metadata?.subject || form.getValues().subject,
          inferred_topic: q.metadata?.inferredTopic || "Generated Topic",
          inferred_chapter: q.metadata?.inferredChapter || "Generated Chapter",
          source_pdf: q.metadata?.sourcePdf || "",
          difficulty: q.metadata?.difficulty || form.getValues().difficulty,
        }));
        await saveQuestions({ questions: questionsPayload });
        toast.success("Questions automatically saved to the Question Bank!");
      } catch (err: any) {
        toast.error(err.message || "Failed to auto-save questions.");
      } finally {
        setIsSavingToBank(false);
      }
    }
  };

  const hasMultipleSources = uploadedDocs.length > 1;
  const hasMultipleChapters = useMemo(() => {
    if (!generatedResult) return false;
    const chapters = new Set<string>();
    (generatedResult.sections || []).forEach((s: any) => {
      (s.questions || []).forEach((q: any) => {
        if (q.metadata?.inferredChapter) {
          chapters.add(q.metadata.inferredChapter);
        }
      });
    });
    return chapters.size > 1;
  }, [generatedResult]);

  const showAutoSave = hasMultipleSources || hasMultipleChapters;

  const hasAnyDocs =
    uploadedDocs.length > 0 ||
    uploadingDocs.length > 0 ||
    hsatSources.length > 0;

  return (
    <div className="h-full flex flex-col p-4 bg-background text-muted-foreground overflow-y-auto custom-scrollbar">
      <div className="mb-6">
        <h2 className="text-lg font-bold text-foreground mb-1">
          Question Generator
        </h2>
        <p className="text-xs text-muted-foreground">
          Questions are generated STRICTLY from your source material.
        </p>
      </div>

      {/* Hidden file input — triggered by the Add Source button */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.txt,.docx"
        multiple
        className="hidden"
        onChange={handleFileChange}
      />

      {/* Source Files */}
      <div className="mb-6 space-y-3">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-foreground">
            Source Files
          </label>
          <div className="flex items-center gap-1">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleAddSourceClick}
              className="h-7 text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-500 dark:hover:text-indigo-300 hover:bg-indigo-50 dark:hover:bg-indigo-500/10"
            >
              <Plus className="h-3 w-3 mr-1" />
              Add Source
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setIsHsatPickerOpen(true)}
              className="h-7 text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-500 dark:hover:text-indigo-300 hover:bg-indigo-50 dark:hover:bg-indigo-500/10"
            >
              <BookOpen className="h-3 w-3 mr-1" />
              Apply Source from HSAT
            </Button>
          </div>
        </div>

        <div className="space-y-2">
          {/* Empty state */}
          {!hasAnyDocs && (
            <div className="text-center py-6 border border-dashed border-border rounded-lg bg-muted/30">
              <p className="text-xs text-muted-foreground">No files uploaded yet.</p>
            </div>
          )}

          {/* Uploading / error rows */}
          {uploadingDocs.map((doc) => (
            <div key={doc.tempId}>
              <div className="flex items-center justify-between p-2 rounded-lg bg-muted/50 border border-border">
                <div className="flex items-center gap-2 min-w-0">
                  {doc.status === "uploading" ? (
                    <Loader2 className="h-4 w-4 text-indigo-500 animate-spin flex-shrink-0" />
                  ) : (
                    <AlertCircle className="h-4 w-4 text-red-400 flex-shrink-0" />
                  )}
                  <div className="min-w-0">
                    <span className="text-xs text-foreground truncate block">
                      {doc.name}
                    </span>
                    {doc.status === "uploading" && (
                      <span className="text-[10px] text-indigo-400 dark:text-indigo-300">
                        Processing document, please wait…
                      </span>
                    )}
                    {doc.status === "error" && (
                      <span className="text-[10px] text-red-400">
                        {doc.error}
                      </span>
                    )}
                  </div>
                </div>
                {doc.status === "error" && (
                  <button
                    onClick={() => dismissUploadError(doc.tempId)}
                    className="p-1 hover:text-red-400 transition-colors flex-shrink-0"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                )}
              </div>
              {doc.status === "uploading" && (
                <div className="mt-1 h-0.5 w-full rounded-full bg-muted-foreground/30 overflow-hidden">
                  <div
                    className="h-full bg-indigo-500 rounded-full animate-[loading-bar_1.4s_ease-in-out_infinite]"
                    style={{ width: "60%" }}
                  />
                </div>
              )}
            </div>
          ))}

          {/* Successfully uploaded rows */}
          {uploadedDocs.map((doc) => (
            <div
              key={doc.id}
              className="flex items-center justify-between p-2 rounded-lg bg-muted/50 border border-border group"
            >
              <div className="flex items-center gap-2 min-w-0">
                <FileCheck className="h-4 w-4 text-green-500 flex-shrink-0" />
                <span className="text-xs text-foreground truncate">
                  {doc.name}
                </span>
              </div>
              <button
                onClick={() => removeDoc(doc.id)}
                className="opacity-0 group-hover:opacity-100 p-1 hover:text-red-400 transition-opacity"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))}

          {/* Applied HSAT sources — visually distinct: book icon + HSAT label */}
          {hsatSources.map((source) => {
            const isPreparing =
              source.status === "processing" || source.status === "pending";
            const isError = source.status === "error";
            return (
              <div
                key={source.id}
                className="flex items-center justify-between p-2 rounded-lg bg-indigo-50/40 dark:bg-indigo-950/20 border border-indigo-200 dark:border-indigo-900/40 group"
              >
                <div className="flex items-center gap-2 min-w-0">
                  {isPreparing ? (
                    <Loader2 className="h-4 w-4 text-indigo-500 animate-spin flex-shrink-0" />
                  ) : isError ? (
                    <AlertCircle className="h-4 w-4 text-red-500 flex-shrink-0" />
                  ) : (
                    <BookOpen className="h-4 w-4 text-indigo-500 flex-shrink-0" />
                  )}
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-[10px] font-semibold uppercase tracking-wide text-indigo-600 dark:text-indigo-300">
                        HSAT
                      </span>
                      <span className="text-xs text-foreground truncate">
                        {source.book}
                      </span>
                    </div>
                    <div className="text-[10px] text-muted-foreground truncate">
                      Class {source.grade} · {source.subject}
                      {source.selectedChapterCount
                        ? ` · ${source.selectedChapterCount} chapter${source.selectedChapterCount === 1 ? "" : "s"}`
                        : ""}
                      {isPreparing && " · preparing…"}
                      {isError && " · failed — remove and try again"}
                    </div>
                  </div>
                </div>
                <button
                  onClick={() => removeHsatSource(source.id)}
                  className="opacity-0 group-hover:opacity-100 p-1 hover:text-red-400 transition-opacity"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            );
          })}
        </div>
      </div>

      <HsatSourcePicker
        open={isHsatPickerOpen}
        onOpenChange={setIsHsatPickerOpen}
        paperId={null}
        appliedIds={hsatSources.map((s) => s.id)}
        onApply={handleHsatApply}
      />

      <Form {...form}>
        <form
          onSubmit={form.handleSubmit(onSubmit)}
          className="space-y-6 flex-1"
        >
          {/* QP Type Selector */}
          <FormField
            control={form.control}
            name="qpType"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-foreground font-semibold">QP Type</FormLabel>
                <Select value={field.value} onValueChange={field.onChange}>
                  <FormControl>
                    <SelectTrigger className="w-full bg-background border-border text-foreground">
                      <SelectValue placeholder="Select QP Type" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent alignItemWithTrigger={false} className="bg-background border-border text-foreground min-w-[var(--radix-select-trigger-width)]">
                    <SelectItem value="board">Board Mode</SelectItem>
                    <SelectItem value="general_instructions">General Instructions Mode</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-[10px] text-zinc-400 dark:text-muted-foreground mt-0.5">
                  {field.value === "board"
                    ? "Uses CBSE/board-specific structure, sections, and Bloom's taxonomy."
                    : "The AI follows your written instructions exactly — no board patterns."}
                </p>
                <FormMessage />
              </FormItem>
            )}
          />

          {/* Board (Board Mode only) + Class share a row; Subject is on
              its own row so the long subject labels (e.g. "English Language
              & Literature (Code 184)") fit in the trigger without being
              truncated by a 1/3-column-wide grid cell. */}
          <div className="grid grid-cols-2 gap-4">
            {currentQpType === "board" && (
              <FormField
                control={form.control}
                name="board"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="text-foreground">Board</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger className="w-full bg-background border-border text-foreground"><SelectValue placeholder="Select" /></SelectTrigger>
                      </FormControl>
                      <SelectContent alignItemWithTrigger={false} className="bg-background border-border text-foreground">
                        <SelectItem value="CBSE">CBSE</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}
            <FormField
              control={form.control}
              name="academicClass"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="text-foreground">Class</FormLabel>
                  <Select value={field.value} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger className="w-full bg-background border-border text-foreground"><SelectValue placeholder="Select" /></SelectTrigger>
                    </FormControl>
                    <SelectContent alignItemWithTrigger={false} className="bg-background border-border text-foreground">
                      <SelectItem value="1">Class 1</SelectItem>
                      <SelectItem value="2">Class 2</SelectItem>
                      <SelectItem value="3">Class 3</SelectItem>
                      <SelectItem value="4">Class 4</SelectItem>
                      <SelectItem value="5">Class 5</SelectItem>
                      <SelectItem value="6">Class 6</SelectItem>
                      <SelectItem value="7">Class 7</SelectItem>
                      <SelectItem value="8">Class 8</SelectItem>
                      <SelectItem value="9">Class 9</SelectItem>
                      <SelectItem value="10">Class 10</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>
          <FormField
            control={form.control}
            name="subject"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-foreground">Subject</FormLabel>
                <Select value={field.value} onValueChange={field.onChange}>
                  <FormControl>
                    <SelectTrigger className="w-full bg-background border-border text-foreground"><SelectValue placeholder="Select" /></SelectTrigger>
                  </FormControl>
                  <SelectContent alignItemWithTrigger={false} className="bg-background border-border text-foreground">
                    <SelectItem value="Science">Science</SelectItem>
                    <SelectItem value="Social Science">Social Science</SelectItem>
                    <SelectItem value="Mathematics">Mathematics Standard (Code 041)</SelectItem>
                    <SelectItem value="English">English Language &amp; Literature (Code 184)</SelectItem>
                    <SelectItem value="Hindi">Hindi Course B (Code 085)</SelectItem>
                    <SelectItem value="Telugu">Telugu Telangana (Code 089)</SelectItem>
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />

          {/* Mathematics tier: Standard (041) vs Basic (241). Same A–E
              section structure — only the cognitive (Bloom) mix differs.
              Shown only for Maths Class 10. */}
          {formSubjectValue === "Mathematics" && formClassValue === "10" && (
            <FormField
              control={form.control}
              name="mathLevel"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="text-foreground">Mathematics Level</FormLabel>
                  <Select value={field.value} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger className="w-full bg-background border-border text-foreground">
                        <SelectValue placeholder="Select" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent alignItemWithTrigger={false} className="bg-background border-border text-foreground">
                      <SelectItem value="standard">Standard (Code 041)</SelectItem>
                      <SelectItem value="basic">Basic (Code 241)</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />
          )}

          <FormField
            control={form.control}
            name="difficulty"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-foreground">
                  Difficulty
                </FormLabel>
                <Select value={field.value} onValueChange={field.onChange}>
                  <FormControl>
                    <SelectTrigger className="w-full bg-background border-border text-foreground">
                      <SelectValue placeholder="Select" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent alignItemWithTrigger={false} className="bg-background border-border text-foreground min-w-[var(--radix-select-trigger-width)]">
                    <SelectItem value="easy">Easy</SelectItem>
                    <SelectItem value="medium">Medium</SelectItem>
                    <SelectItem value="hard">Hard</SelectItem>
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />

          {/* Count Variation — only in Board Mode */}
          {currentQpType === "board" && (
            <FormField
              control={form.control}
              name="countType"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="text-foreground">
                    Count Variation
                  </FormLabel>
                  <Select value={field.value} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger className="w-full bg-background border-border text-foreground">
                        <SelectValue placeholder="Select" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent alignItemWithTrigger={false} className="bg-background border-border text-foreground min-w-[var(--radix-select-trigger-width)]">
                      <SelectItem value="cbse">CBSE Exact Pattern</SelectItem>
                      <SelectItem value="custom">Custom Count</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />
          )}

          {/* Exact Count — shown in Board Custom or GIM */}
          {(currentQpType === "general_instructions" || form.watch("countType") === "custom") && (
            <FormField
              control={form.control}
              name="numberOfQuestions"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="text-foreground">
                    {currentQpType === "general_instructions" ? "Exact Count (optional)" : "Exact Count"}
                  </FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      min="1"
                      max="50"
                      className="bg-background border-border text-foreground"
                      {...field}
                    />
                  </FormControl>
                  {currentQpType === "general_instructions" && (
                    <p className="text-[10px] text-zinc-400 dark:text-muted-foreground">
                      Leave empty if your instructions specify the count.
                    </p>
                  )}
                  <FormMessage />
                </FormItem>
              )}
            />
          )}

          {/* Cluster C: VI alternative toggle. CBSE Sample Papers append a
              Visually Impaired alternative under any visual question; the
              model faithfully reflects the source. The teacher can opt out
              without changing prompting (post-generation filter). */}
          <FormField
            control={form.control}
            name="includeViAlternatives"
            render={({ field }) => (
              <FormItem className="flex items-start gap-3 rounded-md border border-border bg-background px-3 py-2.5">
                <FormControl>
                  <input
                    id="includeViAlternatives"
                    type="checkbox"
                    checked={field.value}
                    onChange={(e) => field.onChange(e.target.checked)}
                    className="mt-0.5 h-4 w-4 cursor-pointer rounded border-border accent-indigo-600"
                  />
                </FormControl>
                <div className="flex-1 space-y-1">
                  <label
                    htmlFor="includeViAlternatives"
                    className="cursor-pointer text-sm font-medium text-foreground"
                  >
                    Include Visually Impaired alternatives
                  </label>
                  <p className="text-[11px] text-zinc-500 dark:text-muted-foreground">
                    CBSE Sample Papers attach a VI alternative to every visual
                    question. Leave on to mirror that pattern; turn off to
                    suppress the VI blocks in the generated paper without
                    changing what the model retrieves from your sources.
                  </p>
                </div>
              </FormItem>
            )}
          />

          {/* General Instructions / Your Instructions */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">
              {currentQpType === "general_instructions" ? (
                <>
                  Your Instructions <span className="text-red-500">*</span>
                </>
              ) : (
                "General Instructions"
              )}
            </label>
            <Textarea
              placeholder={
                currentQpType === "general_instructions"
                  ? "Describe exactly what you want.\nExample: 5 MCQs, 3 short answers of 2 marks each, 2 long answers."
                  : "e.g. Section A: 4 short answer questions (2 marks each)\nSection B: 4 long answer questions (5 marks each)"
              }
              className={`bg-background border-border text-foreground placeholder:text-zinc-400 dark:placeholder:text-zinc-600 text-sm resize-none focus:ring-indigo-500 ${
                currentQpType === "general_instructions"
                  ? "min-h-[120px] border-indigo-300 dark:border-indigo-700 ring-1 ring-indigo-200 dark:ring-indigo-800/50"
                  : "min-h-[90px]"
              }`}
              value={generalInstructions}
              onChange={(e) => setGeneralInstructions(e.target.value)}
            />
            <p className="text-[11px] text-zinc-400 dark:text-muted-foreground">
              {currentQpType === "general_instructions"
                ? "The AI will follow these instructions exactly. Be specific about question types, counts, and marks."
                : "Describe section structure and question types. The AI will follow these instructions."}
            </p>
          </div>

          <div className="pt-4 sticky bottom-0 bg-background pb-4">
            <Button
              type="submit"
              // HSAT books are first-class sources: a paper can be generated
              // from an applied HSAT book with zero uploaded PDFs. Gating on
              // uploadedDocs alone left the button permanently grey after an
              // HSAT-only apply. Readiness (status !== "ready") is enforced
              // in onSubmit with a toast — a disabled button can't explain
              // itself, a toast can.
              disabled={
                isGenerating ||
                (uploadedDocs.length === 0 && hsatSources.length === 0)
              }
              className="w-full bg-indigo-600 hover:bg-indigo-700 text-white shadow-lg gap-2"
            >
              {isGenerating
                ? "Analyzing & Generating..."
                : "Generate Questions"}
            </Button>
          </div>
        </form>
      </Form>

      {/* ── ISSUE 2: insertion-mode toggle ───────────────────────────── */}
      <div className="mt-6 mb-2 p-3 rounded-lg border border-border bg-muted/40">
        <div className="text-xs font-medium text-foreground mb-2">
          When generation finishes:
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setInsertionMode("review")}
            className={`flex-1 text-xs px-2 py-1.5 rounded-md border transition-colors ${
              insertionMode === "review"
                ? "border-indigo-500 bg-indigo-50 dark:bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 font-medium"
                : "border-border text-muted-foreground hover:border-zinc-400"
            }`}
          >
            Review before inserting
          </button>
          <button
            type="button"
            onClick={() => setInsertionMode("auto")}
            className={`flex-1 text-xs px-2 py-1.5 rounded-md border transition-colors ${
              insertionMode === "auto"
                ? "border-indigo-500 bg-indigo-50 dark:bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 font-medium"
                : "border-border text-muted-foreground hover:border-zinc-400"
            }`}
          >
            Auto-insert all
          </button>
        </div>
      </div>

      {/* Review tray — pending generated questions awaiting the teacher's call. */}
      {insertionMode === "review" && <ReviewTray />}

      {generatedResult && insertionMode === "auto" && (
        <div className="mt-6 border-t border-border pt-6 animate-in fade-in duration-500">
          <h3 className="text-lg font-bold text-foreground mb-4 flex items-center gap-2">
            Generated Output
          </h3>

          <div className="space-y-6">
            {generatedResult.sections?.map((section: any, sIdx: number) => (
              <div key={sIdx} className="space-y-4">
                <h4 className="text-sm font-semibold text-indigo-600 dark:text-indigo-400 uppercase tracking-wider">
                  {section.title}
                </h4>
                <div className="space-y-3">
                  {section.questions?.map((q: any, qIdx: number) => (
                    <div
                      key={qIdx}
                      className="p-3 bg-muted/50 border border-border rounded-xl space-y-2"
                    >
                      <div className="flex justify-between items-start gap-2">
                        <p className="font-medium text-sm text-zinc-800 dark:text-zinc-100">
                          {q.content}
                        </p>
                        <span className="text-[10px] bg-zinc-200 dark:bg-zinc-800 px-1.5 py-0.5 rounded text-zinc-600 dark:text-zinc-400 font-mono">
                          {q.marks}m
                        </span>
                      </div>
                      {q.options && q.options.length > 0 && (
                        <div className="grid grid-cols-2 gap-2 mt-2">
                          {q.options.map((opt: string, oIdx: number) => (
                            <div
                              key={oIdx}
                              className="text-[11px] text-muted-foreground dark:text-zinc-400 border border-border p-1.5 rounded bg-background/50"
                            >
                              {String.fromCharCode(65 + oIdx)}. {opt}
                            </div>
                          ))}
                        </div>
                      )}
                      <div className="mt-2 pt-2 border-t border-border">
                        <p className="text-[10px] text-green-600 dark:text-green-500 font-medium truncate">
                          Ans: {q.answer}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>

          <div className="mt-6 flex flex-col gap-2">
            {!isGenerating && (
              <>
                {showAutoSave && (
                  <div className="flex items-center gap-2 p-3 mb-2 bg-indigo-50 dark:bg-indigo-900/20 rounded-lg border border-indigo-100 dark:border-indigo-800/30">
                    <input
                      type="checkbox"
                      id="autoSave"
                      checked={autoSaveEnabled}
                      onChange={(e) => setAutoSaveEnabled(e.target.checked)}
                      className="rounded border-indigo-300 text-indigo-600 focus:ring-indigo-500"
                    />
                    <label
                      htmlFor="autoSave"
                      className="text-sm font-medium text-indigo-900 dark:text-indigo-200 cursor-pointer"
                    >
                      Auto Save Questions by Chapter
                    </label>
                  </div>
                )}
                <Button
                  className="w-full bg-indigo-600 text-white hover:bg-indigo-700 font-semibold"
                  onClick={handleAddToEditor}
                  disabled={isSavingToBank || liveInsertedCount > 0}
                >
                  {isSavingToBank ? (
                    <span className="flex items-center gap-2">
                      <Loader2 className="h-4 w-4 animate-spin" /> Saving...
                    </span>
                  ) : liveInsertedCount > 0 ? (
                    `Inserted ${liveInsertedCount} into Editor`
                  ) : (
                    "Insert All into Editor"
                  )}
                </Button>
                <Button
                  variant="ghost"
                  className="w-full text-zinc-400 dark:text-muted-foreground hover:text-zinc-600 dark:hover:text-zinc-300"
                  onClick={() => setGeneratedResult(null)}
                >
                  Clear Results
                </Button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
