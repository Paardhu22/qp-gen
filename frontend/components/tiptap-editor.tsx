"use client";

import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Typography from "@tiptap/extension-typography";
import Placeholder from "@tiptap/extension-placeholder";
import Underline from "@tiptap/extension-underline";
import TextAlign from "@tiptap/extension-text-align";
import Image from "@tiptap/extension-image";
import ImageResize from "tiptap-extension-resize-image";
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
import CharacterCount from "@tiptap/extension-character-count";
import Focus from "@tiptap/extension-focus";
import Dropcursor from "@tiptap/extension-dropcursor";
import Gapcursor from "@tiptap/extension-gapcursor";
import HardBreak from "@tiptap/extension-hard-break";

import {
  QuestionBlock,
  SectionBlock,
  InstructionBlock,
  QuestionGroupBlock,
  PageBreak,
} from "./editor/extensions/nodes";
import { PaperHeaderBlock as PaperHeaderBlockExt } from "./editor/extensions/header-node";
import { MathBlock, InlineMath } from "./editor/extensions/math-nodes";
import { DrawingBlock } from "./editor/extensions/drawing-node";
import { FontSize } from "./editor/extensions/font-size";
import { LineHeight } from "./editor/extensions/line-height";
import { Indent as IndentExtension } from "./editor/extensions/indent";
import { EditorToolbar } from "./editor/toolbar";
import { FindReplace } from "./editor/find-replace";

import { useEditorStore } from "@/store/editor-store";
import { useEffect, useState, useMemo, useRef, memo } from "react";
import debounce from "lodash.debounce";

// ==================================
// Auto-numbering utility
// ==================================
function updateQuestionNumbers(editor: any) {
  if (!editor) return;
  let currentNumber = 1;
  const tr = editor.state.tr;

  editor.state.doc.descendants((node: any, pos: number) => {
    if (node.type.name === "questionBlock") {
      if (node.attrs.number !== currentNumber) {
        tr.setNodeMarkup(pos, undefined, {
          ...node.attrs,
          number: currentNumber,
        });
      }
      currentNumber++;
    }
  });

  if (tr.docChanged) {
    editor.view.dispatch(tr);
  }
}

// ==================================
// Word count status bar
// ==================================
const StatusBar = memo(({ editor }: { editor: any }) => {
  if (!editor) return null;

  const chars = editor.storage.characterCount?.characters() || 0;
  const words = editor.storage.characterCount?.words() || 0;

  return (
    <div className="flex items-center justify-between px-4 py-1 bg-zinc-50 dark:bg-zinc-950 border-t border-zinc-200 dark:border-zinc-800 text-[10px] text-zinc-500 select-none flex-shrink-0">
      <div className="flex items-center gap-4">
        <span>Words: {words}</span>
        <span>Characters: {chars}</span>
      </div>
      <div className="flex items-center gap-4">
        <span>A4 | Portrait</span>
        <span>100%</span>
      </div>
    </div>
  );
});
StatusBar.displayName = "StatusBar";

// ==================================
// Default content for new papers
// ==================================
const DEFAULT_CONTENT = "";

function scrollToDocumentPosition(editor: any, position: number) {
  if (typeof window === "undefined") return;

  window.requestAnimationFrame(() => {
    try {
      const domAtPos = editor.view.domAtPos(Math.max(position + 1, 1));
      const node = domAtPos.node;
      const element =
        node instanceof HTMLElement ? node : node.parentElement;

      element?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    } catch {
      editor.view.dom.scrollIntoView({
        behavior: "smooth",
        block: "end",
      });
    }
  });
}

// ==================================
// Main Editor Component
// ==================================
type TiptapEditorProps = {
  initialContent?: string;
};

