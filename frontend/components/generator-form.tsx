"use client";

import { useState, useRef, useMemo, useEffect, useCallback } from "react";
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
import { useEditorStore, type TrayItem } from "@/store/editor-store";
import { PaperDesignPanel } from "@/components/paper-design-panel";
import { TemplatePicker } from "@/components/template-picker";
import { usePaperDesign } from "@/lib/use-paper-design";
import { toast } from "sonner";
import {
  AlertCircle,
  BookOpen,
  CheckCircle2,
  FileCheck,
  Loader2,
  Plus,
  Trash2,
} from "lucide-react";
import {
  analyzePdfDocument,
  detectPdfSubject,
  fetchForm,
  fetchJson,
  streamSse,
  validatePdfMetadata,
  type PdfAnalysisResult,
  type PdfValidationReport,
} from "@/lib/api-client";
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
  contentScopePolicy: z.enum(["strict", "source_only"]),
  // Number of parallel paper sets to produce. "1" = Set A only; "2" adds
  // Set B; "3" adds Set C. The pool and Model 1 run once regardless — B and C
  // are derived from Set A by substituting alternatives already in the pool.
  numberOfSets: z.enum(["1", "2", "3"]),
});

interface UploadingDoc {
  tempId: string;
  name: string;
  // "uploading": bytes in flight to the backend.
  // "processing": backend accepted the file and is ingesting it (async); we
  //   poll the status endpoint until it flips to ready/error.
  // "error": upload or ingest failed.
  status: "uploading" | "processing" | "error";
  error?: string;
  /** PdfSource id once the upload POST returns; drives status polling. */
  pdfSourceId?: string;
  size?: number;
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
  "Sanskrit",
  "Computer Science",
];

const ALL_SUBJECT_OPTIONS: { value: string; label: string }[] = [
  { value: "Science", label: "Science" },
  { value: "Social Science", label: "Social Science" },
  { value: "Mathematics", label: "Mathematics Standard (Code 041)" },
  { value: "English", label: "English Language & Literature (Code 184)" },
  { value: "Hindi", label: "Hindi Course B (Code 085)" },
  { value: "Telugu", label: "Telugu Telangana (Code 089)" },
  { value: "Sanskrit", label: "Sanskrit" },
  { value: "Computer Science", label: "Computer Science" },
];

const FORM_CLASS_VALUES = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"];

interface GeneratorFormProps {
  uploadedDocs: { id: string; name: string; size: number }[];
  setUploadedDocs: React.Dispatch<React.SetStateAction<{ id: string; name: string; size: number }[]>>;
  hsatSources: AppliedHsatSource[];
  setHsatSources: React.Dispatch<React.SetStateAction<AppliedHsatSource[]>>;
}

