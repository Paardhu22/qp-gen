import { Node, mergeAttributes } from "@tiptap/core";
import { ReactNodeViewRenderer, NodeViewWrapper, NodeViewContent } from "@tiptap/react";
import React from "react";
import { Trash } from "lucide-react";

// ==========================================
// QuestionBlock - Enhanced from QuestionItem
// ==========================================

const QuestionComponent = ({ node, updateAttributes, deleteNode }: any) => {
  return (
    <NodeViewWrapper className="question-block relative pl-10 pr-4 my-3 py-2 border-l-2 border-transparent hover:border-indigo-500/50 transition-colors group">
      <div className="absolute -right-2 top-0 opacity-0 group-hover:opacity-100 transition-opacity z-10">
        <button 
          onClick={deleteNode}
          className="bg-red-500 text-white p-1 rounded shadow-lg hover:bg-red-600 transition-colors"
          title="Delete Question"
        >
          <Trash className="w-3 h-3" />
        </button>
      </div>
      
      <span className="question-number absolute left-0 top-2 w-8 text-right font-bold text-zinc-400 text-sm select-none">
        {node.attrs.number ? `${node.attrs.number}.` : ""}
      </span>

      <NodeViewContent className="question-content flex-1" />

      <div className="question-marks absolute -right-16 top-2 flex items-center gap-1 select-none">
        <span className="text-[10px] font-mono bg-zinc-100 px-2 py-0.5 rounded-full text-zinc-500 border border-zinc-200">
          {node.attrs.marks}M
        </span>
      </div>
    </NodeViewWrapper>
  );
};

export const QuestionBlock = Node.create({
  name: "questionBlock",
  group: "block",
  content: "block+",
  draggable: true,
  isolating: true,

  addAttributes() {
    return {
      marks: { default: 1 },
      number: { default: null },
      difficulty: { default: "medium" },
      questionType: { default: "SHORT" },
      tags: { default: "" },
      aiGenerated: { default: false },
    };
  },

  parseHTML() {
    return [
      { tag: 'div[data-type="question-block"]' },
      { tag: 'div[data-type="question"]' },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "div",
      mergeAttributes(HTMLAttributes, { "data-type": "question-block" }),
      ["div", { class: "question-content" }, 0]
    ];
  },

  addNodeView() {
    return ReactNodeViewRenderer(QuestionComponent);
  },
});

// ==========================================
// SectionBlock - Enhanced from SectionHeader
// ==========================================

const SectionComponent = ({ node, deleteNode }: any) => {
  return (
    <NodeViewWrapper className="section-block w-full border-y border-zinc-200 py-3 my-6 text-center font-bold tracking-[0.2em] uppercase text-sm bg-zinc-50 select-none group relative">
       <div className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity">
        <button 
          onClick={deleteNode}
          className="bg-red-500 text-white p-1 rounded shadow-lg hover:bg-red-600 transition-colors"
          title="Delete Section"
        >
          <Trash className="w-3 h-3" />
        </button>
      </div>
      <NodeViewContent />
    </NodeViewWrapper>
  );
};

export const SectionBlock = Node.create({
  name: "sectionBlock",
  group: "block",
  content: "inline*",
  draggable: true,
  isolating: true,

  addAttributes() {
    return {
      title: { default: "SECTION A" },
      instructions: { default: "" },
      totalMarks: { default: null },
    };
  },

  parseHTML() {
    return [
      { tag: 'div[data-type="section-block"]' },
      { tag: 'div[data-type="section-header"]' },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "div",
      mergeAttributes(HTMLAttributes, { "data-type": "section-block" }),
      0
    ];
  },

  addNodeView() {
    return ReactNodeViewRenderer(SectionComponent);
  },
});

// ==========================================
// InstructionBlock
// ==========================================

const InstructionComponent = ({ deleteNode }: any) => {
  return (
    <NodeViewWrapper className="instruction-block my-4 p-4 bg-amber-50 border border-amber-200 rounded-lg group relative">
       <div className="absolute -right-2 -top-2 opacity-0 group-hover:opacity-100 transition-opacity">
        <button 
          onClick={deleteNode}
          className="bg-red-500 text-white p-1 rounded-full shadow-lg hover:bg-red-600 transition-colors"
          title="Delete Instructions"
        >
          <Trash className="w-3 h-3" />
        </button>
      </div>
      <div className="text-[10px] uppercase tracking-widest text-amber-600 font-bold mb-2 select-none" contentEditable={false}>
        General Instructions
      </div>
      <NodeViewContent className="instruction-content text-sm text-zinc-800" />
    </NodeViewWrapper>
  );
};

export const InstructionBlock = Node.create({
  name: "instructionBlock",
  group: "block",
  content: "block+",
  draggable: true,

  addAttributes() {
    return {
      variant: { default: "general" },
    };
  },

  parseHTML() {
    return [{ tag: 'div[data-type="instruction-block"]' }];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "div",
      mergeAttributes(HTMLAttributes, { "data-type": "instruction-block" }),
      0
    ];
  },

  addNodeView() {
    return ReactNodeViewRenderer(InstructionComponent);
  },
});

// ==========================================
// QuestionGroupBlock (OR / Choice questions)
// ==========================================

const QuestionGroupComponent = ({ node, deleteNode }: any) => {
  return (
    <NodeViewWrapper className="question-group my-4 border border-dashed border-zinc-300 rounded-lg p-4 bg-zinc-50 group relative">
       <div className="absolute -right-2 -top-2 opacity-0 group-hover:opacity-100 transition-opacity z-10">
        <button 
          onClick={deleteNode}
          className="bg-red-500 text-white p-1 rounded-full shadow-lg hover:bg-red-600 transition-colors"
          title="Delete Group"
        >
          <Trash className="w-3 h-3" />
        </button>
      </div>
      <div className="text-[11px] text-center uppercase tracking-wider text-zinc-400 font-semibold mb-3 select-none" contentEditable={false}>
        {node.attrs.label || "Answer any ONE"}
      </div>
      <NodeViewContent className="question-group-content space-y-2" />
    </NodeViewWrapper>
  );
};

export const QuestionGroupBlock = Node.create({
  name: "questionGroupBlock",
  group: "block",
  content: "block+",
  draggable: true,
  isolating: true,

  addAttributes() {
    return {
      groupType: { default: "or" },
      label: { default: "Answer any ONE of the following:" },
    };
  },

  parseHTML() {
    return [{ tag: 'div[data-type="question-group"]' }];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "div",
      mergeAttributes(HTMLAttributes, { "data-type": "question-group" }),
      0
    ];
  },

  addNodeView() {
    return ReactNodeViewRenderer(QuestionGroupComponent);
  },
});

// ==========================================
// PageBreak node
// ==========================================
export const PageBreak = Node.create({
  name: "pageBreak",
  group: "block",
  atom: true,

  parseHTML() {
    return [{ tag: 'div[data-type="page-break"]' }];
  },

  renderHTML() {
    return [
      "div",
      {
        "data-type": "page-break",
        class: "page-break my-8 border-t-2 border-dashed border-zinc-300 relative",
        contenteditable: "false",
      },
      [
        "span",
        {
          class: "absolute left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white px-3 text-[10px] uppercase tracking-widest text-zinc-400",
        },
        "Page Break",
      ],
    ];
  },

  addCommands() {
    return {
      setPageBreak: () => ({ commands }: any) => {
        return commands.insertContent({ type: "pageBreak" });
      },
    } as any;
  },

  addKeyboardShortcuts() {
    return {
      "Mod-Enter": () => (this.editor.commands as any).setPageBreak(),
    };
  },
});
