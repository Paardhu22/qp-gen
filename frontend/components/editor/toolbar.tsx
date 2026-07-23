"use client";

import React, { useState, useRef, useEffect, useCallback, useMemo } from "react";
import debounce from "lodash.debounce";
import { type Editor } from "@tiptap/react";
import { cn } from "@/lib/utils";
import {
  ChevronDown,
  Bold,
  Italic,
  Underline as UnderlineIcon,
  Strikethrough,
  Superscript,
  Subscript,
  Paintbrush,
  Highlighter,
  RemoveFormatting,
  AlignLeft,
  AlignCenter,
  AlignRight,
  AlignJustify,
  Heading1,
  Heading2,
  Heading3,
  Heading4,
  Heading5,
  Heading6,
  List,
  ListOrdered,
  Table as TableIcon,
  Trash,
  Undo,
  Redo,
  PlusCircle,
  Save,

  Calculator,
  FileDown,
  Printer,
  Indent,
  Outdent,
  Sigma,
  Image as ImageIcon,
  Eraser,
  Type,
  Palette,
  Minus,
  Columns3,
  RowsIcon,
  Merge,
  Split,
  Search,
  Replace,
  Hash,
  FileText,
  FlaskConical,
  FolderOpen,
  Plus,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { Button } from "../ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import { Badge } from "../ui/badge";
import { useEditorStore } from "@/store/editor-store";
import { exportToPDF } from "@/lib/export-pdf";
import { exportToDocx } from "@/lib/export-docx";
import { uploadExportToS3, type ExportType } from "@/lib/s3-upload";
import { toast } from "sonner";
import { extractPagesFromDoc } from "./pagination-utils";

// ==================================
// Toolbar Button Component
// ==================================
interface ToolbarBtnProps {
  onClick: () => void;
  active?: boolean;
  disabled?: boolean;
  title?: string;
  children: React.ReactNode;
  className?: string;
}

const ToolbarBtn: React.FC<ToolbarBtnProps> = ({
  onClick,
  active,
  disabled,
  title,
  children,
  className,
}) => (
  <button
    type="button"
    onMouseDown={(e) => e.preventDefault()}
    onClick={onClick}
    disabled={disabled}
    title={title}
    className={cn(
      "h-7 w-7 flex items-center justify-center rounded text-muted-foreground hover:text-foreground hover:bg-accent transition-all duration-150 disabled:opacity-30 disabled:cursor-not-allowed",
      active && "bg-accent text-primary ring-1 ring-primary/30",
      className,
    )}
  >
    {children}
  </button>
);

// ==================================
// Color Picker Popover
// ==================================
const COLOR_PALETTE = [
  "#ffffff",
  "#000000",
  "#ef4444",
  "#f97316",
  "#eab308",
  "#22c55e",
  "#06b6d4",
  "#3b82f6",
  "#8b5cf6",
  "#ec4899",
  "#f87171",
  "#fb923c",
  "#facc15",
  "#4ade80",
  "#22d3ee",
  "#60a5fa",
  "#a78bfa",
  "#f472b6",
  "#fca5a5",
  "#fdba74",
  "#fde047",
  "#86efac",
  "#67e8f9",
  "#93c5fd",
  "#c4b5fd",
  "#f9a8d4",
];

const ColorPicker: React.FC<{
  onSelect: (color: string) => void;
  currentColor?: string;
  onClear?: () => void;
  label: string;
}> = ({ onSelect, currentColor, onClear, label }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node))
        setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => setOpen(!open)}
        title={label}
        className="h-7 w-7 flex flex-col items-center justify-center rounded text-muted-foreground hover:text-foreground hover:bg-accent transition-all"
      >
        <Type className="h-3.5 w-3.5" />
        <div
          className="h-0.5 w-4 rounded-full mt-0.5"
          style={{ backgroundColor: currentColor || "#ffffff" }}
        />
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1 z-50 bg-popover border border-border rounded-lg p-2 shadow-xl w-[180px]">
          <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1.5 px-1">
            {label}
          </p>
          <div className="grid grid-cols-6 gap-1">
            {COLOR_PALETTE.map((color) => (
              <button
                key={color}
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  onSelect(color);
                  setOpen(false);
                }}
                className={cn(
                  "h-6 w-6 rounded border border-border hover:scale-110 transition-transform",
                  currentColor === color && "ring-2 ring-primary",
                )}
                style={{ backgroundColor: color }}
              />
            ))}
          </div>
          {onClear && (
            <button
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => {
                onClear();
                setOpen(false);
              }}
              className="mt-2 w-full text-[10px] text-muted-foreground hover:text-foreground py-1 hover:bg-accent rounded transition-colors"
            >
              Remove Color
            </button>
          )}
        </div>
      )}
    </div>
  );
};

// ==================================
// Math Picker Popover
// ==================================
const MATH_TEMPLATES = [
  { label: "Fraction", latex: "\\frac{a}{b}" },
  { label: "Integral", latex: "\\int_{a}^{b} x^2 dx" },
  { label: "Summation", latex: "\\sum_{i=1}^{n} i" },
  { label: "Limit", latex: "\\lim_{x \\to \\infty} f(x)" },
  {
    label: "Matrix",
    latex: "\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}",
  },
  { label: "Square Root", latex: "\\sqrt{x^2 + y^2}" },
];

