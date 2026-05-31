"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
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
  SeparatorHorizontal,
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
  PenTool,
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
                  "h-6 w-6 rounded border border-zinc-700 hover:scale-110 transition-transform",
                  currentColor === color && "ring-2 ring-indigo-500",
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
          <div className="mt-2 pt-2 border-t border-zinc-800">
            <button
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => {
                onInsertBlock("E = mc^2");
                setOpen(false);
              }}
              className="w-full text-left text-[11px] text-indigo-400 hover:text-indigo-300 px-2 py-1.5 rounded hover:bg-indigo-500/10 transition-colors"
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
}

export const EditorToolbar: React.FC<ToolbarProps> = ({
  editor,
  onFindReplace,
}) => {
  const router = useRouter();
  const [totalMarks, setTotalMarks] = useState(0);

  const calculateTotalMarks = useCallback(() => {
    let total = 0;
    editor.state.doc.descendants((node: any) => {
      if (
        node.type.name === "questionBlock" ||
        node.type.name === "groupedQuestionBlock"
      ) {
        total += Number(node.attrs.marks) || 0;
      }
    });
    setTotalMarks(total);
  }, [editor]);

  useEffect(() => {
    calculateTotalMarks();
  }, [editor?.state.doc, calculateTotalMarks]);

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
      await exportToPDF("tiptap-paper-container", filename);
      toast.success("PDF downloaded!", { id: toastId });
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
      await exportToDocx(container, filename);
      toast.success("DOCX downloaded!", { id: toastId });
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
    let pageDepth: number | null = null;

    for (let depth = $from.depth; depth > 0; depth--) {
      if ($from.node(depth).type.name === "page") {
        pageDepth = depth;
        break;
      }
    }

    if (pageDepth !== null && $from.depth >= pageDepth + 1) {
      insertPos = $from.after(pageDepth + 1);
    }

    // Find the current top-level paper block if we're inside one
    for (let depth = $from.depth; depth > 0; depth--) {
      const node = $from.node(depth);
      if (node.type.spec.group?.includes("paperBlock")) {
        insertPos = $from.after(depth);
        break;
      }
    }

    editor
      .chain()
      .focus()
      .insertContentAt(insertPos, { type, content, attrs })
      .run();
  };

  return (
    <div className="flex flex-col border-b border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 flex-shrink-0">
      {/* Primary Toolbar */}
      <div className="flex flex-wrap items-center gap-0.5 px-2 py-1.5 overflow-visible">
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
            className="h-7 w-7 flex items-center justify-center rounded text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 transition-all"
          >
            <ImageIcon className="h-3.5 w-3.5" />
          </div>
        </label>

        {/* Horizontal Rule */}
        <ToolbarBtn
          onClick={() => editor.chain().focus().setHorizontalRule().run()}
          title="Horizontal Rule"
        >
          <Minus className="h-3.5 w-3.5" />
        </ToolbarBtn>

        {/* Insert Page Break */}
        <ToolbarBtn
          onClick={() =>
            editor.chain().focus().insertContent({ type: "pageBreak" }).run()
          }
          title="Insert Page Break (Ctrl+Enter)"
        >
          <SeparatorHorizontal className="h-3.5 w-3.5" />
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

        {/* Drawing Canvas */}
        <ToolbarBtn
          onClick={() =>
            editor.chain().focus().insertContent({ type: "drawingBlock" }).run()
          }
          title="Insert Drawing Canvas"
        >
          <PenTool className="h-3.5 w-3.5" />
        </ToolbarBtn>

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
            className="h-7 text-[10px] px-3 font-medium text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50"
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
            className="h-7 text-[10px] px-3 font-medium text-indigo-600 hover:text-indigo-700 hover:bg-indigo-50"
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
            className="h-7 text-[10px] px-3 font-medium text-amber-600 hover:text-amber-700 hover:bg-amber-50"
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
            className="h-7 text-[10px] px-3 font-medium text-indigo-600 border-indigo-200 hover:bg-indigo-50"
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

      {/* Secondary Toolbar - Paper Structure */}
      <div className="flex items-center gap-1 px-2 py-1 border-t border-border/50 bg-muted/30">
        {/* Question Paper Blocks */}
        <button
          type="button"
          onMouseDown={(e) => e.preventDefault()}
          onClick={() =>
            insertAfterCurrentBlock("sectionBlock", [
              { type: "text", text: "SECTION A" },
            ])
          }
          className="h-6 px-2 text-[10px] font-medium text-indigo-400 hover:bg-indigo-500/10 rounded transition-colors flex items-center gap-1"
        >
          <PlusCircle className="h-3 w-3" /> Section
        </button>
        <button
          type="button"
          onMouseDown={(e) => e.preventDefault()}
          onClick={() =>
            insertAfterCurrentBlock(
              "questionBlock",
              [
                {
                  type: "paragraph",
                  content: [{ type: "text", text: "Enter question here..." }],
                },
              ],
              { marks: 2 },
            )
          }
          className="h-6 px-2 text-[10px] font-medium text-emerald-400 hover:bg-emerald-500/10 rounded transition-colors flex items-center gap-1"
        >
          <PlusCircle className="h-3 w-3" /> Question
        </button>
        <button
          type="button"
          onMouseDown={(e) => e.preventDefault()}
          onClick={() =>
            insertAfterCurrentBlock(
              "instructionBlock",
              [
                {
                  type: "orderedList",
                  content: [
                    {
                      type: "listItem",
                      content: [
                        {
                          type: "paragraph",
                          content: [
                            {
                              type: "text",
                              text: "All questions are compulsory.",
                            },
                          ],
                        },
                      ],
                    },
                  ],
                },
              ],
              { variant: "general" },
            )
          }
          className="h-6 px-2 text-[10px] font-medium text-amber-400 hover:bg-amber-500/10 rounded transition-colors flex items-center gap-1"
        >
          <PlusCircle className="h-3 w-3" /> Instructions
        </button>
        <button
          type="button"
          onMouseDown={(e) => e.preventDefault()}
          onClick={() =>
            insertAfterCurrentBlock(
              "questionGroupBlock",
              [
                {
                  type: "questionBlock",
                  attrs: { marks: 5 },
                  content: [
                    {
                      type: "paragraph",
                      content: [
                        { type: "text", text: "Option (a) question..." },
                      ],
                    },
                  ],
                },
                {
                  type: "paragraph",
                  content: [
                    {
                      type: "text",
                      marks: [{ type: "bold" }],
                      text: "OR",
                    },
                  ],
                },
                {
                  type: "questionBlock",
                  attrs: { marks: 5 },
                  content: [
                    {
                      type: "paragraph",
                      content: [
                        { type: "text", text: "Option (b) question..." },
                      ],
                    },
                  ],
                },
              ],
              { label: "Answer any ONE of the following:" },
            )
          }
          className="h-6 px-2 text-[10px] font-medium text-purple-400 hover:bg-purple-500/10 rounded transition-colors flex items-center gap-1"
        >
          <PlusCircle className="h-3 w-3" /> OR Group
        </button>
        <button
          type="button"
          onMouseDown={(e) => e.preventDefault()}
          onClick={() =>
            insertAfterCurrentBlock(
              "groupedQuestionBlock",
              [
                {
                  type: "paragraph",
                  content: [
                    { type: "text", text: "Main question statement..." },
                  ],
                },
                {
                  type: "orderedList",
                  content: [
                    {
                      type: "listItem",
                      content: [
                        {
                          type: "paragraph",
                          content: [
                            {
                              type: "text",
                              text: "Sub-question (a)...",
                            },
                          ],
                        },
                      ],
                    },
                    {
                      type: "listItem",
                      content: [
                        {
                          type: "paragraph",
                          content: [
                            {
                              type: "text",
                              text: "Sub-question (b)...",
                            },
                          ],
                        },
                      ],
                    },
                  ],
                },
              ],
              { marks: 5 },
            )
          }
          className="h-6 px-2 text-[10px] font-medium text-sky-500 hover:bg-sky-500/10 rounded transition-colors flex items-center gap-1"
        >
          <PlusCircle className="h-3 w-3" /> Grouped Questions
        </button>
        <button
          type="button"
          onMouseDown={(e) => e.preventDefault()}
          onClick={() =>
            insertAfterCurrentBlock(
              "questionBlock",
              [
                {
                  type: "paragraph",
                  content: [{ type: "text", text: "Enter MCQ stem here..." }],
                },
                {
                  type: "orderedList",
                  content: [
                    { type: "listItem", content: [{ type: "paragraph", content: [{ type: "text", text: "Option A" }] }] },
                    { type: "listItem", content: [{ type: "paragraph", content: [{ type: "text", text: "Option B" }] }] },
                    { type: "listItem", content: [{ type: "paragraph", content: [{ type: "text", text: "Option C" }] }] },
                    { type: "listItem", content: [{ type: "paragraph", content: [{ type: "text", text: "Option D" }] }] },
                  ],
                },
              ],
              { marks: 1, questionType: "MCQ" },
            )
          }
          className="h-6 px-2 text-[10px] font-medium text-rose-400 hover:bg-rose-500/10 rounded transition-colors flex items-center gap-1"
        >
          <PlusCircle className="h-3 w-3" /> MCQ
        </button>
        <button
          type="button"
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => {
            insertAfterCurrentBlock("paperHeaderBlock", [
              {
                type: "heading",
                attrs: { level: 1 },
                content: [{ type: "text", text: "SCHOOL / INSTITUTION NAME" }],
              },
              {
                type: "heading",
                attrs: { level: 2 },
                content: [{ type: "text", text: "SUBJECT — QUESTION PAPER" }],
              },
              {
                type: "paragraph",
                content: [{ type: "text", text: "Class —  |  Academic Year 20__–26" }],
              },
              {
                type: "table",
                content: [
                  {
                    type: "tableRow",
                    content: [
                      { type: "tableCell", attrs: {}, content: [{ type: "paragraph", content: [{ type: "text", text: "Time Allowed: __ Hours" }] }] },
                      { type: "tableCell", attrs: {}, content: [{ type: "paragraph", content: [{ type: "text", text: "Maximum Marks: __" }] }] },
                    ],
                  },
                ],
              },
            ]);
          }}
          className="h-6 px-2 text-[10px] font-medium text-teal-400 hover:bg-teal-500/10 rounded transition-colors flex items-center gap-1"
        >
          <PlusCircle className="h-3 w-3" /> Header
        </button>

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
            className="hover:text-indigo-400 flex items-center gap-1 transition-colors"
          >
            <FileDown className="h-3 w-3" /> PDF
          </button>
          <button
            onClick={handleExportDocx}
            className="hover:text-indigo-400 flex items-center gap-1 transition-colors"
          >
            <FileDown className="h-3 w-3" /> DOCX
          </button>
          <button
            onClick={() => window.print()}
            className="hover:text-indigo-400 flex items-center gap-1 transition-colors"
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
