"use client";

/**
 * The generation stream's event vocabulary, as one definition.
 *
 * `POST /api/generation/questions/stream` has two clients: the editor's
 * `usePaperGeneration`, and the dashboard chat's `handleGenerate`. They both
 * already share the transport (`streamSse`), and the audit read that as most
 * of the job done. It was not — what they were sharing was the part that was
 * never going to drift. What they each re-implemented was the *meaning* of the
 * stream: which events exist, which field on each carries the number, and what
 * the correct response to one is.
 *
 * And it had drifted. The backend emits thirteen event types on this endpoint.
 * The editor handled twelve; the dashboard handled nine, silently discarding
 * `saved`, `notice` and `warning` — the last two being the pool pipeline's
 * only channel for telling a teacher something went sideways but was
 * recovered ("3 chapters had no usable figures; questions were written without
 * them"). On the chat path those went nowhere at all.
 *
 * ## What is shared here and what is deliberately not
 *
 * Shared: the names, the payload shapes, and the events whose right response
 * is the same everywhere — `notice` and `warning` are messages addressed to
 * the teacher, and neither surface has an opinion about them.
 *
 * Not shared: what a `question` event *does*. The editor merges it into a
 * document and may stage it in a review tray; the dashboard appends a row to a
 * printing-press animation. Those are not two implementations of one thing,
 * they are two different things, and forcing them through a common reducer
 * would produce a state shape that is wrong for both. `GenerationState` stays
 * in the hook and the dashboard keeps its own.
 *
 * The line is: this module knows what the server said, and the caller decides
 * what that means for its own screen.
 */

import { toast } from "sonner";

/**
 * Every event this endpoint emits, verified against the backend rather than
 * against either client — `services/pool/pipeline.py`, `from_bank.py`, and
 * `apps/generation/`.
 *
 * `message` is not emitted deliberately; it is the SSE default the parser
 * falls back to for a frame with no `event:` line, and the older backend paths
 * relied on it. It is treated as a synonym for `update`.
 *
 * Not in this union, on purpose: `delta` and `spec` belong to the chat
 * endpoint, and `run` is synthetic — the durable-run follower emits it to name
 * the run, and `streamSse` consumes it before any handler sees it.
 */
export type GenerationEventName =
  | "status"
  | "plan"
  | "pool"
  | "question"
  | "set"
  | "saved"
  | "notice"
  | "warning"
  | "update"
  | "message"
  | "done"
  | "error";

/** A question as it comes off the wire. Loose on purpose — the generators
 *  differ in what they attach, and both clients read defensively. */
export interface StreamedQuestion {
  content?: string;
  type?: string;
  options?: string[];
  answer?: unknown;
  marks?: number;
  image_url?: string;
  bloom?: string;
  or_choice?: unknown;
  sourceType?: string;
  metadata?: Record<string, unknown> & {
    image_url?: string;
    sourceType?: string;
  };
}

/** One source the readiness gate refused, on a `DOCUMENTS_NOT_READY` error. */
export interface PendingDocument {
  kind?: string;
  id: string;
  name?: string;
  /** `not_found` means it is gone for good; anything else is worth requeuing. */
  reason?: string;
}

export type GenerationEvent =
  /** A stage announcement. `stage` drives progress UI; `message` is prose. */
  | { name: "status"; stage?: string; message?: string }
  /**
   * The compiled blueprint. `total` is the slot count — the one number in this
   * stream that is a real target rather than a pool size, which is why
   * `pool`'s count must never be shown as progress toward it.
   */
  | {
      name: "plan";
      total?: number;
      summary?: unknown;
      generalInstructions?: string[];
    }
  /** The pool finished filling. `total` over-shoots the plan by design. */
  | { name: "pool"; total?: number; byType?: Record<string, number> }
  | { name: "question"; section?: string; question?: StreamedQuestion }
  /** One complete variant set, in multi-set mode. Labels can repeat. */
  | { name: "set"; label: string; result?: unknown }
  | {
      name: "saved";
      saved?: number;
      duplicatesSkipped?: number;
      projectName?: string;
    }
  /** Addressed to the teacher. Same meaning on every surface. */
  | { name: "notice"; message?: string }
  | { name: "warning"; message?: string }
  /** A whole-paper replacement. `message` is the no-`event:`-line spelling. */
  | { name: "update"; result: unknown }
  | { name: "done"; result?: unknown }
  | {
      name: "error";
      error: string;
      code?: string;
      pendingDocuments?: PendingDocument[];
    }
  /**
   * Something the server sent that this build has no case for. Kept rather
   * than dropped so a client can log it — a new backend event reaching an old
   * frontend should be visible, not invisible.
   */
  | { name: "unknown"; raw: string; data: unknown };

