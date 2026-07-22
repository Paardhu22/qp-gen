import { savePaper, updatePaper, fetchPaper } from "@/lib/api-client";

export type PaperSet = {
  id?: string;
  label: string;
  order: number;
  content: string;
  answers?: string;
  metadata?: any;
};

/**
 * Shape the Django API returns for a paper detail.
 */
type DjangoPaper = {
  id: string;
  title: string;
  subject?: string;
  gradeClass?: string;
  board?: string;
  instructions?: string;
  blueprint?: any;
  questionPoolId?: string;
  projectName?: string; // Legacy fallback
  sets?: PaperSet[];
  created_at?: string;
  updated_at?: string;
};

/**
 * Shape the editor expects when it loads a paper.
 */
export type EditorPaper = {
  id: string;
  content: string; // The content of the main set (usually Set A)
  examName: string;
  class: string;
  subject: string;
  board?: string;
  instructions?: string;
  blueprint?: any;
  questionPoolId?: string;
  sets?: PaperSet[];
  updatedAt?: string;
};

/**
 * Parse the Django response into the shape the editor uses.
 */
function toEditorPaper(paper: DjangoPaper): EditorPaper {
  // Graceful fallback for legacy data without subject/class fields
  let c = paper.gradeClass || "";
  let s = paper.subject || "";
  if (!c && !s && paper.projectName) {
    const parts = paper.projectName.split(" — ");
    c = parts[0]?.trim() || "";
    s = parts[1]?.trim() || "";
  }
  
  // Find main content (Set A, or first set, or fallback to empty string)
  let mainContent = "";
  if (paper.sets && paper.sets.length > 0) {
    const setA = paper.sets.find((set) => set.label === "A" || set.label === "Set A") || paper.sets[0];
    mainContent = setA.content;
  }

  return {
    id: paper.id,
    content: mainContent,
    examName: paper.title,
    class: c,
    subject: s,
    board: paper.board,
    instructions: paper.instructions,
    blueprint: paper.blueprint,
    questionPoolId: paper.questionPoolId,
    sets: paper.sets || [],
    updatedAt: paper.updated_at,
  };
}

/**
 * Save a new paper via the Django backend.
 */
export async function savePaperAction(
  data: {
    class: string;
    subject: string;
    examName: string;
    content: string;
    questionRefs: string[];
    hsatSourceIds?: string[];
    board?: string;
    instructions?: string;
    blueprint?: any;
    questionPoolId?: string;
    sets?: PaperSet[];
  },
  signal?: AbortSignal,
): Promise<{ success: boolean; paperId: string }> {
  // If no sets are provided (e.g. legacy/single flow), wrap the content into Set A
  const sets = data.sets?.length ? data.sets : [
    { label: "Set A", order: 1, content: data.content, answers: "", metadata: {} }
  ];

  return savePaper<{ success: boolean; paperId: string }>(
    {
      projectName: `${data.class} — ${data.subject}`,
      title: data.examName,
      subject: data.subject,
      gradeClass: data.class,
      board: data.board || "",
      instructions: data.instructions || "",
      blueprint: data.blueprint,
      questionPoolId: data.questionPoolId || "",
      sets,
      questions: [],
      hsatSourceIds: data.hsatSourceIds || [],
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
    hsatSourceIds?: string[];
    board?: string;
    instructions?: string;
    blueprint?: any;
    questionPoolId?: string;
    sets?: PaperSet[];
  },
  signal?: AbortSignal,
): Promise<{ success: boolean; paperId: string }> {
  // If no sets are provided, wrap the content into Set A
  const sets = data.sets?.length ? data.sets : [
    { label: "Set A", order: 1, content: data.content || "", answers: "", metadata: {} }
  ];

  return updatePaper<{ success: boolean; paperId: string }>(
    paperId,
    {
      projectName: `${data.class ?? ""} — ${data.subject ?? ""}`,
      title: data.examName ?? "",
      subject: data.subject ?? "",
      gradeClass: data.class ?? "",
      board: data.board ?? "",
      instructions: data.instructions ?? "",
      blueprint: data.blueprint,
      questionPoolId: data.questionPoolId ?? "",
      sets,
      questions: [],
      hsatSourceIds: data.hsatSourceIds || [],
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
