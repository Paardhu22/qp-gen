"use client";

import { getAccessToken } from "@/lib/token-storage";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

type FetchJsonOptions = RequestInit & {
  skipAuth?: boolean;
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

export async function fetchJson<T>(
  path: string,
  options: FetchJsonOptions = {},
): Promise<T> {
  const { skipAuth, timeoutMs = 10000, ...requestInit } = options;
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

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...requestInit,
      headers,
      signal: controller.signal,
    });
  } catch (err: unknown) {
    if (err instanceof Error && err.name === "AbortError") {
      throw new ApiError("Request timed out. Please try again.", 408);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}));
    const message = errorBody?.detail || errorBody?.error || "Request failed";
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
    const message = errorBody?.detail || errorBody?.error || "Request failed";
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

export async function fetchProjectsWithQuestions<T>(): Promise<T> {
  return fetchJson<T>("/api/projects/?withQuestions=true", { method: "GET" });
}

export async function fetchPapers<T>(): Promise<T> {
  return fetchJson<T>("/api/projects/papers/", { method: "GET" });
}

export async function fetchPaper<T>(paperId: string): Promise<T> {
  return fetchJson<T>(`/api/projects/papers/${paperId}/`, { method: "GET" });
}

export async function saveQuestions<T>(
  payload: Record<string, any>,
): Promise<T> {
  return fetchJson<T>("/api/projects/questions/save", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function savePaper<T>(payload: Record<string, any>): Promise<T> {
  return fetchJson<T>("/api/projects/papers/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updatePaper<T>(
  paperId: string,
  payload: Record<string, any>,
): Promise<T> {
  return fetchJson<T>(`/api/projects/papers/${paperId}/`, {
    method: "PUT",
    body: JSON.stringify(payload),
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
