import { savePaper, updatePaper, fetchPaper } from "@/lib/api-client";

/**
 * Shape the Django API returns for a paper detail.
 * (id, title, content, projectName, created_at, updated_at)
 */
type DjangoPaper = {
  id: string;
  title: string;
  content: string;
  projectName?: string;
  created_at?: string;
  updated_at?: string;
};

/**
 * Shape the editor expects when it loads a paper.
 * `class` and `subject` are parsed back out of `projectName`.
 */
export type EditorPaper = {
  id: string;
  content: string;
  examName: string;
  class: string;
  subject: string;
  updatedAt?: string;
};

/**
 * Parse the Django response into the shape the editor uses.
 * projectName format: "<class> — <subject>"  (em-dash)
 */
function toEditorPaper(paper: DjangoPaper): EditorPaper {
  const parts = (paper.projectName || "").split(" — ");
  return {
    id: paper.id,
    content: paper.content,
    examName: paper.title,
    class: parts[0]?.trim() || "",
    subject: parts[1]?.trim() || "",
    updatedAt: paper.updated_at,
  };
}

/**
 * Save a new paper via the Django backend.
 *
 * Auth is handled by api-client (JWT Bearer token), NOT better-auth.
 * Django stores the paper as:
 *   title       = examName
 *   projectName = "<class> — <subject>"
 *   content     = raw HTML from the editor
 */
export async function savePaperAction(
  data: {
    class: string;
    subject: string;
    examName: string;
    content: string;
    questionRefs: string[];
  },
  signal?: AbortSignal,
): Promise<{ success: boolean; paperId: string }> {
  return savePaper<{ success: boolean; paperId: string }>(
    {
      projectName: `${data.class} — ${data.subject}`,
      title: data.examName,
      content: data.content,
      questions: [],
    },
    signal,
  );
}

/**
 * Update an existing paper via the Django backend.
 */
export async function updatePaperAction(
  paperId: string,
  data: {
    class?: string;
    subject?: string;
    examName?: string;
    content?: string;
    questionRefs?: string[];
  },
  signal?: AbortSignal,
): Promise<{ success: boolean; paperId: string }> {
  return updatePaper<{ success: boolean; paperId: string }>(
    paperId,
    {
      projectName: `${data.class ?? ""} — ${data.subject ?? ""}`,
      title: data.examName ?? "",
      content: data.content ?? "",
      questions: [],
    },
    signal,
  );
}

/**
 * Load a saved paper by ID.
 * Returns the shape the editor expects (examName, class, subject).
 */
export async function getPaperAction(paperId: string): Promise<EditorPaper> {
  const paper = await fetchPaper<DjangoPaper>(paperId);
  return toEditorPaper(paper);
}
