"use client";

// Read-only render of a saved paper for the Question Bank split view.
//
// Reuses the SAME TipTap node/mark extensions the editor registers (see the
// `useEditor` extensions array in components/tiptap-editor.tsx) so the preview
// matches what the editor and exports produce — but WITHOUT the interactive /
// side-effecting pieces: no PaginationEngine reflow, no Placeholder, no Focus /
// Dropcursor / Gapcursor / CharacterCount, no toolbar, no autosave, no store.
// `editable: false` makes the whole surface non-interactive.
//
// NOTE: this extension list must stay in sync with the editor's. If the editor
// gains a new custom node, add it here too or the preview will drop that node.

import { useEditor, EditorContent } from "@tiptap/react";
import { useEffect, useMemo, useRef } from "react";
import { normalizeInitialContent } from "@/components/tiptap-editor";
import { isEnglishSubject } from "@/lib/subject";
import StarterKit from "@tiptap/starter-kit";
import { OrderedList } from "@tiptap/extension-list";
import Typography from "@tiptap/extension-typography";
import Underline from "@tiptap/extension-underline";
import TextAlign from "@tiptap/extension-text-align";
import { Table } from "@tiptap/extension-table";
import { TableRow } from "@tiptap/extension-table-row";
import { TableCell } from "@tiptap/extension-table-cell";
import { TableHeader } from "@tiptap/extension-table-header";
import Superscript from "@tiptap/extension-superscript";
import Subscript from "@tiptap/extension-subscript";
import Highlight from "@tiptap/extension-highlight";
import Color from "@tiptap/extension-color";
import { TextStyle } from "@tiptap/extension-text-style";
import FontFamily from "@tiptap/extension-font-family";
import HardBreak from "@tiptap/extension-hard-break";
import ImageResize from "tiptap-extension-resize-image";

import {
  QuestionBlock,
  SectionBlock,
  InstructionBlock,
  QuestionGroupBlock,
  GroupedQuestionBlock,
} from "./editor/extensions/nodes";
import { PaperHeaderBlock as PaperHeaderBlockExt } from "./editor/extensions/header-node";
import { OrGroupInvariant } from "./editor/extensions/or-group-invariant";
import { MathBlock, InlineMath } from "./editor/extensions/math-nodes";
import { FloatImage } from "./editor/extensions/float-image";
import { PaginatedDocument } from "./editor/extensions/document-node";
import { PageNode } from "./editor/extensions/page-node";
import { FontSize } from "./editor/extensions/font-size";
import { LineHeight } from "./editor/extensions/line-height";
import { Indent as IndentExtension } from "./editor/extensions/indent";
import { ensurePageDocument } from "./editor/pagination-utils";

const previewExtensions = [
  PaginatedDocument,
  PageNode,
  StarterKit.configure({
    document: false,
    heading: { levels: [1, 2, 3, 4, 5, 6] },
    dropcursor: false,
    gapcursor: false,
    hardBreak: false,
    underline: false,
    orderedList: false,
  }),
  OrderedList.extend({ addInputRules() { return []; } }),
  Typography,
  Underline,
  Superscript,
  Subscript,
  Highlight.configure({ multicolor: true }),
  TextStyle,
  Color,
  FontFamily,
  FontSize,
  LineHeight,
  IndentExtension,
  TextAlign.configure({
    types: ["heading", "paragraph", "questionBlock", "groupedQuestionBlock", "sectionBlock", "instructionBlock"],
  }),
  ImageResize.configure({ inline: true, allowBase64: true }),
  FloatImage,
  Table.configure({ resizable: false }),
  TableRow,
  TableHeader,
  TableCell,
  QuestionBlock,
  SectionBlock,
  InstructionBlock,
  QuestionGroupBlock,
  GroupedQuestionBlock,
  OrGroupInvariant,
  PaperHeaderBlockExt,
  MathBlock,
  InlineMath,
  HardBreak,
];

/** Unwrap the persisted content string into a page-document TipTap JSON. */
function toDocument(content: string | undefined) {
  if (!content || !content.trim()) return null;
  try {
    const doc = normalizeInitialContent(content);
    return doc || null;
  } catch {
    return null;
  }
}

export function PaperPreview({
  content,
  subject,
}: {
  content: string | undefined;
  subject?: string | null;
}) {
  const doc = useMemo(() => toDocument(content), [content]);

  const editor = useEditor(
    {
      editable: false,
      immediatelyRender: false,
      extensions: previewExtensions,
      content: doc ?? { type: "doc", content: [{ type: "page", content: [{ type: "paragraph" }] }] },
      editorProps: {
        attributes: {
          // The editor's paper styling (white page, question/marks layout) is
          // keyed to this ID in globals.css — the preview must carry it to
          // render identically. Safe: the real editor is never mounted on the
          // same page as this preview.
          id: "tiptap-paper-container",
          class: "document-editor focus:outline-none text-black",
        },
      },
    },
    [],
  );

  // Refresh when a different paper — or a different SET of the same paper —
  // is selected.
  //
  // Deferred to a microtask rather than run inline. Every block in a paper is
  // a React NodeView, and TipTap mounts those through `flushSync`; calling
  // `setContent` straight from an effect runs that flush while React is still
  // committing, which React refuses to do ("flushSync was called from inside a
  // lifecycle method"). It skips the flush, the NodeViews never get their
  // synchronous mount, and because a read-only editor dispatches no further
  // transactions nothing ever re-renders them — so switching to Set B swapped
  // the document but left the previous set's blocks on screen. A microtask
  // runs after the commit, where the flush is legal.
  // Seeded with the FIRST render's `doc` — the very value `useEditor` was
  // constructed with (its dep array is empty, so it captures render one).
  // Re-setting that same document would discard NodeViews that are already
  // correct, and on a null first render it would skip the first real document
  // entirely and leave the preview blank.
  const appliedDocRef = useRef<unknown>(doc);
  useEffect(() => {
    if (!editor || !doc) return;
    if (appliedDocRef.current === doc) return;
    appliedDocRef.current = doc;

    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled || editor.isDestroyed) return;
      editor.commands.setContent(doc, { emitUpdate: false });
    });
    return () => {
      cancelled = true;
    };
  }, [editor, doc]);

  if (!doc) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        This paper has no previewable content.
      </div>
    );
  }

  return (
    <div
      className={`paper-preview-scroll h-full overflow-auto bg-muted/40 p-4 sm:p-6${
        isEnglishSubject(subject) ? " is-english-paper" : ""
      }`}
    >
      <EditorContent editor={editor} />
    </div>
  );
}
