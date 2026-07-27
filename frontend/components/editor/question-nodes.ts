/**
 * Block mapping — one place where a generated question becomes editor nodes.
 *
 * There were three copies of this conversion inside `tiptap-editor.tsx`: the
 * initial-content path (Set B / Set C), the `questionsToAppend` path (live
 * auto-insert) and the `sectionsToAppend` path (review tray / comparison
 * workspace). They drifted, which is how a question could render one way when
 * streamed and another way when loaded from a saved set. Everything now routes
 * through `buildQuestionBlock` here.
 *
 * The MCQ rule lives here too. A multiple-choice question is not a paragraph
 * that happens to start with "A." — it is a `questionBlock` carrying
 * `questionType: "MCQ"` whose options are an `orderedList`, which is what the
 * MCQ toolbar preset inserts and what `.question-body ol li::before` styles as
 * "(A) (B) (C) (D)". Generated MCQs frequently arrive with their options
 * written into the stem text instead of the `options` array; `splitStemAndOptions`
 * pulls them back out so both sources produce the same block.
 */

// LaTeX delimiter contract (matches the LLM prompt directive in
// generation_router.py): inline math = \( ... \), display math = \[ ... \].
// $...$ is also accepted as a tolerant fallback because the editor's existing
// `$x$` InputRule already trained users on it; we transform it into the same
// inlineMath node so the rendered output is consistent.
const DISPLAY_MATH_RE = /\\\[([\s\S]+?)\\\]/g;
const INLINE_MATH_RE = /\\\(([\s\S]+?)\\\)|\$([^\n$]+?)\$/g;

/**
 * One option line: "A. text", "(a) text", "A) text", "1. text".
 * The label must be followed by a separator AND whitespace, so a sentence
 * beginning "A wire carries…" is never mistaken for option A.
 */
const OPTION_LINE_RE = /^\s*\(?\s*([A-Da-d]|[1-4])\s*[.)\]]\s+(\S.*)$/;

/** Sequences an option label can legally follow. */
const OPTION_SEQUENCES = [
  ["A", "B", "C", "D"],
  ["a", "b", "c", "d"],
  ["1", "2", "3", "4"],
];

/**
 * Question types whose body legitimately contains lettered or numbered parts
 * that are NOT top-level options: a reading passage's sub-questions, a grammar
 * task set's twelve items, an extract's four parts, a case study's (i)/(ii).
 * Pulling those apart would shred the question, so option extraction is
 * skipped entirely for them.
 */
const COMPOSITE_TYPES = new Set([
  "READING_COMP",
  "GRAMMAR",
  "CASE_STUDY",
  "EXTRACT_PROSE",
  "EXTRACT_POETRY",
  "ANALYTICAL_PARAGRAPH",
  "LETTER",
  "COMPOSITION",
  "SOURCE_BASED",
  "PASSAGE_UNSEEN",
]);

/** Types that are option-bearing by definition. */
const OPTION_TYPES = new Set([
  "MCQ",
  "MCQ_SINGLE",
  "MCQ_MULTI",
  "ASSERTION_REASON",
  "TRUE_FALSE",
  "MULTIPLE_CHOICE",
]);

const normalizeType = (raw: unknown) =>
  String(raw ?? "")
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_");

export function isCompositeQuestionType(type: unknown): boolean {
  return COMPOSITE_TYPES.has(normalizeType(type));
}

export function isOptionBearingType(type: unknown): boolean {
  return OPTION_TYPES.has(normalizeType(type));
}

// ── Inline / display math ───────────────────────────────────────────────

export function buildInlineRun(text: string): any[] {
  const out: any[] = [];
  let cursor = 0;
  INLINE_MATH_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = INLINE_MATH_RE.exec(text))) {
    if (m.index > cursor) {
      out.push({ type: "text", text: text.slice(cursor, m.index) });
    }
    const latex = (m[1] ?? m[2] ?? "").trim();
    if (latex) {
      out.push({ type: "inlineMath", attrs: { latex } });
    }
    cursor = m.index + m[0].length;
  }
  if (cursor < text.length) {
    out.push({ type: "text", text: text.slice(cursor) });
  }
  return out.length > 0 ? out : [{ type: "text", text }];
}

