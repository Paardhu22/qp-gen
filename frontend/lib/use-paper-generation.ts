"use client";

/**
 * Running a generation, extracted from the surface that starts it.
 *
 * This logic lived inside `generator-form.tsx`, which meant the SSE contract
 * was implemented inside a 1,865-line form component — and re-implemented,
 * near-identically, in the dashboard. Two copies of a hard interface is one
 * copy too many: a new event handled in one place and not the other is a bug
 * nobody notices until a teacher hits it.
 *
 * The hook owns the stream and the produced sets. It deliberately does NOT own:
 *
 *   * **sources** — an in-flight upload has to survive the modal closing, so
 *     the page owns uploads and passes ids in; and
 *   * **what happens to a question** — auto-insert vs. review-tray staging is
 *     an editor concern read from the store at call time, not a parameter,
 *     because the teacher can flip it mid-stream.
 *
 * ## Progress is a message, never a count
 *
 * The `pool_progress` event carries `produced` and `target`, and showing them
 * was actively misleading: the pool over-generates, so "83/78" happened
 * routinely. It now renders as plain prose. That reasoning survives the move
 * to exact generation — a count that can exceed its own target has taught
 * teachers not to trust the number.
 */

import * as React from "react";
import { toast } from "sonner";

import { streamSse } from "@/lib/api-client";
import { useEditorStore, type TrayItem } from "@/store/editor-store";

export interface GenerationRequest {
  pdfSourceIds: string[];
  hsatSourceIds: string[];
  subject: string;
  academicClass: string;
  board: string;
  difficulty: string;
  numberOfSets: string;
  /** Mathematics only — `resolve_maths_basic` reads it; ignored elsewhere. */
  mathLevel?: string;
  instructions?: string;
  /** The reviewed blueprint. Sending it means the paper approved is the paper produced. */
  blueprint?: { slots: unknown[] };
  templateId?: string;
}

export interface ProducedSet {
  label: string;
  result: any;
}

export interface GenerationState {
  isGenerating: boolean;
  result: any;
  variantSets: ProducedSet[];
  poolStatus: string;
  savedToBank: {
    saved: number;
    duplicatesSkipped: number;
    projectName: string;
  } | null;
  liveInsertedCount: number;
  multiSetMode: boolean;
}

const INITIAL: GenerationState = {
  isGenerating: false,
  result: null,
  variantSets: [],
  poolStatus: "",
  savedToBank: null,
  liveInsertedCount: 0,
  multiSetMode: false,
};

/** Merge one streamed question into the accumulating preview. */
function appendQuestionToResult(
  current: any,
  sectionTitle: string,
  question: any,
) {
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
}

function toEditorQuestion(question: any) {
  return {
    content: question.content,
    type: question.type,
    options: question.options || [],
    answer: question.answer,
    marks: question.marks,
    image_url: question.image_url || question.metadata?.image_url || "",
  };
}

export interface UsePaperGenerationOptions {
  /**
   * Reconcile local source state when the backend's readiness gate rejects a
   * source. The hook does not own uploads, so it reports rather than repairs.
   */
  onSourcesNotReady?: (pending: {
    drop: string[];
    requeue: { id: string; name: string }[];
  }) => void;
}

