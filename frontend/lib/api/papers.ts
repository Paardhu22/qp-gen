/** Projects, papers and questions: list, save, update, trash and restore, export and answer scripts. */
"use client";

import { FetchJsonOptions, fetchJson } from "@/lib/api/http";

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
