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
    <NodeViewWrapper className="math-block">
      {!isEditing ? (
        <div 
          onClick={() => setIsEditing(true)} 
          className="math-block-display"
          title="Click to edit equation"
        >
          {latex ? (
            <div dangerouslySetInnerHTML={{ __html: katex.renderToString(latex, { displayMode: true, throwOnError: false }) }} />
          ) : (
            <span className="math-block-empty">Empty math block. Click to edit.</span>
          )}
        </div>
      ) : (
        <div className="math-block-editor">
          <textarea
            value={latex}
            onChange={(e) => setLatex(e.target.value)}
            className="math-block-input"
            autoFocus
            onBlur={handleSave}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSave();
              }
            }}
          />
          <div className="math-block-hint">
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
    <NodeViewWrapper as="span" className="inline-math">
      {!isEditing ? (
        <span 
          onClick={() => setIsEditing(true)} 
          className="inline-math-display"
          title="Click to edit inline math"
        >
          {latex ? (
            <span dangerouslySetInnerHTML={{ __html: katex.renderToString(latex, { displayMode: false, throwOnError: false }) }} />
          ) : (
            <span className="inline-math-empty">math</span>
          )}
        </span>
      ) : (
        <span className="inline-math-editor">
          <input
            type="text"
            value={latex}
            onChange={(e) => setLatex(e.target.value)}
            className="inline-math-input"
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
          const end = range.to;

          const latex = match[1];

          tr.replaceWith(start, end, this.type.create({ latex }));
        },
      }),
    ];
  },
});
