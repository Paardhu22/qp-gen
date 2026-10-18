import { Node, mergeAttributes, InputRule } from "@tiptap/core";
import { ReactNodeViewRenderer, NodeViewWrapper } from "@tiptap/react";
import React, { useRef, useState } from "react";
import "katex/dist/katex.min.css";

import katex from "katex";

// The equation shown is always the node's own `latex` attribute. These views
// used to copy it into `useState` once and render the copy, so when undo, redo
// or a paste changed the attribute from outside, the document was right and the
// screen kept the old equation — an undo that looked like it had done nothing.
// The local `draft` exists only while the textarea is open.
export const MathBlockComponent = ({ node, updateAttributes }: any) => {
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const latex: string = node.attrs.latex ?? "";

  // Escape discards the draft. Unmounting the focused field can still fire a
  // blur, which would save it, so the cancel is remembered across that.
  const cancelled = useRef(false);

  const startEditing = () => {
    cancelled.current = false;
    setDraft(latex);
    setIsEditing(true);
  };

  const cancelEditing = () => {
    cancelled.current = true;
    setIsEditing(false);
  };

  const handleSave = () => {
    if (cancelled.current) return;
    if (draft !== latex) updateAttributes({ latex: draft });
    setIsEditing(false);
  };

  return (
    <NodeViewWrapper className="math-block">
      {!isEditing ? (
        <div 
          onClick={startEditing}
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
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="math-block-input"
            autoFocus
            onBlur={handleSave}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                e.preventDefault();
                cancelEditing();
              } else if (e.key === "Enter" && !e.shiftKey) {
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
  const [draft, setDraft] = useState("");
  const latex: string = node.attrs.latex ?? "";

  // Escape discards the draft. Unmounting the focused field can still fire a
  // blur, which would save it, so the cancel is remembered across that.
  const cancelled = useRef(false);

  const startEditing = () => {
    cancelled.current = false;
    setDraft(latex);
    setIsEditing(true);
  };

  const cancelEditing = () => {
    cancelled.current = true;
    setIsEditing(false);
  };

  const handleSave = () => {
    if (cancelled.current) return;
    if (draft !== latex) updateAttributes({ latex: draft });
    setIsEditing(false);
  };

  return (
    <NodeViewWrapper as="span" className="inline-math">
      {!isEditing ? (
        <span 
          onClick={startEditing}
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
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="inline-math-input"
            autoFocus
            onBlur={handleSave}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                e.preventDefault();
                cancelEditing();
              } else if (e.key === "Enter") {
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