export function usePaperGeneration(options: UsePaperGenerationOptions = {}) {
  const [state, setState] = React.useState<GenerationState>(INITIAL);

  // Sections already opened by live insertion. A ref, not state: it is read
  // and written inside the stream callback, where a stale closure over state
  // would re-open a section for every question in it.
  const insertedSectionsRef = React.useRef<Set<string>>(new Set());

  // Kept in a ref so the callback can read the latest without the stream being
  // torn down and rebuilt when the option identity changes.
  const onSourcesNotReadyRef = React.useRef(options.onSourcesNotReady);
  React.useEffect(() => {
    onSourcesNotReadyRef.current = options.onSourcesNotReady;
  }, [options.onSourcesNotReady]);

  const reset = React.useCallback(() => {
    insertedSectionsRef.current = new Set();
    setState(INITIAL);
  }, []);

  const generate = React.useCallback(async (request: GenerationRequest) => {
    const store = useEditorStore.getState();
    const isMultiSet = request.numberOfSets !== "1";

    insertedSectionsRef.current = new Set();
    store.clearComparisonSets();
    setState({ ...INITIAL, isGenerating: true, multiSetMode: isMultiSet });

    let generationError: string | null = null;

    const appendToEditor = (sectionTitle: string, question: any) => {
      const editorQuestion = toEditorQuestion(question);
      if (!insertedSectionsRef.current.has(sectionTitle)) {
        insertedSectionsRef.current.add(sectionTitle);
        useEditorStore
          .getState()
          .appendSections([{ title: sectionTitle, questions: [editorQuestion] }]);
      } else {
        useEditorStore.getState().appendQuestions([editorQuestion]);
      }
      setState((s) => ({ ...s, liveInsertedCount: s.liveInsertedCount + 1 }));
    };

    const stageForReview = (sectionTitle: string, question: any) => {
      useEditorStore.getState().pushToTray({
        sectionTitle,
        sourceType:
          (question?.sourceType as TrayItem["sourceType"] | undefined) ||
          (question?.metadata?.sourceType as TrayItem["sourceType"] | undefined) ||
          "unknown",
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

    try {
      await streamSse(
        "/api/generation/questions/stream",
        {
          pdfSourceIds: request.pdfSourceIds,
          hsatSourceIds: request.hsatSourceIds,
          subject: request.subject,
          class: request.academicClass,
          board: request.board,
          difficulty: request.difficulty,
          sets: parseInt(request.numberOfSets, 10),
          mathLevel: request.mathLevel || "standard",
          instructions: request.instructions || "",
          include_vi_alternatives: false,
          // The reviewed structure. The backend resolves the template into
          // slots; sending the edited blueprint means the paper the teacher
          // approved in the Builder is the paper they get, with no second
          // design call and no chance of a different structure coming back.
          ...(request.blueprint?.slots?.length
            ? { blueprint: request.blueprint, templateId: request.templateId }
            : {}),
        },
        (event, data) => {
          if (event === "error") {
            generationError = data.error || "Generation failed";
            if (data.code === "DOCUMENTS_NOT_READY") {
              const pending: any[] = Array.isArray(data.pendingDocuments)
                ? data.pendingDocuments
                : [];
              const pdfPending = pending.filter((p) => p.kind === "pdf");
              onSourcesNotReadyRef.current?.({
                drop: pdfPending
                  .filter((p) => p.reason === "not_found")
                  .map((p) => p.id),
                requeue: pdfPending
                  .filter((p) => p.reason !== "not_found")
                  .map((p) => ({ id: p.id, name: p.name || "Document" })),
              });
            }
          } else if (event === "status") {
            setState((s) => ({
              ...s,
              poolStatus:
                data.stage === "pool_progress"
                  ? "Writing questions…"
                  : data.message || s.poolStatus,
            }));
          } else if (event === "pool") {
            setState((s) => ({
              ...s,
              poolStatus: `Questions ready — ${data.total} across ${
                Object.keys(data.byType || {}).length
              } types.`,
            }));
          } else if (event === "saved") {
            setState((s) => ({
              ...s,
              savedToBank: {
                saved: data.saved ?? 0,
                duplicatesSkipped: data.duplicatesSkipped ?? 0,
                projectName: data.projectName || "",
              },
            }));
          } else if (event === "notice") {
            if (data.message) toast.info(data.message);
          } else if (event === "warning") {
            if (data.message) toast.warning(data.message);
          } else if (event === "plan") {
            const generalInstructions = data.generalInstructions || [];
            setState((s) => ({
              ...s,
              result: { sections: [], generalInstructions },
            }));
            // Only auto-insert the instruction block when auto-insert is on.
            // In review mode the editor rebuilds instructions from what was
            // actually inserted, so a planned 38-question header above a
            // 0-question paper would be a lie.
            if (
              !isMultiSet &&
              useEditorStore.getState().insertionMode === "auto" &&
              Array.isArray(generalInstructions) &&
              generalInstructions.length > 0
            ) {
              useEditorStore.getState().appendInstructions(generalInstructions);
            }
          } else if (event === "question") {
            setState((s) => ({
              ...s,
              result: appendQuestionToResult(s.result, data.section, data.question),
            }));
            if (isMultiSet) {
              // Preview only — sets are inserted from the comparison view so
              // two of them can never merge into one document.
            } else if (useEditorStore.getState().insertionMode === "auto") {
              appendToEditor(data.section, data.question);
            } else {
              stageForReview(data.section, data.question);
            }
          } else if (event === "set") {
            setState((s) => ({
              ...s,
              variantSets: [
                ...s.variantSets.filter((v) => v.label !== data.label),
                { label: data.label, result: data.result },
              ],
            }));
          } else if (event === "update" || event === "message") {
            setState((s) => ({ ...s, result: data }));
          } else if (event === "done" && data.result) {
            setState((s) => ({ ...s, result: data.result }));
          }
        },
      );

      if (generationError) toast.error(generationError);
      return { ok: !generationError };
    } catch (error: any) {
      console.error("Generation failed:", error);
      toast.error(
        error?.message ||
          "Failed to generate questions. Check whether your sources contain relevant content.",
      );
      return { ok: false };
    } finally {
      setState((s) => ({ ...s, isGenerating: false }));
    }
  }, []);

  /** Set A plus every derived set, in order. Empty until something is produced. */
  const allSets = React.useMemo<ProducedSet[]>(
    () =>
      state.result
        ? [{ label: "A", result: state.result }, ...state.variantSets]
        : [],
    [state.result, state.variantSets],
  );

  // Mirror produced sets into the store so the Comparison Workspace (mounted
  // by the editor page, not here) can read them.
  const setComparisonSets = useEditorStore((s) => s.setComparisonSets);
  React.useEffect(() => {
    if (state.multiSetMode && allSets.length >= 2) {
      setComparisonSets(
        allSets.map((s) => ({ label: s.label, result: s.result })),
      );
    }
  }, [state.multiSetMode, allSets, setComparisonSets]);

  return { ...state, allSets, generate, reset };
}
