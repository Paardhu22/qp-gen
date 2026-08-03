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
 * ## Reloads
 *
 * A run is owned by the server, not by this tab. `POST /api/generation/runs/`
 * starts a worker thread and returns an id; the stream this class follows is a
 * reader over that run's event log. So a reload is survivable: `reconcileOnLoad`
 * asks what is still running and reattaches from the last event this tab saw,
 * replaying anything it missed.
 *
 * The `_seq` on every event is what makes that seamless — it is the log's own
 * sequence number, tracked here so a reattach resumes rather than restarts.
 */

import {
  cancelGenerationRun,
  fetchActiveGenerationRun,
  startGenerationRun,
  streamRunEvents,
} from "@/lib/api-client";
import { useEditorStore, type ActiveRun } from "@/store/editor-store";

export type RunnerEventHandler = (event: string, data: any) => void;

export interface StartRunOptions {
  /**
   * Kept for call-site readability; the durable path always starts a run at
   * `/api/generation/runs/` and follows its log, so it is not a URL any more.
   */
  path?: string;
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
  /** Last event sequence applied, so a mid-session reattach can resume. */
  private lastSeq = 0;

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

  /**
   * Stop the run — on the server, not just in this tab.
   *
   * Aborting the local stream alone would only stop this tab watching: the
   * worker thread would keep writing questions nobody asked for any more, and
   * a reload would reattach to a generation the teacher had already cancelled.
   */
  cancel(): void {
    const runId = this.runId;
    this.controller?.abort();
    if (runId) {
      void cancelGenerationRun(runId).catch(() => {
        // The abort already stopped this tab following it. A failed cancel
        // leaves the server finishing a paper nobody is waiting for, which is
        // wasteful but not wrong, and the reaper cleans it up regardless.
      });
    }
  }

  /**
   * Pick up a run that outlived the page.
   *
   * The persisted `activeRun` says this tab was watching something; the server
   * is the only authority on whether it still exists. So this asks, and either
   * reattaches — replaying every event missed since `lastSeq` — or clears a
   * claim that is now a ghost. Without the ask, a reload after starting a
   * paper looks exactly like the work having been thrown away.
   */
  async reconcileOnLoad(): Promise<void> {
    if (this.isRunning()) return;

    let active = null;
    try {
      active = await fetchActiveGenerationRun();
    } catch {
      // Offline or the endpoint is unreachable. Clearing is the safe read:
      // better to under-report a run than to show one that cannot be watched.
    }

    const store = useEditorStore.getState();
    if (!active) {
      if (store.activeRun) store.endRun();
      return;
    }

    // Resume, not restart. The editor flushes every fill to IndexedDB as it
    // lands, so after a reload the document already holds everything this tab
    // had applied — replaying from zero would insert all of it a second time
    // and hand the teacher a paper with every question twice.
    //
    // The saved position only counts if it belongs to *this* run. A different
    // run (started in another tab, say) has never been applied here, so it
    // replays whole.
    const wasWatchingThisRun = store.activeRun?.runId === active.runId;
    const resumeFrom = wasWatchingThisRun ? (store.activeRun?.lastSeq ?? 0) : 0;

    store.startRun({
      runId: active.runId,
      paperId: active.paperId || store.activeRun?.paperId || null,
      origin: store.activeRun?.origin ?? "editor",
      startedAt: store.activeRun?.startedAt ?? Date.now(),
      phase: active.phase || "Writing your paper",
      produced: active.produced ?? 0,
      total: active.total ?? 0,
      multiSet: store.activeRun?.multiSet ?? false,
      lastSeq: resumeFrom,
    });

    void this.follow(active.runId, resumeFrom);
  }

  async start(options: StartRunOptions): Promise<StartRunResult> {
    // One run at a time. Starting a second would have both streams inserting
    // into the same document with no way to tell their questions apart.
    if (this.isRunning()) {
      return { ok: false, cancelled: false, error: "A generation is already running." };
    }

    const controller = new AbortController();
    this.controller = controller;
    this.result = null;
    this.variantSets = [];
    this.lastSeq = 0;

    const unsubscribeStarter = options.onEvent
      ? this.subscribe(options.onEvent)
      : null;

    let runId: string;
    try {
      const started = await startGenerationRun(options.payload);
      runId = started.runId;
    } catch (error: any) {
      this.controller = null;
      unsubscribeStarter?.();
      return {
        ok: false,
        cancelled: false,
        error: error?.message || "Could not start the generation.",
      };
    }
    this.runId = runId;

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
      lastSeq: 0,
    });

    try {
      return await this.follow(runId, 0, controller);
    } finally {
      unsubscribeStarter?.();
    }
  }

  /**
   * Read a run's event log and apply it, from `afterSeq` onwards.
   *
   * Shared by starting and reattaching, because they differ only in where they
   * begin: a fresh start reads from 0 because there is nothing to catch up on,
   * and a reattach after a reload also reads from 0 because the tab has lost
   * the document it was building. Mid-session reattachment is what a non-zero
   * `afterSeq` is for.
   */
  private async follow(
    runId: string,
    afterSeq: number,
    existingController?: AbortController,
  ): Promise<StartRunResult> {
    const controller = existingController ?? new AbortController();
    if (!existingController) {
      this.controller = controller;
      this.runId = runId;
    }

    /** Ignore anything arriving after this run stopped being the current one. */
    const isCurrent = () => this.runId === runId;

    let streamError: string | null = null;
    let cancelledByServer = false;

    try {
      await streamRunEvents(
        runId,
        afterSeq,
        (event, data) => {
          if (!isCurrent()) return;

          // The log's own sequence number, so a reattach can resume rather
          // than replay. Stripped from what subscribers see: it is transport
          // bookkeeping, not part of the event.
          if (typeof data?._seq === "number") {
            this.lastSeq = data._seq;
            useEditorStore.getState().updateRun({ lastSeq: data._seq });
          }

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
          } else if (event === "cancelled") {
            cancelledByServer = true;
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

      if (cancelledByServer) {
        this.emit("cancelled", {});
        return { ok: false, cancelled: true };
      }
      return {
        ok: !streamError,
        cancelled: false,
        error: streamError ?? undefined,
      };
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
      if (isCurrent()) {
        this.controller = null;
        this.runId = null;
        useEditorStore.getState().endRun();
      }
    }
  }
}

export const generationRunner = new GenerationRunner();
