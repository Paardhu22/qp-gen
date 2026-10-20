/**
 * The first few questions of a saved paper, as plain one-line-ish text for a
 * library card. Pure and tolerant: anything it cannot read yields fewer
 * questions, never an exception, because a card must not break the page.
 */

import { extractDoc } from "../paper-breakdown";

export interface PreviewQuestion {
  number: number;
  text: string;
}

type Node = {
  type?: string;
  attrs?: Record<string, unknown> | null;
  content?: Node[];
  text?: string;
};

const QUESTION_NODES = new Set(["questionBlock", "groupedQuestionBlock"]);

const LATEX_GLYPHS: [RegExp, string][] = [
  [/\\times/g, "×"],
  [/\\div/g, "÷"],
  [/\\cdot/g, "·"],
  [/\\pm/g, "±"],
  [/\\neq/g, "≠"],
  [/\\leq?/g, "≤"],
  [/\\geq?/g, "≥"],
  [/\\approx/g, "≈"],
  [/\\theta/g, "θ"],
  [/\\alpha/g, "α"],
  [/\\beta/g, "β"],
  [/\\pi/g, "π"],
  [/\\circ/g, "°"],
  [/\\sqrt\{([^{}]*)\}/g, "√$1"],
  [/\\frac\{([^{}]*)\}\{([^{}]*)\}/g, "$1/$2"],
  [/\\(?:left|right|,|;|!)/g, ""],
  [/[{}]/g, ""],
  [/\^2/g, "²"],
  [/\^3/g, "³"],
  [/\\/g, ""],
];

/** A readable approximation of a LaTeX fragment. Good enough for a thumbnail. */
function plainLatex(latex: string): string {
  return LATEX_GLYPHS.reduce((s, [re, to]) => s.replace(re, to), latex).trim();
}

function inlineText(node: Node): string {
  if (node.text) return node.text;
  if (node.type === "inlineMath" || node.type === "mathBlock") {
    return plainLatex(String(node.attrs?.latex ?? ""));
  }
  if (node.type === "hardBreak") return " ";
  return (node.content ?? []).map(inlineText).join("");
}

/** The question's own wording: its first non-empty paragraph. */
function questionText(node: Node): string {
  for (const child of node.content ?? []) {
    if (child.type !== "paragraph" && child.type !== "heading") continue;
    const text = inlineText(child).replace(/\s+/g, " ").trim();
    if (text) return text;
  }
  return inlineText(node).replace(/\s+/g, " ").trim();
}

export function extractQuestionPreview(raw: unknown, max = 4): PreviewQuestion[] {
  const doc = extractDoc(raw) as Node | null;
  if (!doc) return [];

  const out: PreviewQuestion[] = [];
  const walk = (node: Node) => {
    if (out.length >= max) return;
    if (node.type && QUESTION_NODES.has(node.type)) {
      const text = questionText(node);
      if (text) out.push({ number: out.length + 1, text });
      return;
    }
    node.content?.forEach(walk);
  };
  doc.content?.forEach(walk);
  return out;
}