export const TiptapEditor = ({ initialContent }: TiptapEditorProps) => {
  const [isClient, setIsClient] = useState(false);

  useEffect(() => {
    setIsClient(true);
  }, []);

  const debouncedNumbering = useMemo(
    () =>
      debounce((editor: any) => {
        updateQuestionNumbers(editor);
      }, 800),
    [],
  );

  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit.configure({
        heading: {
          levels: [1, 2, 3, 4, 5, 6],
        },
        dropcursor: false,
        gapcursor: false,
        hardBreak: false,
        underline: false,
      }),
      Typography,
      Underline,
      Superscript,
      Subscript,
      Highlight.configure({
        multicolor: true,
      }),
      TextStyle,
      Color,
      FontFamily,
      FontSize,
      LineHeight,
      IndentExtension,
      TextAlign.configure({
        types: [
          "heading",
          "paragraph",
          "questionBlock",
          "sectionBlock",
          "instructionBlock",
        ],
      }),
      Image.configure({
        inline: true,
        allowBase64: true,
      }),
      ImageResize.configure({
        inline: true,
        allowBase64: true,
      }),
      Placeholder.configure({
        placeholder: "Start writing your exam paper...",
      }),
      Table.configure({
        resizable: true,
        allowTableNodeSelection: true,
      }),
      TableRow,
      TableHeader,
      TableCell,
      // Custom exam nodes
      QuestionBlock,
      SectionBlock,
      InstructionBlock,
      QuestionGroupBlock,
      PaperHeaderBlockExt,
      MathBlock,
      InlineMath,
      DrawingBlock,
      PageBreak,
      // Utilities
      CharacterCount,
      Focus.configure({
        className: "has-focus",
        mode: "deepest",
      }),
      Dropcursor.configure({
        color: "#6366f1",
        width: 2,
      }),
      Gapcursor,
      HardBreak,
    ],
    content: initialContent ?? DEFAULT_CONTENT,
    editorProps: {
      attributes: {
        id: "tiptap-paper-container",
        class:
          "prose prose-sm sm:prose-base prose-zinc max-w-none focus:outline-none min-h-[1100px] p-16 md:p-20 bg-[#fcfbf9] text-black border border-border/50 mx-auto my-6 paper-container",
        spellcheck: "true",
      },
    },
    onUpdate: ({ editor }) => {
      debouncedNumbering(editor);
    },
  });

  useEffect(() => {
    return () => debouncedNumbering.cancel();
  }, [debouncedNumbering]);

  // Handle question insertion from AI generator
  const questionsToAppend = useEditorStore((state) => state.questionsToAppend);
  const clearQuestionsToAppend = useEditorStore(
    (state) => state.clearQuestionsToAppend,
  );
  const sectionsToAppend = useEditorStore((state) => state.sectionsToAppend);
  const clearSectionsToAppend = useEditorStore(
    (state) => state.clearSectionsToAppend,
  );

  const lastLoadedContentRef = useRef<string | null>(null);

  useEffect(() => {
    if (!editor) return;
    if (initialContent === undefined) return;
    if (lastLoadedContentRef.current === initialContent) return;

    // Mark as loaded immediately so a rapid re-render doesn't fire this twice.
    const content = initialContent;
    lastLoadedContentRef.current = content;

    editor.commands.setContent(content || "", { emitUpdate: false });
  }, [editor, initialContent]);

  useEffect(() => {
    if (questionsToAppend.length === 0 || !editor) return;

    const questions = [...questionsToAppend];
    clearQuestionsToAppend();

    const contentToInsert: any[] = [];
    questions.forEach((q) => {
      const questionContent: any[] = [
        {
          type: "paragraph",
          content: [{ type: "text", text: q.content }],
        },
      ];

      if (q.type !== "TF" && q.options && q.options.length > 0) {
        questionContent.push({
          type: "bulletList",
          content: q.options.map((opt: string) => ({
            type: "listItem",
            content: [
              {
                type: "paragraph",
                content: [{ type: "text", text: opt }],
              },
            ],
          })),
        });
      }

      contentToInsert.push({
        type: "questionBlock",
        attrs: { marks: q.marks || 1 },
        content: questionContent,
      });
    });

    queueMicrotask(() => {
      if (editor.isDestroyed) return;

      const insertPosition = editor.state.doc.content.size;
      editor.commands.insertContentAt(insertPosition, contentToInsert);
      editor.commands.focus("end");
      scrollToDocumentPosition(editor, insertPosition);
    });
  }, [questionsToAppend, editor, clearQuestionsToAppend]);

  // Handle section-wise insertion from AI generator
  useEffect(() => {
    if (sectionsToAppend.length === 0 || !editor) return;

    const sections = [...sectionsToAppend];
    clearSectionsToAppend();

    const contentToInsert: any[] = [];
    sections.forEach((section) => {
      // Insert section header block
      contentToInsert.push({
        type: "sectionBlock",
        content: [{ type: "text", text: section.title }],
      });

      // Insert each question in this section
      section.questions.forEach((q) => {
        const questionContent: any[] = [
          {
            type: "paragraph",
            content: [{ type: "text", text: q.content }],
          },
        ];

        if (q.type !== "TF" && q.options && q.options.length > 0) {
          questionContent.push({
            type: "bulletList",
            content: q.options.map((opt: string) => ({
              type: "listItem",
              content: [
                {
                  type: "paragraph",
                  content: [{ type: "text", text: opt }],
                },
              ],
            })),
          });
        }

        contentToInsert.push({
          type: "questionBlock",
          attrs: { marks: q.marks || 1 },
          content: questionContent,
        });
      });
    });

    queueMicrotask(() => {
      if (editor.isDestroyed) return;

      const insertPosition = editor.state.doc.content.size;
      editor.commands.insertContentAt(insertPosition, contentToInsert);
      editor.commands.focus("end");
      scrollToDocumentPosition(editor, insertPosition);
    });
  }, [sectionsToAppend, editor, clearSectionsToAppend]);

  // Find/Replace state
  const [showFindReplace, setShowFindReplace] = useState(false);

  if (!isClient) return null;

  return (
    <div className="flex-1 flex flex-col h-full bg-zinc-100 dark:bg-zinc-950 overflow-hidden">
      {editor && (
        <EditorToolbar
          editor={editor}
          onFindReplace={() => setShowFindReplace((v) => !v)}
        />
      )}
      {editor && showFindReplace && (
        <FindReplace
          editor={editor}
          onClose={() => setShowFindReplace(false)}
        />
      )}
      <div className="flex-1 overflow-y-auto custom-scrollbar bg-zinc-100 dark:bg-zinc-950 print:p-0">
        <EditorContent editor={editor} className="h-full pb-32" />
      </div>
      {editor && <StatusBar editor={editor} />}

      <style
        dangerouslySetInnerHTML={{
          __html: `
        /* ===== Paper Container ===== */
        .paper-container {
          width: 210mm;
          min-height: 297mm;
          max-width: none;
          margin: 2rem auto;
          border: 1px solid rgba(63, 63, 70, 0.25);
          box-shadow: 0 10px 30px rgba(0,0,0,0.1);
          background: white !important;
          color: black !important;
        }

        .paper-container img,
        .ProseMirror img {
          max-width: 100%;
          height: auto;
        }

        .ProseMirror p img,
        .ProseMirror li img {
          display: inline-block;
          vertical-align: middle;
          max-height: 220px;
        }

        .ProseMirror {
          color: #000000 !important;
          caret-color: #111111 !important;
          background: white !important;
        }
        /* Ensure text cursor is always visible inside question content */
        .question-block [data-node-view-content],
        .question-block [data-node-view-content] * {
          cursor: text !important;
        }
        /* ===== Paper Header ===== */
        .paper-header-block .paper-header-content h1 {
          font-size: 1.8rem;
          font-weight: 800;
          text-transform: uppercase;
          margin: 0;
          line-height: 1.2;
        }
        .paper-header-block .paper-header-content p {
          font-size: 1rem;
          margin: 2px 0;
          color: #333;
        }
        .paper-header-block .paper-header-layout {
          display: flex;
          align-items: flex-start;
          gap: 2rem;
          padding: 1rem;
        }
        .paper-header-block .paper-header-logo {
          flex: 0 0 8rem;
          width: 8rem;
          min-height: 8rem;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .paper-header-block .paper-header-logo-image {
          max-width: 100%;
          max-height: 8rem;
          object-fit: contain;
        }
        .paper-header-block .paper-header-logo-empty {
          display: none;
        }

        /* ===== Question Block Styles ===== */
        .question-block {
          position: relative;
          transition: border-color 0.2s;
        }
        /* Force the first paragraph in a question to have zero top margin */
        .question-block [data-node-view-content] > div > p:first-child,
        .question-block [data-node-view-content] > p:first-child,
        .question-block .question-content > div > p:first-child,
        .question-block .question-content > p:first-child {
          margin-top: 0 !important;
          padding-top: 0 !important;
        }
        .question-block .question-content p:first-child {
          margin-top: 0 !important;
        }
        .question-block:hover {
          border-left-color: rgba(99, 102, 241, 0.5);
        }
        .question-block .question-number {
          font-family: 'Times New Roman', serif;
          font-size: 0.95rem;
        }
        /* ===== Question Block Controls Cursor Override ===== */
        /* ProseMirror sets cursor:text on all editable content. These rules
           ensure the non-editable controls always show the correct cursor
           regardless of ProseMirror's own cascade. */
        .question-block [contenteditable="false"] {
          cursor: default !important;
        }
        .question-block [contenteditable="false"] button {
          cursor: pointer !important;
        }
        .question-block [contenteditable="false"] input[type="number"] {
          cursor: text !important;
        }

        /* ===== Section Block ===== */
        .section-block {
          page-break-before: auto;
          page-break-inside: avoid;
        }

        /* ===== Instruction Block ===== */
        .instruction-block {
          page-break-inside: avoid;
        }

        /* ===== Question Group (OR) ===== */
        .question-group {
          page-break-inside: avoid;
        }

        /* ===== Math Block ===== */
        .math-block {
          page-break-inside: avoid;
        }

        /* ===== Page Break ===== */
        .page-break {
          margin: 2rem -5rem;
          border-top: 2px dashed rgba(99, 102, 241, 0.45);
          page-break-after: always;
          break-after: page;
          position: relative;
        }
        .page-break span {
          background: white;
          color: #71717a;
          border: 1px solid rgba(212, 212, 216, 0.9);
          border-radius: 9999px;
          padding: 0.2rem 0.65rem;
        }

        /* ===== Focus Styles ===== */
        .has-focus {
          border-radius: 2px;
          box-shadow: 0 0 0 1px rgba(99, 102, 241, 0.2);
        }

        /* ===== Table Styles ===== */
        .ProseMirror table {
          border-collapse: collapse;
          width: 100%;
          margin: 16px 0;
          overflow: hidden;
        }
        .ProseMirror table td,
        .ProseMirror table th {
          border: 1px solid rgba(63, 63, 70, 0.5);
          padding: 8px 12px;
          vertical-align: top;
          position: relative;
        }
        .ProseMirror table th {
          background: rgba(63, 63, 70, 0.2);
          font-weight: 600;
        }
        .ProseMirror table .selectedCell {
          background: rgba(99, 102, 241, 0.15);
        }
        .ProseMirror .tableWrapper {
          overflow-x: auto;
          margin: 16px 0;
        }
        .ProseMirror .column-resize-handle {
          position: absolute;
          right: -2px;
          top: 0;
          bottom: 0;
          width: 4px;
          background-color: #6366f1;
          pointer-events: none;
        }

        /* ===== Custom Scrollbar ===== */
        .custom-scrollbar::-webkit-scrollbar {
          width: 6px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: transparent;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: rgba(63, 63, 70, 0.5);
          border-radius: 3px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: rgba(99, 102, 241, 0.5);
        }

        /* ===== List Styles ===== */
        .ProseMirror ul {
          list-style-type: disc;
          padding-left: 1.5em;
        }
        .ProseMirror ol {
          list-style-type: decimal;
          padding-left: 1.5em;
        }

        .question-block ul,
        .question-block ol {
          list-style-type: lower-alpha;
          padding-left: 1.5rem;
        }

        .question-block ul li p,
        .question-block ol li p {
          display: inline;
          margin: 0 !important;
        }

        .ProseMirror ul ul {
          list-style-type: circle;
        }
        .ProseMirror ul ul ul {
          list-style-type: square;
        }
        .ProseMirror ol ol {
          list-style-type: lower-alpha;
        }
        .ProseMirror ol ol ol {
          list-style-type: lower-roman;
        }

        .question-block ul,
        .question-block ol {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          align-items: start;
          column-gap: 2rem;
          row-gap: 0.5rem;
          margin-top: 0.5rem !important;
        }

        .question-block ul li,
        .question-block ol li {
          list-style-position: inside;
          min-width: 0;
          overflow-wrap: anywhere;
          word-break: break-word;
          align-self: start;
        }

        .question-block ul li p,
        .question-block ol li p {
          margin: 0 !important;
          overflow-wrap: anywhere;
          word-break: break-word;
        }

        /* ===== Placeholder ===== */
        .ProseMirror .is-editor-empty:first-child::before {
          content: attr(data-placeholder);
          float: left;
          color: rgba(161, 161, 170, 0.4);
          pointer-events: none;
          height: 0;
          font-style: italic;
        }

        /* ===== Horizontal Rule ===== */
        .ProseMirror hr {
          border: none;
          border-top: 2px solid rgba(63, 63, 70, 0.3);
          margin: 24px 0;
        }

        /* ===== Print Styles ===== */
        @media print {
          body * {
            visibility: hidden;
          }
          #tiptap-paper-container,
          #tiptap-paper-container * {
            visibility: visible;
          }
          #tiptap-paper-container {
            position: absolute;
            left: 0;
            top: 0;
            width: 100%;
            padding: 15mm !important;
            margin: 0 !important;
            color: black !important;
            background: white !important;
            border: none !important;
            box-shadow: none !important;
            max-width: none !important;
          }
          .page-break {
            border: none !important;
            page-break-after: always;
            break-after: page;
            margin: 0 !important;
          }
          .page-break span {
            display: none !important;
          }
          .question-marks span {
            background: transparent !important;
            border: none !important;
            color: #333 !important;
          }
          .custom-scrollbar {
            overflow: visible !important;
          }
        }
      `,
        }}
      />
    </div>
  );
};
