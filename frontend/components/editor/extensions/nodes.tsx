import { Node, mergeAttributes } from "@tiptap/core";
import {
  ReactNodeViewRenderer,
  NodeViewWrapper,
  NodeViewContent,
} from "@tiptap/react";
import React from "react";
import { GripVertical, Trash, Plus } from "lucide-react";

// ==========================================
// QuestionBlock - Enhanced from QuestionItem
// ==========================================

const QuestionComponent = ({ node, updateAttributes, deleteNode }: any) => {
  React.useEffect(() => {
    console.log(
      "[DEBUG QuestionComponent] MOUNT for question:",
      node.attrs.number,
    );
    return () => {
      console.log(
        "[DEBUG QuestionComponent] UNMOUNT for question:",
        node.attrs.number,
      );
    };
  }, [node.attrs.number]);

  console.log(
    "[DEBUG QuestionComponent] RERENDER for question:",
    node.attrs.number,
  );

  return (
    <NodeViewWrapper className="question-block group">
      <div
        data-drag-handle
        contentEditable={false}
        className="block-drag-handle"
        title="Drag to reorder"
      >
        <GripVertical className="w-3.5 h-3.5" />
      </div>
      <div className="question-row">
        <div
          className="question-cell question-no"
          contentEditable={false}
          style={{ cursor: "default" }}
        >
          {node.attrs.number ? `${node.attrs.number}.` : ""}
        </div>
        <div className="question-cell question-body editable-container">
          <NodeViewContent />
        </div>
        <div
          className="question-cell question-marks"
          contentEditable={false}
          style={{ cursor: "default" }}
        >
          <input
            type="number"
            min={0}
            step={1}
            value={Number(node.attrs.marks ?? 1)}
            onChange={(event) => {
              const nextValue = Number(event.target.value);
              updateAttributes({
                marks: Number.isNaN(nextValue) ? 1 : nextValue,
              });
            }}
            className="question-marks-input"
            title="Marks for this question"
            onMouseDown={(e) => e.stopPropagation()}
          />
          <span className="question-marks-label">M</span>
        </div>
      </div>
      <div className="question-controls" contentEditable={false}>
        <button
          onClick={deleteNode}
          onMouseDown={(e) => e.preventDefault()}
          className="question-delete"
          title="Delete question"
        >
          <Trash className="w-3 h-3" />
        </button>
      </div>
    </NodeViewWrapper>
  );
};

export const QuestionBlock = Node.create({
  name: "questionBlock",
  group: "block paperBlock",
  content:
    "(paragraph | bulletList | orderedList | mathBlock | drawingBlock | floatImage)+",
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
      {
        tag: 'div[data-type="question-block"]',
        getAttrs: (element) => {
          const el = element as HTMLElement;
          const marksAttr = el.getAttribute("data-marks");
          const numberAttr = el.getAttribute("data-number");
          const marks = marksAttr ? Number(marksAttr) : 1;
          const number = numberAttr ? Number(numberAttr) : null;
          return {
            marks: Number.isNaN(marks) ? 1 : marks,
            number: Number.isNaN(number) ? null : number,
          };
        },
      },
      { tag: 'div[data-type="question"]' },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "div",
      mergeAttributes(HTMLAttributes, {
        "data-type": "question-block",
        "data-marks": HTMLAttributes.marks ?? "",
        "data-number": HTMLAttributes.number ?? "",
      }),
      ["div", { class: "question-content" }, 0],
    ];
  },

  addNodeView() {
    return ReactNodeViewRenderer(QuestionComponent);
  },
});

// ==========================================
// GroupedQuestionBlock - Question with sub-questions (a, b, ...)
// ==========================================

