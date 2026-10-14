/** HTTP core: authenticated JSON/form fetch with token refresh, and the error types callers catch. */
"use client";

import { getAccessToken } from "@/lib/api/token-storage";
import { ensureFreshTokens, refreshAccessToken } from "@/features/auth/auth-client";
import { API_BASE_URL } from "@/lib/api/api-base-url";

export type FetchJsonOptions = RequestInit & {
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
export async function errorMessageFrom(
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
