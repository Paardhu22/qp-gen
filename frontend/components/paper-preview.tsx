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
import { useEffect, useMemo } from "react";
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
    const parsed = JSON.parse(content);
    const doc =
      parsed?.type === "doc"
        ? parsed
        : parsed?.editorJSON?.type === "doc"
        ? parsed.editorJSON
        : parsed?.document?.type === "doc"
        ? parsed.document
        : null;
    return doc ? ensurePageDocument(doc) : null;
  } catch {
    return null;
  }
}

export function PaperPreview({ content }: { content: string | undefined }) {
  const doc = useMemo(() => toDocument(content), [content]);

  const editor = useEditor(
    {
      editable: false,
      immediatelyRender: false,
      extensions: previewExtensions,
      content: doc ?? { type: "doc", content: [{ type: "page", content: [{ type: "paragraph" }] }] },
      editorProps: {
        attributes: {
          class: "document-editor focus:outline-none text-black",
        },
      },
    },
    [],
  );

  // Refresh when a different paper is selected.
  useEffect(() => {
    if (editor && doc) editor.commands.setContent(doc);
  }, [editor, doc]);

  if (!doc) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        This paper has no previewable content.
      </div>
    );
  }

  return (
    <div className="paper-preview-scroll h-full overflow-auto bg-muted/40 p-4 sm:p-6">
      <div className="mx-auto max-w-[820px]">
        <EditorContent editor={editor} />
      </div>
    </div>
  );
}