const GroupedQuestionComponent = ({ node, updateAttributes, deleteNode, editor, getPos }: any) => {
  const handleAddSubQuestion = () => {
    if (!editor || typeof getPos !== "function") return;

    const pos = getPos();
    if (typeof pos !== "number") return;

    const { state } = editor;
    const { schema } = state;
    const tr = state.tr;
    const nodeStart = pos + 1;

    let listPos: number | null = null;
    let listNode: any = null;

    node.content.forEach((child: any, offset: number) => {
      if (listPos !== null) return;
      if (child.type.name === "orderedList" || child.type.name === "bulletList") {
        listPos = nodeStart + offset;
        listNode = child;
      }
    });

    const listItem = schema.nodes.listItem.create(
      {},
      schema.nodes.paragraph.create({}, schema.text("Sub-question...")),
    );

    if (!listNode || listPos === null) {
      const orderedList = schema.nodes.orderedList.create({}, [listItem]);
      tr.insert(nodeStart + node.content.size, orderedList);
    } else {
      tr.insert(listPos + listNode.nodeSize - 1, listItem);
    }

    editor.view.dispatch(tr);
    editor.chain().focus().run();
  };
  return (
    <NodeViewWrapper className="question-block grouped-question-block group">
      <div
        data-drag-handle
        contentEditable={false}
        className="block-drag-handle"
        title="Drag to reorder"
      >
        <GripVertical className="w-3.5 h-3.5" />
      </div>
      <div className="question-row">
        <div
          className="question-cell question-no"
          contentEditable={false}
          style={{ cursor: "default" }}
        >
          {node.attrs.number ? `${node.attrs.number}.` : ""}
        </div>
        <div className="question-cell question-body editable-container">
          <NodeViewContent />
        </div>
        <div
          className="question-cell question-marks"
          contentEditable={false}
          style={{ cursor: "default" }}
        >
          <input
            type="number"
            min={0}
            step={1}
            value={Number(node.attrs.marks ?? 1)}
            onChange={(event) => {
              const nextValue = Number(event.target.value);
              updateAttributes({
                marks: Number.isNaN(nextValue) ? 1 : nextValue,
              });
            }}
            className="question-marks-input"
            title="Marks for this question"
            onMouseDown={(e) => e.stopPropagation()}
          />
          <span className="question-marks-label">M</span>
        </div>
      </div>
      <div className="question-controls" contentEditable={false}>
        <button
          onClick={handleAddSubQuestion}
          onMouseDown={(e) => e.preventDefault()}
          className="question-add-sub"
          title="Add sub-question"
        >
          <Plus className="w-3 h-3" />
        </button>
        <button
          onClick={deleteNode}
          onMouseDown={(e) => e.preventDefault()}
          className="question-delete"
          title="Delete question"
        >
          <Trash className="w-3 h-3" />
        </button>
      </div>
    </NodeViewWrapper>
  );
};

