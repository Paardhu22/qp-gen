"use client";

/**
 * The editor's view of a generation.
 *
 * This used to own the run: it held the stream, the produced sets and the
 * progress in React state. That made the run a property of whichever component
 * happened to be mounted, so navigating away from the editor left a stream
 * still running with nothing watching it, and coming back showed an idle Paper
 * Studio over a generation that was still in flight.
 *
 * The run now lives in `lib/generation-runner.ts`, a module singleton that no
 * component owns. What is left here is the editor's *interpretation* of it:
 * where a question goes when it arrives (the page, or the review tray) and how
 * the produced sets reach the comparison workspace. The dashboard subscribes to
 * the same runner and interprets the same events completely differently, which
 * is exactly why the runner broadcasts instead of deciding.
 *
 * It deliberately does NOT own:
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
 * routinely. It renders as plain prose. That reasoning survives the move to
 * exact generation — a count that can exceed its own target has taught teachers
 * not to trust the number.
 */

import * as React from "react";
import { toast } from "sonner";

import { generationRunner } from "@/lib/generation-runner";
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
  /** The paper the run belongs to, so its questions cannot land in another. */
  paperId?: string | null;
}

export interface ProducedSet {
  label: string;
  result: any;
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
  // Progress comes from the store, so it is the same on every mount and
  // survives the page unmounting mid-run.
  const activeRun = useEditorStore((s) => s.activeRun);

  // The assembled paper lives in the runner (too big for localStorage), so it
  // is mirrored into React state to drive re-renders while a run streams.
  const [result, setResult] = React.useState<any>(() =>
    generationRunner.getResult(),
  );
  const [variantSets, setVariantSets] = React.useState<ProducedSet[]>(() =>
    generationRunner.getVariantSets(),
  );
  const [savedToBank, setSavedToBank] = React.useState<{
    saved: number;
    duplicatesSkipped: number;
    projectName: string;
  } | null>(null);

  // Sections already opened by live insertion. A ref, not state: it is read
  // and written inside the stream callback, where a stale closure over state
  // would re-open a section for every question in it.
  const insertedSectionsRef = React.useRef<Set<string>>(new Set());

  // Whether this run laid its blueprint out as placeholders. False for a run
  // with no client-side blueprint, which then falls back to appending.
  const ghostsPlacedRef = React.useRef(false);

  const onSourcesNotReadyRef = React.useRef(options.onSourcesNotReady);
  React.useEffect(() => {
    onSourcesNotReadyRef.current = options.onSourcesNotReady;
  }, [options.onSourcesNotReady]);

  const isGenerating = activeRun !== null;
  const multiSetMode = activeRun?.multiSet ?? false;
  const poolStatus = activeRun?.phase ?? "";
  const liveInsertedCount = activeRun?.produced ?? 0;

  // ── Subscribe to the run, however it was started ──────────────────────
  // Mounting mid-run is normal now: the teacher can leave and come back while
  // a generation continues. Subscribing on mount rather than at `generate()`
  // time is what makes the returning editor pick the stream back up.
  React.useEffect(() => {
    const unsubscribe = generationRunner.subscribe((event, data) => {
      if (event === "error") {
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
        return;
      }

      if (event === "saved") {
        setSavedToBank({
          saved: data.saved ?? 0,
          duplicatesSkipped: data.duplicatesSkipped ?? 0,
          projectName: data.projectName || "",
        });
        return;
      }

      if (event === "notice") {
        if (data.message) toast.info(data.message);
        return;
      }

      if (event === "warning") {
        if (data.message) toast.warning(data.message);
        return;
      }

      // Everything below mirrors the runner's accumulated paper into React so
      // the preview and the comparison workspace re-render as it grows.
      if (
        event === "plan" ||
        event === "question" ||
        event === "done" ||
        event === "update" ||
        event === "message"
      ) {
        setResult(generationRunner.getResult());
      }
      if (event === "set") {
        setVariantSets(generationRunner.getVariantSets());
      }

      if (event === "plan") {
        const generalInstructions = data.generalInstructions || [];
        // Only auto-insert the instruction block when auto-insert is on. In
        // review mode the editor rebuilds instructions from what was actually
        // inserted, so a planned 38-question header above a 0-question paper
        // would be a lie.
        const store = useEditorStore.getState();
        if (
          !store.activeRun?.multiSet &&
          store.insertionMode === "auto" &&
          Array.isArray(generalInstructions) &&
          generalInstructions.length > 0
        ) {
          store.appendInstructions(generalInstructions);
        }
        return;
      }

      if (event === "question") {
        const store = useEditorStore.getState();

        // ── The question must belong to the document that is open ────────
        // (see the paper-id gate below)
        //
        // A run is tied to the paper it was started for. The teacher can open
        // a different paper while it streams, and before this the arriving
        // questions went into whatever document happened to be mounted — the
        // wrong paper, silently. Skipping the insert is not a loss: the run's
        // assembled result still reaches the right paper through
        // `comparisonSets` / `approvedSets` when it finishes.
        //
        // A run with a null `paperId` (a draft that had no id when it started)
        // is exempt, since there is nothing to disagree with.
        const runPaperId = store.activeRun?.paperId ?? null;
        if (runPaperId !== null && runPaperId !== store.activeEditorPaperId) {
          return;
        }

        if (store.insertionMode === "auto") {
          const editorQuestion = toEditorQuestion(data.question);
          const slotIndex = Number(data.index);

          // The blueprint was laid out as placeholders before the stream
          // started, so the ordinary path is to fill the slot this question
          // was written for. `data.index` is the slot's own index — the
          // backend sends `assignment.slot.index` — so it lines up with the
          // ghosts without any mapping.
          if (ghostsPlacedRef.current && Number.isFinite(slotIndex)) {
            store.fillSlot({
              index: slotIndex,
              sectionTitle: data.section,
              question: { ...editorQuestion, metadata: data.question.metadata },
            });
          } else if (!insertedSectionsRef.current.has(data.section)) {
            // No ghosts to fill — a run with no client-side blueprint, e.g.
            // one started from a plain brief. Falls back to appending, which
            // is what every run did before slots were placed up front.
            insertedSectionsRef.current.add(data.section);
            store.appendSections([
              {
                title: data.section,
                questions: [editorQuestion],
                ...(store.activeRun?.multiSet ? { setLabel: "A" } : {}),
              },
            ]);
          } else {
            store.appendQuestions([editorQuestion]);
          }
        } else if (store.activeRun?.multiSet) {
          // Multi-set staging keeps its old shape: the sets are reviewed side
          // by side in the Comparison Workspace, so questions are not staged
          // individually in the tray as well.
          return;
        } else {
          store.pushToTray({
            sectionTitle: data.section,
            sourceType:
              (data.question?.sourceType as TrayItem["sourceType"] | undefined) ||
              (data.question?.metadata?.sourceType as
                | TrayItem["sourceType"]
                | undefined) ||
              "unknown",
            question: {
              content: data.question.content,
              type: data.question.type,
              options: data.question.options || [],
              answer: data.question.answer,
              marks: data.question.marks,
              image_url:
                data.question.image_url ||
                data.question.metadata?.image_url ||
                "",
              metadata: data.question.metadata || {},
              bloom: data.question.bloom,
              or_choice: data.question.or_choice,
              vi_alternative: data.question.vi_alternative,
            },
          });
        }
      }
    });
    return unsubscribe;
  }, []);

