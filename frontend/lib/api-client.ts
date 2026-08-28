"use client";

import { getAccessToken } from "@/lib/token-storage";
import { ensureFreshTokens, refreshAccessToken } from "@/lib/auth-client";

import { API_BASE_URL } from "@/lib/api-base-url";

type FetchJsonOptions = RequestInit & {
  skipAuth?: boolean;
  /** Override the default 30 s timeout. Pass Infinity to disable. */
  timeoutMs?: number;
};

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/**
 * Thrown when a request is intentionally cancelled by the caller (e.g. because
 * a newer sync superseded it).  Callers should catch this and return silently
 * rather than showing an error to the user.
 */
export class SyncCancelledError extends Error {
  constructor() {
    super("Sync cancelled");
    this.name = "SyncCancelledError";
  }
}

/**
 * Turn a failed Response into the most specific message the server offered.
 *
 * Three shapes have to be handled, and missing any one of them turns a stated
 * cause into a mystery:
 *
 *   * `{ detail }` / `{ error }` — DRF's APIException and our own views.
 *   * `{ field: ["msg"] }` — DRF *serializer validation*, which has no
 *     top-level key at all. A required field the client forgot to send lands
 *     here, so swallowing this shape reports "request failed" for a fault that
 *     the body named exactly.
 *   * Not JSON at all — nginx's HTML 502/504, or a Django debug traceback.
 *     `.json()` rejects, and the status is the only real information; say so
 *     instead of pretending the server explained itself.
 */
async function errorMessageFrom(
  response: Response,
  fallback: string,
): Promise<string> {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    // Non-JSON error page — the status line is all we have.
    return `${fallback} (HTTP ${response.status}${
      response.statusText ? ` ${response.statusText}` : ""
    })`;
  }

  if (typeof body === "string" && body.trim()) return body;
  if (typeof body !== "object" || body === null) return fallback;

  const record = body as Record<string, unknown>;
  if (typeof record.detail === "string" && record.detail) return record.detail;
  if (typeof record.error === "string" && record.error) return record.error;

  const fields = Object.entries(record)
    .map(([field, msgs]) => {
      const text = Array.isArray(msgs) ? msgs.join(", ") : String(msgs ?? "");
      return text ? `${field}: ${text}` : "";
    })
    .filter(Boolean)
    .join(" | ");

  return fields || fallback;
}

export async function fetchJson<T>(
  path: string,
  options: FetchJsonOptions = {},
): Promise<T> {
  // Separate the caller-supplied signal from the rest of RequestInit so we
  // can merge it with our own internal timeout signal.
  const {
    skipAuth,
    timeoutMs = 30000,
    signal: callerSignal,
    ...requestInit
  } = options;
  const buildHeaders = () => {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...((requestInit.headers || {}) as Record<string, string>),
    };

    const accessToken = getAccessToken();
    if (
      !skipAuth &&
      accessToken &&
      !Object.prototype.hasOwnProperty.call(headers, "Authorization")
    ) {
      headers["Authorization"] = `Bearer ${accessToken}`;
    }

    return headers;
  };

  // Bail immediately if the caller already cancelled before we even started.
  if (callerSignal?.aborted) throw new SyncCancelledError();

  // Renew a known-dead token before spending a round trip on a guaranteed 401.
  // The 401 retry below still covers the cases this can't see (clock skew, a
  // token revoked early); this just stops the predictable failure.
  if (!skipAuth) await ensureFreshTokens();

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  // Forward the caller's cancellation into our internal controller so a single
  // AbortSignal drives the actual fetch.
  const forwardAbort = () => controller.abort();
  callerSignal?.addEventListener("abort", forwardAbort, { once: true });

  const runFetch = () =>
    fetch(`${API_BASE_URL}${path}`, {
      ...requestInit,
      headers: buildHeaders(),
      signal: controller.signal,
    });

  let response: Response;
  try {
    response = await runFetch();
    if (response.status === 401 && !skipAuth) {
      const refreshed = await refreshAccessToken();
      if (refreshed) response = await runFetch();
    }
  } catch (err: unknown) {
    if (err instanceof Error && err.name === "AbortError") {
      // Distinguish intentional cancellation from a genuine timeout.
      if (callerSignal?.aborted) throw new SyncCancelledError();
      throw new ApiError("Request timed out. Please try again.", 408);
    }
    throw err;
  } finally {
    clearTimeout(timer);
    callerSignal?.removeEventListener("abort", forwardAbort);
  }

  if (!response.ok) {
    throw new ApiError(
      await errorMessageFrom(response, "Request failed"),
      response.status,
    );
  }

  // 204 No Content (or any empty body) — nothing to parse.
  if (
    response.status === 204 ||
    response.headers.get("content-length") === "0"
  ) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export async function fetchForm<T>(
  path: string,
  formData: FormData,
): Promise<T> {
  const buildHeaders = () => {
    const headers: Record<string, string> = {};
    const accessToken = getAccessToken();
    if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
    return headers;
  };

  await ensureFreshTokens();

  let response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    body: formData,
    headers: buildHeaders(),
  });
  if (response.status === 401) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      response = await fetch(`${API_BASE_URL}${path}`, {
        method: "POST",
        body: formData,
        headers: buildHeaders(),
      });
    }
  }

  if (!response.ok) {
    throw new ApiError(
      await errorMessageFrom(response, "Request failed"),
      response.status,
    );
  }

  return response.json() as Promise<T>;
}

