import { Node, mergeAttributes, InputRule } from "@tiptap/core";
import { ReactNodeViewRenderer, NodeViewWrapper } from "@tiptap/react";
import React, { useState } from "react";
import "katex/dist/katex.min.css";

// Actually we installed `react-katex`. Let's import from that.
import katex from "katex";

export const MathBlockComponent = ({ node, updateAttributes }: any) => {
  const [isEditing, setIsEditing] = useState(false);
  const [latex, setLatex] = useState(node.attrs.latex || "E = mc^2");

  const handleSave = () => {
    updateAttributes({ latex });
    setIsEditing(false);
  };

  return (
    <NodeViewWrapper className="math-block my-4 p-4 bg-zinc-900/50 border border-zinc-800 rounded-lg text-center font-mono text-sm group relative hover:border-indigo-500/50 transition-colors">
      {!isEditing ? (
        <div 
          onClick={() => setIsEditing(true)} 
          className="cursor-pointer py-2"
          title="Click to edit equation"
        >
          {latex ? (
            <div dangerouslySetInnerHTML={{ __html: katex.renderToString(latex, { displayMode: true, throwOnError: false }) }} />
          ) : (
            <span className="text-zinc-500 italic">Empty math block. Click to edit.</span>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          <textarea
            value={latex}
            onChange={(e) => setLatex(e.target.value)}
            className="w-full bg-zinc-950 border border-indigo-500/50 rounded p-2 text-zinc-200 font-mono text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-y min-h-[60px]"
            autoFocus
            onBlur={handleSave}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSave();
              }
            }}
          />
          <div className="text-[10px] text-zinc-500 text-left">
            Press Enter to save, Shift+Enter for new line.
          </div>
        </div>
      )}
    </NodeViewWrapper>
  );
};

export const MathBlock = Node.create({
  name: "mathBlock",
  group: "block",
  content: "text*",
  marks: "",
  isolating: true,
  atom: true,

  addAttributes() {
    return {
      latex: { default: "E = mc^2" },
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
        class: "math-block",
      }),
    ];
  },

  addNodeView() {
    return ReactNodeViewRenderer(MathBlockComponent);
  },

  addKeyboardShortcuts() {
    return {
      "Mod-Shift-m": () => {
        return this.editor
          .chain()
          .focus()
          .insertContent({
            type: this.name,
            attrs: { latex: "E = mc^2" },
          })
          .run();
      },
    };
  },
});

export const InlineMathComponent = ({ node, updateAttributes }: any) => {
  const [isEditing, setIsEditing] = useState(false);
  const [latex, setLatex] = useState(node.attrs.latex || "x");

  const handleSave = () => {
    updateAttributes({ latex });
    setIsEditing(false);
  };

  return (
    <NodeViewWrapper as="span" className="inline-math relative inline-block mx-1">
      {!isEditing ? (
        <span 
          onClick={() => setIsEditing(true)} 
          className="cursor-pointer bg-zinc-800/50 hover:bg-indigo-500/20 px-1 rounded transition-colors"
          title="Click to edit inline math"
        >
          {latex ? (
            <span dangerouslySetInnerHTML={{ __html: katex.renderToString(latex, { displayMode: false, throwOnError: false }) }} />
          ) : (
            <span className="text-zinc-500 italic">math</span>
          )}
        </span>
      ) : (
        <span className="inline-flex items-center gap-1 bg-zinc-900 border border-indigo-500/50 rounded px-1 relative z-10 shadow-lg">
          <input
            type="text"
            value={latex}
            onChange={(e) => setLatex(e.target.value)}
            className="bg-transparent border-none text-zinc-200 font-mono text-xs w-[100px] focus:outline-none"
            autoFocus
            onBlur={handleSave}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                handleSave();
              }
            }}
          />
        </span>
      )}
    </NodeViewWrapper>
  );
};

export const InlineMath = Node.create({
  name: "inlineMath",
  group: "inline",
  inline: true,
  atom: true,

  addAttributes() {
    return {
      latex: { default: "x" },
    };
  },

  parseHTML() {
    return [
      {
        tag: 'span[data-type="inline-math"]',
        getAttrs: (el) => {
          const element = el as HTMLElement;
          return { latex: element.getAttribute("data-latex") || "x" };
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
        class: "inline-math",
      }),
    ];
  },

  addNodeView() {
    return ReactNodeViewRenderer(InlineMathComponent);
  },

  addInputRules() {
    return [
      new InputRule({
        find: /\$(.+?)\$$/,
        handler: ({ state, range, match }) => {
          const { tr } = state;
          const start = range.from;
          let end = range.to;

          const latex = match[1];

          tr.replaceWith(start, end, this.type.create({ latex }));
        },
      }),
    ];
  },
});
