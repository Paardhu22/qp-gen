"use client";

import { getAccessToken } from "@/lib/token-storage";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

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

  // Bail immediately if the caller already cancelled before we even started.
  if (callerSignal?.aborted) throw new SyncCancelledError();

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  // Forward the caller's cancellation into our internal controller so a single
  // AbortSignal drives the actual fetch.
  const forwardAbort = () => controller.abort();
  callerSignal?.addEventListener("abort", forwardAbort, { once: true });

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...requestInit,
      headers,
      signal: controller.signal,
    });
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
  const headers: Record<string, string> = {};
  const accessToken = getAccessToken();
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    body: formData,
    headers,
  });

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

type SseEventHandler = (event: string, data: any) => void;

export async function streamSse(
  path: string,
  payload: Record<string, any>,
  onEvent: SseEventHandler,
): Promise<void> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  const accessToken = getAccessToken();
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });

  if (!response.ok || !response.body) {
    const errorBody = await response.json().catch(() => ({}));
    const message =
      errorBody?.detail || errorBody?.error || "Stream request failed";
    throw new ApiError(message, response.status);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

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
        if (line.startsWith("event:")) {
          event = line.replace("event:", "").trim();
        } else if (line.startsWith("data:")) {
          data += line.replace("data:", "").trim();
        }
      }

      if (!data) continue;
      try {
        onEvent(event, JSON.parse(data));
      } catch (error) {
        onEvent("error", { error: "Failed to parse stream payload" });
      }
    }
  }
}

export async function fetchProjects<T>(): Promise<T> {
  return fetchJson<T>("/api/projects/", { method: "GET" });
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

export async function generateAnswerScript(
  paperId: string,
): Promise<{ answer_script_paper_id: string; editor_url: string }> {
  return fetchJson<{ answer_script_paper_id: string; editor_url: string }>(
    `/api/generation/papers/${paperId}/generate-answer-script/`,
    {
      method: "POST",
      // Answer generation may take a while for papers with many questions
      timeoutMs: 300000,
    },
  );
}
