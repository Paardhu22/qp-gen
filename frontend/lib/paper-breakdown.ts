// Parse a saved paper's stored TipTap content into a structural breakdown for
// the Question Bank split-view left panel. Mirrors the node shape the editor
// writes (see components/tiptap-editor.tsx `normalizeInitialContent` /
// `buildDocument`) and the backend walk in
// services/answer_script_service._extract_questions_from_content:
//
//   doc -> page[] -> [ sectionBlock, questionBlock{attrs:{marks,questionType}},
//                      groupedQuestionBlock, instructionBlock, ... ]
//
// Pure + side-effect free so it can be unit-checked with mock JSON.

export type PaperSection = {
  title: string;
  questionCount: number;
  marks: number;
};

export type PaperBreakdown = {
  totalQuestions: number;
  totalMarks: number;
  sectionCount: number;
  sections: PaperSection[];
  /** questionType (normalized upper-case) -> count */
  typeDistribution: Record<string, number>;
};

type TipTapNode = {
  type?: string;
  attrs?: Record<string, unknown> | null;
  content?: TipTapNode[];
  text?: string;
};

const QUESTION_NODES = new Set(["questionBlock", "groupedQuestionBlock"]);
const DEFAULT_SECTION = "Ungrouped";

/** Unwrap the doc from the several shapes papers are persisted in. */
function extractDoc(raw: unknown): TipTapNode | null {
  let parsed: unknown = raw;
  if (typeof raw === "string") {
    const trimmed = raw.trim();
    if (!trimmed) return null;
    try {
      parsed = JSON.parse(trimmed);
    } catch {
      return null;
    }
  }
  if (!parsed || typeof parsed !== "object") return null;
  const p = parsed as Record<string, unknown>;
  if ((p as TipTapNode).type === "doc") return p as TipTapNode;
  if ((p.editorJSON as TipTapNode)?.type === "doc") return p.editorJSON as TipTapNode;
  if ((p.document as TipTapNode)?.type === "doc") return p.document as TipTapNode;
  return null;
}

/** Flatten a section/question node's text content into a trimmed string. */
function nodeText(node: TipTapNode): string {
  if (node.text) return node.text;
  if (!node.content) return "";
  return node.content.map(nodeText).join("").trim();
}

function coerceMarks(attrs: Record<string, unknown> | null | undefined): number {
  const raw = attrs?.marks;
  const n = typeof raw === "number" ? raw : parseInt(String(raw ?? ""), 10);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

function coerceType(attrs: Record<string, unknown> | null | undefined): string {
  const raw = String(attrs?.questionType ?? "").trim().toUpperCase();
  return raw || "OTHER";
}

/**
 * Walk the doc depth-first. `sectionBlock` nodes open a new section bucket;
 * subsequent question nodes accumulate into the current section. Recurses
 * through `page` (and any wrapper) nodes so pagination doesn't hide questions.
 */
export function computePaperBreakdown(rawContent: unknown): PaperBreakdown {
  const doc = extractDoc(rawContent);
  const empty: PaperBreakdown = {
    totalQuestions: 0,
    totalMarks: 0,
    sectionCount: 0,
    sections: [],
    typeDistribution: {},
  };
  if (!doc) return empty;

  const sections: PaperSection[] = [];
  const typeDistribution: Record<string, number> = {};
  let current: PaperSection | null = null;

  const ensureSection = (title: string): PaperSection => {
    const section: PaperSection = { title, questionCount: 0, marks: 0 };
    sections.push(section);
    return section;
  };

  const walk = (node: TipTapNode) => {
    const type = node.type;
    if (type === "sectionBlock") {
      current = ensureSection(nodeText(node) || DEFAULT_SECTION);
      return; // its text children aren't questions
    }
    if (type && QUESTION_NODES.has(type)) {
      if (!current) current = ensureSection(DEFAULT_SECTION);
      const marks = coerceMarks(node.attrs);
      const qtype = coerceType(node.attrs);
      current.questionCount += 1;
      current.marks += marks;
      typeDistribution[qtype] = (typeDistribution[qtype] ?? 0) + 1;
      return; // don't descend into sub-questions as separate questions
    }
    node.content?.forEach(walk);
  };

  doc.content?.forEach(walk);

  const totalQuestions = sections.reduce((a, s) => a + s.questionCount, 0);
  const totalMarks = sections.reduce((a, s) => a + s.marks, 0);

  return {
    totalQuestions,
    totalMarks,
    sectionCount: sections.length,
    sections,
    typeDistribution,
  };
}

/** Human label for a normalized questionType code. */
export function questionTypeLabel(code: string): string {
  const map: Record<string, string> = {
    MCQ: "MCQ",
    ASSERTION_REASON: "Assertion–Reason",
    SHORT: "Short answer",
    SHORT_ANSWER: "Short answer",
    LONG: "Long answer",
    LONG_ANSWER: "Long answer",
    VSA: "Very short",
    CASE_STUDY: "Case study",
    TF: "True / False",
    OTHER: "Other",
  };
  return map[code] ?? code.replace(/_/g, " ").toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
}
