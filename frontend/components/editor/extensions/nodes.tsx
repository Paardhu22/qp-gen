import { Node, mergeAttributes } from "@tiptap/core";
import {
  ReactNodeViewRenderer,
  NodeViewWrapper,
  NodeViewContent,
} from "@tiptap/react";
import React, { useState } from "react";
import { GripVertical, Trash, Plus, RefreshCw, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { ApiError, replaceQuestion } from "@/lib/api-client";
import {
  buildQuestionBlocks,
  compositeRunSize,
  isCompositeQuestionType,
  parseSlotMeta,
} from "@/components/editor/question-nodes";

// ==========================================
// QuestionBlock - Enhanced from QuestionItem
// ==========================================

/**
 * Swap ONE question block for a freshly resolved replacement.
 *
 * The node carries the blueprint slot it filled (`slotMeta`), so the backend
 * can return a question of the same marks, type, section, chapter and
 * generator. The replacement is written straight over this node's range —
 * nothing else in the document is read or touched, which is the whole point:
 * a teacher who dislikes question 7 should not have to regenerate the paper.
 */
async function replaceQuestionNode({
  editor,
  getPos,
  node,
  onBusy,
}: {
  editor: any;
  getPos: () => number | undefined;
  node: any;
  onBusy: (busy: boolean) => void;
}) {
  const slot = parseSlotMeta(node.attrs?.slotMeta);
  if (!slot) return;

  // Every question already in the document, so the replacement is not one of
  // them. Matching on the id the generator stamped keeps this exact even when
  // two questions share a stem prefix.
  const excludeIds: string[] = [];
  editor.state.doc.descendants((child: any) => {
    if (child.type?.name !== "questionBlock") return;
    const meta = parseSlotMeta(child.attrs?.slotMeta);
    if (meta?.questionId) excludeIds.push(String(meta.questionId));
  });

  onBusy(true);
  try {
    const { question, source } = await replaceQuestion(
      {
        slotIndex: Number(slot.slotIndex) || 0,
        section: String(slot.section || ""),
        marks: Number(node.attrs?.marks ?? slot.marks ?? 1),
        type: String(slot.type || node.attrs?.questionType || "SHORT_ANSWER"),
        generator: String(slot.generator || "question_pool"),
        assetType: String(slot.assetType || ""),
        chapter: String(slot.chapter || ""),
        topic: String(slot.topic || ""),
        difficulty: String(slot.difficulty || ""),
        subject: String(slot.subject || ""),
        poolId: String(slot.poolId || ""),
        questionId: String(slot.questionId || ""),
      },
      { excludeIds },
    );

    const pos = getPos();
    if (typeof pos !== "number") return;

    const replacement = buildQuestionBlocks({
      content: question.content,
      type: question.type,
      options: question.options,
      answer: question.answer,
      marks: question.marks,
      image_url: question.image_url,
      metadata: question.metadata,
    });

    // Preserve the printed number and any OR-branch label; those belong to the
    // slot's position on the paper, not to the question that happens to be in
    // it. Auto-numbering would fix the number on its next pass anyway, but not
    // before the teacher sees it flicker. On a composite only the head block
    // is numbered, so it is the one that inherits them.
    replacement[0].attrs = {
      ...replacement[0].attrs,
      number: node.attrs?.number ?? null,
      subLabel: node.attrs?.subLabel ?? null,
    };

    // A composite question occupies a run of sibling blocks rather than a
    // single node, so the range being overwritten has to cover the run — drop
    // only the head and the new passage lands underneath the old one. The
    // extent is bounded by the next structural block, so anything a teacher
    // typed after the following question is untouched; prose they typed
    // between this composite's last sub-question and that block is not, which
    // is the price of a run with no wrapper node to delimit it.
    const $pos = editor.state.doc.resolve(pos);
    const replacedSize = isCompositeQuestionType(node.attrs?.questionType)
      ? compositeRunSize($pos.parent, $pos.index())
      : node.nodeSize;

    editor
      .chain()
      .focus()
      .insertContentAt({ from: pos, to: pos + replacedSize }, replacement)
      .run();

    toast.success(
      source === "bank"
        ? "Swapped in another question from your bank."
        : "Wrote a new question for this slot.",
    );
  } catch (error) {
    const message =
      error instanceof ApiError && error.status === 409
        ? "No other question fits this slot yet. Generate more for this chapter first."
        : error instanceof Error
          ? error.message
          : "Could not replace this question.";
    toast.error(message);
  } finally {
    onBusy(false);
  }
}

const QuestionComponent = ({ node, updateAttributes, deleteNode, editor, getPos }: any) => {
  // C — OR-branch labels ("31(A)") have no trailing dot; standalone
  // questions ("31.") do. subLabel wins when set.
  const subLabel = node.attrs.subLabel;
  const numberDisplay = subLabel
    ? subLabel
    : node.attrs.number
    ? `${node.attrs.number}.`
    : "";

  // Replace is offered only on generated questions: a hand-written one has no
  // blueprint slot to regenerate against.
  const [replacing, setReplacing] = useState(false);
  const canReplace = Boolean(parseSlotMeta(node.attrs?.slotMeta));

  return (
    <NodeViewWrapper className="question-block group">
      {editor?.isEditable && (
        <div
          data-drag-handle
          contentEditable={false}
          className="block-drag-handle"
          title="Drag to reorder"
        >
          <GripVertical className="w-3.5 h-3.5" />
        </div>
      )}
      <div className="question-row">
        <div
          className="question-cell question-no"
          contentEditable={false}
          style={{ cursor: "default" }}
        >
          {numberDisplay}
        </div>
        <div className="question-cell question-body editable-container">
          <NodeViewContent />
        </div>
        <div
          className="question-cell question-marks"
          contentEditable={false}
          style={{ cursor: "default" }}
        >
          {editor?.isEditable ? (
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
          ) : (
            <span className="question-marks-input-readonly">{node.attrs.marks ?? 1}</span>
          )}
          <span className="question-marks-label">M</span>
        </div>
      </div>
      {editor?.isEditable && (
        <div className="question-controls" contentEditable={false}>
          {canReplace && (
            <button
              onClick={() =>
                replaceQuestionNode({
                  editor,
                  getPos,
                  node,
                  onBusy: setReplacing,
                })
              }
              onMouseDown={(e) => e.preventDefault()}
              disabled={replacing}
              className="question-replace"
              title="Replace this question — same marks, type and section"
            >
              {replacing ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                <RefreshCw className="w-3 h-3" />
              )}
            </button>
          )}
          <button
            onClick={deleteNode}
            onMouseDown={(e) => e.preventDefault()}
            className="question-delete"
            title="Delete question"
          >
            <Trash className="w-3 h-3" />
          </button>
        </div>
      )}
    </NodeViewWrapper>
  );
};