  const reset = React.useCallback(() => {
    insertedSectionsRef.current = new Set();
    setResult(null);
    setVariantSets([]);
    setSavedToBank(null);
  }, []);

  const cancel = React.useCallback(() => {
    generationRunner.cancel();
  }, []);

  const generate = React.useCallback(async (request: GenerationRequest) => {
    const store = useEditorStore.getState();
    const isMultiSet = request.numberOfSets !== "1";

    insertedSectionsRef.current = new Set();
    store.clearComparisonSets();
    setResult(null);
    setVariantSets([]);
    setSavedToBank(null);

    // ── Lay the paper out before a word of it exists ─────────────────────
    // The blueprint is already agreed — the teacher approved it in the
    // Builder — so the finished shape is knowable now, while the questions
    // are minutes away. Placing the slots first means the document reads as
    // itself immediately and fills in, instead of growing from an empty page
    // with no indication of how much is still to come.
    //
    // Only in auto mode: in review mode nothing is placed on the page at all,
    // so there would be nothing for the ghosts to become.
    const slots = request.blueprint?.slots as
      | { index: number; sectionTitle: string; marks: number; questionType: string }[]
      | undefined;
    const canPlaceGhosts =
      store.insertionMode === "auto" && Array.isArray(slots) && slots.length > 0;
    ghostsPlacedRef.current = canPlaceGhosts;
    if (canPlaceGhosts) {
      store.placeGhostSlots(
        slots!.map((slot) => ({
          index: Number(slot.index),
          sectionTitle: String(slot.sectionTitle || ""),
          marks: Number(slot.marks) || 1,
          questionType: String(slot.questionType || "SHORT"),
        })),
      );
    }

    const outcome = await generationRunner.start({
      path: "/api/generation/questions/stream",
      paperId: request.paperId ?? store.activeEditorPaperId,
      origin: "editor",
      multiSet: isMultiSet,
      payload: {
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
        include_vi_alternatives: false,
        // The reviewed structure. The backend resolves the template into
        // slots; sending the edited blueprint means the paper the teacher
        // approved in the Builder is the paper they get, with no second
        // design call and no chance of a different structure coming back.
        ...(request.blueprint?.slots?.length
          ? { blueprint: request.blueprint, templateId: request.templateId }
          : {}),
      },
    });

    // Every ending sweeps, success included: the pool can come up short, and a
    // slot the pipeline never filled would otherwise stay on the page as an
    // empty numbered question forever.
    if (ghostsPlacedRef.current) {
      useEditorStore.getState().sweepPendingSlots();
      ghostsPlacedRef.current = false;
    }

    if (outcome.cancelled) {
      toast.info("Generation cancelled.");
    } else if (!outcome.ok && outcome.error) {
      toast.error(outcome.error);
    }
    return { ok: outcome.ok };
  }, []);

  /** Set A plus every derived set, in order. Empty until something is produced. */
  const allSets = React.useMemo<ProducedSet[]>(
    () => (result ? [{ label: "A", result }, ...variantSets] : []),
    [result, variantSets],
  );

  // Mirror produced sets into the store so the Comparison Workspace (mounted
  // by the editor page, not here) can read them.
  const setComparisonSets = useEditorStore((s) => s.setComparisonSets);
  React.useEffect(() => {
    if (multiSetMode && allSets.length >= 2) {
      setComparisonSets(
        allSets.map((s) => ({ label: s.label, result: s.result })),
      );
    }
  }, [multiSetMode, allSets, setComparisonSets]);

  return {
    isGenerating,
    result,
    variantSets,
    poolStatus,
    savedToBank,
    liveInsertedCount,
    multiSetMode,
    allSets,
    generate,
    cancel,
    reset,
  };
}
