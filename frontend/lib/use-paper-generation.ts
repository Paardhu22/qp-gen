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

import { resumeSseRun, streamSse, type SseRunPosition } from "@/lib/api-client";
import { useEditorStore, type TrayItem } from "@/store/editor-store";

/**
 * Where the last generation had got to, remembered across a page reload.
 *
 * A generation runs for minutes on the server whether or not anyone is
 * watching (see services/generation_runs.py). What a reload destroys is not
 * the work — it is this client's knowledge of which run to go back to. One
 * localStorage key fixes that; without it a teacher who refreshed mid-paper
 * had no way to reach a generation that was still perfectly alive.
 */
const RESUME_KEY = "qp-gen:last-generation-run";

/** A run older than this is not worth offering — it has almost certainly ended. */
const RESUME_MAX_AGE_MS = 30 * 60 * 1000;

type StoredRun = SseRunPosition & { startedAt: number };

function rememberRun(position: SseRunPosition) {
  try {
    const existing = readRememberedRun();
    const stored: StoredRun = {
      ...position,
      // The clock runs from when the run started, not from the last frame:
      // the question is "is this generation still plausibly alive", and a long
      // quiet stretch mid-generation is entirely normal.
      startedAt:
        existing && existing.runId === position.runId
          ? existing.startedAt
          : Date.now(),
    };
    window.localStorage.setItem(RESUME_KEY, JSON.stringify(stored));
  } catch {
    // Private browsing, or a full quota. Losing the ability to resume is not
    // worth failing a generation over.
  }
}

function readRememberedRun(): StoredRun | null {
  try {
    const raw = window.localStorage.getItem(RESUME_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredRun;
    if (!parsed?.runId) return null;
    if (Date.now() - (parsed.startedAt || 0) > RESUME_MAX_AGE_MS) return null;
    return parsed;
  } catch {
    return null;
  }
}

function forgetRun() {
  try {
    window.localStorage.removeItem(RESUME_KEY);
  } catch {
    // See `rememberRun`.
  }
}

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
  /**
   * The blueprint's own slot count, from the `plan` event — the one number in
   * this stream that is an actual target rather than a pool size (see the
   * file comment on why `pool_progress`'s `produced`/`target` are not this).
   * 0 until the plan event lands, which a progress bar reads as "unknown yet".
   */
  plannedTotal: number;
  /** Questions streamed so far, counted the moment each arrives — unlike
   *  `liveInsertedCount`, this advances in review mode too, since it tracks
   *  what the model has written, not what has landed in the document. */
  generatedCount: number;
  /** The most recent question to stream in, for a live "just written" line. */
  lastQuestion: { section: string; type: string; marks: number } | null;
}

