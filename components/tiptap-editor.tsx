"use client";

import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Typography from "@tiptap/extension-typography";
import Placeholder from "@tiptap/extension-placeholder";
import Underline from "@tiptap/extension-underline";
import TextAlign from "@tiptap/extension-text-align";
import Image from "@tiptap/extension-image";
import { Table } from "@tiptap/extension-table";
import { TableRow } from "@tiptap/extension-table-row";
import { TableCell } from "@tiptap/extension-table-cell";
import { TableHeader } from "@tiptap/extension-table-header";
import { QuestionItem, SectionHeader } from "./editor/extensions/nodes";
import { templates } from "./editor/templates";
import { 
  Bold, Italic, Underline as UnderlineIcon, Strikethrough, 
  AlignLeft, AlignCenter, AlignRight, AlignJustify,
  Heading1, Heading2, Heading3, 
  List, ListOrdered, Image as ImageIcon,
  Table as TableIcon, Trash, 
  Undo, Redo,
  TableProperties,
  FileDown,
  Printer,
  Calculator,
  PlusCircle,
  Save,
  Wand2,
  Layout
} from "lucide-react";
import { Button } from "./ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { useEditorStore } from "@/store/editor-store";
import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { exportToPDF } from "@/lib/export-pdf";
import { exportToDocx } from "@/lib/export-docx";
import debounce from "lodash.debounce";
import { Badge } from "./ui/badge";