export { API_BASE_URL };

export type SseEventHandler = (event: string, data: any) => void;

/**
 * Where a generation had got to when the connection dropped.
 *
 * `runId` is the recorded run on the server; `cursor` is how many of its
 * frames this client has already seen. Together they are enough to pick the
 * generation back up without losing or repeating anything — see
 * services/generation_runs.py.
 */
export type SseRunPosition = { runId: string; cursor: number };

export type StreamSseOptions = {
  /** Told the run id and cursor as they advance, so a caller can persist them
   *  and offer to resume after a page reload. */
  onRunPosition?: (position: SseRunPosition) => void;
  /** How many times to re-attach after the transport drops. */
  maxResumes?: number;
};

/** Attempts to re-attach after a dropped connection, before giving up. */
const DEFAULT_MAX_RESUMES = 3;

/**
 * Read one SSE response, dispatching frames and tracking where we got to.
 *
 * The cursor is counted rather than read off the wire: the server's `follow`
 * emits its stored frames in sequence order, one per recorded event, preceded
 * by a single synthetic `run` frame. So "frames seen since the start cursor,
 * not counting `run`" is exactly the server's sequence number. Keeping the
 * count here means the frames themselves stay byte-identical to what the
 * pipeline produced.
 */
async function consumeSse(
  response: Response,
  onEvent: SseEventHandler,
  position: { runId: string | null; cursor: number },
  onRunPosition?: (position: SseRunPosition) => void,
): Promise<boolean> {
  if (!response.body) {
    throw new ApiError(
      "The server accepted the request but returned no stream. Check that no " +
        "proxy is buffering text/event-stream responses.",
      response.status,
    );
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let sawTerminalEvent = false;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";

    for (const part of parts) {
      const lines = part.split("\n");
      let event = "message";
      let data = "";

      for (const line of lines) {
        // Lines beginning with ":" are SSE comments. The backend sends them
        // as keepalive pings during long silent stages; they carry no data
        // and must be skipped, not parsed.
        if (line.startsWith(":")) continue;
        if (line.startsWith("event:")) {
          event = line.replace("event:", "").trim();
        } else if (line.startsWith("data:")) {
          data += line.replace("data:", "").trim();
        }
      }

      if (!data) continue;

      if (event === "run") {
        // Synthetic, from the follower. It names the run and is not itself a
        // recorded frame, so it does not advance the cursor.
        try {
          const parsed = JSON.parse(data);
          if (parsed?.runId) {
            position.runId = String(parsed.runId);
            onRunPosition?.({ runId: position.runId, cursor: position.cursor });
          }
        } catch {
          // A malformed run frame costs the ability to resume, nothing else.
        }
        continue;
      }

      position.cursor += 1;
      if (position.runId) {
        onRunPosition?.({ runId: position.runId, cursor: position.cursor });
      }

      if (event === "done" || event === "error") sawTerminalEvent = true;
      try {
        onEvent(event, JSON.parse(data));
      } catch (error) {
        onEvent("error", { error: "Failed to parse stream payload" });
      }
    }
  }

  return sawTerminalEvent;
}

export async function streamSse(
  path: string,
  payload: Record<string, any>,
  onEvent: SseEventHandler,
  options: StreamSseOptions = {},
): Promise<void> {
  const buildHeaders = () => {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    const accessToken = getAccessToken();
    if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
    return headers;
  };

  // A generation runs for minutes; the token is only checked when the stream
  // connects, so renewing here is what keeps a long paper from dying at the
  // door. Retrying a 401 after the fact would restart the whole generation.
  await ensureFreshTokens();

  let response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify(payload),
  });
  if (response.status === 401) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      response = await fetch(`${API_BASE_URL}${path}`, {
        method: "POST",
        headers: buildHeaders(),
        body: JSON.stringify(payload),
      });
    }
  }

  if (!response.ok) {
    // A rejected stream is almost always a serializer complaint naming the
    // exact field that is missing or wrong. Report that, not "it failed".
    throw new ApiError(
      await errorMessageFrom(response, "Stream request failed"),
      response.status,
    );
  }

  if (!response.body) {
    // 2xx with no readable body: not a server rejection, so there is no error
    // payload to quote. Distinguish it — it means the transport dropped the
    // stream, not that the request was invalid.
    throw new ApiError(
      "The server accepted the request but returned no stream. Check that no " +
        "proxy is buffering text/event-stream responses.",
      response.status,
    );
  }

  // A generation is only complete when the backend says so. Anything that
  // cuts the connection first — a proxy read timeout, a killed gunicorn
  // worker, a dropped network — surfaces as a clean `done: true` from
  // `reader.read()`, which used to make this function resolve as if the
  // generation had succeeded. The caller then saw no error and no result.
  //
  // Now it means something better: the run is still being produced on the
  // server, and we can go back for the rest of it.
  const position = { runId: null as string | null, cursor: 0 };
  let sawTerminalEvent = await consumeSse(
    response,
    onEvent,
    position,
    options.onRunPosition,
  );

  const maxResumes = options.maxResumes ?? DEFAULT_MAX_RESUMES;
  for (let attempt = 0; !sawTerminalEvent && position.runId && attempt < maxResumes; attempt++) {
    // A short, growing pause. The drop is usually a proxy timing out on a
    // silent stretch, so reconnecting instantly just repeats it.
    await new Promise((resolve) => setTimeout(resolve, 1000 * (attempt + 1)));
    try {
      sawTerminalEvent = await consumeSse(
        await openRunStream(position.runId, position.cursor),
        onEvent,
        position,
        options.onRunPosition,
      );
    } catch {
      // Keep trying until the attempts run out; the error below is the one
      // the caller should see.
      break;
    }
  }

  if (!sawTerminalEvent) {
    throw new ApiError(
      position.runId
        ? "The connection to this generation keeps dropping. It is still " +
          "running on the server — reopen it from your recent generations " +
          "once your connection settles."
        : "The connection closed before generation finished. This usually means " +
          "the request took longer than the server allows — try again, or " +
          "generate fewer chapters at once.",
      response.status,
    );
  }
}

