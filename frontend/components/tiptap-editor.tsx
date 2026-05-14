"use client";

import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Typography from "@tiptap/extension-typography";
import Placeholder from "@tiptap/extension-placeholder";
import Underline from "@tiptap/extension-underline";
import TextAlign from "@tiptap/extension-text-align";
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
import { MathBlock, InlineMath } from "./editor/extensions/math-nodes";
import { DrawingBlock } from "./editor/extensions/drawing-node";
import { FontSize } from "./editor/extensions/font-size";
import { LineHeight } from "./editor/extensions/line-height";
import { Indent as IndentExtension } from "./editor/extensions/indent";
import { EditorToolbar } from "./editor/toolbar";
import { FindReplace } from "./editor/find-replace";

import { useEditorStore } from "@/store/editor-store";
import { useEffect, useState, useCallback, useRef, memo } from "react";
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
    <div className="flex items-center justify-between px-4 py-1 bg-zinc-950 border-t border-zinc-800 text-[10px] text-zinc-500 select-none flex-shrink-0">
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
const DEFAULT_CONTENT = `
  <h1 style="text-align: center;">ABC INTERNATIONAL SCHOOL</h1>
  <h2 style="text-align: center;">ANNUAL EXAMINATION 2026</h2>

  <table>
    <tbody>
      <tr>
        <td><strong>Subject:</strong> Physics</td>
        <td style="text-align: right;"><strong>Time:</strong> 3 Hours</td>
      </tr>
      <tr>
        <td><strong>Class:</strong> XII</td>
        <td style="text-align: right;"><strong>Max Marks:</strong> 100</td>
      </tr>
    </tbody>
  </table>

  <hr />

  <div data-type="instruction-block">
    <p><strong>General Instructions:</strong></p>
    <p>- All questions are compulsory.</p>
    <p>- Question numbers 1 to 5 are very short answer questions.</p>
    <p>- Use of calculator is not permitted.</p>
  </div>

  <div data-type="section-block">SECTION A (Objective Type Questions)</div>
  
  <div data-type="question-block" data-marks="2" data-number="1">
    <p>Define electric flux. Is it a scalar or vector quantity?</p>
  </div>

  <div data-type="question-block" data-marks="2" data-number="2">
    <p>A point charge q is placed at the center of a cube. What is the flux through any one face of the cube?</p>
  </div>
`;

// ==================================
// Main Editor Component
// ==================================
export const TiptapEditor = () => {
  const [isClient, setIsClient] = useState(false);

  useEffect(() => {
    setIsClient(true);
  }, []);

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
      ImageResize.configure({
        inline: false,
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
    content: DEFAULT_CONTENT,
    editorProps: {
      attributes: {
        id: "tiptap-paper-container",
        class:
          "prose prose-sm sm:prose-base prose-zinc max-w-none focus:outline-none min-h-[1100px] p-16 md:p-20 bg-white text-black shadow-2xl mx-auto my-6 paper-container",
        spellcheck: "true",
      },
    },
    onUpdate: ({ editor }) => {
      debouncedNumbering(editor);
    },
  });

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const debouncedNumbering = useCallback(
    debounce((editor: any) => {
      updateQuestionNumbers(editor);
    }, 800),
    []
  );

  // Handle question insertion from AI generator
  const { questionsToAppend, clearQuestionsToAppend } = useEditorStore();

  useEffect(() => {
    if (questionsToAppend.length > 0 && editor) {
      questionsToAppend.forEach((q) => {
        editor
          .chain()
          .focus()
          .insertContent({
            type: "questionBlock",
            attrs: {
              marks: q.marks || 1,
            },
            content: [
              {
                type: "paragraph",
                content: [{ type: "text", text: q.content }],
              },
            ],
          })
          .run();
      });
      clearQuestionsToAppend();
    }
  }, [questionsToAppend, editor, clearQuestionsToAppend]);

  // Find/Replace state
  const [showFindReplace, setShowFindReplace] = useState(false);

  // Keyboard shortcut for Find
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "f") {
        e.preventDefault();
        setShowFindReplace((v) => !v);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  if (!isClient) return null;

  return (
    <div className="flex-1 flex flex-col h-full bg-zinc-900/50 overflow-hidden">
      {editor && <EditorToolbar editor={editor} onFindReplace={() => setShowFindReplace(v => !v)} />}
      {editor && showFindReplace && (
        <FindReplace editor={editor} onClose={() => setShowFindReplace(false)} />
      )}
      <div className="flex-1 overflow-y-auto custom-scrollbar bg-zinc-900/50 print:p-0">
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
          max-width: 210mm;
          border: 1px solid rgba(63, 63, 70, 0.5);
        }

        .ProseMirror {
          color: #000000 !important;
        }
        /* ===== Question Block Styles ===== */
        .question-block {
          position: relative;
          transition: border-color 0.2s;
        }
        .question-block:hover {
          border-left-color: rgba(99, 102, 241, 0.5);
        }
        .question-block .question-number {
          font-family: 'Times New Roman', serif;
          font-size: 0.95rem;
        }
        .question-block .question-marks {
          opacity: 0.6;
          transition: opacity 0.2s;
        }
        .question-block:hover .question-marks {
          opacity: 1;
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
          page-break-after: always;
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