function pushTextBlocks(chunk: string, blocks: any[]) {
  const lines = chunk
    .split(/\n{2,}|\n/)
    .map((l) => l.trim())
    .filter(Boolean);
  for (const line of lines) {
    blocks.push({ type: "paragraph", content: buildInlineRun(line) });
  }
}

export function buildQuestionContentNodes(content: string) {
  const raw = String(content || "");
  if (!raw.trim()) {
    return [{ type: "paragraph" }];
  }

  // First split out display-math segments as standalone block nodes; the
  // remaining string is processed paragraph-by-paragraph with inline math.
  const blocks: any[] = [];
  let cursor = 0;
  DISPLAY_MATH_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = DISPLAY_MATH_RE.exec(raw))) {
    if (m.index > cursor) {
      pushTextBlocks(raw.slice(cursor, m.index), blocks);
    }
    const latex = (m[1] ?? "").trim();
    if (latex) {
      blocks.push({ type: "mathBlock", attrs: { latex, displayMode: true } });
    }
    cursor = m.index + m[0].length;
  }
  if (cursor < raw.length) {
    pushTextBlocks(raw.slice(cursor), blocks);
  }

  return blocks.length > 0 ? blocks : [{ type: "paragraph" }];
}

// ── Option extraction ───────────────────────────────────────────────────

/**
 * Split a question stem from options the generator wrote into the stem text.
 *
 * Only a trailing, contiguous, correctly-sequenced run of 2–6 option lines
 * counts. Every one of those conditions is load-bearing:
 *
 *  • trailing + contiguous — "A." mid-paragraph is prose, not an option;
 *  • sequenced from the first label — guards against a stem that ends with a
 *    parenthetical "(a) note" or two unrelated lettered asides;
 *  • 2–6 — an MCQ has four options, an assertion-reason four, a true/false
 *    two; twelve "options" means we are looking at a grammar task set;
 *  • short lines — a 400-word paragraph starting "D. " is not an option.
 *
 * Returns the original stem and an empty array when the text does not hold a
 * clean option block, so the caller can fall back to whatever `options` the
 * backend sent.
 */
export function splitStemAndOptions(content: string): {
  stem: string;
  options: string[];
} {
  const raw = String(content || "");
  const lines = raw.split(/\r?\n/);
  if (lines.length < 3) return { stem: raw, options: [] };

  // Walk backwards over the trailing option-shaped lines.
  const trailing: { label: string; text: string }[] = [];
  let index = lines.length - 1;
  for (; index >= 0; index -= 1) {
    const line = lines[index];
    if (!line.trim()) {
      // A blank line ends the run only once we have started collecting.
      if (trailing.length > 0) break;
      continue;
    }
    const match = OPTION_LINE_RE.exec(line);
    if (!match) break;
    if (match[2].length > 200) break;
    trailing.unshift({ label: match[1], text: match[2].trim() });
    if (trailing.length > 6) break;
  }

  if (trailing.length < 2 || trailing.length > 6) {
    return { stem: raw, options: [] };
  }

  const sequence = OPTION_SEQUENCES.find((s) => s[0] === trailing[0].label);
  if (!sequence) return { stem: raw, options: [] };
  const followsSequence = trailing.every(
    (item, i) => i < sequence.length && item.label === sequence[i],
  );
  if (!followsSequence) return { stem: raw, options: [] };

  const stem = lines.slice(0, index + 1).join("\n").trim();
  if (!stem) return { stem: raw, options: [] };

  return { stem, options: trailing.map((t) => t.text) };
}

/**
 * The options an inserted question should carry, and the stem left over.
 *
 * The backend's `options` array wins when it has one — it is the structured
 * source of truth. Extraction from the stem is the fallback for the common
 * case where the model wrote the options into the question text instead.
 * When BOTH are present the stem copy is still removed, otherwise the paper
 * prints every option twice.
 */
