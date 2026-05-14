import { Node, mergeAttributes } from "@tiptap/core";
import { ReactNodeViewRenderer } from "@tiptap/react";

// ==========================================
// QuestionBlock - Enhanced from QuestionItem
// ==========================================
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
    const attrs = mergeAttributes(HTMLAttributes, {
      "data-type": "question-block",
      "data-marks": HTMLAttributes.marks,
      "data-number": HTMLAttributes.number,
      "data-difficulty": HTMLAttributes.difficulty,
      "data-question-type": HTMLAttributes.questionType,
      class:
        "question-block relative pl-10 pr-20 my-3 py-2 border-l-2 border-transparent hover:border-indigo-500/50 transition-colors group",
    });

    return [
      "div",
      attrs,
      [
        "span",
        {
          class:
            "question-number absolute left-0 top-2 w-8 text-right font-bold text-zinc-400 text-sm select-none",
          contenteditable: "false",
        },
        HTMLAttributes.number ? `${HTMLAttributes.number}.` : "",
      ],
      ["div", { class: "question-content flex-1" }, 0],
      [
        "div",
        {
          class:
            "question-marks absolute right-0 top-2 flex items-center gap-1 select-none",
          contenteditable: "false",
        },
        [
          "span",
          {
            class:
              "text-[10px] font-mono bg-zinc-800/80 backdrop-blur px-2 py-0.5 rounded-full text-zinc-400 border border-zinc-700/50",
          },
          `${HTMLAttributes.marks}M`,
        ],
      ],
    ];
  },

  addKeyboardShortcuts() {
    return {
      "Mod-Shift-q": () => {
        return this.editor
          .chain()
          .focus()
          .insertContent({
            type: this.name,
            attrs: { marks: 2 },
            content: [
              {
                type: "paragraph",
                content: [{ type: "text", text: "Enter question here..." }],
              },
            ],
          })
          .run();
      },
    };
  },
});

// ==========================================
// SectionBlock - Enhanced from SectionHeader
// ==========================================
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
    const marksText = HTMLAttributes.totalMarks
      ? ` (${HTMLAttributes.totalMarks} Marks)`
      : "";

    return [
      "div",
      mergeAttributes(HTMLAttributes, {
        "data-type": "section-block",
        class:
          "section-block w-full border-y border-zinc-700/50 py-3 my-6 text-center font-bold tracking-[0.2em] uppercase text-sm bg-zinc-900/30 select-none",
      }),
      0,
    ];
  },

  addKeyboardShortcuts() {
    return {
      "Mod-Shift-s": () => {
        return this.editor
          .chain()
          .focus()
          .insertContent({
            type: this.name,
            content: [{ type: "text", text: "SECTION A" }],
          })
          .run();
      },
    };
  },
});

// ==========================================
// InstructionBlock
// ==========================================
export const InstructionBlock = Node.create({
  name: "instructionBlock",
  group: "block",
  content: "block+",
  draggable: true,

  addAttributes() {
    return {
      variant: { default: "general" }, // general, warning, note
    };
  },

  parseHTML() {
    return [{ tag: 'div[data-type="instruction-block"]' }];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "div",
      mergeAttributes(HTMLAttributes, {
        "data-type": "instruction-block",
        class:
          "instruction-block my-4 p-4 bg-amber-500/5 border border-amber-500/20 rounded-lg",
      }),
      [
        "div",
        {
          class:
            "text-[10px] uppercase tracking-widest text-amber-500/70 font-bold mb-2 select-none",
          contenteditable: "false",
        },
        "General Instructions",
      ],
      ["div", { class: "instruction-content text-sm" }, 0],
    ];
  },
});

// ==========================================
// QuestionGroupBlock (OR / Choice questions)
// ==========================================
export const QuestionGroupBlock = Node.create({
  name: "questionGroupBlock",
  group: "block",
  content: "block+",
  draggable: true,
  isolating: true,

  addAttributes() {
    return {
      groupType: { default: "or" }, // or, compulsory, internal-choice
      label: { default: "Answer any ONE of the following:" },
    };
  },

  parseHTML() {
    return [{ tag: 'div[data-type="question-group"]' }];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "div",
      mergeAttributes(HTMLAttributes, {
        "data-type": "question-group",
        class:
          "question-group my-4 border border-dashed border-zinc-700/50 rounded-lg p-4 bg-zinc-900/20",
      }),
      [
        "div",
        {
          class:
            "text-[11px] text-center uppercase tracking-wider text-zinc-500 font-semibold mb-3 select-none",
          contenteditable: "false",
        },
        HTMLAttributes.label || "Answer any ONE",
      ],
      ["div", { class: "question-group-content space-y-2" }, 0],
    ];
  },
});

// ==========================================
// MathBlock - KaTeX equation node
// ==========================================
export const MathBlock = Node.create({
  name: "mathBlock",
  group: "block",
  content: "text*",
  marks: "",
  isolating: true,

  addAttributes() {
    return {
      latex: { default: "" },
      displayMode: { default: true },
    };
  },

  parseHTML() {
    return [
      {
        tag: 'div[data-type="math-block"]',
        getAttrs: (el) => {
          const element = el as HTMLElement;
          return { latex: element.getAttribute("data-latex") || "" };
        },
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "div",
      mergeAttributes(HTMLAttributes, {
        "data-type": "math-block",
        "data-latex": HTMLAttributes.latex,
        class:
          "math-block my-4 p-4 bg-zinc-900/50 border border-zinc-800 rounded-lg text-center font-mono text-sm cursor-pointer hover:border-indigo-500/50 transition-colors",
      }),
      0,
    ];
  },

  addKeyboardShortcuts() {
    return {
      "Mod-Shift-m": () => {
        return this.editor
          .chain()
          .focus()
          .insertContent({
            type: this.name,
            content: [{ type: "text", text: "E = mc^2" }],
          })
          .run();
      },
    };
  },
});

// ==========================================
// InlineMath - Inline KaTeX expression
// ==========================================
export const InlineMath = Node.create({
  name: "inlineMath",
  group: "inline",
  inline: true,
  atom: true,

  addAttributes() {
    return {
      latex: { default: "" },
    };
  },

  parseHTML() {
    return [
      {
        tag: 'span[data-type="inline-math"]',
        getAttrs: (el) => {
          const element = el as HTMLElement;
          return { latex: element.getAttribute("data-latex") || "" };
        },
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "span",
      mergeAttributes(HTMLAttributes, {
        "data-type": "inline-math",
        "data-latex": HTMLAttributes.latex,
        class:
          "inline-math px-1 py-0.5 bg-indigo-500/10 border border-indigo-500/20 rounded text-indigo-300 font-mono text-sm cursor-pointer",
      }),
      HTMLAttributes.latex || "math",
    ];
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
        class:
          "page-break my-8 border-t-2 border-dashed border-zinc-600 relative",
        contenteditable: "false",
      },
      [
        "span",
        {
          class:
            "absolute left-1/2 -translate-x-1/2 -translate-y-1/2 bg-zinc-900 px-3 text-[10px] uppercase tracking-widest text-zinc-500",
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
          return commands.insertContent({
            type: "pageBreak",
          });
        },
    } as any;
  },

  addKeyboardShortcuts() {
    return {
      "Mod-Enter": () => (this.editor.commands as any).setPageBreak(),
    };
  },
});