/** Open (or re-open) the event stream of a recorded run at `cursor`. */
async function openRunStream(runId: string, cursor: number): Promise<Response> {
  await ensureFreshTokens();
  const headers: Record<string, string> = {};
  const accessToken = getAccessToken();
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;

  const response = await fetch(
    `${API_BASE_URL}/api/generation/runs/${encodeURIComponent(runId)}/events?cursor=${cursor}`,
    { method: "GET", headers },
  );
  if (!response.ok) {
    throw new ApiError(
      await errorMessageFrom(response, "Could not reopen that generation"),
      response.status,
    );
  }
  return response;
}

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
  type: string;
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

export async function fetchProjects<T>(
  options: FetchJsonOptions = {},
): Promise<T> {
  return fetchJson<T>("/api/projects/", { method: "GET", ...options });
}

export async function fetchProjectsWithQuestions<T>(
  options: FetchJsonOptions = {},
): Promise<T> {
  return fetchJson<T>("/api/projects/?withQuestions=true", {
    method: "GET",
    ...options,
  });
}

export async function fetchPapers<T>(options: FetchJsonOptions = {}): Promise<T> {
  return fetchJson<T>("/api/projects/papers/", { method: "GET", timeoutMs: 60000, ...options });
}

export async function fetchPaper<T>(paperId: string): Promise<T> {
  return fetchJson<T>(`/api/projects/papers/${paperId}/`, { method: "GET", timeoutMs: 60000 });
}

export async function fetchQuestionTypes<T>(options: FetchJsonOptions = {}): Promise<T> {
  return fetchJson<T>("/api/projects/questions/types", { method: "GET", timeoutMs: 15000, ...options });
}

