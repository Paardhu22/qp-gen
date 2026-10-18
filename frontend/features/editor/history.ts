/**
 * Undo / redo for the paper editor.
 *
 * ProseMirror's history records every transaction as something the user did,
 * and undoes them one event at a time. That is right for typing and wrong for
 * work the editor does on its own, which is most of what it does here: it
 * renumbers questions, rewrites section summaries, moves blocks between pages,
 * and loads documents. Each of those used to become an undo step of its own, so
 * one Ctrl+Z reverted the invisible bookkeeping instead of the user's action,
 * and the next edit threw the redo stack away.
 *
 * The rules this module holds the editor to:
 *
 *  - **Derived work is not history.** Anything computed from the document goes
 *    through `markDerived`. History still maps earlier steps over it, so an old
 *    edit stays undoable after the page breaks have moved.
 *  - **Opening a paper is not an edit.** `loadDocument` keeps the first load of
 *    a fresh editor out of history (otherwise Ctrl+Z empties the paper) and
 *    leaves a reload into a live editor as one ordinary, undoable step.
 *  - **Ctrl+Z works wherever focus is.** A delete button takes focus with it
 *    when it disappears, and a keypress with nothing focused never reaches
 *    ProseMirror. `useGlobalUndoRedo` picks those keystrokes up.
 */

import { useEffect } from "react";
import { redoDepth, undoDepth } from "@tiptap/pm/history";
import type { Transaction } from "@tiptap/pm/state";

/** Keep a transaction out of the undo stack. Position mapping is unaffected. */
export function markDerived<T extends Transaction>(tr: T): T {
  tr.setMeta("addToHistory", false);
  return tr;
}

// ── Keyboard ────────────────────────────────────────────────────────────

export type UndoIntent = "undo" | "redo";

type KeyLike = {
  key: string;
  ctrlKey: boolean;
  metaKey: boolean;
  shiftKey: boolean;
  altKey: boolean;
};

/**
 * What a keystroke asks for, if anything: Ctrl/Cmd+Z undoes, Ctrl/Cmd+Shift+Z
 * and Ctrl+Y redo. Cmd+Y is deliberately left to the browser (History on Mac).
 */
export function undoRedoIntent(event: KeyLike): UndoIntent | null {
  if (event.altKey) return null;
  if (!event.ctrlKey && !event.metaKey) return null;
  const key = event.key.toLowerCase();
  if (key === "z") return event.shiftKey ? "redo" : "undo";
  if (key === "y" && event.ctrlKey && !event.metaKey && !event.shiftKey) return "redo";
  return null;
}

// Fields that keep their own undo stack. Selects, checkboxes, colour pickers
// and the like have none, so a Ctrl+Z with one focused is meant for the paper.
const OWN_UNDO_FIELDS = [
  "textarea",
  "input:not([type])",
  ...["text", "search", "email", "url", "tel", "password", "number"].map(
    (type) => `input[type="${type}"]`,
  ),
  "[contenteditable='']",
  "[contenteditable='true']",
].join(", ");
const OPEN_OVERLAYS = '[role="dialog"], [role="alertdialog"], [role="menu"], [role="listbox"]';

/**
 * Should the page handle this undo keystroke itself?
 *
 * No when the editor has focus (ProseMirror already did), when a text field
 * has focus (it has an undo stack of its own), or when a dialog or menu is
 * open (the keystroke belongs to that). Yes otherwise — focus on the body or
 * on a button, which is where it lands after a click on a delete control.
 */
export function shouldTakeOver(
  target: EventTarget | null,
  editorDom: Element | null | undefined,
  doc: Document = document,
): boolean {
  const el = target instanceof Element ? target : null;
  if (el && editorDom && editorDom.contains(el)) return false;
  if (el?.closest(OWN_UNDO_FIELDS)) return false;
  if (doc.querySelector(OPEN_OVERLAYS)) return false;
  return true;
}

type EditorLike = {
  isDestroyed: boolean;
  isEditable: boolean;
  view?: { dom: Element };
  chain: () => any;
};

function editorDomOf(editor: EditorLike): Element | null {
  try {
    return editor.view?.dom ?? null;
  } catch {
    return null; // the view is not mounted yet
  }
}

/** Make Ctrl+Z / Ctrl+Y act on the paper even when focus is not in it. */
export function useGlobalUndoRedo(editor: EditorLike | null) {
  useEffect(() => {
    if (!editor) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.isComposing) return;
      const intent = undoRedoIntent(event);
      if (!intent) return;
      if (editor.isDestroyed || !editor.isEditable) return;
      if (!shouldTakeOver(event.target, editorDomOf(editor))) return;

      event.preventDefault();
      const chain = editor.chain().focus();
      (intent === "undo" ? chain.undo() : chain.redo()).run();
    };

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [editor]);
}

// ── Loading a document ──────────────────────────────────────────────────

type LoadableEditor = {
  state: any;
  schema: any;
  chain: () => any;
};

/**
 * Put `content` in the editor as the document, without making the load itself
 * something Ctrl+Z can undo — unless the editor already has history.
 *
 * - Fresh editor (nothing to undo or redo): the load is excluded from history.
 *   Otherwise the first Ctrl+Z after opening a paper replaces it with the
 *   empty starter document.
 * - Editor with history: the load is one ordinary step. Its inverse restores
 *   the previous document exactly, and every older step is still valid; a
 *   silent replacement would leave steps that point into text that is gone.
 * - Content identical to what is already there: nothing happens, so a reload
 *   that changes nothing cannot disturb the selection or the undo stack.
 *
 * Returns whether the document was replaced.
 */
export function loadDocument(editor: LoadableEditor, content: unknown): boolean {
  const { state } = editor;

  try {
    const incoming = editor.schema.nodeFromJSON(content);
    if (incoming.eq(state.doc)) return false;
  } catch {
    // Not a document we can compare (a string, or something the schema
    // rejects): let setContent decide what to do with it.
  }

  const hasHistory = undoDepth(state) > 0 || redoDepth(state) > 0;
  const chain = editor.chain();
  if (!hasHistory) chain.setMeta("addToHistory", false);
  chain.setContent(content as never, { emitUpdate: false }).run();
  return true;
}
