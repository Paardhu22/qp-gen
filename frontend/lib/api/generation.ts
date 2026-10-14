/** Generating papers: durable runs, building from a bank, replacing a question, designing a paper. */
"use client";

import { ApiError, fetchJson } from "@/lib/api/http";
import {
  DEFAULT_MAX_RESUMES,
  SseEventHandler,
  StreamSseOptions,
  consumeSse,
  openRunStream,
  streamSse,
} from "@/lib/api/sse";

/**
 * A generation recorded on the server, as the "recent generations" list shows.
 *
 * Runs are a delivery mechanism, not history — they are purged after a week.
 * What they are for is the teacher whose phone slept during a four-minute
 * generation and who would otherwise have lost the paper entirely.
 */
export type GenerationRunSummary = {
  id: string;
  kind: string;
  status: "running" | "completed" | "failed" | "abandoned";
  created_at: string;
  finished_at: string | null;
  error: string;
  eventCount: number;
  request: Record<string, any>;
};

export async function listGenerationRuns(): Promise<GenerationRunSummary[]> {
  return fetchJson<GenerationRunSummary[]>("/api/generation/runs", {
    method: "GET",
  });
}

/**
 * Re-attach to a run that was started earlier — after a page reload, or from
 * the recent-generations list. Replays everything after `cursor`, then follows
 * the rest live.
 */
export async function resumeSseRun(
  runId: string,
  cursor: number,
  onEvent: SseEventHandler,
  options: StreamSseOptions = {},
): Promise<void> {
  const position = { runId, cursor };
  let sawTerminalEvent = await consumeSse(
    await openRunStream(runId, cursor),
    onEvent,
    position,
    options.onRunPosition,
  );

  const maxResumes = options.maxResumes ?? DEFAULT_MAX_RESUMES;
  for (let attempt = 0; !sawTerminalEvent && attempt < maxResumes; attempt++) {
    await new Promise((resolve) => setTimeout(resolve, 1000 * (attempt + 1)));
    try {
      sawTerminalEvent = await consumeSse(
        await openRunStream(runId, position.cursor),
        onEvent,
        position,
        options.onRunPosition,
      );
    } catch {
      break;
    }
  }

  if (!sawTerminalEvent) {
    throw new ApiError(
      "That generation could not be reopened. It may have been cleared, or it " +
        "stopped on the server before it finished.",
      200,
    );
  }
}

export type BankChapter = {
  projectId: string;
  projectName: string;
  subject: string | null;
  gradeClass: string | null;
  chapter: string | null;
  count: number;
};

/** Per-chapter counts of what is already in the user's question bank. */
export async function fetchBankSummary(): Promise<{ chapters: BankChapter[] }> {
  return fetchJson<{ chapters: BankChapter[] }>(
    "/api/generation/bank-summary",
    { method: "GET" },
  );
}

/**
 * Assemble a paper from questions already saved in the bank.
 *
 * Skips Model 1 entirely — a chapter that has been generated once costs a
 * single assembly call to re-paper, instead of re-reading the chapter and
 * re-writing every question.
 */
export async function streamPaperFromBank(
  payload: Record<string, any>,
  onEvent: SseEventHandler,
): Promise<void> {
  return streamSse("/api/generation/paper-from-bank", payload, onEvent);
}

/** The blueprint identity of one question, as the editor stores it. */
export type ReplacementSlot = {
  slotIndex?: number;
  section?: string;
  marks: number;
  /** The runtime shape. Still decides eligibility. */
  type: string;
  /** The catalogue type, when known; reconciled with `type` by the backend. */
  typeCode?: string;
  hots?: boolean;
  competency?: boolean;
  generator?: string;
  assetType?: string;
  chapter?: string;
  topic?: string;
  difficulty?: string;
  subject?: string;
  classNum?: number;
  poolId?: string;
  questionId?: string;
};

export type ReplacementResponse = {
  /** "bank" when an existing question was reused, "generated" when one was written. */
  source: "bank" | "generated";
  question: {
    content: string;
    type: string;
    typeCode?: string;
    options: string[];
    answer: string;
    marks: number;
    explanation?: string;
    image_url?: string;
    metadata?: Record<string, any>;
  };
};

/**
 * Regenerate exactly ONE question, preserving its blueprint slot.
 *
 * Marks, question type, section, chapter, difficulty and the generator that
 * owns the slot all travel in `slot`, so the replacement is eligible for the
 * same position and nothing else on the paper changes. `excludeIds` are the
 * questions already on the paper, which keeps the replacement from being one
 * the teacher is already looking at.
 */
export async function replaceQuestion(
  slot: ReplacementSlot,
  options: {
    excludeIds?: string[];
    excludeHashes?: string[];
    pdfSourceIds?: string[];
    hsatSourceIds?: string[];
    allowGeneration?: boolean;
  } = {},
): Promise<ReplacementResponse> {
  return fetchJson<ReplacementResponse>("/api/generation/replace-question", {
    method: "POST",
    body: JSON.stringify({
      slot,
      excludeIds: options.excludeIds || [],
      excludeHashes: options.excludeHashes || [],
      pdfSourceIds: options.pdfSourceIds || [],
      hsatSourceIds: options.hsatSourceIds || [],
      allowGeneration: options.allowGeneration !== false,
    }),
    // Writing a fresh question runs a model call; the default 30s can be tight
    // for a 10-mark reading passage.
    timeoutMs: 120000,
  });
}

export interface DesignGroup {
  type: string;
  marks: number;
  count: number;
  topic: string;
  choice: boolean;
  totalMarks: number;
}

export interface DesignSection {
  title: string;
  instruction: string;
  groups: DesignGroup[];
  totalMarks: number;
  totalQuestions: number;
}

export interface PaperDesign {
  title: string;
  duration: string;
  sections: DesignSection[];
  generalInstructions: string[];
  totalMarks: number;
  totalQuestions: number;
  /** What the validator had to correct. Shown, never swallowed. */
  corrections: string[];
  /** True when the designer was unavailable and a simpler parse was used. */
  degraded: boolean;
}

export interface DesignGap {
  field: string;
  label: string;
  /** "required" blocks generation; "assumed" is filled and changeable. */
  kind: "required" | "assumed";
  options: { value: string; label: string }[];
  value: string;
  note: string;
}

export interface DesignResponse {
  design: PaperDesign;
  gaps: DesignGap[];
  /** The stated settings plus every assumed default, ready to generate with. */
  settings: Record<string, string>;
  ready: boolean;
  generalInstructions: string[];
}

export async function designPaper(body: {
  instructions: string;
  settings?: Record<string, string>;
  pdfSourceIds?: string[];
  hsatSourceIds?: string[];
  numberOfQuestions?: string;
  signal?: AbortSignal;
}): Promise<DesignResponse> {
  const { signal, ...payload } = body;
  return fetchJson<DesignResponse>("/api/generation/design-paper", {
    method: "POST",
    body: JSON.stringify(payload),
    signal,
  });
}

// ── Templates & blueprints ─────────────────────────────────────────────────
//
// A template is now the ONLY way a paper's structure is chosen — "QP Type" is
// gone, and what used to be Board Mode / General Instructions Mode are two
// entries in the same picker. See backend `services/templates.py`.