export const GeneratorForm = ({
  uploadedDocs,
  setUploadedDocs,
  hsatSources,
  setHsatSources,
}: GeneratorFormProps) => {
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
      contentScopePolicy: "strict",
      numberOfSets: "1",
    },
  });

  const currentQpType = form.watch("qpType");

  const fileInputRef = useRef<HTMLInputElement>(null);

  const [isGenerating, setIsGenerating] = useState(false);
  const [generatedResult, setGeneratedResult] = useState<any>(null);
  const [uploadingDocs, setUploadingDocs] = useState<UploadingDoc[]>([]);
  const [isHsatPickerOpen, setIsHsatPickerOpen] = useState(false);
  const [detectedSubject, setDetectedSubject] = useState<string | null>(null);
  const [isDetectingSubject, setIsDetectingSubject] = useState<boolean>(false);
  const [pdfAnalysisMap, setPdfAnalysisMap] = useState<Map<string, PdfAnalysisResult>>(new Map());
  const [analysisProgressMap, setAnalysisProgressMap] = useState<Map<string, string>>(new Map());
  const [validationReport, setValidationReport] = useState<PdfValidationReport | null>(null);

  const revalidatePdfResults = async (results: PdfAnalysisResult[]) => {
    if (results.length === 0) {
      setValidationReport(null);
      setDetectedSubject(null);
      return;
    }
    try {
      const report = await validatePdfMetadata(results);
      setValidationReport(report);
      if (report.valid) {
        if (report.subject) {
          setDetectedSubject(report.subject);
          form.setValue("subject", report.subject);
          toast.success(`✓ Subject detected: ${report.subject}`);
        }
      } else {
        setDetectedSubject(null);
        if (report.message) {
          toast.error(report.message);
        }
      }
    } catch (err) {
      console.warn("Validation failed:", err);
    }
  };
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

  // ── General Instructions Mode: live design + gap resolution ───────────
  // The settings the designer needs, read off the form so a value the teacher
  // already picked is never asked for again. `useMemo` on the watched values
  // rather than the whole form object, which is a new identity every render
  // and would restart the debounce on every keystroke anywhere in the form.
  const watchedClass = form.watch("academicClass");
  const watchedSubject = form.watch("subject");
  const watchedDifficulty = form.watch("difficulty");
  const watchedMarks = form.watch("marks");
  const watchedSets = form.watch("numberOfSets");
  const watchedBoard = form.watch("board");
  const designSettings = useMemo(
    () => ({
      board: watchedBoard || "",
      academicClass: watchedClass || "",
      subject: watchedSubject || "",
      difficulty: watchedDifficulty || "",
      marks: watchedMarks || "",
      numberOfSets: watchedSets || "",
    }),
    [
      watchedBoard,
      watchedClass,
      watchedSubject,
      watchedDifficulty,
      watchedMarks,
      watchedSets,
    ],
  );

  const isGimMode = currentQpType === "general_instructions";
  const paperDesign = usePaperDesign({
    instructions: generalInstructions,
    settings: designSettings,
    pdfSourceIds: useMemo(
      () => uploadedDocs.map((d) => d.id).filter(Boolean) as string[],
      [uploadedDocs],
    ),
    hsatSourceIds: useMemo(
      () => hsatSources.map((s) => s.id).filter(Boolean) as string[],
      [hsatSources],
    ),
    enabled: isGimMode,
  });

  // Answering a gap writes straight into the form, which is what the generator
  // submits — so the panel and the form can never disagree about what the
  // teacher chose. `sources` is the exception: it is satisfied by uploading,
  // not by picking a value.
  const resolveDesignGap = useCallback(
    (field: string, value: string) => {
      if (field === "sources") return;
      form.setValue(field as Parameters<typeof form.setValue>[0], value as never, {
        shouldDirty: true,
      });
    },
    [form],
  );

  const applyTemplate = useCallback(
    (template: { instructions: string; settings: Record<string, string> }) => {
      setGeneralInstructions(template.instructions);
      // The saved answers, so re-using a template does not re-ask for
      // difficulty or set count. Only fields the template actually recorded.
      for (const [field, value] of Object.entries(template.settings || {})) {
        const text = String(value ?? "").trim();
        if (!text) continue;
        form.setValue(
          field as Parameters<typeof form.setValue>[0],
          text as never,
          { shouldDirty: true },
        );
      }
      // A template is a paper described in prose, so it only makes sense in
      // the mode that reads prose.
      form.setValue("qpType", "general_instructions");
    },
    [form, setGeneralInstructions],
  );
  // Requirements gathered by the dashboard assistant, if the teacher arrived
  // from there. Applied once and then cleared: without the clear, every later
  // visit to the editor would re-apply the same settings and quietly undo
  // whatever the teacher had changed by hand since.
  const paperSpecHandoff = useEditorStore((s) => s.paperSpecHandoff);
  const setPaperSpecHandoff = useEditorStore((s) => s.setPaperSpecHandoff);
  // Saving is no longer a user action. The backend persists the entire
  // generated question pool (~80 questions, not just the ~38 this paper uses)
  // to the bank automatically and reports the outcome on the `saved` SSE
  // event. These two pieces of state exist only to show what happened.
  const [savedToBank, setSavedToBank] = useState<{
    saved: number;
    duplicatesSkipped: number;
    projectName: string;
  } | null>(null);
  const [poolStatus, setPoolStatus] = useState<string>("");
  const [liveInsertedCount, setLiveInsertedCount] = useState(0);
  const liveInsertedSectionsRef = useRef<Set<string>>(new Set());

  // Multiple sets (A/B/C). `variantSets` holds only the DERIVED sets (B, C)
  // streamed on `set` events; Set A stays in `generatedResult` so the single-
  // set path is untouched. `activeSet` drives the preview switcher.
  const [variantSets, setVariantSets] = useState<
    { label: string; result: any }[]
  >([]);
  const [activeSet, setActiveSet] = useState<string>("A");
  // True for the duration of a multi-set generation. Kept separate from
  // `variantSets.length` so the switcher still owns the UI (and Set A stays
  // reachable) even if the backend could not derive B/C for this pool.
  const [multiSetMode, setMultiSetMode] = useState(false);

  // ── ISSUE 2: insertion mode (review vs auto) ───────────────────────
  const insertionMode = useEditorStore((s) => s.insertionMode);
  const setInsertionMode = useEditorStore((s) => s.setInsertionMode);
  const pushToTray = useEditorStore((s) => s.pushToTray);
  const setGeneratorContext = useEditorStore((s) => s.setGeneratorContext);
  // Comparison Workspace — the primary review UI for multi-set output.
  const setComparisonSets = useEditorStore((s) => s.setComparisonSets);
  const clearComparisonSets = useEditorStore((s) => s.clearComparisonSets);
  const setComparisonOpen = useEditorStore((s) => s.setComparisonOpen);
  const comparisonSets = useEditorStore((s) => s.comparisonSets);

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

  // Apply the dashboard assistant's spec, once. Fields the conversation never
  // settled are left at their defaults rather than blanked, so a partial
  // handoff still leaves a form the teacher can submit. Chapter names go into
  // the instructions box because chapters are not a form field — the
  // generator scopes content by uploaded source, and a named chapter is only
  // a hint until one is attached.
  useEffect(() => {
    if (!paperSpecHandoff) return;

    const spec = paperSpecHandoff as Record<string, any>;
    const apply = (
      field: Parameters<typeof form.setValue>[0],
      value: unknown,
    ) => {
      const text = String(value ?? "").trim();
      if (text) form.setValue(field, text as never);
    };

    apply("board", spec.board);
    apply("academicClass", spec.academicClass);
    apply("subject", spec.subject);
    apply("difficulty", spec.difficulty);
    apply("marks", spec.marks);
    apply("numberOfSets", spec.numberOfSets);
    if (String(spec.numberOfQuestions ?? "").trim()) {
      form.setValue("countType", "custom");
      apply("numberOfQuestions", spec.numberOfQuestions);
    }

    const chapters: string[] = Array.isArray(spec.chapters) ? spec.chapters : [];
    if (chapters.length > 0) {
      const line = `Chapters: ${chapters.join(", ")}`;
      setGeneralInstructions(
        generalInstructions ? `${generalInstructions}\n${line}` : line,
      );
    }

    setPaperSpecHandoff(null);
    // `generalInstructions` is read, not tracked: including it would re-run
    // this effect on every keystroke in the instructions box. The handoff is
    // cleared on the first pass, so there is nothing to re-apply anyway.
  }, [paperSpecHandoff, form, setGeneralInstructions, setPaperSpecHandoff]);

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

      // Duplicate PDF Detection: check if identical file is already uploaded or uploading
      const isDuplicate =
        uploadedDocs.some(
          (d) => d.name === file.name && (d.size === file.size || !d.size),
        ) || uploadingDocs.some((d) => d.name === file.name);

      if (isDuplicate) {
        toast.warning("This PDF has already been uploaded.");
        continue;
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

      // Trigger automatic intelligent PDF analysis for PDF files
      if (file.name.toLowerCase().endsWith(".pdf") || file.type === "application/pdf") {
        setIsDetectingSubject(true);
        setAnalysisProgressMap((prev) => new Map(prev).set(file.name, "Extracting Text..."));

        void analyzePdfDocument(file)
          .then((res) => {
            setAnalysisProgressMap((prev) => new Map(prev).set(file.name, "Detection Complete ✓"));
            setPdfAnalysisMap((prev) => {
              const nextMap = new Map(prev);
              nextMap.set(file.name, res);
              void revalidatePdfResults(Array.from(nextMap.values()));
              return nextMap;
            });
          })
          .catch((err) => {
            console.warn("Automatic PDF analysis failed:", err);
            setAnalysisProgressMap((prev) => new Map(prev).set(file.name, "Analysis failed"));
          })
          .finally(() => {
            setIsDetectingSubject(false);
          });
      }

      const tempId = `${Date.now()}-${Math.random()}`;
      const fileSize = file.size;
      setUploadingDocs((prev) => [
        ...prev,
        { tempId, name: file.name, status: "uploading", size: fileSize },
      ]);

      try {
        const formData = new FormData();
        formData.append("file", file);

        const data = await fetchForm<{
          pdfSourceId: string;
          status?: string;
        }>("/api/documents/upload", formData);

        if (data.status === "ready") {
          // Deduped/cached source — already ingested. Promote immediately.
          setUploadingDocs((prev) => prev.filter((d) => d.tempId !== tempId));
          setUploadedDocs((prev) => [
            ...prev,
            { id: data.pdfSourceId, name: file.name, size: fileSize },
          ]);
        } else {
          // Async ingest in progress — keep the row (spinner) and let the
          // polling effect below promote it to uploadedDocs once ready.
          setUploadingDocs((prev) =>
            prev.map((d) =>
              d.tempId === tempId
                ? { ...d, status: "processing", pdfSourceId: data.pdfSourceId }
                : d,
            ),
          );
        }
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

  const removeDoc = (id: string, name?: string) => {
    setUploadedDocs((prev) => {
      const nextDocs = prev.filter((d) => d.id !== id);
      setPdfAnalysisMap((prevMap) => {
        const nextMap = new Map(prevMap);
        const targetName = name || prev.find((d) => d.id === id)?.name;
        if (targetName) nextMap.delete(targetName);
        void revalidatePdfResults(Array.from(nextMap.values()));
        return nextMap;
      });
      if (nextDocs.length === 0 && hsatSources.length === 0) {
        setDetectedSubject(null);
        setValidationReport(null);
      }
      return nextDocs;
    });
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
    setHsatSources((prev) => {
      const next = prev.filter((s) => s.id !== id);
      if (next.length === 0 && uploadedDocs.length === 0) {
        setDetectedSubject(null);
      }
      return next;
    });
  };

  // ── Async PDF upload: poll ingest status until ready ──────────────────────
  // The upload endpoint now returns immediately with status "processing"; the
  // backend ingests (extract → caption → embed) on a worker thread. Poll the
  // status endpoint and promote each source to `uploadedDocs` (the ready set)
  // once it reports "ready", or surface the error. Mirrors the HSAT self-heal
  // poll above. A ref feeds the interval the latest list so sources uploaded
  // mid-poll are picked up without restarting the timer.
  const uploadingDocsRef = useRef<UploadingDoc[]>(uploadingDocs);
  uploadingDocsRef.current = uploadingDocs;
  const hasProcessingUploads = uploadingDocs.some(
    (d) => d.status === "processing" && d.pdfSourceId,
  );
  useEffect(() => {
    if (!hasProcessingUploads) return;
    let cancelled = false;

    const poll = async () => {
      const targets = uploadingDocsRef.current.filter(
        (d) => d.status === "processing" && d.pdfSourceId,
      );
      await Promise.all(
        targets.map(async (doc) => {
          try {
            const st = await fetchJson<{
              status: string;
              error?: string | null;
            }>(`/api/documents/${doc.pdfSourceId}/status`);
            if (cancelled) return;
            if (st.status === "ready") {
              setUploadingDocs((prev) =>
                prev.filter((d) => d.tempId !== doc.tempId),
              );
              setUploadedDocs((prev) =>
                prev.some((d) => d.id === doc.pdfSourceId)
                  ? prev
                  : [
                      ...prev,
                      {
                        id: doc.pdfSourceId!,
                        name: doc.name,
                        size: doc.size || 0,
                      },
                    ],
              );
            } else if (st.status === "error") {
              setUploadingDocs((prev) =>
                prev.map((d) =>
                  d.tempId === doc.tempId
                    ? {
                        ...d,
                        status: "error",
                        error: st.error || "Processing failed",
                      }
                    : d,
                ),
              );
            }
          } catch {
            // Transient — next tick retries.
          }
        }),
      );
    };

    void poll();
    const interval = setInterval(poll, 3_000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [hasProcessingUploads, setUploadedDocs]);

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
      (question?.sourceType as TrayItem["sourceType"] | undefined) ||
      (question?.metadata?.sourceType as TrayItem["sourceType"] | undefined) ||
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
    // Async upload: a PDF still uploading/ingesting is not yet in `uploadedDocs`
    // and would be silently excluded. Block with a toast until it's ready.
    const stillIngesting = uploadingDocs.find(
      (d) => d.status === "uploading" || d.status === "processing",
    );
    if (stillIngesting) {
      toast.error(
        `${stillIngesting.name} is still being processed. Wait for it to finish, then generate again.`,
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
      setSavedToBank(null);
      setPoolStatus("");
      setVariantSets([]);
      setActiveSet("A");
      clearComparisonSets();
      liveInsertedSectionsRef.current = new Set();

      let generationError: string | null = null;

      const isGIM = values.qpType === "general_instructions";
      // Multiple sets route through the results switcher rather than live
      // auto-insert: stacking three sets into the editor as they stream would
      // mix them. Set A is inserted from the switcher just like B and C.
      const isMultiSet = values.numberOfSets !== "1";
      setMultiSetMode(isMultiSet);

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
          instructions: isGIM ? generalInstructions || "" : "",
          board: isGIM ? "" : values.board,
          subject: values.subject,
          class: values.academicClass,
          qp_type: values.qpType,
          mathLevel: values.mathLevel,
          include_vi_alternatives: false,
          contentScopePolicy: values.contentScopePolicy,
          sets: parseInt(values.numberOfSets, 10),
          // The structure the teacher just reviewed in the panel. Sending it
          // means the paper they approved is the paper they get — and saves a
          // second design call. Omitted outside General Instructions Mode,
          // where the blueprint decides the structure.
          ...(isGIM && paperDesign.design?.sections.length
            ? { design: paperDesign.design, marks: values.marks }
            : {}),
        },
        (event, data) => {
          if (event === "error") {
            generationError = data.error || "Generation failed";
            // Backend is the authoritative readiness gate. If it reports
            // DOCUMENTS_NOT_READY, reconcile the local UI to match: drop any
            // vanished sources and re-queue the not-ready ones for polling so
            // the button re-gates and the source flips back to ready on its own.
            if (data.code === "DOCUMENTS_NOT_READY") {
              const pending: Array<{
                id: string;
                name?: string | null;
                kind?: string;
                reason?: string;
              }> = Array.isArray(data.pendingDocuments)
                ? data.pendingDocuments
                : [];
              const pdfPending = pending.filter((p) => p.kind === "pdf");
              const dropIds = new Set(
                pdfPending
                  .filter((p) => p.reason === "not_found")
                  .map((p) => p.id),
              );
              const requeueIds = new Set(
                pdfPending
                  .filter((p) => p.reason !== "not_found")
                  .map((p) => p.id),
              );
              if (dropIds.size > 0 || requeueIds.size > 0) {
                setUploadedDocs((prev) =>
                  prev.filter(
                    (d) => !dropIds.has(d.id) && !requeueIds.has(d.id),
                  ),
                );
              }
              if (requeueIds.size > 0) {
                setUploadingDocs((prev) => {
                  const known = new Set(
                    prev.map((d) => d.pdfSourceId).filter(Boolean),
                  );
                  const requeued: UploadingDoc[] = pdfPending
                    .filter((p) => requeueIds.has(p.id) && !known.has(p.id))
                    .map((p) => ({
                      tempId: `requeue-${p.id}`,
                      name: p.name || "Document",
                      status: "processing",
                      pdfSourceId: p.id,
                    }));
                  return requeued.length > 0 ? [...prev, ...requeued] : prev;
                });
              }
            }
          } else if (event === "status") {
            // Model 1 reads the whole chapter before any question exists, so
            // without progress the panel would sit silent for 30-60s.
            if (data.stage === "pool_progress") {
              // No counter: the pool deliberately over-generates (a paper of
              // 38 draws from a pool of ~84), so "produced/target" both reads
              // wrong and can exceed the target (e.g. 83/78). Show a plain
              // in-progress message instead.
              setPoolStatus("Writing questions…");
            } else if (data.message) {
              setPoolStatus(data.message);
            }
          } else if (event === "pool") {
            setPoolStatus(
              `Question pool ready — ${data.total} questions across ` +
                `${Object.keys(data.byType || {}).length} types.`,
            );
          } else if (event === "saved") {
            setSavedToBank({
              saved: data.saved ?? 0,
              duplicatesSkipped: data.duplicatesSkipped ?? 0,
              projectName: data.projectName || "",
            });
          } else if (event === "notice") {
            if (data.message) toast.info(data.message);
          } else if (event === "warning") {
            if (data.message) toast.warning(data.message);
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
              !isMultiSet &&
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
            // Multi-set: build the Set A preview only; insertion happens from
            // the switcher so sets stay separate.
            if (isMultiSet) {
              // preview only
            } else if (insertionMode === "auto") {
              appendQuestionToEditor(data.section, data.question);
            } else {
              stageQuestionForReview(data.section, data.question);
            }
          } else if (event === "set") {
            // A derived set (B or C). Collect it for the switcher; Set A stays
            // in `generatedResult`.
            setVariantSets((prev) => [
              ...prev.filter((s) => s.label !== data.label),
              { label: data.label, result: data.result },
            ]);
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

  const handleAddToEditor = async (resultOverride?: any) => {
    // When a specific set is inserted from the switcher, `resultOverride` is
    // that set's result and the live-insert guard does not apply (multi-set
    // never live-inserts).
    const result = resultOverride ?? generatedResult;
    const setLabel: string | undefined = result?.meta?.setLabel;
    if (!result) return;
    if (!resultOverride && liveInsertedCount > 0) {
      toast.success(`${liveInsertedCount} generated question(s) already inserted into the editor.`);
      return;
    }

    const hasSections = result.sections && result.sections.length > 0;

    let allQuestions: any[] = [];
    if (hasSections) {
      const sections = result.sections.map((section: any) => {
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
          // Tag the first section's title with the set label so a document
          // holding a specific set is self-identifying once exported.
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
      if (setLabel) {
        // A "Set B" heading line so a stacked/exported document names its set.
        useEditorStore.getState().appendInstructions([`Set ${setLabel}`]);
      }
      useEditorStore.getState().appendSections(sections);
      // Bug 5: surface backend `meta.footerNotes` (curriculum-fallback
      // disclosure) as instruction lines at the bottom of the doc so the
      // teacher and the rendered PDF both show which questions came from
      // curriculum knowledge instead of the uploaded sources.
      const footerNotes: string[] = Array.isArray(result?.meta?.footerNotes)
        ? result.meta.footerNotes
        : [];
      if (footerNotes.length > 0) {
        useEditorStore.getState().appendInstructions(footerNotes);
      }
      toast.success(
        setLabel
          ? `Inserted Set ${setLabel} into the editor.`
          : "Inserted generated sections into the editor.",
      );
    } else {
      (result.questions || []).forEach((q: any) => {
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

    // Saving used to happen here, gated behind a checkbox, and only covered
    // the questions this paper used. The backend now persists the entire
    // pool during generation, so inserting into the editor is purely an
    // editor action.
  };

  const hasAnyDocs =
    uploadedDocs.length > 0 ||
    uploadingDocs.length > 0 ||
    hsatSources.length > 0;

  // All produced sets in order: Set A (the master, in `generatedResult`)
  // followed by the derived sets. Drives the multi-set switcher; empty of
  // variants means the single-set UI shows instead.
  const allSets = useMemo(
    () =>
      generatedResult
        ? [{ label: "A", result: generatedResult }, ...variantSets]
        : [],
    [generatedResult, variantSets],
  );
  // Mirror the produced sets into the store so the Comparison Workspace (a
  // full-screen overlay mounted by the editor page) can read them. Only while
  // multi-set — the single-set path keeps the review tray / auto-insert UI.
  useEffect(() => {
    if (multiSetMode && allSets.length >= 2) {
      setComparisonSets(allSets.map((s) => ({ label: s.label, result: s.result })));
    }
  }, [multiSetMode, allSets, setComparisonSets]);

  return (
    <div className="h-full flex flex-col p-4 bg-background text-muted-foreground overflow-y-auto custom-scrollbar">
      <div className="mb-6">
        <h2 className="text-lg font-bold text-foreground mb-1">
          Question Generator
        </h2>
        
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
              className="h-7 text-xs text-primary dark:text-primary hover:text-primary dark:hover:text-primary hover:bg-primary/10 dark:hover:bg-primary/10"
            >
              <Plus className="h-3 w-3 mr-1" />
              Add Source
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setIsHsatPickerOpen(true)}
              className="h-7 text-xs text-primary dark:text-primary hover:text-primary dark:hover:text-primary hover:bg-primary/10 dark:hover:bg-primary/10"
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
                  {doc.status !== "error" ? (
                    <Loader2 className="h-4 w-4 text-primary animate-spin flex-shrink-0" />
                  ) : (
                    <AlertCircle className="h-4 w-4 text-red-400 flex-shrink-0" />
                  )}
                  <div className="min-w-0">
                    <span className="text-xs text-foreground truncate block">
                      {doc.name}
                    </span>
                    {doc.status === "uploading" && (
                      <span className="text-[10px] text-primary dark:text-primary">
                        Uploading…
                      </span>
                    )}
                    {doc.status === "processing" && (
                      <span className="text-[10px] text-primary dark:text-primary">
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
              {doc.status !== "error" && (
                <div className="mt-1 h-0.5 w-full rounded-full bg-muted-foreground/30 overflow-hidden">
                  <div
                    className="h-full bg-primary rounded-full animate-[loading-bar_1.4s_ease-in-out_infinite]"
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
                <div className="min-w-0">
                  <span className="text-xs text-foreground truncate block">
                    {doc.name}
                  </span>
                  {analysisProgressMap.get(doc.name) && (
                    <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-medium block">
                      {analysisProgressMap.get(doc.name)}
                    </span>
                  )}
                </div>
              </div>
              <button
                onClick={() => removeDoc(doc.id, doc.name)}
                className="opacity-0 group-hover:opacity-100 p-1 hover:text-red-400 transition-opacity"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))}

          {/* Multi-PDF Validation Error Card */}
          {validationReport && !validationReport.valid && (
            <div className="p-3 rounded-lg border border-red-300 dark:border-red-800 bg-red-50 dark:bg-red-950/40 text-red-900 dark:text-red-200 space-y-2">
              <div className="flex items-center gap-1.5 font-semibold text-xs text-red-700 dark:text-red-400">
                <AlertCircle className="h-4 w-4 shrink-0 text-red-500" />
                {validationReport.message || "PDF Metadata Validation Error"}
              </div>
              {validationReport.mismatches && validationReport.mismatches.length > 0 && (
                <div className="space-y-1 text-xs border-t border-red-200 dark:border-red-800/60 pt-2">
                  {validationReport.mismatches.map((m, idx) => (
                    <div key={idx} className="flex justify-between items-center text-[11px]">
                      <span className="font-medium truncate max-w-[180px]">{m.file || `PDF ${idx + 1}`}</span>
                      <span className="bg-red-100 dark:bg-red-900/60 text-red-800 dark:text-red-300 px-1.5 py-0.5 rounded font-mono text-[10px]">
                        {m.subject || m.chapter || m.board || m.class || m.reason || "Mismatch"}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Applied HSAT sources — visually distinct: book icon + HSAT label */}
          {hsatSources.map((source) => {
            const isPreparing =
              source.status === "processing" || source.status === "pending";
            const isError = source.status === "error";
            return (
              <div
                key={source.id}
                className="flex items-center justify-between p-2 rounded-lg bg-primary/40 dark:bg-primary/20 border border-primary/30 dark:border-primary/40 group"
              >
                <div className="flex items-center gap-2 min-w-0">
                  {isPreparing ? (
                    <Loader2 className="h-4 w-4 text-primary animate-spin flex-shrink-0" />
                  ) : isError ? (
                    <AlertCircle className="h-4 w-4 text-red-500 flex-shrink-0" />
                  ) : (
                    <BookOpen className="h-4 w-4 text-primary flex-shrink-0" />
                  )}
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-[10px] font-semibold uppercase tracking-wide text-primary dark:text-primary">
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
                <Select
                  value={field.value}
                  onValueChange={field.onChange}
                  disabled={!!detectedSubject}
                >
                  <FormControl>
                    <SelectTrigger className="w-full bg-background border-border text-foreground">
                      <SelectValue placeholder="Select" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent alignItemWithTrigger={false} className="bg-background border-border text-foreground">
                    {detectedSubject ? (
                      <SelectItem value={detectedSubject}>{detectedSubject}</SelectItem>
                    ) : (
                      ALL_SUBJECT_OPTIONS.map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>
                          {opt.label}
                        </SelectItem>
                      ))
                    )}
                  </SelectContent>
                </Select>
                {detectedSubject && (
                  <p className="text-[11px] font-medium text-emerald-600 dark:text-emerald-400 mt-1 flex items-center gap-1">
                    ✓ Subject detected: {detectedSubject}
                  </p>
                )}
                {isDetectingSubject && (
                  <p className="text-[11px] text-primary dark:text-primary mt-1 flex items-center gap-1 animate-pulse">
                    <Loader2 className="h-3 w-3 animate-spin inline" /> Analyzing PDF subject…
                  </p>
                )}
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

          {/* Number of Sets — the pool is generated once; Sets B/C are derived
              from Set A by swapping in alternative questions from the pool. */}
          <FormField
            control={form.control}
            name="numberOfSets"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-foreground">
                  Number of Sets
                </FormLabel>
                <Select value={field.value} onValueChange={field.onChange}>
                  <FormControl>
                    <SelectTrigger className="w-full bg-background border-border text-foreground">
                      <SelectValue placeholder="Select" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent alignItemWithTrigger={false} className="bg-background border-border text-foreground min-w-[var(--radix-select-trigger-width)]">
                    <SelectItem value="1">1 Set (default)</SelectItem>
                    <SelectItem value="2">2 Sets (A, B)</SelectItem>
                    <SelectItem value="3">3 Sets (A, B, C)</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-[10px] text-zinc-400 dark:text-muted-foreground mt-1 leading-snug">
                  {field.value === "1"
                    ? "A single paper (Set A)."
                    : `Set A plus ${field.value === "2" ? "one variant (Set B)" : "two variants (Sets B & C)"}. Each variant keeps ~70% of Set A, swaps ~30% for parallel questions from the same pool, and reshuffles within sections. MCQs stay the same across all sets.`}
                </p>
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

          
          <FormField
            control={form.control}
            name="contentScopePolicy"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-foreground">
                  Generation Strictness
                </FormLabel>
                <Select value={field.value} onValueChange={field.onChange}>
                  <FormControl>
                    <SelectTrigger className="w-full bg-background border-border text-foreground">
                      <SelectValue placeholder="Select strictness" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent alignItemWithTrigger={false} className="bg-background border-border text-foreground min-w-[var(--radix-select-trigger-width)]">
                    <SelectItem value="strict">Standard Default (Allows Curriculum Fallback)</SelectItem>
                    <SelectItem value="source_only">Strict to Source Material (Source Only)</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-[10px] text-zinc-400 dark:text-muted-foreground mt-1 leading-snug">
                  {field.value === "strict" 
                    ? "If uploaded chapters lack coverage for certain blueprint topics, the AI will generate those questions from general CBSE curriculum knowledge."
                    : "Questions are generated STRICTLY from your source material. Blueprint slots missing from your PDF will be skipped, which may result in a shorter paper."}
                </p>
                <FormMessage />
              </FormItem>
            )}
          />

          {/* Your Instructions — shown ONLY in General Instructions Mode */}
          {currentQpType === "general_instructions" && (
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <label className="text-sm font-medium text-foreground">
                  Your Instructions <span className="text-red-500">*</span>
                </label>
                <TemplatePicker
                  instructions={generalInstructions}
                  settings={designSettings}
                  onApply={applyTemplate}
                />
              </div>
              <Textarea
                placeholder={
                  "Describe the paper in your own words.\n" +
                  "Example: Weekly test on Light, 20 marks — 5 MCQs, " +
                  "3 short answers of 2 marks, 1 long answer of 5."
                }
                className="bg-background border-border text-foreground placeholder:text-zinc-400 dark:placeholder:text-zinc-600 text-sm resize-none focus:ring-primary min-h-[120px] border-primary/30 dark:border-primary ring-1 ring-primary/40 dark:ring-primary/50"
                value={generalInstructions}
                onChange={(e) => setGeneralInstructions(e.target.value)}
              />
              <p className="text-[11px] text-zinc-400 dark:text-muted-foreground">
                Written in plain words. The paper follows these instructions —
                no board pattern, no Bloom&apos;s targets.
              </p>

              {/* What the instructions actually describe, and what they left
                  open — before spending three minutes finding out. */}
              <PaperDesignPanel
                design={paperDesign.design}
                gaps={paperDesign.gaps}
                loading={paperDesign.loading}
                onResolve={resolveDesignGap}
                sourceAction={
                  <p className="mt-1.5 text-[11px] text-muted-foreground">
                    Use “Add Source” above to upload a PDF or apply a textbook
                    chapter.
                  </p>
                }
              />
              {paperDesign.error && (
                <p className="text-[11px] text-amber-600 dark:text-amber-400">
                  {paperDesign.error} You can still generate — the preview is
                  just unavailable.
                </p>
              )}
            </div>
          )}

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
                (uploadedDocs.length === 0 && hsatSources.length === 0) ||
                (validationReport !== null && !validationReport.valid)
              }
              className="w-full bg-primary hover:bg-primary/90 text-white shadow-lg gap-2"
            >
              {isGenerating
                ? "Analyzing & Generating..."
                : "Generate Questions"}
            </Button>

            {/* Model 1 reads the entire chapter before the first question
                exists, so this is the only feedback during that window. */}
            {isGenerating && poolStatus && (
              <p className="mt-2 text-xs text-center text-muted-foreground flex items-center justify-center gap-1.5">
                <Loader2 className="h-3 w-3 animate-spin" />
                {poolStatus}
              </p>
            )}
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
                ? "border-primary bg-primary/10 dark:bg-primary/10 text-primary dark:text-primary font-medium"
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
                ? "border-primary bg-primary/10 dark:bg-primary/10 text-primary dark:text-primary font-medium"
                : "border-border text-muted-foreground hover:border-zinc-400"
            }`}
          >
            Auto-insert all
          </button>
        </div>
      </div>

      {/* Review tray — pending generated questions awaiting the teacher's call.
          Suppressed for multi-set: those route through the set switcher. */}
      {insertionMode === "review" && !multiSetMode && <ReviewTray />}

      {generatedResult && insertionMode === "auto" && !multiSetMode && (
        <div className="mt-6 border-t border-border pt-6 animate-in fade-in duration-500">
          <h3 className="text-lg font-bold text-foreground mb-4 flex items-center gap-2">
            Generated Output
          </h3>

          <div className="space-y-6">
            {generatedResult.sections?.map((section: any, sIdx: number) => (
              <div key={sIdx} className="space-y-4">
                <h4 className="text-sm font-semibold text-primary dark:text-primary uppercase tracking-wider">
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
                {savedToBank && savedToBank.saved > 0 && (
                  <div className="flex items-start gap-2 p-3 mb-2 bg-emerald-50 dark:bg-emerald-900/20 rounded-lg border border-emerald-100 dark:border-emerald-800/30">
                    <CheckCircle2 className="h-4 w-4 mt-0.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
                    <div className="text-sm text-emerald-900 dark:text-emerald-200">
                      <p className="font-medium">
                        {savedToBank.saved} question
                        {savedToBank.saved === 1 ? "" : "s"} saved to your
                        question bank
                      </p>
                      <p className="text-xs opacity-80 mt-0.5">
                        {savedToBank.projectName}
                        {savedToBank.duplicatesSkipped > 0 &&
                          ` · ${savedToBank.duplicatesSkipped} already saved`}
                      </p>
                    </div>
                  </div>
                )}
                <Button
                  className="w-full bg-primary text-white hover:bg-primary/90 font-semibold"
                  onClick={() => handleAddToEditor()}
                  disabled={liveInsertedCount > 0}
                >
                  {liveInsertedCount > 0
                    ? `Inserted ${liveInsertedCount} into Editor`
                    : "Insert All into Editor"}
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

      {/* ── Multiple-set result → Comparison Workspace entry point ────────
          The old inline set switcher (which could only insert a whole set and
          contaminated the doc when inserting a second set) is replaced by the
          Comparison Workspace: sets side by side with per-question / per-section
          / per-set insertion that no longer collides. */}
      {((multiSetMode && generatedResult) || (comparisonSets && comparisonSets.length > 1)) && (
        <div className="mt-6 border-t border-border pt-6 animate-in fade-in duration-500">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-lg font-bold text-foreground">Generated Sets</h3>
            <span className="text-[11px] text-muted-foreground">
              {allSets.length > 0 ? allSets.length : comparisonSets.length} sets
            </span>
          </div>

          {savedToBank && savedToBank.saved > 0 && (
            <div className="flex items-start gap-2 p-3 mb-3 bg-emerald-50 dark:bg-emerald-900/20 rounded-lg border border-emerald-100 dark:border-emerald-800/30">
              <CheckCircle2 className="h-4 w-4 mt-0.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
              <div className="text-sm text-emerald-900 dark:text-emerald-200">
                <p className="font-medium">
                  {savedToBank.saved} question{savedToBank.saved === 1 ? "" : "s"}{" "}
                  saved to your question bank
                </p>
                <p className="text-xs opacity-80 mt-0.5">
                  {savedToBank.projectName}
                </p>
              </div>
            </div>
          )}

          <p className="text-[11px] text-muted-foreground mb-3 leading-snug">
            Review Sets {allSets.map((s) => s.label).join(", ")} side by side —
            aligned by section and marks, with changed questions highlighted.
            Edit, delete or replace any single question, then approve: each set
            goes straight into its own tab in the editor.
          </p>

          <div className="flex flex-col gap-2">
            {!isGenerating && (
              <>
                <Button
                  className="w-full bg-primary text-white hover:bg-primary/90 font-semibold"
                  onClick={() => setComparisonOpen(true)}
                  disabled={allSets.length > 0 ? allSets.length < 2 : comparisonSets.length < 2}
                >
                  Review &amp; approve sets
                </Button>
                <Button
                  variant="ghost"
                  className="w-full text-zinc-400 dark:text-muted-foreground hover:text-zinc-600 dark:hover:text-zinc-300"
                  onClick={() => {
                    setGeneratedResult(null);
                    setVariantSets([]);
                    setActiveSet("A");
                    setMultiSetMode(false);
                    clearComparisonSets();
                  }}
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