export function resolveStemAndOptions(question: {
  content?: string;
  options?: string[] | null;
  type?: string;
}): { stem: string; options: string[] } {
  const content = String(question?.content || "");
  const supplied = (question?.options || []).filter(
    (o) => String(o || "").trim().length > 0,
  );

  // True/False renders its own wording; a composite question's lettered parts
  // belong to its sub-questions, not to the question itself.
  if (
    normalizeType(question?.type) === "TF" ||
    isCompositeQuestionType(question?.type)
  ) {
    return { stem: content, options: supplied.length > 0 ? supplied : [] };
  }

  const extracted = splitStemAndOptions(content);
  if (extracted.options.length === 0) {
    return { stem: content, options: supplied };
  }

  // Options existed in both places — keep the structured ones, drop the
  // duplicated copy from the stem.
  return {
    stem: extracted.stem,
    options: supplied.length >= extracted.options.length ? supplied : extracted.options,
  };
}

// ── Figures ─────────────────────────────────────────────────────────────

// Insertion guard for generated figures. We accept ONLY a `data:` URL (the
// validated inline-SVG figure pipeline emits these) or an absolute http(s)://
// URL. Relative paths are also accepted because the FloatImage NodeView
// resolves them against the Django origin at render time. Any other shape
// (blank, "null"/"undefined" literals, hallucinated URLs the backend already
// rejected) produces an empty src that renders as a broken-image icon — in
// that case we skip the floatImage entirely and let the question stem speak
// for itself, matching the backend's "text-self-contained on retry" contract.
export function buildFigureNode(imageUrl: string | undefined | null) {
  const src = String(imageUrl || "").trim();
  if (!src) return null;
  const lower = src.toLowerCase();
  if (lower === "null" || lower === "undefined") return null;
  const isUsable =
    src.startsWith("data:") ||
    lower.startsWith("http://") ||
    lower.startsWith("https://") ||
    src.startsWith("/");
  if (!isUsable) return null;
  return {
    type: "floatImage",
    attrs: { src, align: "center", width: 320 },
  };
}

// ── The block ───────────────────────────────────────────────────────────

export interface InsertableQuestion {
  content: string;
  type?: string;
  options?: string[] | null;
  answer?: string;
  marks?: number;
  image_url?: string;
  metadata?: Record<string, any> | null;
}

/**
 * Build the `questionBlock` node for one generated question.
 *
 * `questionType` is resolved from the payload rather than guessed from the
 * presence of options alone, so an assertion-reason or true/false question
 * keeps its own identity. `slotMeta` carries the blueprint provenance the
 * "Replace question" action needs to regenerate exactly this slot; it is
 * stringified because ProseMirror attributes must survive an HTML round trip.
 */
export function buildQuestionBlock(question: InsertableQuestion): any {
  const { stem, options } = resolveStemAndOptions(question);
  const content: any[] = buildQuestionContentNodes(stem);

  const figureNode = buildFigureNode(question.image_url);
  if (figureNode) content.push(figureNode);

  const declaredType = normalizeType(question.type);
  const hasOptions = options.length > 0 && declaredType !== "TF";

  if (hasOptions) {
    content.push({
      type: "orderedList",
      content: options.map((opt: string) => ({
        type: "listItem",
        content: [{ type: "paragraph", content: buildInlineRun(opt) }],
      })),
    });
  }

  const questionType =
    declaredType || (hasOptions ? "MCQ" : "SHORT");

  return {
    type: "questionBlock",
    attrs: {
      marks: question.marks || 1,
      questionType,
      slotMeta: buildSlotMeta(question),
    },
    content,
  };
}

/** The pieces of a composite question, as sent in `metadata.composite`. */
interface CompositeParts {
  preamble: string;
  body: string[];
  subQuestions: string[];
}

function readCompositeParts(question: InsertableQuestion): CompositeParts | null {
  const raw = question.metadata?.composite;
  if (!raw || typeof raw !== "object") return null;

  const asLines = (value: unknown) =>
    (Array.isArray(value) ? value : [])
      .map((entry) => String(entry ?? "").trim())
      .filter(Boolean);

  const preamble = String(raw.preamble ?? "").trim();
  const body = asLines(raw.body);
  const subQuestions = asLines(raw.subQuestions);

  // A composite with nothing after the preamble is just an ordinary question;
  // splitting it would only cost it its marks cell.
  if (body.length === 0 && subQuestions.length === 0) return null;
  return { preamble, body, subQuestions };
}

