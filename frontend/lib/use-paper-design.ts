"use client";

/**
 * Keeps a live paper design in step with what the teacher is typing.
 *
 * Shared by the editor's generator form and the dashboard, because the flow is
 * the same in both: instructions change → re-design → show the structure and
 * whatever is still missing. Only the surrounding chrome differs.
 *
 * Two things make it safe to run against a text box:
 *
 *  - **Debounced.** Each call is a (small) OpenAI request. Firing one per
 *    keystroke would be both slow and expensive; a pause in typing is the
 *    signal that the instructions are worth reading.
 *  - **Aborted on supersede.** Responses can land out of order — a request
 *    started at 200 characters may return after one started at 300. Without
 *    cancelling, the panel would settle on a design for text that no longer
 *    exists. The in-flight request is aborted before the next one starts, and
 *    a late response is dropped by sequence number even if the abort loses the
 *    race.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import {
  designPaper,
  type DesignGap,
  type DesignResponse,
  type PaperDesign,
} from "@/lib/api-client";

export const DESIGN_DEBOUNCE_MS = 700;

/** Below this there is nothing to design and the model would only guess. */
export const MIN_INSTRUCTION_CHARS = 12;

export interface UsePaperDesignArgs {
  instructions: string;
  settings: Record<string, string>;
  pdfSourceIds?: string[];
  hsatSourceIds?: string[];
  numberOfQuestions?: string;
  /** Off in board mode — the blueprint decides the structure there. */
  enabled?: boolean;
}

export interface UsePaperDesignResult {
  design: PaperDesign | null;
  gaps: DesignGap[];
  /** Stated settings plus every assumed default — what to generate with. */
  resolvedSettings: Record<string, string>;
  ready: boolean;
  loading: boolean;
  error: string | null;
  /** Re-run now, ignoring the debounce. */
  refresh: () => void;
}

export function usePaperDesign({
  instructions,
  settings,
  pdfSourceIds,
  hsatSourceIds,
  numberOfQuestions,
  enabled = true,
}: UsePaperDesignArgs): UsePaperDesignResult {
  const [result, setResult] = useState<DesignResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  const abortRef = useRef<AbortController | null>(null);
  // Monotonic: a response whose sequence is not the latest is stale and gets
  // dropped, whether or not the abort landed first.
  const sequenceRef = useRef(0);

  // Serialised so the effect re-runs on VALUE changes, not on the new object
  // identity a parent hands us every render.
  const settingsKey = JSON.stringify(settings);
  const sourcesKey = JSON.stringify([pdfSourceIds ?? [], hsatSourceIds ?? []]);
  const text = instructions.trim();

  useEffect(() => {
    if (!enabled || text.length < MIN_INSTRUCTION_CHARS) {
      abortRef.current?.abort();
      abortRef.current = null;
      sequenceRef.current += 1;
      setResult(null);
      setLoading(false);
      setError(null);
      return;
    }

    const timer = window.setTimeout(() => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const sequence = ++sequenceRef.current;
      setLoading(true);
      setError(null);

      const [pdfIds, hsatIds] = JSON.parse(sourcesKey) as [string[], string[]];
      designPaper({
        instructions: text,
        settings: JSON.parse(settingsKey),
        pdfSourceIds: pdfIds,
        hsatSourceIds: hsatIds,
        numberOfQuestions,
        signal: controller.signal,
      })
        .then((response) => {
          if (sequence !== sequenceRef.current) return;
          setResult(response);
        })
        .catch((err: unknown) => {
          if (sequence !== sequenceRef.current) return;
          if (err instanceof DOMException && err.name === "AbortError") return;
          // The panel is an aid, not a gate: a failed design leaves the
          // teacher able to generate, just without the preview.
          setError(
            err instanceof Error ? err.message : "Could not read those instructions.",
          );
        })
        .finally(() => {
          if (sequence !== sequenceRef.current) return;
          setLoading(false);
        });
    }, DESIGN_DEBOUNCE_MS);

    return () => window.clearTimeout(timer);
  }, [text, settingsKey, sourcesKey, numberOfQuestions, enabled, nonce]);

  // Abort whatever is in flight when the component goes away, so a resolved
  // promise cannot call setState on an unmounted tree.
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      sequenceRef.current += 1;
    };
  }, []);

  const refresh = useCallback(() => setNonce((n) => n + 1), []);

  return {
    design: result?.design ?? null,
    gaps: result?.gaps ?? [],
    resolvedSettings: result?.settings ?? {},
    ready: result?.ready ?? false,
    loading,
    error,
    refresh,
  };
}