const MenuBar = ({ editor }: { editor: any }) => {
  if (!editor) return null;

  const [totalMarks, setTotalMarks] = useState(0);

  const calculateTotalMarks = useCallback(() => {
    let total = 0;
    editor.state.doc.descendants((node: any) => {
      if (node.type.name === 'questionItem') {
        total += Number(node.attrs.marks) || 0;
      }
    });
    setTotalMarks(total);
    return total;
  }, [editor]);

  useEffect(() => {
    calculateTotalMarks();
  }, [editor?.state.doc, calculateTotalMarks]);

  const handleExportPDF = async () => {
    const filename = `paper-${Date.now()}.pdf`;
    await exportToPDF('tiptap-paper-container', filename);
  };

  const handleExportDocx = async () => {
    const filename = `paper-${Date.now()}.docx`;
    await exportToDocx(editor.getHTML(), filename);
  };

  return (
    <div className="flex flex-col border-b border-zinc-800 bg-zinc-950">
      <div className="flex flex-wrap gap-1 p-2 items-center overflow-x-auto border-b border-zinc-800/50">
        {/* Undo/Redo */}
        <div className="flex items-center gap-1 border-r border-zinc-800 pr-2 mr-1">
          <Button variant="ghost" size="sm" onClick={() => editor.chain().focus().undo().run()} disabled={!editor.can().undo()} className="h-8 w-8 p-0 text-zinc-400 hover:text-zinc-100"><Undo className="h-4 w-4" /></Button>
          <Button variant="ghost" size="sm" onClick={() => editor.chain().focus().redo().run()} disabled={!editor.can().redo()} className="h-8 w-8 p-0 text-zinc-400 hover:text-zinc-100"><Redo className="h-4 w-4" /></Button>
        </div>

        {/* Text Formatting */}
        <div className="flex items-center gap-1 border-r border-zinc-800 pr-2 mr-1">
          <Button variant="ghost" size="sm" onClick={() => editor.chain().focus().toggleBold().run()} className={`h-8 w-8 p-0 ${editor.isActive('bold') ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-400 hover:text-zinc-100'}`}><Bold className="h-4 w-4" /></Button>
          <Button variant="ghost" size="sm" onClick={() => editor.chain().focus().toggleItalic().run()} className={`h-8 w-8 p-0 ${editor.isActive('italic') ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-400 hover:text-zinc-100'}`}><Italic className="h-4 w-4" /></Button>
          <Button variant="ghost" size="sm" onClick={() => editor.chain().focus().toggleUnderline().run()} className={`h-8 w-8 p-0 ${editor.isActive('underline') ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-400 hover:text-zinc-100'}`}><UnderlineIcon className="h-4 w-4" /></Button>
        </div>

        {/* Alignment */}
        <div className="flex items-center gap-1 border-r border-zinc-800 pr-2 mr-1">
          <Button variant="ghost" size="sm" onClick={() => editor.chain().focus().setTextAlign('left').run()} className={`h-8 w-8 p-0 ${editor.isActive({ textAlign: 'left' }) ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-400 hover:text-zinc-100'}`}><AlignLeft className="h-4 w-4" /></Button>
          <Button variant="ghost" size="sm" onClick={() => editor.chain().focus().setTextAlign('center').run()} className={`h-8 w-8 p-0 ${editor.isActive({ textAlign: 'center' }) ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-400 hover:text-zinc-100'}`}><AlignCenter className="h-4 w-4" /></Button>
          <Button variant="ghost" size="sm" onClick={() => editor.chain().focus().setTextAlign('right').run()} className={`h-8 w-8 p-0 ${editor.isActive({ textAlign: 'right' }) ? 'bg-zinc-800 text-zinc-100' : 'text-zinc-400 hover:text-zinc-100'}`}><AlignRight className="h-4 w-4" /></Button>
        </div>

        {/* Paper Structure */}
        <div className="flex items-center gap-1 border-r border-zinc-800 pr-2 mr-1">
          <Button 
            variant="ghost" 
            size="sm" 
            onClick={() => editor.chain().focus().insertContent({ type: 'sectionHeader', content: [{ type: 'text', text: 'SECTION A' }] }).run()} 
            className="h-8 px-2 text-xs text-indigo-400 hover:bg-indigo-500/10"
          >
            <PlusCircle className="h-3 w-3 mr-1" /> Add Section
          </Button>
          <Button 
            variant="ghost" 
            size="sm" 
            onClick={() => editor.chain().focus().insertContent({ type: 'questionItem', attrs: { marks: 2 }, content: [{ type: 'paragraph', content: [{ type: 'text', text: 'Enter question here...' }] }] }).run()} 
            className="h-8 px-2 text-xs text-emerald-400 hover:bg-emerald-500/10"
          >
            <PlusCircle className="h-3 w-3 mr-1" /> Add Question
          </Button>
        </div>

        {/* Table Options */}
        <div className="flex items-center gap-1 border-r border-zinc-800 pr-2 mr-1">
          <Button variant="ghost" size="sm" onClick={() => editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()} className="h-8 w-8 p-0 text-zinc-400 hover:text-zinc-100" title="Insert Table"><TableIcon className="h-4 w-4" /></Button>
          {editor.isActive('table') && (
            <div className="flex items-center gap-1 bg-zinc-900 rounded px-1">
              <Button variant="ghost" size="sm" onClick={() => editor.chain().focus().addColumnAfter().run()} className="h-8 px-2 text-xs text-zinc-400">Add Col</Button>
              <Button variant="ghost" size="sm" onClick={() => editor.chain().focus().addRowAfter().run()} className="h-8 px-2 text-xs text-zinc-400">Add Row</Button>
              <Button variant="ghost" size="sm" onClick={() => editor.chain().focus().deleteTable().run()} className="h-8 w-8 p-0 text-red-400"><Trash className="h-4 w-4" /></Button>
            </div>
          )}
        </div>

        <div className="ml-auto flex items-center gap-3">
          <Select onValueChange={(val) => {
            if (val === 'cbse') editor.commands.setContent(templates.cbse);
            if (val === 'university') editor.commands.setContent(templates.university);
          }}>
            <SelectTrigger className="h-8 w-[140px] bg-zinc-900 border-zinc-800 text-[11px]">
              <Layout className="h-3 w-3 mr-2" />
              <SelectValue placeholder="Apply Template" />
            </SelectTrigger>
            <SelectContent className="bg-zinc-900 border-zinc-800 text-zinc-100">
              <SelectItem value="cbse">CBSE Style</SelectItem>
              <SelectItem value="university">University Style</SelectItem>
            </SelectContent>
          </Select>

          <div className="flex items-center gap-2 px-3 py-1 bg-zinc-900 rounded-full border border-zinc-800">
             <Calculator className="h-3 w-3 text-zinc-500" />
             <span className="text-[11px] font-bold text-zinc-300">Total Marks:</span>
             <Badge variant="secondary" className="h-5 px-1.5 text-[10px] bg-indigo-500/20 text-indigo-400 border-indigo-500/30">{totalMarks}</Badge>
          </div>
          
          <Button 
            variant="outline" 
            size="sm" 
            className="h-8 text-xs bg-indigo-600 hover:bg-indigo-700 text-white border-none"
            onClick={() => useEditorStore.getState().setSaveModalOpen(true)}
          >
            <Save className="h-3 w-3 mr-1" /> Save
          </Button>
        </div>
      </div>

      <div className="flex items-center justify-between px-4 py-1.5 bg-zinc-900/30 text-[11px] text-zinc-500">
        <div className="flex items-center gap-4">
          <button onClick={handleExportPDF} className="hover:text-indigo-400 flex items-center gap-1.5 transition-colors">
            <FileDown className="h-3 w-3" /> Export PDF
          </button>
          <button onClick={handleExportDocx} className="hover:text-indigo-400 flex items-center gap-1.5 transition-colors">
            <FileDown className="h-3 w-3" /> Export DOCX
          </button>
          <button onClick={() => window.print()} className="hover:text-indigo-400 flex items-center gap-1.5 transition-colors">
            <Printer className="h-3 w-3" /> Print Mode
          </button>
        </div>
        <div className="flex items-center gap-2">
           <span className="flex items-center gap-1"><span className="h-1 w-1 rounded-full bg-green-500 animate-pulse"></span> Autosave enabled</span>
        </div>
      </div>
    </div>
  );
};