export async function saveQuestions<T>(
  payload: Record<string, any>,
): Promise<T> {
  return fetchJson<T>("/api/projects/questions/save", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function savePaper<T>(
  payload: Record<string, any>,
  signal?: AbortSignal,
): Promise<T> {
  return fetchJson<T>("/api/projects/papers/", {
    method: "POST",
    body: JSON.stringify(payload),
    // Paper saves talk to Neon which may need to wake from cold-start — 30 s.
    timeoutMs: 30000,
    signal,
  });
}

export async function updatePaper<T>(
  paperId: string,
  payload: Record<string, any>,
  signal?: AbortSignal,
): Promise<T> {
  return fetchJson<T>(`/api/projects/papers/${paperId}/`, {
    method: "PUT",
    body: JSON.stringify(payload),
    timeoutMs: 30000,
    signal,
  });
}

export async function deleteQuestion(questionId: string): Promise<void> {
  await fetchJson<void>(`/api/projects/questions/${questionId}/`, {
    method: "DELETE",
  });
}

/**
 * Move a paper to the recycle bin.
 *
 * Not a hard delete. What this destroys is a term's worth of work — blueprint,
 * every set variant, answer key, every question — and the button sits one row
 * away from "open". `permanent` is the deliberate second step, offered only
 * from inside the bin.
 */
export async function deletePaper(
  paperId: string,
  options: { permanent?: boolean } = {},
): Promise<void> {
  const query = options.permanent ? "?permanent=true" : "";
  await fetchJson<void>(`/api/projects/papers/${paperId}/${query}`, {
    method: "DELETE",
  });
}

/** One binned paper, as the bin lists it. Same shape as a library row. */
export type TrashedPapers<T> = {
  /** How long a binned paper is kept before it is permanently removed. */
  retention_days: number;
  papers: T[];
};

/** The recycle bin. Listing it also purges whatever has aged out. */
export async function fetchTrashedPapers<T>(): Promise<TrashedPapers<T>> {
  return fetchJson<TrashedPapers<T>>("/api/projects/papers/trash", {
    method: "GET",
    timeoutMs: 60000,
  });
}

/** Take one paper back out of the bin. */
export async function restorePaper(paperId: string): Promise<void> {
  await fetchJson<void>(`/api/projects/papers/${paperId}/restore`, {
    method: "POST",
  });
}

/** Permanently remove everything in the bin. */
export async function emptyPaperTrash(): Promise<void> {
  await fetchJson<void>("/api/projects/papers/trash", { method: "DELETE" });
}

export async function getExportUrl(
  s3Key: string,
): Promise<{ url: string; expires_in: number }> {
  return fetchJson<{ url: string; expires_in: number }>(
    `/api/storage/export-url/?key=${encodeURIComponent(s3Key)}`,
    { method: "GET" },
  );
}

export async function generateAnswerScript(
  paperId: string,
  setId?: string,
): Promise<{ answer_script_paper_id: string; editor_url: string }> {
  return fetchJson<{ answer_script_paper_id: string; editor_url: string }>(
    `/api/generation/papers/${paperId}/generate-answer-script/`,
    {
      method: "POST",
      body: setId ? JSON.stringify({ setId }) : undefined,
      // Answer generation may take a while for papers with many questions
      timeoutMs: 300000,
    },
  );
}

// ── Dashboard assistant ─────────────────────────────────────────────────
//
// The assistant is a plain conversation model, separate from the generation
// pipeline: it asks the follow-up questions a half-specified request leaves
// open and accumulates the answers into a `PaperSpec`. Generating the paper
// is still the pool pipeline's job — the spec is handed to it.

/** Field names match `formSchema` in components/generator-form.tsx. */
export interface PaperSpec {
  board?: string;
  academicClass?: string;
  subject?: string;
  difficulty?: string;
  marks?: string;
  numberOfQuestions?: string;
  numberOfSets?: string;
  chapters?: string[];
  /**
   * A paper structure the teacher described in their own words ("5 MCQs and
   * 3 short answers", "same as our weekly test"). Its presence switches
   * generation from the CBSE blueprint to General Instructions Mode, where
   * `services/paper_design.py` lays the paper out from this text alone.
   */
  instructions?: string;
}

export interface ChatAttachment {
  id: string;
  name: string;
  size?: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  attachments?: ChatAttachment[];
  created_at?: string;
}

/** What the interface should put in front of the teacher next. */
export interface FollowUpPrompt {
  field: string;
  kind: "choice" | "files" | "text";
  label: string;
  hint?: string;
  optional?: boolean;
  allowOther?: boolean;
  options?: { value: string; label: string; hint?: string }[];
}

export type ConversationMode = "chat" | "paper";
export type ConversationStatus =
  | "active"
  | "paused"
  | "generating"
  | "completed";

export interface Conversation {
  id: string;
  title: string;
  spec: PaperSpec;
  mode: ConversationMode;
  status: ConversationStatus;
  paper_id?: string | null;
  ready: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface ConversationDetail extends Conversation {
  messages: ChatMessage[];
  next_prompt: FollowUpPrompt | null;
  /** Every PDF attached across the session — what generation reads from. */
  source_ids: string[];
  /**
   * Whether pressing Generate would actually succeed. Stricter than `ready`:
   * the blueprint needs four fields, but the pipeline also needs a source.
   */
  can_generate: boolean;
}

export async function setConversationStatus(
  conversationId: string,
  status: ConversationStatus,
  paperId?: string,
): Promise<Conversation> {
  return fetchJson<Conversation>(
    `/api/chat/conversations/${conversationId}/status`,
    {
      method: "POST",
      body: JSON.stringify({ status, ...(paperId ? { paperId } : {}) }),
    },
  );
}

export async function fetchConversations(): Promise<Conversation[]> {
  return fetchJson<Conversation[]>("/api/chat/conversations", { method: "GET" });
}

export async function fetchConversation(
  conversationId: string,
): Promise<ConversationDetail> {
  return fetchJson<ConversationDetail>(
    `/api/chat/conversations/${conversationId}`,
    { method: "GET" },
  );
}

export async function createConversation(): Promise<ConversationDetail> {
  return fetchJson<ConversationDetail>("/api/chat/conversations", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function deleteConversation(conversationId: string): Promise<void> {
  await fetchJson<void>(`/api/chat/conversations/${conversationId}`, {
    method: "DELETE",
  });
}

export async function renameConversation(
  conversationId: string,
  title: string,
): Promise<Conversation> {
  return fetchJson<Conversation>(`/api/chat/conversations/${conversationId}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
}

/**
 * Stream one assistant turn.
 *
 * Events: `delta` ({text}) per token, `spec` ({spec, ready}) once the reply is
 * complete, then the terminal `done` — or `error`. `streamSse` throws if the
 * connection closes before a terminal event, so a proxy timeout surfaces as a
 * failure rather than a silently truncated reply.
 */
export async function streamChatMessage(
  conversationId: string,
  content: string,
  attachments: ChatAttachment[],
  onEvent: SseEventHandler,
): Promise<void> {
  return streamSse(
    `/api/chat/conversations/${conversationId}/messages`,
    { content, attachments },
    onEvent,
  );
}

/**
 * Ingest a PDF and return the source the chat can reference.
 *
 * Tries the presigned direct-to-S3 route first and falls back to a server
 * upload, mirroring components/file-upload.tsx. That duplication is
 * deliberate for now: the upload component interleaves progress reporting
 * with each step, and unpicking it is a bigger change than this needs.
 */
export async function uploadPdfSource(file: File): Promise<UploadedSource> {
  let presign: {
    url?: string;
    fields?: Record<string, string>;
    key?: string;
  } | null = null;

  try {
    presign = await fetchJson<{
      url?: string;
      fields?: Record<string, string>;
      key?: string;
    }>("/api/documents/presign", {
      method: "POST",
      body: JSON.stringify({
        name: file.name,
        content_type: file.type,
        size: file.size,
      }),
    });
  } catch {
    presign = null;
  }

  if (presign?.url && presign.fields && presign.key) {
    try {
      const s3form = new FormData();
      Object.entries(presign.fields).forEach(([k, v]) => s3form.append(k, v));
      s3form.append("file", file);

      const uploadRes = await fetch(presign.url, {
        method: "POST",
        body: s3form,
      });
      if (!uploadRes.ok) {
        throw new Error(`S3 rejected the upload (${uploadRes.status})`);
      }

      return await fetchJson<UploadedSource>("/api/documents/confirm", {
        method: "POST",
        body: JSON.stringify({
          key: presign.key,
          name: file.name,
          content_type: file.type,
        }),
      });
    } catch (error) {
      // Fall through to the server upload rather than failing the attachment.
      // A presigned POST straight from the browser is the one step in this
      // flow that depends on the bucket's CORS rules, and those are set
      // outside the app — when they are wrong (or the bucket is in another
      // region, or an extension blocks the cross-origin POST) every direct
      // upload fails while the server-side route is perfectly healthy. That
      // is exactly the state the generator form has always been in, since it
      // only ever used the server route.
      console.warn("Direct-to-S3 upload failed, falling back to server:", error);
    }
  }

  const formData = new FormData();
  formData.append("file", file);
  return fetchForm<UploadedSource>("/api/documents/upload", formData);
}

export interface UploadedSource {
  pdfSourceId: string;
  /** "ready" for a deduped/cached source, otherwise "processing". */
  status?: string;
  warnings?: string[];
}

export interface SourceStatus {
  id: string;
  status: string;
  chunk_count: number;
  error?: string | null;
}

export async function fetchSourceStatus(
  sourceId: string,
): Promise<SourceStatus> {
  return fetchJson<SourceStatus>(`/api/documents/${sourceId}/status`, {
    method: "GET",
  });
}

/**
 * Block until an uploaded PDF is actually usable.
 *
 * Ingestion runs on a worker thread and the upload returns as soon as the row
 * is saved, so a source is normally `processing` for a while after it appears
 * to have uploaded. The generation endpoint refuses a request that names one
 * (`DOCUMENTS_NOT_READY`), so attaching without waiting produces a Generate
 * button that fails minutes later for no visible reason.
 */
export async function waitForPdfSource(
  sourceId: string,
  { timeoutMs = 240000, intervalMs = 2000 }: { timeoutMs?: number; intervalMs?: number } = {},
): Promise<SourceStatus> {
  const deadline = Date.now() + timeoutMs;

  for (;;) {
    const status = await fetchSourceStatus(sourceId);
    if (status.status === "ready") return status;
    if (status.status === "error") {
      throw new ApiError(
        status.error || "This PDF could not be processed.",
        422,
      );
    }
    if (Date.now() > deadline) {
      throw new ApiError(
        "This PDF is taking unusually long to process. It will keep going — " +
          "try again in a minute.",
        504,
      );
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

export interface DetectSubjectResponse {
  detected: boolean;
  subject: string | null;
  confidence: number;
  error?: string | null;
}

export async function detectPdfSubject(file: File): Promise<DetectSubjectResponse> {
  const formData = new FormData();
  formData.append("file", file);
  return fetchForm<DetectSubjectResponse>("/api/documents/detect-subject", formData);
}

export interface PdfAnalysisResult {
  fileName: string;
  hash: string;
  subject: string | null;
  board: string | null;
  class: string | null;
  chapter: string | null;
  documentType: string;
  confidence: number;
  isEducational: boolean;
  pagesAnalyzed: number;
  error?: string | null;
  fromCache?: boolean;
}

export interface PdfValidationMismatch {
  file?: string;
  subject?: string;
  board?: string;
  class?: string;
  chapter?: string;
  documentType?: string;
  reason?: string;
}

export interface PdfValidationReport {
  valid: boolean;
  errorType?: "SUBJECT_MISMATCH" | "BOARD_MISMATCH" | "CLASS_MISMATCH" | "UNSUPPORTED_DOCUMENT" | "LOW_CONFIDENCE";
  message?: string;
  mismatches: PdfValidationMismatch[];
  subject?: string | null;
  board?: string | null;
  class?: string | null;
  chapter?: string | null;
  chapters?: string[];
}

export async function analyzePdfDocument(file: File): Promise<PdfAnalysisResult> {
  const formData = new FormData();
  formData.append("file", file);
  return fetchForm<PdfAnalysisResult>("/api/documents/analyze-pdf", formData);
}

export async function validatePdfMetadata(documents: PdfAnalysisResult[]): Promise<PdfValidationReport> {
  return fetchJson<PdfValidationReport>("/api/documents/validate-metadata", {
    method: "POST",
    body: JSON.stringify({ documents }),
  });
}



// ── General Instructions Mode: designing a paper from prose ─────────────
//
// `/design-paper` reads free-form instructions and returns the paper they
// describe plus the constraints they did not settle. Cheap (one small model
// call), writes nothing, and safe to call while the teacher is still typing —
// callers debounce it. See `services/paper_design.py`.

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

/** Where one question slot's content comes from. */
export type SlotSource = "generate" | "saved";

/** One question position, as the Blueprint Builder edits it. */
export interface BlueprintSlot {
  index: number;
  sectionTitle: string;
  questionType: string;
  marks: number;
  source: SlotSource;
  choiceRequired: boolean;
  /** Engine fields the Builder does not show. Round-trip untouched. */
  passthrough?: Record<string, unknown>;
}

/**
 * Totals arrive computed from the slots — the backend never echoes back a
 * total the client sent. Treat them as read-only: to change a total, change
 * the slots.
 */
export interface Blueprint {
  slots: BlueprintSlot[];
  totalQuestions: number;
  totalMarks: number;
  generatedCount: number;
  savedCount: number;
  byType: Record<string, number>;
  bySection: { title: string; questions: number; marks: number }[];
}

export const EMPTY_BLUEPRINT: Blueprint = {
  slots: [],
  totalQuestions: 0,
  totalMarks: 0,
  generatedCount: 0,
  savedCount: 0,
  byType: {},
  bySection: [],
};

/** A built-in starting point. Generated server-side; never a stored row. */
export interface BuiltinTemplate {
  id: string;
  name: string;
  description: string;
  kind: "cbse_blueprint" | "blank" | "instructions";
  builtin: true;
  board: string;
  academicClass: string;
  subject: string;
  settings: Record<string, string>;
}

export interface PaperTemplate {
  id: string;
  name: string;
  instructions: string;
  settings: Record<string, string>;
  blueprint: Blueprint;
  /** True when the teacher edited slots, so the stored blueprint is authoritative. */
  pinned: boolean;
  builtin: false;
  base_template_id: string;
  source_config: Record<string, unknown>;
  /** Which folder this is filed in; null means unfiled, a normal resting state. */
  folderId: string | null;
  last_used_at: string | null;
  created_at: string;
  updated_at: string;
}

/** Anything the picker can show. Switch on `builtin` to tell them apart. */
export type PickableTemplate = BuiltinTemplate | PaperTemplate;

export interface QuestionTypeOption {
  code: string;
  label: string;
  group: string;
  defaultMarks: number;
}

/** Built-ins and the teacher's own, in one call — the picker shows one grid. */
export async function fetchTemplateCatalog(params?: {
  subject?: string;
  academicClass?: string;
}): Promise<{ templates: PaperTemplate[]; builtin: BuiltinTemplate[] }> {
  const query = new URLSearchParams();
  if (params?.subject) query.set("subject", params.subject);
  if (params?.academicClass) query.set("class", params.academicClass);
  const suffix = query.toString() ? `?${query}` : "";
  const data = await fetchJson<{
    templates: PaperTemplate[];
    builtin: BuiltinTemplate[];
  }>(`/api/generation/templates${suffix}`, { method: "GET" });
  return { templates: data.templates ?? [], builtin: data.builtin ?? [] };
}

/**
 * Compile a template into an editable blueprint. Writes nothing, so browsing
 * the picker never commits the teacher to anything.
 */
/**
 * Settings the resolve read off the template itself — out of a plain-English
 * brief, or off the board card that was picked. Only the keys it actually
 * settled are present, because the Builder writes these over a form the
 * teacher may already have touched: absent means "leave their setting alone",
 * which a null or an empty string could not say.
 */
export interface DetectedSettings {
  subject?: string;
  academicClass?: string;
  totalMarks?: number;
  numberOfSets?: string;
  difficulty?: string;
}

export interface ResolvedTemplate {
  blueprint: Blueprint;
  template?: PaperTemplate;
  detected?: DetectedSettings;
  /** What the designer had to change, e.g. a stated total the slots miss. */
  corrections?: string[];
}

export async function resolveTemplate(body: {
  templateId: string;
  subject?: string;
  academicClass?: string;
  difficulty?: string;
  instructions?: string;
  savedCount?: number;
}): Promise<ResolvedTemplate> {
  return fetchJson<ResolvedTemplate>("/api/generation/templates/resolve", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/**
 * The per-slot type menu for the Blueprint Builder. Served so the
 * subject-appropriate mapping can change server-side.
 *
 * Distinct from `fetchQuestionTypes` above, which returns the `QuestionType`
 * DB vocabulary used for classifying saved questions. Same words, different
 * jobs: this one is a menu a teacher picks from.
 */
export async function fetchQuestionTypeMenu(
  subject?: string,
): Promise<QuestionTypeOption[]> {
  const suffix = subject ? `?subject=${encodeURIComponent(subject)}` : "";
  const data = await fetchJson<{ questionTypes: QuestionTypeOption[] }>(
    `/api/generation/question-types${suffix}`,
    { method: "GET" },
  );
  return data.questionTypes ?? [];
}

// ── On-demand question images ──────────────────────────────────────────────

export type QuestionImageStyle = "line_art" | "realistic" | "cartoon";

export interface QuestionImageStyleOption {
  value: QuestionImageStyle;
  label: string;
  description: string;
}

/** The style picker's options. Served so adding one needs no frontend release. */
export async function fetchQuestionImageStyles(): Promise<
  QuestionImageStyleOption[]
> {
  const data = await fetchJson<{ styles: QuestionImageStyleOption[] }>(
    "/api/generation/question-image",
    { method: "GET" },
  );
  return data.styles ?? [];
}

/**
 * Draw a figure for one question.
 *
 * Slow — image generation is tens of seconds — so the caller must show
 * progress. `timeoutMs` is raised well above the default for that reason: the
 * default would abort a request that was going to succeed.
 */
export async function generateQuestionImage(body: {
  questionText: string;
  style: QuestionImageStyle;
}): Promise<{ imageUrl: string; style: QuestionImageStyle; cached: boolean }> {
  return fetchJson<{
    imageUrl: string;
    style: QuestionImageStyle;
    cached: boolean;
  }>("/api/generation/question-image", {
    method: "POST",
    body: JSON.stringify(body),
    timeoutMs: 180_000,
  });
}

export async function fetchPaperTemplates(): Promise<PaperTemplate[]> {
  const data = await fetchJson<{ templates: PaperTemplate[] }>(
    "/api/generation/templates",
    { method: "GET" },
  );
  return data.templates ?? [];
}

/**
 * Save, or overwrite the template of the same name.
 *
 * Either `instructions` or `blueprint` is required — a teacher who edited
 * slots should not also have to write prose describing what they did.
 */
export async function savePaperTemplate(body: {
  name: string;
  instructions?: string;
  settings?: Record<string, string>;
  blueprint?: { slots: BlueprintSlot[] };
  baseTemplateId?: string;
  sourceConfig?: Record<string, unknown>;
  folderId?: string | null;
}): Promise<PaperTemplate> {
  const data = await fetchJson<{ template: PaperTemplate }>(
    "/api/generation/templates",
    { method: "POST", body: JSON.stringify(body) },
  );
  return data.template;
}

/** Fetch a template's contents and mark it as used (drives picker ordering). */
export async function applyPaperTemplate(
  templateId: string,
): Promise<PaperTemplate> {
  const data = await fetchJson<{ template: PaperTemplate }>(
    `/api/generation/templates/${templateId}`,
    { method: "POST", body: JSON.stringify({}) },
  );
  return data.template;
}

export async function deletePaperTemplate(templateId: string): Promise<void> {
  await fetchJson<void>(`/api/generation/templates/${templateId}`, {
    method: "DELETE",
  });
}

/**
 * Edit a saved template in place.
 *
 * Distinct from `savePaperTemplate`, which is create-or-overwrite-by-name, and
 * from `applyPaperTemplate`, which only records that a template was used. Only
 * the keys present in `body` are touched server-side, so a rename cannot blank
 * a blueprint — pass exactly what is changing.
 *
 * `folderId: null` unfiles; `blueprint: null` reverts a pinned template to
 * instruction-driven.
 */
export async function updatePaperTemplate(
  templateId: string,
  body: {
    name?: string;
    instructions?: string;
    settings?: Record<string, string>;
    blueprint?: { slots: BlueprintSlot[] } | null;
    sourceConfig?: Record<string, unknown>;
    folderId?: string | null;
  },
): Promise<PaperTemplate> {
  const data = await fetchJson<{ template: PaperTemplate }>(
    `/api/generation/templates/${templateId}`,
    { method: "PATCH", body: JSON.stringify(body) },
  );
  return data.template;
}

/**
 * Turn a built-in catalog entry into a row the teacher owns.
 *
 * Built-ins are generated server-side from the engine's eligibility matrix —
 * code, not rows — which is what keeps the picker in step with the engine but
 * also means a built-in has nothing to edit and nowhere to be filed. Forking
 * resolves it once and writes it down; from then on it is an ordinary template.
 */
export async function forkBuiltinTemplate(body: {
  templateId: string;
  name?: string;
  subject?: string;
  academicClass?: string;
  instructions?: string;
  folderId?: string | null;
}): Promise<PaperTemplate> {
  const data = await fetchJson<{ template: PaperTemplate }>(
    "/api/generation/templates/fork",
    { method: "POST", body: JSON.stringify(body) },
  );
  return data.template;
}

/** Copy one of your own templates. The copy starts unused. */
export async function duplicatePaperTemplate(
  templateId: string,
  body: { name?: string; folderId?: string | null } = {},
): Promise<PaperTemplate> {
  const data = await fetchJson<{ template: PaperTemplate }>(
    `/api/generation/templates/${templateId}/duplicate`,
    { method: "POST", body: JSON.stringify(body) },
  );
  return data.template;
}

// ── Template folders ───────────────────────────────────────────────────────
//
// Purely the teacher's filing: nothing in generation reads a folder, and an
// unfiled template is completely usable. See backend `TemplateFolder`.

export interface TemplateFolder {
  id: string;
  name: string;
  /** Null for a root folder. */
  parentId: string | null;
  /** Templates filed directly here — not counting subfolders. */
  templateCount: number;
  created_at: string;
  updated_at: string;
}

export async function fetchTemplateFolders(): Promise<TemplateFolder[]> {
  const data = await fetchJson<{ folders: TemplateFolder[] }>(
    "/api/generation/template-folders",
    { method: "GET" },
  );
  return data.folders ?? [];
}

export async function createTemplateFolder(body: {
  name: string;
  parentId?: string | null;
}): Promise<TemplateFolder> {
  const data = await fetchJson<{ folder: TemplateFolder }>(
    "/api/generation/template-folders",
    { method: "POST", body: JSON.stringify(body) },
  );
  return data.folder;
}

/** Rename (`name`) or re-file (`parentId`, null for root) one folder. */
export async function updateTemplateFolder(
  folderId: string,
  body: { name?: string; parentId?: string | null },
): Promise<TemplateFolder> {
  const data = await fetchJson<{ folder: TemplateFolder }>(
    `/api/generation/template-folders/${folderId}`,
    { method: "PATCH", body: JSON.stringify(body) },
  );
  return data.folder;
}

/**
 * Delete a folder. Its subfolders go with it; the templates inside do not —
 * they fall back to unfiled. Tidying up filing must never destroy a recipe.
 */
export async function deleteTemplateFolder(folderId: string): Promise<void> {
  await fetchJson<void>(`/api/generation/template-folders/${folderId}`, {
    method: "DELETE",
  });
}

// ── Brand kit ──────────────────────────────────────────────────────────────
//
// A school's identity, stored once and applied to every paper instead of being
// retyped into each header. See backend `services/brand_kit.py`.

export interface BrandAsset {
  id: string;
  name: string;
  kind: string;
  /**
   * The app's own stable `/media/...` URL, minted per read. Never a presigned
   * S3 link — a saved paper outlives any signature, and never a direct bucket
   * URL either: html2canvas taints the canvas on a cross-origin image and the
   * whole PDF export fails.
   */
  url: string;
  width: number | null;
  height: number | null;
}

export interface BrandKit {
  instituteName: string;
  instituteAddress: string;
  accentColor: string;
  fontFamily: string;
  headerLayout: Record<string, unknown>;
  logos: BrandAsset[];
}

/** Reads the kit, creating an empty one server-side on first touch. */
export async function fetchBrandKit(): Promise<BrandKit> {
  const data = await fetchJson<{ brandKit: BrandKit }>("/api/auth/brand-kit", {
    method: "GET",
  });
  return data.brandKit;
}

/** Updates only the fields present in `body`; everything else is left alone. */
export async function updateBrandKit(body: {
  instituteName?: string;
  instituteAddress?: string;
  accentColor?: string;
  fontFamily?: string;
  headerLayout?: Record<string, unknown>;
}): Promise<BrandKit> {
  const data = await fetchJson<{ brandKit: BrandKit }>("/api/auth/brand-kit", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
  return data.brandKit;
}

/** Uploads a logo to the brand kit, so the next paper already has it. */
export async function uploadBrandLogo(
  file: File,
  name?: string,
): Promise<BrandAsset> {
  const form = new FormData();
  form.append("file", file);
  if (name) form.append("name", name);
  const data = await fetchForm<{ asset: BrandAsset }>(
    "/api/auth/brand-kit/assets",
    form,
  );
  return data.asset;
}

export async function renameBrandLogo(
  assetId: string,
  name: string,
): Promise<BrandAsset> {
  const data = await fetchJson<{ asset: BrandAsset }>(
    `/api/auth/brand-kit/assets/${assetId}`,
    { method: "PATCH", body: JSON.stringify({ name }) },
  );
  return data.asset;
}

export async function deleteBrandLogo(assetId: string): Promise<void> {
  await fetchJson<void>(`/api/auth/brand-kit/assets/${assetId}`, {
    method: "DELETE",
  });
}