function asRecord(data: unknown): Record<string, any> {
  return data && typeof data === "object" ? (data as Record<string, any>) : {};
}

function asNumber(value: unknown): number | undefined {
  const n = Number(value);
  return Number.isFinite(n) ? n : undefined;
}

/**
 * Turn a raw `(event, data)` pair into something with a known shape.
 *
 * Never throws. A handler that throws inside an SSE callback used to be
 * reported to the teacher as "Failed to parse stream payload" regardless of
 * what actually went wrong (fixed at the root in `api-client.ts`), and the
 * cheapest way to keep that class of bug from coming back is for the decoding
 * step to have no failure mode at all.
 */
export function decodeGenerationEvent(
  event: string,
  data: unknown,
): GenerationEvent {
  const d = asRecord(data);

  switch (event) {
    case "status":
      return { name: "status", stage: d.stage, message: d.message };
    case "plan":
      return {
        name: "plan",
        total: asNumber(d.total),
        summary: d.summary,
        generalInstructions: Array.isArray(d.generalInstructions)
          ? d.generalInstructions
          : [],
      };
    case "pool":
      return { name: "pool", total: asNumber(d.total), byType: d.byType || {} };
    case "question":
      return { name: "question", section: d.section, question: d.question };
    case "set":
      return { name: "set", label: String(d.label ?? ""), result: d.result };
    case "saved":
      return {
        name: "saved",
        saved: asNumber(d.saved) ?? 0,
        duplicatesSkipped: asNumber(d.duplicatesSkipped) ?? 0,
        projectName: d.projectName || "",
      };
    case "notice":
      return { name: "notice", message: d.message };
    case "warning":
      return { name: "warning", message: d.message };
    case "update":
    case "message":
      // The payload *is* the paper here, not a wrapper around it.
      return { name: "update", result: data };
    case "done":
      return { name: "done", result: d.result };
    case "error":
      return {
        name: "error",
        error: String(d.error || "Generation failed"),
        code: d.code,
        pendingDocuments: Array.isArray(d.pendingDocuments)
          ? d.pendingDocuments
          : [],
      };
    default:
      return { name: "unknown", raw: event, data };
  }
}

/**
 * The events whose correct handling is identical on every surface.
 *
 * Returns true when it has dealt with the event, so a caller can write
 * `if (handleAmbientEvent(ev)) return;` and then only concern itself with the
 * events it actually renders differently. This is the piece the dashboard was
 * missing entirely.
 */
export function handleAmbientEvent(event: GenerationEvent): boolean {
  if (event.name === "notice") {
    if (event.message) toast.info(event.message);
    return true;
  }
  if (event.name === "warning") {
    if (event.message) toast.warning(event.message);
    return true;
  }
  if (event.name === "unknown") {
    // Not an error — an older client meeting a newer server. Visible in a
    // console, silent to the teacher.
    console.warn(`[generation] unhandled stream event: ${event.raw}`);
    return true;
  }
  return false;
}

/**
 * Read the readiness gate's rejection into the two lists a caller can act on.
 *
 * Only PDF sources appear: an HSAT book that is still indexing is not a
 * failure to repair, it is a wait, and `useHsatReadiness` is already watching
 * it.
 */
export function splitPendingDocuments(pending: PendingDocument[]): {
  drop: string[];
  requeue: { id: string; name: string }[];
} {
  const pdfs = pending.filter((p) => p.kind === "pdf");
  return {
    drop: pdfs.filter((p) => p.reason === "not_found").map((p) => p.id),
    requeue: pdfs
      .filter((p) => p.reason !== "not_found")
      .map((p) => ({ id: p.id, name: p.name || "Document" })),
  };
}
