"use client";

import { getAccessToken } from "@/lib/token-storage";
import { refreshAccessToken } from "@/lib/auth-client";

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
    const errorBody = await response.json().catch(() => ({}));
    // DRF can return field-level errors as { fieldName: ["msg"] } with no top-level
    // "detail" or "error" key. Flatten those into a readable string.
    const message =
      errorBody?.detail ||
      errorBody?.error ||
      (typeof errorBody === "object" && errorBody !== null
        ? Object.entries(errorBody)
            .map(
              ([field, msgs]) =>
                `${field}: ${Array.isArray(msgs) ? msgs.join(", ") : msgs}`,
            )
            .join(" | ")
        : null) ||
      "Request failed";
    throw new ApiError(message, response.status);
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
    const errorBody = await response.json().catch(() => ({}));
    const message =
      errorBody?.detail ||
      errorBody?.error ||
      (typeof errorBody === "object" && errorBody !== null
        ? Object.entries(errorBody)
            .map(
              ([field, msgs]) =>
                `${field}: ${Array.isArray(msgs) ? msgs.join(", ") : msgs}`,
            )
            .join(" | ")
        : null) ||
      "Request failed";
    throw new ApiError(message, response.status);
  }

  return response.json() as Promise<T>;
}

export { API_BASE_URL };

export type SseEventHandler = (event: string, data: any) => void;

export async function streamSse(
  path: string,
  payload: Record<string, any>,
  onEvent: SseEventHandler,
): Promise<void> {
  const buildHeaders = () => {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    const accessToken = getAccessToken();
    if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
    return headers;
  };

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

  if (!response.ok || !response.body) {
    const errorBody = await response.json().catch(() => ({}));
    const message =
      errorBody?.detail || errorBody?.error || "Stream request failed";
    throw new ApiError(message, response.status);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  // A generation is only complete when the backend says so. Anything that
  // cuts the connection first — a proxy read timeout, a killed gunicorn
  // worker, a dropped network — surfaces as a clean `done: true` from
  // `reader.read()`, which used to make this function resolve as if the
  // generation had succeeded. The caller then saw no error and no result.
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
      if (event === "done" || event === "error") sawTerminalEvent = true;
      try {
        onEvent(event, JSON.parse(data));
      } catch (error) {
        onEvent("error", { error: "Failed to parse stream payload" });
      }
    }
  }

  if (!sawTerminalEvent) {
    throw new ApiError(
      "The connection closed before generation finished. This usually means " +
        "the request took longer than the server allows — try again, or " +
        "generate fewer chapters at once.",
      response.status,
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

export async function deletePaper(paperId: string): Promise<void> {
  await fetchJson<void>(`/api/projects/papers/${paperId}/`, {
    method: "DELETE",
  });
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
  errorType?: "SUBJECT_MISMATCH" | "CHAPTER_MISMATCH" | "BOARD_MISMATCH" | "CLASS_MISMATCH" | "UNSUPPORTED_DOCUMENT" | "LOW_CONFIDENCE";
  message?: string;
  mismatches: PdfValidationMismatch[];
  subject?: string | null;
  board?: string | null;
  class?: string | null;
  chapter?: string | null;
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


