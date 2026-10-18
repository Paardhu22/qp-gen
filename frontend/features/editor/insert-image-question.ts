/**
 * Putting a question generated from a teacher's image into the paper.
 *
 * The question arrives in the same shape every generated question does, with
 * `image_url` set, so `buildQuestionBlocks` lays it out exactly as it would any
 * other — the picture above the options, the options as a list — and the editor's
 * own passes number it. It lands straight after the question the cursor is in,
 * or at the end of the paper when the cursor is nowhere useful.
 */

import type { ImageQuestionWire } from "@/lib/api/image-questions";
import { buildQuestionBlocks } from "./question-nodes";

const QUESTION_NODES = new Set(["questionBlock", "groupedQuestionBlock", "questionGroupBlock"]);

/** The end of the last page's content: where "append to the paper" goes. */
export function getLastPageInsertPos(editor: any): number {
  const { doc } = editor.state;
  let lastPage: { node: any; pos: number } | null = null;

  doc.descendants((node: any, pos: number) => {
    if (node.type.name === "page") lastPage = { node, pos };
  });

  if (!lastPage) return doc.content.size;
  const page = lastPage as { node: any; pos: number };
  return page.pos + page.node.nodeSize - 1;
}

/** Straight after the question the cursor is in, else the end of the paper. */
export function questionInsertPos(editor: any): number {
  try {
    const { $from } = editor.state.selection;
    for (let depth = $from.depth; depth > 0; depth -= 1) {
      if (QUESTION_NODES.has($from.node(depth).type.name)) return $from.after(depth);
    }
  } catch {
    // A selection that cannot be resolved falls through to the end of the paper.
  }
  return getLastPageInsertPos(editor);
}

/** The editor nodes for a generated image question (pure: no editor needed). */
export function imageQuestionBlocks(question: ImageQuestionWire): any[] {
  return buildQuestionBlocks({
    content: question.content,
    type: question.type,
    options: question.options,
    answer: question.answer,
    marks: question.marks,
    image_url: question.image_url,
    image_alt: question.image_alt,
    metadata: question.metadata,
  });
}

/** Insert the question; returns where it went, or null if the editor is not ready. */
export function insertImageQuestion(editor: any, question: ImageQuestionWire): number | null {
  if (!editor || editor.isDestroyed) return null;
  const position = questionInsertPos(editor);
  editor.chain().focus().insertContentAt(position, imageQuestionBlocks(question)).run();
  return position;
}