/**
 * Every editor node one generated question becomes.
 *
 * Ordinary questions are a single `questionBlock` — one node, as before. A
 * composite (an unseen passage, a grammar task set) is instead emitted as a
 * RUN of sibling page-level blocks: a numbered head carrying the marks and the
 * slot provenance, then the passage body and each sub-question as plain
 * paragraphs.
 *
 * The run is the point. `pagination-engine.ts` breaks a page only *between*
 * a page's top-level children — `splitPageAtIndex` works on `pageNode.child(i)`
 * and never descends — so a 400-word passage inside one block has no seam to
 * break at and is clipped at the page edge. As siblings, the same passage
 * flows onto the next page paragraph by paragraph.
 *
 * Only the head is a `questionBlock`, which keeps `updateQuestionNumbers`
 * honest: the composite consumes exactly one question number, as it did when
 * it was one node, instead of renumbering every sub-question as a question in
 * its own right. The sub-questions keep the "(i) … [2]" labels the backend
 * already renders into their text.
 */
export function buildQuestionBlocks(question: InsertableQuestion): any[] {
  const parts = readCompositeParts(question);
  if (!parts) return [buildQuestionBlock(question)];

  // `options` is dropped from the head: a composite's choices belong to its
  // individual sub-questions, whose text already carries them.
  const head = buildQuestionBlock({
    ...question,
    content: parts.preamble,
    options: [],
  });
  return [
    head,
    ...parts.body.flatMap((chunk) => buildQuestionContentNodes(chunk)),
    ...parts.subQuestions.flatMap((chunk) => buildQuestionContentNodes(chunk)),
  ];
}

/** Blocks that can never be part of a preceding composite's run. */
const STRUCTURAL_BLOCKS = new Set([
  "questionBlock",
  "groupedQuestionBlock",
  "questionGroupBlock",
  "sectionBlock",
  "instructionBlock",
  "paperHeaderBlock",
  "pageBreak",
]);

/**
 * How far a composite question extends past its head block.
 *
 * A composite is a run of siblings with no wrapper node to delimit it, so its
 * end is found structurally: everything after the head that is not itself a
 * numbered or structural block belongs to it. That survives editing — a
 * teacher who adds or deletes a passage paragraph does not invalidate it,
 * which a stored length would.
 */
export function compositeRunSize(parent: any, headIndex: number): number {
  let size = parent.child(headIndex).nodeSize;
  for (let i = headIndex + 1; i < parent.childCount; i += 1) {
    const name = parent.child(i).type?.name;
    if (STRUCTURAL_BLOCKS.has(name)) break;
    size += parent.child(i).nodeSize;
  }
  return size;
}

/**
 * Blueprint provenance for one inserted question, as a JSON string.
 *
 * This is what makes "Replace question" possible from inside the editor: the
 * node remembers which slot it filled, so a replacement can be generated with
 * the same marks, type, section, chapter and generator without regenerating
 * anything else. Returns "" when the payload carries no metadata (a
 * hand-written question), and the Replace control then stays hidden.
 */
export function buildSlotMeta(question: InsertableQuestion): string {
  const meta = question.metadata || {};
  const slotIndex = Number(meta.slotIndex);
  if (!Number.isFinite(slotIndex)) return "";

  const payload = {
    slotIndex,
    section: meta.section ?? "",
    marks: Number(question.marks ?? meta.marks ?? 1),
    type: question.type ?? "",
    generator: meta.generator ?? "question_pool",
    assetType: meta.assetType ?? "",
    chapter: meta.inferredChapter ?? meta.chapterTitle ?? "",
    topic: meta.inferredTopic ?? "",
    difficulty: meta.difficulty ?? "",
    poolId: meta.poolId ?? "",
    questionId: meta.questionId ?? "",
    subject: meta.subject ?? "",
  };

  try {
    return JSON.stringify(payload);
  } catch {
    return "";
  }
}

export function parseSlotMeta(raw: unknown): Record<string, any> | null {
  const text = String(raw || "").trim();
  if (!text) return null;
  try {
    const parsed = JSON.parse(text);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}
