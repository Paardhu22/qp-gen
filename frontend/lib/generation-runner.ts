"use client";

/**
 * The one thing that owns a running generation.
 *
 * ## Why this is not a hook
 *
 * A generation takes minutes. The surfaces that start one — the editor's Paper
 * Studio, the dashboard's press check — are React components, and a component
 * unmounts the moment the teacher navigates. When the run lived in that
 * component's state, walking to the dashboard and back gave you a Paper Studio
 * that looked idle: the `fetch` was still streaming (nothing aborted it), the
 * questions were still landing in the store, but the remounted panel started
 * from its initial state and had no idea any of it was happening. The work
 * survived; the evidence of it did not.
 *
 * So the run lives here, in module scope, next to the zustand store and for the
 * same reason: a module singleton outlives every component that reads it. A
 * page can mount, unmount and remount while one run continues untouched.
 *
 * ## What lives where
 *
 * - **Here:** the transport, the abort handle, and the heavy accumulating
 *   result (the assembled paper, the derived sets). Big, volatile, and cheap to
 *   keep in memory for the life of the tab.
 * - **The store (`activeRun`):** the small durable facts — phase, counts, which
 *   paper it belongs to. Persisted, so any route can render progress.
 *
 * Splitting them this way keeps a multi-hundred-KB paper out of localStorage,
 * which has a ~5MB cap shared with everything else the editor persists.
 *
 * ## What this deliberately does not do
 *
 * It does not survive a page reload. The stream is a POST whose generator runs
 * inside the Django request, so closing the connection ends the run server-side
 * — there is no job to reattach to yet. That is the backend phase of this work
 * (`GenerationRun`); until it lands, a reload legitimately loses the run and
 * `reconcileOnLoad()` below is what stops the UI claiming otherwise.
 */

import { streamSse } from "@/lib/api-client";
import { useEditorStore, type ActiveRun } from "@/store/editor-store";

export type RunnerEventHandler = (event: string, data: any) => void;

export interface StartRunOptions {
  /** Endpoint to stream from. Both current callers use the questions stream. */
  path: string;
  payload: Record<string, any>;
  /** The paper this run belongs to; inserts are gated on it matching. */
  paperId: string | null;
  origin: ActiveRun["origin"];
  multiSet: boolean;
  /**
   * The starter's own event handler, subscribed for the life of the run.
   *
   * Convenience for a caller that wants the events of the run it just started
   * without managing a subscription around it. Identical to `subscribe()`
   * otherwise — including that a throw from here is contained, so a broken
   * handler cannot kill the stream. Report failure through the returned
   * `StartRunResult`, not by throwing.
   */
  onEvent?: RunnerEventHandler;
}

export interface StartRunResult {
  ok: boolean;
  /** True when the run ended because someone cancelled it. */
  cancelled: boolean;
  error?: string;
}