export const TiptapEditor = () => {
  const [isClient, setIsClient] = useState(false);

  useEffect(() => {
    setIsClient(true);
  }, []);

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: {
          levels: [1, 2, 3],
        },
      }),
      Typography,
      Underline,
      TextAlign.configure({
        types: ['heading', 'paragraph', 'questionItem', 'sectionHeader'],
      }),
      Image,
      Placeholder.configure({
        placeholder: 'Start writing your professional exam paper...',
      }),
      Table.configure({
        resizable: true,
      }),
      TableRow,
      TableHeader,
      TableCell,
      QuestionItem,
      SectionHeader,
    ],
    content: `
      <h1 style="text-align: center; margin-bottom: 0;">ABC INTERNATIONAL SCHOOL</h1>
      <h2 style="text-align: center; margin-top: 0; margin-bottom: 20px; font-weight: bold; font-size: 1.2rem;">ANNUAL EXAMINATION 2026</h2>
      
      <div style="display: flex; justify-content: space-between; border-bottom: 2px solid #333; padding-bottom: 10px; margin-bottom: 20px;">
        <div>
          <p><strong>Subject:</strong> Physics</p>
          <p><strong>Class:</strong> XII</p>
        </div>
        <div style="text-align: right;">
          <p><strong>Time:</strong> 3 Hours</p>
          <p><strong>Max Marks:</strong> 100</p>
        </div>
      </div>

      <p><strong>General Instructions:</strong></p>
      <ul>
        <li>All questions are compulsory.</li>
        <li>Question numbers 1 to 5 are very short answer questions.</li>
        <li>Use of calculator is not permitted.</li>
      </ul>

      <div data-type="section-header">SECTION A (Objective Type Questions)</div>
      
      <div data-type="question" data-marks="2" data-number="1">
        <p>Define electric flux. Is it a scalar or vector quantity?</p>
      </div>

      <div data-type="question" data-marks="2" data-number="2">
        <p>A point charge q is placed at the center of a cube. What is the flux through any one face of the cube?</p>
      </div>
    `,
    editorProps: {
      attributes: {
        id: 'tiptap-paper-container',
        class: 'prose prose-sm sm:prose-base dark:prose-invert prose-zinc max-w-none focus:outline-none min-h-[1000px] p-12 md:p-16 lg:p-20 bg-white text-black dark:bg-zinc-950 dark:text-zinc-100 border border-zinc-200 dark:border-zinc-800 shadow-2xl mx-auto my-8 max-w-[850px] paper-shadow print:shadow-none print:my-0 print:border-none',
      },
    },
    onUpdate: ({ editor }) => {
      debouncedUpdate(editor);
    }
  });

  const debouncedUpdate = useCallback(
    debounce((editor: any) => {
      import("./editor/extensions/auto-numbering").then(({ updateQuestionNumbers }) => {
        updateQuestionNumbers(editor);
      });
    }, 1000),
    []
  );

  const { questionsToAppend, clearQuestionsToAppend } = useEditorStore();

  useEffect(() => {
    if (questionsToAppend.length > 0 && editor) {
      questionsToAppend.forEach((q) => {
        editor.chain().focus().insertContent({
          type: 'questionItem',
          attrs: { 
            marks: q.marks || 1,
          },
          content: [
            { 
              type: 'paragraph', 
              content: [{ type: 'text', text: q.content }] 
            }
          ]
        }).run();
      });
      clearQuestionsToAppend();
    }
  }, [questionsToAppend, editor, clearQuestionsToAppend]);

  if (!isClient) return null;

  const paperStyles = `
    .question-item .question-number {
       font-family: serif;
       font-size: 1.1rem;
    }
    .question-item::before {
      content: attr(data-number) ".";
      position: absolute;
      left: 0;
      font-weight: bold;
      font-family: serif;
    }
    @media print {
      body * {
        visibility: hidden;
      }
      #tiptap-paper-container, #tiptap-paper-container * {
        visibility: visible;
      }
      #tiptap-paper-container {
        position: absolute;
        left: 0;
        top: 0;
        width: 100%;
        padding: 0 !important;
        margin: 0 !important;
        color: black !important;
        background: white !important;
      }
      .custom-scrollbar {
        overflow: visible !important;
      }
    }
  `;

  return (
    <div className="flex-1 flex flex-col h-full bg-zinc-900/50 overflow-hidden">
      <MenuBar editor={editor} />
      <div className="flex-1 overflow-y-auto custom-scrollbar bg-zinc-900/50 p-4 print:p-0">
        <EditorContent editor={editor} className="h-full pb-32" />
      </div>
      
      <style dangerouslySetInnerHTML={{ __html: paperStyles }} />
    </div>
  );
};