export const QuestionBlock = Node.create({
  name: "questionBlock",
  group: "block paperBlock",
  content:
    "(paragraph | bulletList | orderedList | mathBlock | floatImage)+",
  draggable: true,
  isolating: true,

  addAttributes() {
    return {
      marks: { default: 1 },
      number: { default: null },
      // C — when this block is the branch of an OR group its visible
      // label is the parent question's number plus a branch letter
      // ("31(A)" / "31(B)"). `subLabel` overrides `number` rendering;
      // updateQuestionNumbers writes it whenever the block is inside
      // a questionGroupBlock and clears it otherwise.
      subLabel: { default: null },
      difficulty: { default: "medium" },
      questionType: { default: "SHORT" },
      tags: { default: "" },
      aiGenerated: { default: false },
      // Blueprint provenance for a generated question, as a JSON string:
      // which slot it filled, its marks, type, section, chapter and which
      // generator produced it. "Replace question" reads this to regenerate
      // exactly this slot and nothing else. Empty for hand-written questions,
      // which is what hides the Replace control on them.
      //
      // `renderHTML: () => ({})` suppresses the automatic camelCase attribute;
      // it is emitted once, as `data-slot-meta`, by the node's own renderHTML.
      // Without this the JSON blob appears twice in the serialised HTML.
      slotMeta: { default: "", renderHTML: () => ({}) },
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
          const subLabelAttr = el.getAttribute("data-sub-label");
          const marks = marksAttr ? Number(marksAttr) : 1;
          const number = numberAttr ? Number(numberAttr) : null;
          return {
            marks: Number.isNaN(marks) ? 1 : marks,
            number: Number.isNaN(number) ? null : number,
            subLabel: subLabelAttr || null,
            questionType: el.getAttribute("data-question-type") || "SHORT",
            slotMeta: el.getAttribute("data-slot-meta") || "",
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
        "data-sub-label": HTMLAttributes.subLabel ?? "",
        "data-question-type": HTMLAttributes.questionType ?? "",
        "data-slot-meta": HTMLAttributes.slotMeta ?? "",
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

type LabelStyle = "alpha" | "numeric" | "roman";

const LABEL_STYLE_OPTIONS: { value: LabelStyle; label: string }[] = [
  { value: "alpha", label: "(a)(b)(c)" },
  { value: "numeric", label: "1.2.3." },
  { value: "roman", label: "(i)(ii)(iii)" },
];

const GroupedQuestionComponent = ({ node, updateAttributes, deleteNode, editor, getPos }: any) => {
  const labelStyle: LabelStyle = node.attrs.labelStyle || "alpha";
  // C — OR-branch labels ("31(A)") for grouped questions inside an OR
  // group; standalone grouped questions use "31." numbering.
  const subLabel = node.attrs.subLabel;
  const numberDisplay = subLabel
    ? subLabel
    : node.attrs.number
    ? `${node.attrs.number}.`
    : "";

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

    // Issue 2 — "Sub-question..." used to be inserted as real text in the
    // new list item. That left the literal "Sub-question..." string in the
    // saved document if the teacher didn't manually clear it. Now the new
    // list item is created EMPTY and the Placeholder extension renders the
    // greyed prompt on the empty paragraph instead.
    const listItem = schema.nodes.listItem.create(
      {},
      schema.nodes.paragraph.create(),
    );

    if (!listNode || listPos === null) {
      const orderedList = schema.nodes.orderedList.create({}, [listItem]);
      tr.insert(nodeStart + node.content.size, orderedList);
    } else {
      tr.insert((listPos as number) + listNode.nodeSize - 1, listItem);
    }

    editor.view.dispatch(tr);
    editor.chain().focus().run();
  };

  return (
    <NodeViewWrapper
      className="question-block grouped-question-block group"
      data-label-style={labelStyle}
    >
      {editor?.isEditable && (
        <div
          data-drag-handle
          contentEditable={false}
          className="block-drag-handle"
          title="Drag to reorder"
        >
          <GripVertical className="w-3.5 h-3.5" />
        </div>
      )}
      <div className="question-row">
        <div
          className="question-cell question-no"
          contentEditable={false}
          style={{ cursor: "default" }}
        >
          {numberDisplay}
        </div>
        <div className="question-cell question-body editable-container">
          <NodeViewContent />
        </div>
        <div
          className="question-cell question-marks"
          contentEditable={false}
          style={{ cursor: "default" }}
        >
          {editor?.isEditable ? (
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
          ) : (
            <span className="question-marks-input-readonly">{node.attrs.marks ?? 1}</span>
          )}
          <span className="question-marks-label">M</span>
        </div>
      </div>
      {editor?.isEditable && (
        <div className="question-controls" contentEditable={false}>
          {/* Sub-label style picker */}
          <div
            className="question-label-style-picker"
            title="Sub-question label style"
            onMouseDown={(e) => e.preventDefault()}
          >
            <select
              value={labelStyle}
              onChange={(e) =>
                updateAttributes({ labelStyle: e.target.value as LabelStyle })
              }
              className="question-label-style-select"
              onMouseDown={(e) => e.stopPropagation()}
            >
              {LABEL_STYLE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
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
      )}
    </NodeViewWrapper>
  );
};

export const GroupedQuestionBlock = Node.create({
  name: "groupedQuestionBlock",
  group: "block paperBlock",
  content:
    "(paragraph | bulletList | orderedList | mathBlock | floatImage)+",
  draggable: true,
  isolating: true,

  addAttributes() {
    return {
      marks: { default: 1 },
      number: { default: null },
      // C — OR-branch label like "31(A)" when this grouped question
      // is inside a questionGroupBlock.
      subLabel: { default: null },
      difficulty: { default: "medium" },
      questionType: { default: "GROUPED" },
      tags: { default: "" },
      aiGenerated: { default: false },
      labelStyle: { default: "alpha" },
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
          const subLabelAttr = el.getAttribute("data-sub-label");
          const marks = marksAttr ? Number(marksAttr) : 1;
          const number = numberAttr ? Number(numberAttr) : null;
          return {
            marks: Number.isNaN(marks) ? 1 : marks,
            number: Number.isNaN(number) ? null : number,
            subLabel: subLabelAttr || null,
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
        "data-sub-label": HTMLAttributes.subLabel ?? "",
        "data-label-style": HTMLAttributes.labelStyle ?? "alpha",
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

const SectionComponent = ({ node, deleteNode, editor }: any) => {
  const summaryText = node.attrs?.summaryText || "";
  const instructions = node.attrs?.instructions || "";

  return (
    <NodeViewWrapper className="section-block group">
      {editor?.isEditable && (
        <div
          data-drag-handle
          contentEditable={false}
          className="block-drag-handle"
          title="Drag to reorder"
        >
          <GripVertical className="w-3.5 h-3.5" />
        </div>
      )}
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
      {editor?.isEditable && (
        <div className="section-controls" contentEditable={false}>
          <button
            onClick={deleteNode}
            className="section-delete"
            title="Delete Section"
          >
            <Trash className="w-3 h-3" />
          </button>
        </div>
      )}
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
    // ProseMirror requires the content hole (`0`) to be the only child of its
    // immediate parent array. Wrap `0` in its own `.section-title` div so we
    // can still emit sibling decorations like the section summary span.
    const summaryText = node.attrs?.summaryText;
    const titleSpec: any[] = ["div", { class: "section-title" }, 0];

    if (summaryText) {
      return [
        "div",
        mergeAttributes(HTMLAttributes, { "data-type": "section-block" }),
        titleSpec,
        ["span", { class: "section-summary" }, ` (${summaryText})`],
      ];
    }

    return [
      "div",
      mergeAttributes(HTMLAttributes, { "data-type": "section-block" }),
      titleSpec,
    ];
  },

  addNodeView() {
    return ReactNodeViewRenderer(SectionComponent);
  },
});

// ==========================================
// InstructionBlock
// ==========================================

const InstructionComponent = ({ node, deleteNode, editor }: any) => {
  const summaryItems = node.attrs?.summaryItems || [];

  return (
    <NodeViewWrapper className="instruction-block group">
      {editor?.isEditable && (
        <div
          data-drag-handle
          contentEditable={false}
          className="block-drag-handle"
          title="Drag to reorder"
        >
          <GripVertical className="w-3.5 h-3.5" />
        </div>
      )}
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
      {editor?.isEditable && (
        <div className="instruction-controls" contentEditable={false}>
          <button
            onClick={deleteNode}
            className="instruction-delete"
            title="Delete Instructions"
          >
            <Trash className="w-3 h-3" />
          </button>
        </div>
      )}
    </NodeViewWrapper>
  );
};

export const InstructionBlock = Node.create({
  name: "instructionBlock",
  group: "block paperBlock",
  content:
    "(paragraph | bulletList | orderedList | mathBlock | floatImage)+",
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
    // ProseMirror requires the content hole (`0`) to be the only child of its
    // immediate parent array. Wrap `0` in its own `.instruction-content` div so
    // we can still emit the header + summary list as siblings of the content.
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

    children.push(["div", { class: "instruction-content" }, 0]);

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

const QuestionGroupComponent = ({ node, deleteNode, editor }: any) => {
  // C — Board-paper OR groups are rendered as bare branches
  // ("31(A) … OR 31(B) …"). The parent number lives on each branch's
  // subLabel (via updateQuestionNumbers); no "Answer any ONE of the
  // following:" header is shown.
  return (
    <NodeViewWrapper className="question-group group">
      {editor?.isEditable && (
        <div
          data-drag-handle
          contentEditable={false}
          className="block-drag-handle"
          title="Drag to reorder"
        >
          <GripVertical className="w-3.5 h-3.5" />
        </div>
      )}
      <div className="question-group-content editable-container">
        <NodeViewContent />
      </div>
      {editor?.isEditable && (
        <div className="question-group-controls" contentEditable={false}>
          <button
            onClick={deleteNode}
            className="question-group-delete"
            title="Delete Group"
          >
            <Trash className="w-3 h-3" />
          </button>
        </div>
      )}
    </NodeViewWrapper>
  );
};

export const QuestionGroupBlock = Node.create({
  name: "questionGroupBlock",
  group: "block paperBlock",
  // OR branches can be plain questions, grouped questions, or separator paragraphs
  content: "(questionBlock | groupedQuestionBlock | paragraph)+",
  draggable: true,
  isolating: true,

  addAttributes() {
    return {
      groupType: { default: "or" },
      label: { default: "Answer any ONE of the following:" },
      number: { default: null },
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
// PageBreak — parseHTML compatibility shim only.
// The page-break feature was retired.  This stub silently drops any
// data-type="page-break" nodes found in saved papers so they load
// without crashing.  It is NOT added to the editor extensions;
// it is exported only so external code that imports it doesn't break.
// ==========================================
export const PageBreak = Node.create({
  name: "pageBreak",
  group: "block",
  atom: true,

  parseHTML() {
    return [{ tag: 'div[data-type="page-break"]' }];
  },

  renderHTML() {
    return ["div", { "data-type": "page-break", style: "display:none" }];
  },
});