const INITIAL: GenerationState = {
  isGenerating: false,
  result: null,
  variantSets: [],
  poolStatus: "",
  savedToBank: null,
  liveInsertedCount: 0,
  multiSetMode: false,
  plannedTotal: 0,
  generatedCount: 0,
  lastQuestion: null,
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

/**
 * The SSE event handler, as one definition used by both paths.
 *
 * There are two ways into a generation now — starting one, and re-attaching to
 * one the connection dropped — and they must interpret the stream identically.
 * Two copies of this is precisely the bug the hook itself exists to prevent
 * (see the file comment): an event handled in one and not the other is broken
 * only for the teacher unlucky enough to have lost their connection.
 */
function makeStreamHandler(deps: {
  isMultiSet: boolean;
  setState: React.Dispatch<React.SetStateAction<GenerationState>>;
  insertedSections: React.MutableRefObject<Set<string>>;
  onSourcesNotReady?: UsePaperGenerationOptions["onSourcesNotReady"];
  onError: (message: string) => void;
}) {
  const isMultiSet = deps.isMultiSet;

  const appendToEditor = (sectionTitle: string, question: any) => {
    const editorQuestion = toEditorQuestion(question);
    if (!deps.insertedSections.current.has(sectionTitle)) {
      deps.insertedSections.current.add(sectionTitle);
      useEditorStore
        .getState()
        .appendSections([{ title: sectionTitle, questions: [editorQuestion] }]);
    } else {
      useEditorStore.getState().appendQuestions([editorQuestion]);
    }
    deps.setState((s) => ({ ...s, liveInsertedCount: s.liveInsertedCount + 1 }));
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
      },
    });
  };

  return (event: string, data: any) => {
    if (event === "error") {
      deps.onError(data.error || "Generation failed");
      if (data.code === "DOCUMENTS_NOT_READY") {
        const pending: any[] = Array.isArray(data.pendingDocuments)
          ? data.pendingDocuments
          : [];
        const pdfPending = pending.filter((p) => p.kind === "pdf");
        deps.onSourcesNotReady?.({
          drop: pdfPending
            .filter((p) => p.reason === "not_found")
            .map((p) => p.id),
          requeue: pdfPending
            .filter((p) => p.reason !== "not_found")
            .map((p) => ({ id: p.id, name: p.name || "Document" })),
        });
      }
    } else if (event === "status") {
      deps.setState((s) => ({
        ...s,
        poolStatus:
          data.stage === "pool_progress"
            ? "Writing questions…"
            : data.message || s.poolStatus,
      }));
    } else if (event === "pool") {
      deps.setState((s) => ({
        ...s,
        poolStatus: `Questions ready — ${data.total} across ${
          Object.keys(data.byType || {}).length
        } types.`,
      }));
    } else if (event === "saved") {
      deps.setState((s) => ({
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
      deps.setState((s) => ({
        ...s,
        result: { sections: [], generalInstructions },
        plannedTotal:
          typeof data.total === "number" ? data.total : s.plannedTotal,
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
      deps.setState((s) => ({
        ...s,
        result: appendQuestionToResult(s.result, data.section, data.question),
        generatedCount: s.generatedCount + 1,
        lastQuestion: {
          section: data.section || "",
          type: data.question?.type || "",
          marks: data.question?.marks || 0,
        },
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
      deps.setState((s) => ({
        ...s,
        variantSets: [
          ...s.variantSets.filter((v) => v.label !== data.label),
          { label: data.label, result: data.result },
        ],
      }));
    } else if (event === "update" || event === "message") {
      deps.setState((s) => ({ ...s, result: data }));
    } else if (event === "done" && data.result) {
      deps.setState((s) => ({ ...s, result: data.result }));
    }
  };
}

export function usePaperGeneration(options: UsePaperGenerationOptions = {}) {
  const [state, setState] = React.useState<GenerationState>(INITIAL);
  /**
   * A generation this browser started and lost sight of — a reload, a closed
   * tab, a phone that slept. Null on the overwhelming majority of mounts.
   */
  const [resumableRun, setResumableRun] = React.useState<StoredRun | null>(null);

  // Read once on mount rather than during render: localStorage is not
  // available while the page is being prerendered on the server.
  React.useEffect(() => {
    setResumableRun(readRememberedRun());
  }, []);

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

  const makeHandler = React.useCallback(
    (isMultiSet: boolean, onError: (message: string) => void) =>
      makeStreamHandler({
        isMultiSet,
        setState,
        insertedSections: insertedSectionsRef,
        onSourcesNotReady: onSourcesNotReadyRef.current,
        onError,
      }),
    [],
  );

  /** Common setup for both starting a generation and re-attaching to one. */
  const beginRun = React.useCallback((isMultiSet: boolean) => {
    insertedSectionsRef.current = new Set();
    useEditorStore.getState().clearComparisonSets();
    setState({ ...INITIAL, isGenerating: true, multiSetMode: isMultiSet });
  }, []);

  const generate = React.useCallback(
    async (request: GenerationRequest) => {
      const isMultiSet = request.numberOfSets !== "1";
      beginRun(isMultiSet);

      let generationError: string | null = null;

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
              // -1 = "the blueprint decides how many questions". The Builder always
              // has a structure, so there is never a free-standing count to send.
              // Sent explicitly rather than left to the serializer's default so the
              // intent is on the wire and readable in a request log.
              count: -1,
              sets: parseInt(request.numberOfSets, 10),
              mathLevel: request.mathLevel || "standard",
              instructions: request.instructions || "",
              // The reviewed structure. The backend resolves the template into
              // slots; sending the edited blueprint means the paper the teacher
              // approved in the Builder is the paper they get, with no second
              // design call and no chance of a different structure coming back.
              ...(request.blueprint?.slots?.length
                ? { blueprint: request.blueprint, templateId: request.templateId }
                : {}),
            },
          makeHandler(isMultiSet, (message) => {
            generationError = message;
          }),
          {
            // Remembered so a reload — or a connection that gives out for
            // longer than the automatic re-attach covers — can pick this run
            // back up instead of losing a paper that is still being produced.
            onRunPosition: (position) => {
              rememberRun(position);
              setResumableRun(null);
            },
          },
        );

        // Finished one way or the other, so there is nothing to offer resuming.
        forgetRun();
        if (generationError) toast.error(generationError);
        return { ok: !generationError };
      } catch (error: any) {
        console.error("Generation failed:", error);
        toast.error(
          error?.message ||
            "Failed to generate questions. Check whether your sources contain relevant content.",
        );
        // Deliberately NOT forgotten: a transport failure is exactly the case
        // where the run is still alive on the server and worth going back for.
        setResumableRun(readRememberedRun());
        return { ok: false };
      } finally {
        setState((s) => ({ ...s, isGenerating: false }));
      }
    },
    [beginRun, makeHandler],
  );

  /**
   * Pick a generation back up — after a reload, or after the connection gave
   * out for good. Replays everything recorded past our cursor and then follows
   * the rest live, so the paper arrives whole rather than half-written.
   */
  const resume = React.useCallback(async () => {
    const stored = readRememberedRun();
    if (!stored) return { ok: false };

    beginRun(false);
    let generationError: string | null = null;

    try {
      await resumeSseRun(
        stored.runId,
        stored.cursor,
        makeHandler(false, (message) => {
          generationError = message;
        }),
        { onRunPosition: rememberRun },
      );
      forgetRun();
      setResumableRun(null);
      if (generationError) toast.error(generationError);
      return { ok: !generationError };
    } catch (error: any) {
      toast.error(error?.message || "That generation could not be reopened.");
      return { ok: false };
    } finally {
      setState((s) => ({ ...s, isGenerating: false }));
    }
  }, [beginRun, makeHandler]);

  const dismissResumable = React.useCallback(() => {
    forgetRun();
    setResumableRun(null);
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

  return {
    ...state,
    allSets,
    generate,
    reset,
    /** A generation this browser started and lost sight of, or null. */
    resumableRun,
    resume,
    dismissResumable,
  };
}