const CHEMISTRY_TEMPLATES = [
  { label: "Water", latex: "\\text{H}_2\\text{O}" },
  { label: "Carbon Dioxide", latex: "\\text{CO}_2" },
  { label: "Reaction Arrow", latex: "\\rightarrow" },
  { label: "Equilibrium", latex: "\\rightleftharpoons" },
  { label: "Sulfuric Acid", latex: "\\text{H}_2\\text{SO}_4" },
  { label: "Glucose", latex: "\\text{C}_6\\text{H}_{12}\\text{O}_6" },
  {
    label: "Simple Reaction",
    latex: "\\text{A} + \\text{B} \\rightarrow \\text{C}",
  },
];

const ChemistryPicker: React.FC<{
  onInsertInline: (latex: string) => void;
}> = ({ onInsertInline }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node))
        setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => setOpen(!open)}
        title="Insert Chemistry"
        className={cn(
          "h-7 w-7 flex items-center justify-center rounded text-muted-foreground hover:text-foreground hover:bg-accent transition-all",
          open && "bg-accent text-primary",
        )}
      >
        <FlaskConical className="h-3.5 w-3.5" />
      </button>
      {open && (
        <div className="absolute top-full right-0 mt-1 z-50 bg-popover border border-border rounded-lg p-2 shadow-xl w-[200px]">
          <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-2 px-1">
            Chemistry
          </p>
          <div className="flex flex-col gap-1">
            {CHEMISTRY_TEMPLATES.map((tpl) => (
              <button
                key={tpl.label}
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  onInsertInline(tpl.latex);
                  setOpen(false);
                }}
                className="text-left text-[11px] text-foreground hover:text-primary px-2 py-1.5 rounded hover:bg-accent transition-colors"
              >
                {tpl.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

const MathPicker: React.FC<{
  onInsertBlock: (latex: string) => void;
  onInsertInline: (latex: string) => void;
}> = ({ onInsertBlock, onInsertInline }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node))
        setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => setOpen(!open)}
        title="Insert Math"
        className={cn(
          "h-7 w-7 flex items-center justify-center rounded text-muted-foreground hover:text-foreground hover:bg-accent transition-all",
          open && "bg-accent text-primary",
        )}
      >
        <Sigma className="h-3.5 w-3.5" />
      </button>
      {open && (
        <div className="absolute top-full right-0 mt-1 z-50 bg-popover border border-border rounded-lg p-2 shadow-xl w-[220px]">
          <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-2 px-1">
            Math Templates
          </p>
          <div className="flex flex-col gap-1">
            {MATH_TEMPLATES.map((tpl) => (
              <div key={tpl.label} className="flex items-center gap-1">
                <button
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => {
                    onInsertBlock(tpl.latex);
                    setOpen(false);
                  }}
                  className="flex-1 text-left text-[11px] text-foreground hover:text-primary px-2 py-1.5 rounded hover:bg-accent transition-colors"
                >
                  Block: {tpl.label}
                </button>
                <button
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => {
                    onInsertInline(tpl.latex);
                    setOpen(false);
                  }}
                  className="text-[10px] text-muted-foreground hover:text-primary px-2 py-1.5 rounded hover:bg-accent transition-colors"
                  title="Insert Inline"
                >
                  Inline
                </button>
              </div>
            ))}
          </div>
          <div className="mt-2 pt-2 border-t border-border">
            <button
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => {
                onInsertBlock("E = mc^2");
                setOpen(false);
              }}
              className="w-full text-left text-[11px] text-primary hover:text-primary px-2 py-1.5 rounded hover:bg-primary/10 transition-colors"
            >
              + Custom Math Block
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

// ==================================
// Divider Component
// ==================================
const ToolbarDivider = () => (
  <div className="w-px h-5 bg-border mx-0.5 flex-shrink-0" />
);

// ==================================
// Insert Block Dropdown
// ==================================
interface InsertBlockDropdownProps {
  insertAfterCurrentBlock: (type: string, content?: any, attrs?: any) => void;
  editor: Editor;
}

const InsertBlockDropdown: React.FC<InsertBlockDropdownProps> = ({
  insertAfterCurrentBlock,
  editor,
}) => {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node))
        setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleSelect = (fn: () => void) => {
    fn();
    setOpen(false);
  };

  const options = [
    {
      label: "Header",
      color: "text-teal-500",
      hoverBg: "hover:bg-teal-500/10",
      action: () =>
        insertAfterCurrentBlock("paperHeaderBlock", [
          { type: "heading", attrs: { level: 1 } },
          { type: "heading", attrs: { level: 2 } },
          { type: "paragraph" },
          {
            type: "table",
            content: [
              {
                type: "tableRow",
                content: [
                  { type: "tableCell", attrs: {}, content: [{ type: "paragraph" }] },
                  { type: "tableCell", attrs: {}, content: [{ type: "paragraph" }] },
                ],
              },
            ],
          },
        ]),
    },
    {
      label: "Instructions",
      color: "text-amber-500",
      hoverBg: "hover:bg-amber-500/10",
      action: () =>
        insertAfterCurrentBlock(
          "instructionBlock",
          [
            {
              type: "orderedList",
              content: [
                { type: "listItem", content: [{ type: "paragraph" }] },
              ],
            },
          ],
          { variant: "general" },
        ),
    },
    {
      label: "Section",
      color: "text-primary",
      hoverBg: "hover:bg-primary/10",
      action: () => {
        let sectionCount = 0;
        editor.state.doc.descendants((node: any) => {
          if (node.type.name === "sectionBlock") sectionCount++;
        });
        const letter = String.fromCharCode(65 + sectionCount);
        insertAfterCurrentBlock("sectionBlock", [
          { type: "text", text: `SECTION ${letter}` },
        ]);
      },
    },
    {
      label: "Question",
      color: "text-emerald-500",
      hoverBg: "hover:bg-emerald-500/10",
      action: () =>
        insertAfterCurrentBlock(
          "questionBlock",
          [{ type: "paragraph" }],
          { marks: 2 },
        ),
    },
    {
      label: "MCQ",
      color: "text-rose-500",
      hoverBg: "hover:bg-rose-500/10",
      action: () =>
        insertAfterCurrentBlock(
          "questionBlock",
          [
            { type: "paragraph" },
            {
              type: "orderedList",
              content: [
                { type: "listItem", content: [{ type: "paragraph" }] },
                { type: "listItem", content: [{ type: "paragraph" }] },
                { type: "listItem", content: [{ type: "paragraph" }] },
                { type: "listItem", content: [{ type: "paragraph" }] },
              ],
            },
          ],
          { marks: 1, questionType: "MCQ" },
        ),
    },
    {
      label: "Assertion–Reason",
      color: "text-fuchsia-500",
      hoverBg: "hover:bg-fuchsia-500/10",
      action: () =>
        insertAfterCurrentBlock(
          "questionBlock",
          [
            { type: "paragraph" },
            { type: "paragraph" },
            {
              type: "orderedList",
              content: [
                {
                  type: "listItem",
                  content: [{
                    type: "paragraph",
                    content: [{ type: "text", text: "Both A and R are true, and R is the correct explanation of A." }],
                  }],
                },
                {
                  type: "listItem",
                  content: [{
                    type: "paragraph",
                    content: [{ type: "text", text: "Both A and R are true, but R is not the correct explanation of A." }],
                  }],
                },
                {
                  type: "listItem",
                  content: [{
                    type: "paragraph",
                    content: [{ type: "text", text: "A is true but R is false." }],
                  }],
                },
                {
                  type: "listItem",
                  content: [{
                    type: "paragraph",
                    content: [{ type: "text", text: "A is false but R is true." }],
                  }],
                },
              ],
            },
          ],
          { marks: 1, questionType: "ASSERTION_REASON" },
        ),
    },
    {
      label: "OR Group",
      color: "text-purple-500",
      hoverBg: "hover:bg-purple-500/10",
      action: () => {
        const emptyBranch = (marks: number) => ({
          type: "questionBlock",
          attrs: { marks },
          content: [{ type: "paragraph" }],
        });
        insertAfterCurrentBlock(
          "questionGroupBlock",
          [emptyBranch(5), emptyBranch(5)],
          { label: "Answer any ONE of the following:" },
        );
      },
    },
    {
      label: "Grouped OR",
      color: "text-violet-500",
      hoverBg: "hover:bg-violet-500/10",
      action: () => {
        const groupedBranch = () => ({
          type: "groupedQuestionBlock",
          attrs: { marks: 5 },
          content: [
            { type: "paragraph" },
            {
              type: "orderedList",
              content: [
                { type: "listItem", content: [{ type: "paragraph" }] },
                { type: "listItem", content: [{ type: "paragraph" }] },
              ],
            },
          ],
        });
        insertAfterCurrentBlock(
          "questionGroupBlock",
          [groupedBranch(), groupedBranch()],
          { label: "Answer any ONE of the following:" },
        );
      },
    },
    {
      label: "Grouped Questions",
      color: "text-sky-500",
      hoverBg: "hover:bg-sky-500/10",
      action: () =>
        insertAfterCurrentBlock(
          "groupedQuestionBlock",
          [
            { type: "paragraph" },
            {
              type: "orderedList",
              content: [
                { type: "listItem", content: [{ type: "paragraph" }] },
                { type: "listItem", content: [{ type: "paragraph" }] },
              ],
            },
          ],
          { marks: 5 },
        ),
    },
  ];

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => setOpen(!open)}
        className={cn(
          "h-6 px-2.5 text-[10px] font-semibold rounded transition-colors flex items-center gap-1.5",
          "border border-border bg-background text-foreground hover:bg-accent hover:border-primary/40",
          open && "bg-accent border-primary/40",
        )}
      >
        <PlusCircle className="h-3 w-3 text-primary" />
        Insert Block
        <ChevronDown className={cn("h-3 w-3 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1 z-50 bg-popover border border-border rounded-lg shadow-xl py-1 min-w-[180px]">
          <p className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground px-3 pt-1.5 pb-1">
            Paper Structure
          </p>
          {options.map((opt) => (
            <button
              key={opt.label}
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => handleSelect(opt.action)}
              className={cn(
                "w-full flex items-center gap-2 px-3 py-1.5 text-[11px] font-medium transition-colors text-left",
                opt.color,
                opt.hoverBg,
              )}
            >
              <PlusCircle className="h-3 w-3 shrink-0" />
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

// ==================================
// Font Family Dropdown
// ==================================
const FONT_FAMILIES = [
  { label: "Default", value: "" },
  { label: "Serif", value: "Georgia, serif" },
  { label: "Sans", value: "Inter, sans-serif" },
  { label: "Mono", value: "'Fira Code', monospace" },
  { label: "Arial", value: "Arial, sans-serif" },
  { label: "Times New Roman", value: "'Times New Roman', serif" },
  { label: "Courier New", value: "'Courier New', monospace" },
];

const FONT_SIZES = [
  "8px",
  "10px",
  "11px",
  "12px",
  "14px",
  "16px",
  "18px",
  "20px",
  "24px",
  "28px",
  "32px",
  "36px",
  "48px",
  "64px",
];

const HEADING_LEVELS = [
  { label: "Normal", value: 0 },
  { label: "Heading 1", value: 1 },
  { label: "Heading 2", value: 2 },
  { label: "Heading 3", value: 3 },
  { label: "Heading 4", value: 4 },
  { label: "Heading 5", value: 5 },
  { label: "Heading 6", value: 6 },
];

// ==================================
// Main Toolbar
// ==================================
interface ToolbarProps {
  editor: Editor;
  onFindReplace?: () => void;
  paperId?: string | null;
  exportType?: ExportType;
}

export const EditorToolbar: React.FC<ToolbarProps> = ({
  editor,
  onFindReplace,
  paperId,
  exportType = "question_paper",
}) => {
  const router = useRouter();
  const [totalMarks, setTotalMarks] = useState(0);

  // Cluster B.1/B.2 — re-render the toolbar on every TipTap selection or
  // transaction so `editor.isActive(...)` and `editor.getAttributes(...)`
  // results reflect the LIVE cursor state. Without this the bold/italic
  // buttons, heading dropdown, font/family/size selects, color swatches,
  // alignment buttons and list toggles all read stale state and never
  // visually highlight even when the underlying marks are present in
  // the selection.
  //
  // We use a bumping `tick` instead of mirroring each attribute into its
  // own piece of state because TipTap's `editor.state` is updated
  // synchronously by the editor — we just need React to re-read it.
  const [, setSelectionTick] = useState(0);
  useEffect(() => {
    if (!editor) return;
    const bump = () => setSelectionTick((t) => (t + 1) | 0);
    editor.on("selectionUpdate", bump);
    editor.on("transaction", bump);
    // Initial bump catches the first render after mount, which often
    // happens before the editor has emitted any events.
    bump();
    return () => {
      editor.off("selectionUpdate", bump);
      editor.off("transaction", bump);
    };
  }, [editor]);

  const calculateTotalMarks = useCallback(() => {
    let total = 0;
    editor.state.doc.descendants((node: any) => {
      // OR group = ONE question answered once; count only the first branch's marks.
      if (node.type.name === "questionGroupBlock") {
        let groupMarks = 0;
        node.forEach((child: any) => {
          if (
            groupMarks === 0 &&
            (child.type.name === "questionBlock" ||
              child.type.name === "groupedQuestionBlock")
          ) {
            groupMarks = Number(child.attrs?.marks ?? 0) || 0;
          }
        });
        total += groupMarks;
        return false; // do NOT recurse into the children
      }
      if (
        node.type.name === "questionBlock" ||
        node.type.name === "groupedQuestionBlock"
      ) {
        total += Number(node.attrs.marks) || 0;
      }
    });
    setTotalMarks(total);
  }, [editor]);

  // PERF: subscribe to editor `update` events with a 400 ms debounce
  // instead of re-running on every render (the old `useEffect` deps
  // included `editor?.state.doc`, which is a fresh reference on every
  // transaction — i.e. a full doc walk per keystroke). The badge only
  // needs to be eventually-consistent.
  const debouncedRecount = useMemo(
    () => debounce(() => calculateTotalMarks(), 400),
    [calculateTotalMarks],
  );
  useEffect(() => {
    if (!editor) return;
    calculateTotalMarks();
    editor.on("update", debouncedRecount);
    return () => {
      editor.off("update", debouncedRecount);
      debouncedRecount.cancel();
    };
  }, [editor, calculateTotalMarks, debouncedRecount]);

  // Get current text attributes
  const currentFontFamily = editor.getAttributes("textStyle")?.fontFamily || "";
  const currentFontSize = editor.getAttributes("textStyle")?.fontSize || "";
  const currentTextColor = editor.getAttributes("textStyle")?.color || "";

  // Detect current heading
  const currentHeading = HEADING_LEVELS.find(
    (h) => h.value > 0 && editor.isActive("heading", { level: h.value }),
  );

  const handleExportPDF = async () => {
    const defaultName = `paper-${Date.now()}.pdf`;
    const rawName = window.prompt("Enter a filename for the PDF", defaultName);
    if (!rawName) return;
    const filename = rawName.trim().endsWith(".pdf")
      ? rawName.trim()
      : `${rawName.trim()}.pdf`;
    const toastId = toast.loading("Generating PDF…");
    try {
      const blob = await exportToPDF("tiptap-paper-container", filename);
      toast.success("PDF downloaded!", { id: toastId });
      // Fire-and-forget cloud backup — never blocks the local download.
      if (paperId && paperId !== "current") {
        uploadExportToS3(blob, { exportType, fileFormat: "pdf", paperId })
          .then(() => toast.success("Saved to cloud.", { duration: 2000 }))
          .catch((err) => console.error("[S3 upload]", err));
      }
    } catch (err) {
      console.error(err);
      toast.error("Failed to export PDF. Please try again.", { id: toastId });
    }
  };

  const handleExportDocx = async () => {
    const defaultName = `paper-${Date.now()}.docx`;
    const rawName = window.prompt("Enter a filename for the DOCX", defaultName);
    if (!rawName) return;
    const trimmed = rawName.trim();
    const baseName = /\.docx$/i.test(trimmed)
      ? trimmed
      : trimmed.replace(/\s*docx$/i, "");
    const filename = /\.docx$/i.test(baseName)
      ? baseName
      : `${baseName}.docx`;
    const toastId = toast.loading("Generating DOCX…");
    try {
      const container = document.getElementById("tiptap-paper-container");
      if (!container) throw new Error("Editor container not found.");
      const blob = await exportToDocx(container, filename);
      toast.success("DOCX downloaded!", { id: toastId });
      // Fire-and-forget cloud backup — never blocks the local download.
      if (paperId && paperId !== "current") {
        uploadExportToS3(blob, { exportType, fileFormat: "docx", paperId })
          .then(() => toast.success("Saved to cloud.", { duration: 2000 }))
          .catch((err) => console.error("[S3 upload]", err));
      }
    } catch (err) {
      console.error(err);
      toast.error("Failed to export DOCX. Please try again.", { id: toastId });
    }
  };

  const insertAfterCurrentBlock = (
    type: string,
    content?: any,
    attrs?: any,
  ) => {
    const { state } = editor;
    const { selection } = state;
    const { $from } = selection;

    let insertPos = selection.to;

    // Walk ancestors from innermost → outermost; each time we cross a
    // paperBlock boundary we update insertPos so the FINAL value is always
    // the position AFTER the outermost paperBlock ancestor.  This prevents
    // nested nodes (e.g. a questionBlock inside a questionGroupBlock) from
    // accidentally capturing the new insert inside them.
    for (let depth = $from.depth; depth > 0; depth--) {
      const node = $from.node(depth);
      if (node.type.spec.group?.includes("paperBlock")) {
        insertPos = $from.after(depth);
        // keep walking — we want the outermost boundary, not the innermost
      }
    }

    editor
      .chain()
      .focus()
      .insertContentAt(insertPos, { type, content, attrs })
      .run();
  };

  return (
    <div className="flex flex-col border-b border-border bg-background flex-shrink-0">
      {/* Primary Toolbar — single horizontally-scrollable row on mobile,
          wraps to multiple rows on desktop (lg+). */}
      <div className="editor-toolbar-scroll flex flex-nowrap items-center gap-0.5 px-2 py-1.5 overflow-x-auto no-scrollbar lg:flex-wrap lg:overflow-visible">
        {/* Undo / Redo */}
        <ToolbarBtn
          onClick={() => editor.chain().focus().undo().run()}
          disabled={!editor.can().undo()}
          title="Undo (Ctrl+Z)"
        >
          <Undo className="h-3.5 w-3.5" />
        </ToolbarBtn>
        <ToolbarBtn
          onClick={() => editor.chain().focus().redo().run()}
          disabled={!editor.can().redo()}
          title="Redo (Ctrl+Y)"
        >
          <Redo className="h-3.5 w-3.5" />
        </ToolbarBtn>

        <ToolbarDivider />

        {/* Heading Dropdown */}
        <select
          value={currentHeading?.value || 0}
          onChange={(e) => {
            const level = Number(e.target.value);
            if (level === 0) {
              editor.chain().focus().setParagraph().run();
            } else {
              editor
                .chain()
                .focus()
                .toggleHeading({ level: level as 1 | 2 | 3 | 4 | 5 | 6 })
                .run();
            }
          }}
          className="h-7 bg-muted border border-border rounded text-[11px] text-foreground px-1.5 min-w-[100px] focus:outline-none focus:ring-1 focus:ring-primary/50 cursor-pointer"
        >
          {HEADING_LEVELS.map((h) => (
            <option key={h.value} value={h.value}>
              {h.label}
            </option>
          ))}
        </select>

        {/* Font Family */}
        <select
          value={currentFontFamily}
          onChange={(e) => {
            const val = e.target.value;
            if (val) {
              editor.chain().focus().setFontFamily(val).run();
            } else {
              editor.chain().focus().unsetFontFamily().run();
            }
          }}
          className="h-7 bg-muted border border-border rounded text-[11px] text-foreground px-1.5 min-w-[90px] focus:outline-none focus:ring-1 focus:ring-primary/50 cursor-pointer"
        >
          {FONT_FAMILIES.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label}
            </option>
          ))}
        </select>

        {/* Font Size */}
        <select
          value={currentFontSize}
          onChange={(e) => {
            const val = e.target.value;
            if (val) {
              (editor.chain().focus() as any).setFontSize(val).run();
            } else {
              (editor.chain().focus() as any).unsetFontSize().run();
            }
          }}
          className="h-7 bg-muted border border-border rounded text-[11px] text-foreground px-1.5 w-[60px] focus:outline-none focus:ring-1 focus:ring-primary/50 cursor-pointer"
        >
          <option value="">Size</option>
          {FONT_SIZES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>

        <ToolbarDivider />

        {/* Text Formatting */}
        <ToolbarBtn
          onClick={() => editor.chain().focus().toggleBold().run()}
          active={editor.isActive("bold")}
          title="Bold (Ctrl+B)"
        >
          <Bold className="h-3.5 w-3.5" />
        </ToolbarBtn>
        <ToolbarBtn
          onClick={() => editor.chain().focus().toggleItalic().run()}
          active={editor.isActive("italic")}
          title="Italic (Ctrl+I)"
        >
          <Italic className="h-3.5 w-3.5" />
        </ToolbarBtn>
        <ToolbarBtn
          onClick={() => editor.chain().focus().toggleUnderline().run()}
          active={editor.isActive("underline")}
          title="Underline (Ctrl+U)"
        >
          <UnderlineIcon className="h-3.5 w-3.5" />
        </ToolbarBtn>
        <ToolbarBtn
          onClick={() => editor.chain().focus().toggleStrike().run()}
          active={editor.isActive("strike")}
          title="Strikethrough"
        >
          <Strikethrough className="h-3.5 w-3.5" />
        </ToolbarBtn>
        <ToolbarBtn
          onClick={() => editor.chain().focus().toggleSuperscript().run()}
          active={editor.isActive("superscript")}
          title="Superscript"
        >
          <Superscript className="h-3.5 w-3.5" />
        </ToolbarBtn>
        <ToolbarBtn
          onClick={() => editor.chain().focus().toggleSubscript().run()}
          active={editor.isActive("subscript")}
          title="Subscript"
        >
          <Subscript className="h-3.5 w-3.5" />
        </ToolbarBtn>

        <ToolbarDivider />

        {/* Colors */}
        <ColorPicker
          label="Text Color"
          currentColor={currentTextColor}
          onSelect={(color) => editor.chain().focus().setColor(color).run()}
          onClear={() => editor.chain().focus().unsetColor().run()}
        />
        <ColorPicker
          label="Highlight"
          currentColor={editor.getAttributes("highlight")?.color || ""}
          onSelect={(color) =>
            editor.chain().focus().toggleHighlight({ color }).run()
          }
          onClear={() => editor.chain().focus().unsetHighlight().run()}
        />

        <ToolbarDivider />

        {/* Alignment */}
        <ToolbarBtn
          onClick={() => editor.chain().focus().setTextAlign("left").run()}
          active={editor.isActive({ textAlign: "left" })}
          title="Align Left"
        >
          <AlignLeft className="h-3.5 w-3.5" />
        </ToolbarBtn>
        <ToolbarBtn
          onClick={() => editor.chain().focus().setTextAlign("center").run()}
          active={editor.isActive({ textAlign: "center" })}
          title="Align Center"
        >
          <AlignCenter className="h-3.5 w-3.5" />
        </ToolbarBtn>
        <ToolbarBtn
          onClick={() => editor.chain().focus().setTextAlign("right").run()}
          active={editor.isActive({ textAlign: "right" })}
          title="Align Right"
        >
          <AlignRight className="h-3.5 w-3.5" />
        </ToolbarBtn>
        <ToolbarBtn
          onClick={() => editor.chain().focus().setTextAlign("justify").run()}
          active={editor.isActive({ textAlign: "justify" })}
          title="Justify"
        >
          <AlignJustify className="h-3.5 w-3.5" />
        </ToolbarBtn>

        <ToolbarDivider />

        {/* Indent */}
        <ToolbarBtn
          onClick={() => (editor.commands as any).indent()}
          title="Increase Indent (Tab)"
        >
          <Indent className="h-3.5 w-3.5" />
        </ToolbarBtn>
        <ToolbarBtn
          onClick={() => (editor.commands as any).outdent()}
          title="Decrease Indent (Shift+Tab)"
        >
          <Outdent className="h-3.5 w-3.5" />
        </ToolbarBtn>

        <ToolbarDivider />

        {/* Lists */}
        <ToolbarBtn
          onClick={() => editor.chain().focus().toggleBulletList().run()}
          active={editor.isActive("bulletList")}
          title="Bullet List"
        >
          <List className="h-3.5 w-3.5" />
        </ToolbarBtn>
        <ToolbarBtn
          onClick={() => editor.chain().focus().toggleOrderedList().run()}
          active={editor.isActive("orderedList")}
          title="Numbered List"
        >
          <ListOrdered className="h-3.5 w-3.5" />
        </ToolbarBtn>

        <ToolbarDivider />

        {/* Table */}
        <ToolbarBtn
          onClick={() =>
            editor
              .chain()
              .focus()
              .insertTable({ rows: 3, cols: 3, withHeaderRow: true })
              .run()
          }
          title="Insert Table"
        >
          <TableIcon className="h-3.5 w-3.5" />
        </ToolbarBtn>
        {editor.isActive("table") && (
          <>
            <ToolbarBtn
              onClick={() => editor.chain().focus().addColumnAfter().run()}
              title="Add Column"
            >
              <Columns3 className="h-3.5 w-3.5" />
            </ToolbarBtn>
            <ToolbarBtn
              onClick={() => editor.chain().focus().addRowAfter().run()}
              title="Add Row"
            >
              <RowsIcon className="h-3.5 w-3.5" />
            </ToolbarBtn>
            <ToolbarBtn
              onClick={() => editor.chain().focus().mergeCells().run()}
              title="Merge Cells"
            >
              <Merge className="h-3.5 w-3.5" />
            </ToolbarBtn>
            <ToolbarBtn
              onClick={() => editor.chain().focus().splitCell().run()}
              title="Split Cell"
            >
              <Split className="h-3.5 w-3.5" />
            </ToolbarBtn>
            <ToolbarBtn
              onClick={() => editor.chain().focus().deleteTable().run()}
              title="Delete Table"
              className="text-red-400 hover:text-red-300"
            >
              <Trash className="h-3.5 w-3.5" />
            </ToolbarBtn>
          </>
        )}

        <ToolbarDivider />

        {/* Image */}
        <label className="cursor-pointer">
          <input
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) {
                const reader = new FileReader();
                reader.onload = (e) => {
                  const result = e.target?.result as string;
                  // Insert as a block-level float image (resizable + draggable)
                  (editor.chain().focus() as any)
                    .insertFloatImage({ src: result })
                    .run();
                };
                reader.readAsDataURL(file);
              }
              e.target.value = ""; // Reset input
            }}
          />
          <div
            title="Insert Image"
            className="h-7 w-7 flex items-center justify-center rounded text-muted-foreground hover:text-foreground hover:bg-accent transition-all cursor-pointer"
          >
            <ImageIcon className="h-3.5 w-3.5" />
          </div>
        </label>

        {/* Horizontal Rule.

            Cluster A.2 — the StarterKit HR command (`setHorizontalRule`)
            inserts at the cursor position, but `horizontalRule` is not in
            any paperBlock's content schema (questionBlock, sectionBlock,
            instructionBlock, etc.). When the cursor was inside one of
            those blocks the engine could not place the HR there and
            would split/insert near the block edge, which interacted
            poorly with the pagination engine and corrupted layout when
            the rule landed on a page boundary. Routing HR through the
            same `insertAfterCurrentBlock` helper used by the
            paper-structure buttons puts the HR AFTER the outermost
            paperBlock ancestor, which is always a legal placement and
            never interferes with pagination. */}
        <ToolbarBtn
          onClick={() => {
            const { state } = editor;
            const { $from } = state.selection;
            let insideQp = false;
            for (let depth = $from.depth; depth > 0; depth--) {
              if ($from.node(depth).type.spec.group?.includes("paperBlock")) {
                insideQp = true;
                break;
              }
            }
            if (insideQp) {
              insertAfterCurrentBlock("horizontalRule");
            } else {
              editor.chain().focus().setHorizontalRule().run();
            }
          }}
          title="Horizontal Rule"
        >
          <Minus className="h-3.5 w-3.5" />
        </ToolbarBtn>

        <ToolbarDivider />

        {/* Math & Chemistry */}
        <MathPicker
          onInsertBlock={(latex) => {
            editor
              .chain()
              .focus()
              .insertContent({ type: "mathBlock", attrs: { latex } })
              .run();
          }}
          onInsertInline={(latex) => {
            editor
              .chain()
              .focus()
              .insertContent({ type: "inlineMath", attrs: { latex } })
              .run();
          }}
        />

        <ChemistryPicker
          onInsertInline={(latex) => {
            editor
              .chain()
              .focus()
              .insertContent({ type: "inlineMath", attrs: { latex } })
              .run();
          }}
        />

        {/* Clear Formatting */}
        <ToolbarBtn
          onClick={() =>
            editor.chain().focus().clearNodes().unsetAllMarks().run()
          }
          title="Clear Formatting"
        >
          <Eraser className="h-3.5 w-3.5" />
        </ToolbarBtn>

        {/* Find/Replace */}
        {onFindReplace && (
          <ToolbarBtn onClick={onFindReplace} title="Find & Replace">
            <Search className="h-3.5 w-3.5" />
          </ToolbarBtn>
        )}

        {/* Right side tools */}
        <div className="ml-auto flex items-center gap-1.5">
          {/* Total Marks */}
          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-background rounded-full border border-border select-none shadow-sm">
            <Calculator className="h-3 w-3 text-primary" />
            <span className="text-[10px] font-semibold text-foreground">
              Marks:
            </span>
            <Badge
              variant="secondary"
              className="h-4 px-1.5 text-[9px] bg-muted text-foreground border-border"
            >
              {totalMarks}
            </Badge>
          </div>

          {/* Add Existing Question */}
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-[10px] px-3 font-medium text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50 dark:text-emerald-400 dark:hover:text-emerald-300 dark:hover:bg-emerald-950/30"
            onClick={() => {
              const store = useEditorStore.getState();
              store.setQuestionBankBrowserOpen(true);
            }}
          >
            <PlusCircle className="h-3 w-3 mr-1" /> Add Existing
          </Button>

          {/* New Paper */}
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-[10px] px-3 font-medium text-primary hover:text-primary hover:bg-primary/10 dark:text-primary dark:hover:text-primary dark:hover:bg-primary/30"
            onClick={() => {
              const confirm = window.confirm(
                "Are you sure you want to start a new paper? Any unsaved changes in the editor will be discarded."
              );
              if (confirm) {
                router.push("/editor?new=true");
              }
            }}
          >
            <Plus className="h-3 w-3 mr-1" /> New Paper
          </Button>

          {/* Open Paper */}
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-[10px] px-3 font-medium text-amber-600 hover:text-amber-700 hover:bg-amber-50 dark:text-amber-400 dark:hover:text-amber-300 dark:hover:bg-amber-950/30"
            onClick={() => {
              router.push("/question-bank");
            }}
          >
            <FolderOpen className="h-3 w-3 mr-1" /> Open Paper
          </Button>

          {/* Save Questions */}
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-[10px] px-3 font-medium text-primary border-primary/30 hover:bg-primary/10 dark:text-primary dark:border-primary/50 dark:hover:bg-primary/30 dark:hover:text-primary"
            onClick={() => {
              const store = useEditorStore.getState();
              const questions: any[] = [];
              editor.state.doc.descendants((node: any) => {
                if (node.type.name !== "questionBlock") return;
                let questionText = "";
                const options: string[] = [];
                node.forEach((child: any) => {
                  if (child.type.name === "paragraph" && !questionText) {
                    child.forEach((inline: any) => {
                      if (inline.text) questionText += inline.text;
                    });
                  }
                  if (
                    child.type.name === "bulletList" ||
                    child.type.name === "orderedList"
                  ) {
                    child.forEach((li: any) => {
                      let optText = "";
                      li.forEach((p: any) => {
                        p.forEach((inline: any) => {
                          if (inline.text) optText += inline.text;
                        });
                      });
                      if (optText) options.push(optText);
                    });
                  }
                });
                questions.push({
                  content: questionText,
                  type: options.length > 0 ? "mcq" : "short",
                  marks: node.attrs.marks ?? 1,
                  options,
                });
              });
              store.setQuestionsToSave(questions);
              store.setSaveQuestionModalOpen(true);
            }}
          >
            <Save className="h-3 w-3 mr-1" /> Save Questions
          </Button>

          {/* Paper Details */}
          <Button
            variant="default"
            size="sm"
            className="h-7 text-[10px] px-4 font-medium"
            onClick={() => {
              const store = useEditorStore.getState();
              store.setPages(extractPagesFromDoc(editor.state.doc));
              store.setSavePaperModalOpen(true);
            }}
          >
            <Save className="h-3 w-3 mr-1" /> Paper Details
          </Button>
        </div>
      </div>

      {/* Secondary Toolbar - Paper Structure (compact dropdown). */}
      <div className="flex items-center gap-2 px-2 py-1 border-t border-border/50 bg-muted/30">
        <InsertBlockDropdown
          insertAfterCurrentBlock={insertAfterCurrentBlock}
          editor={editor}
        />

        <ToolbarDivider />

        <button
          type="button"
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => {
            toast.warning("Clear the entire paper?", {
              description:
                "This removes all editor content in the current document.",
              action: {
                label: "Clear",
                onClick: () => editor.commands.clearContent(),
              },
            });
          }}
          className="h-6 px-2 text-[10px] font-medium text-red-400 hover:bg-red-500/10 rounded transition-colors flex items-center gap-1"
        >
          <Trash className="h-3 w-3" /> Clear All
        </button>

        <div className="ml-auto flex items-center gap-3 text-[10px] text-muted-foreground">
          <button
            onClick={handleExportPDF}
            className="hover:text-primary flex items-center gap-1 transition-colors"
          >
            <FileDown className="h-3 w-3" /> PDF
          </button>
          <button
            onClick={handleExportDocx}
            className="hover:text-primary flex items-center gap-1 transition-colors"
          >
            <FileDown className="h-3 w-3" /> DOCX
          </button>
          <button
            onClick={() => window.print()}
            className="hover:text-primary flex items-center gap-1 transition-colors"
          >
            <Printer className="h-3 w-3" /> Print
          </button>
          <span className="flex items-center gap-1">
            <span className="h-1 w-1 rounded-full bg-green-500 animate-pulse" />
            Live Sync
          </span>
        </div>
      </div>
    </div>
  );
};