export const GroupedQuestionBlock = Node.create({
  name: "groupedQuestionBlock",
  group: "block paperBlock",
  content:
    "(paragraph | bulletList | orderedList | mathBlock | drawingBlock | floatImage)+",
  draggable: true,
  isolating: true,

  addAttributes() {
    return {
      marks: { default: 1 },
      number: { default: null },
      difficulty: { default: "medium" },
      questionType: { default: "GROUPED" },
      tags: { default: "" },
      aiGenerated: { default: false },
    };
  },

  parseHTML() {
    return [
      {
        tag: 'div[data-type="grouped-question-block"]',
        getAttrs: (element) => {
          const el = element as HTMLElement;
          const marksAttr = el.getAttribute("data-marks");
          const numberAttr = el.getAttribute("data-number");
          const marks = marksAttr ? Number(marksAttr) : 1;
          const number = numberAttr ? Number(numberAttr) : null;
          return {
            marks: Number.isNaN(marks) ? 1 : marks,
            number: Number.isNaN(number) ? null : number,
          };
        },
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "div",
      mergeAttributes(HTMLAttributes, {
        "data-type": "grouped-question-block",
        "data-marks": HTMLAttributes.marks ?? "",
        "data-number": HTMLAttributes.number ?? "",
      }),
      ["div", { class: "question-content" }, 0],
    ];
  },

  addNodeView() {
    return ReactNodeViewRenderer(GroupedQuestionComponent);
  },
});

// ==========================================
// SectionBlock - Enhanced from SectionHeader
// ==========================================

const SectionComponent = ({ node, deleteNode }: any) => {
  const summaryText = node.attrs?.summaryText || "";
  const instructions = node.attrs?.instructions || "";

  React.useEffect(() => {
    console.log("[DEBUG SectionComponent] MOUNT for title:", node.attrs.title);
    return () => {
      console.log(
        "[DEBUG SectionComponent] UNMOUNT for title:",
        node.attrs.title,
      );
    };
  }, [node.attrs.title]);

  console.log("[DEBUG SectionComponent] RERENDER for title:", node.attrs.title);

  return (
    <NodeViewWrapper className="section-block group">
      <div
        data-drag-handle
        contentEditable={false}
        className="block-drag-handle"
        title="Drag to reorder"
      >
        <GripVertical className="w-3.5 h-3.5" />
      </div>
      <div className="section-header">
        <div className="section-title">
          <NodeViewContent />
        </div>
        {summaryText ? (
          <div className="section-summary" contentEditable={false}>
            ({summaryText})
          </div>
        ) : null}
      </div>
      {instructions ? (
        <div className="section-instructions" contentEditable={false}>
          {instructions}
        </div>
      ) : null}
      <div className="section-controls" contentEditable={false}>
        <button
          onClick={deleteNode}
          className="section-delete"
          title="Delete Section"
        >
          <Trash className="w-3 h-3" />
        </button>
      </div>
    </NodeViewWrapper>
  );
};

export const SectionBlock = Node.create({
  name: "sectionBlock",
  group: "block paperBlock",
  content: "inline*",
  draggable: true,
  isolating: true,

  addAttributes() {
    return {
      title: { default: "SECTION A" },
      instructions: { default: "" },
      totalMarks: { default: null, renderHTML: () => ({}) },
      questionCount: { default: 0, renderHTML: () => ({}) },
      marksEach: { default: null, renderHTML: () => ({}) },
      summaryText: { default: "", renderHTML: () => ({}) },
    };
  },

  parseHTML() {
    return [
      { tag: 'div[data-type="section-block"]' },
      { tag: 'div[data-type="section-header"]' },
    ];
  },

  renderHTML({ node, HTMLAttributes }) {
    const summaryText = node.attrs?.summaryText;
    const children: any[] = [0];

    if (summaryText) {
      children.push([
        "span",
        { class: "section-summary" },
        ` (${summaryText})`,
      ]);
    }

    return [
      "div",
      mergeAttributes(HTMLAttributes, { "data-type": "section-block" }),
      ...children,
    ];
  },

  addNodeView() {
    return ReactNodeViewRenderer(SectionComponent);
  },
});

// ==========================================
// InstructionBlock
// ==========================================

const InstructionComponent = ({ node, deleteNode }: any) => {
  const summaryItems = node.attrs?.summaryItems || [];

  React.useEffect(() => {
    console.log("[DEBUG InstructionComponent] MOUNT");
    return () => {
      console.log("[DEBUG InstructionComponent] UNMOUNT");
    };
  }, []);

  console.log("[DEBUG InstructionComponent] RERENDER");

  return (
    <NodeViewWrapper className="instruction-block group">
      <div
        data-drag-handle
        contentEditable={false}
        className="block-drag-handle"
        title="Drag to reorder"
      >
        <GripVertical className="w-3.5 h-3.5" />
      </div>
      <div className="instruction-header" contentEditable={false}>
        General Instructions
      </div>
      {summaryItems.length > 0 ? (
        <ol className="instruction-list" contentEditable={false}>
          {summaryItems.map((item: string, index: number) => (
            <li key={`${index}-${item}`}>{item}</li>
          ))}
        </ol>
      ) : null}
      <div className="instruction-content editable-container">
        <NodeViewContent />
      </div>
      <div className="instruction-controls" contentEditable={false}>
        <button
          onClick={deleteNode}
          className="instruction-delete"
          title="Delete Instructions"
        >
          <Trash className="w-3 h-3" />
        </button>
      </div>
    </NodeViewWrapper>
  );
};

export const InstructionBlock = Node.create({
  name: "instructionBlock",
  group: "block paperBlock",
  content:
    "(paragraph | bulletList | orderedList | mathBlock | drawingBlock | floatImage)+",
  draggable: true,

  addAttributes() {
    return {
      variant: { default: "general" },
      summaryItems: {
        default: [],
        renderHTML: () => ({}),
      },
    };
  },

  parseHTML() {
    return [{ tag: 'div[data-type="instruction-block"]' }];
  },

  renderHTML({ node, HTMLAttributes }) {
    const summaryItems = Array.isArray(node.attrs.summaryItems)
      ? node.attrs.summaryItems
      : [];

    const children: any[] = [
      ["div", { class: "instruction-header" }, "General Instructions"],
    ];

    if (summaryItems.length > 0) {
      children.push([
        "ol",
        { class: "instruction-list" },
        ...summaryItems.map((item: string) => ["li", {}, item]),
      ]);
    }

    children.push(0);

    return [
      "div",
      mergeAttributes(HTMLAttributes, { "data-type": "instruction-block" }),
      ...children,
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
  React.useEffect(() => {
    console.log("[DEBUG QuestionGroupComponent] MOUNT");
    return () => {
      console.log("[DEBUG QuestionGroupComponent] UNMOUNT");
    };
  }, []);

  console.log("[DEBUG QuestionGroupComponent] RERENDER");

  return (
    <NodeViewWrapper className="question-group group">
      <div
        data-drag-handle
        contentEditable={false}
        className="block-drag-handle"
        title="Drag to reorder"
      >
        <GripVertical className="w-3.5 h-3.5" />
      </div>
      <div className="question-group-label" contentEditable={false}>
        {node.attrs.label || "Answer any ONE"}
      </div>
      <div className="question-group-content editable-container">
        <NodeViewContent />
      </div>
      <div className="question-group-controls" contentEditable={false}>
        <button
          onClick={deleteNode}
          className="question-group-delete"
          title="Delete Group"
        >
          <Trash className="w-3 h-3" />
        </button>
      </div>
    </NodeViewWrapper>
  );
};

export const QuestionGroupBlock = Node.create({
  name: "questionGroupBlock",
  group: "block paperBlock",
  content: "(questionBlock | paragraph)+",
  draggable: true,
  isolating: true,

  addAttributes() {
    return {
      groupType: { default: "or" },
      label: { default: "Answer any ONE of the following:" },
    };
  },

  parseHTML() {
    return [
      {
        tag: 'div[data-type="question-group"]',
        getAttrs: (element) => {
          const el = element as HTMLElement;
          return { label: el.getAttribute("data-label") || undefined };
        },
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "div",
      mergeAttributes(HTMLAttributes, {
        "data-type": "question-group",
        "data-label": HTMLAttributes.label || undefined,
      }),
      0,
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
  group: "block paperBlock",
  atom: true,

  parseHTML() {
    return [{ tag: 'div[data-type="page-break"]' }];
  },

  renderHTML() {
    return [
      "div",
      {
        "data-type": "page-break",
        class:
          "page-break my-8 border-t-2 border-dashed border-zinc-300 relative",
        contenteditable: "false",
      },
      [
        "span",
        {
          class:
            "absolute left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white px-3 text-[10px] uppercase tracking-widest text-zinc-400",
        },
        "Page Break",
      ],
    ];
  },

  addCommands() {
    return {
      setPageBreak:
        () =>
        ({ commands }: any) => {
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