function newRunId(): string {
  return `run-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

/**
 * Merge one streamed question into the accumulating preview.
 *
 * Structural rather than mutating: the result is read as React state by the
 * comparison workspace and the editor tabs, so every level that changes has to
 * be a new object or nothing re-renders.
 */
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

class GenerationRunner {
  private controller: AbortController | null = null;
  private runId: string | null = null;
  private listeners = new Set<RunnerEventHandler>();

  /**
   * The accumulating paper, kept out of the store because of its size. Read
   * through `getResult()` by whichever surface is mounted when it is wanted.
   */
  private result: any = null;
  private variantSets: { label: string; result: any }[] = [];

  /**
   * Subscribe to the raw event stream.
   *
   * Both surfaces need the same events but render them completely differently
   * — the editor places questions in the document, the dashboard animates them
   * onto a press sheet — so the runner broadcasts rather than deciding.
   * Returns an unsubscribe function.
   */
  subscribe(handler: RunnerEventHandler): () => void {
    this.listeners.add(handler);
    return () => {
      this.listeners.delete(handler);
    };
  }

  private emit(event: string, data: any) {
    // Snapshot before iterating: a handler that unsubscribes itself mid-event
    // would otherwise mutate the set being walked.
    for (const handler of [...this.listeners]) {
      try {
        handler(event, data);
      } catch (error) {
        // One bad subscriber must not stop the others from seeing the event,
        // and must never abort the stream.
        console.error("[generation-runner] subscriber threw:", error);
      }
    }
  }

  isRunning(): boolean {
    return this.controller !== null;
  }

  currentRunId(): string | null {
    return this.runId;
  }

  getResult(): any {
    return this.result;
  }

  getVariantSets(): { label: string; result: any }[] {
    return [...this.variantSets];
  }

  /** Set A plus every derived set, in order. Empty until something is produced. */
  getAllSets(): { label: string; result: any }[] {
    return this.result
      ? [{ label: "A", result: this.result }, ...this.variantSets]
      : [];
  }

  cancel(): void {
    this.controller?.abort();
  }

  /**
   * A run recorded in localStorage that this tab is not actually running.
   *
   * After a reload the persisted `activeRun` is still there but the stream that
   * produced it is gone, so the tracker would show a paper being written
   * forever. Called once on app start: if the store claims a run and the runner
   * has none, the claim is stale and gets cleared.
   */
  reconcileOnLoad(): void {
    const { activeRun, endRun } = useEditorStore.getState();
    if (activeRun && !this.isRunning()) endRun();
  }

  async start(options: StartRunOptions): Promise<StartRunResult> {
    // One run at a time. Starting a second would have both streams inserting
    // into the same document with no way to tell their questions apart.
    if (this.isRunning()) {
      return { ok: false, cancelled: false, error: "A generation is already running." };
    }

    const runId = newRunId();
    const controller = new AbortController();
    this.runId = runId;
    this.controller = controller;
    this.result = null;
    this.variantSets = [];

    const unsubscribeStarter = options.onEvent
      ? this.subscribe(options.onEvent)
      : null;

    const store = useEditorStore.getState();
    store.startRun({
      runId,
      paperId: options.paperId,
      origin: options.origin,
      startedAt: Date.now(),
      phase: "Planning the blueprint…",
      produced: 0,
      total: 0,
      multiSet: options.multiSet,
    });

    /** Ignore anything arriving after this run stopped being the current one. */
    const isCurrent = () => this.runId === runId;

    let streamError: string | null = null;

    try {
      await streamSse(
        options.path,
        options.payload,
        (event, data) => {
          if (!isCurrent()) return;

          // Canonical progress first, so every subscriber sees a store that
          // already agrees with the event it is about to be handed.
          const patch: Partial<ActiveRun> = {};
          if (event === "status") {
            patch.phase =
              data.stage === "pool_progress"
                ? "Writing questions…"
                : data.message || undefined;
          } else if (event === "plan") {
            const total = Number(data.total);
            if (Number.isFinite(total) && total > 0) patch.total = total;
            patch.phase = "Blueprint compiled";
          } else if (event === "question") {
            const current = useEditorStore.getState().activeRun;
            patch.produced = (current?.produced ?? 0) + 1;
            // `total` is authoritative from `plan`, but a run that never sent
            // one still gets a sensible denominator from the question events.
            const total = Number(data.total);
            if (Number.isFinite(total) && total > 0) patch.total = total;
          } else if (event === "error") {
            streamError = data.error || "Generation failed";
          }

          const cleaned = Object.fromEntries(
            Object.entries(patch).filter(([, v]) => v !== undefined),
          );
          if (Object.keys(cleaned).length > 0) {
            useEditorStore.getState().updateRun(cleaned);
          }

          // Accumulate the heavy result here rather than in any one surface,
          // so a surface that mounts halfway through a run can still show it.
          if (event === "plan") {
            this.result = {
              sections: [],
              generalInstructions: data.generalInstructions || [],
            };
          } else if (event === "question") {
            this.result = appendQuestionToResult(
              this.result,
              data.section,
              data.question,
            );
          } else if (event === "set") {
            this.variantSets = [
              ...this.variantSets.filter((v) => v.label !== data.label),
              { label: data.label, result: data.result },
            ];
          } else if (event === "done" && data.result) {
            this.result = data.result;
          } else if (event === "update" || event === "message") {
            this.result = data;
          }

          this.emit(event, data);
        },
        controller.signal,
      );

      return { ok: !streamError, cancelled: false, error: streamError ?? undefined };
    } catch (error: any) {
      // An abort is a teacher changing their mind, not a failure. It reaches
      // here as `AbortError` and must not be reported as a broken generation.
      const cancelled = error?.name === "AbortError";
      if (cancelled) this.emit("cancelled", {});
      return {
        ok: false,
        cancelled,
        error: cancelled ? undefined : error?.message || "Generation failed",
      };
    } finally {
      unsubscribeStarter?.();
      if (isCurrent()) {
        this.controller = null;
        this.runId = null;
        useEditorStore.getState().endRun();
      }
    }
  }
}

export const generationRunner = new GenerationRunner();
