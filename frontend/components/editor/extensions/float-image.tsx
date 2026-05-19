"use client";

import { Node, mergeAttributes } from "@tiptap/core";
import { ReactNodeViewRenderer, NodeViewWrapper } from "@tiptap/react";
import React, { useEffect, useRef, useState } from "react";
import { AlignLeft, AlignCenter, AlignRight, Trash } from "lucide-react";

interface FloatImageProps {
  node: any;
  updateAttributes: (attrs: Record<string, any>) => void;
  deleteNode: () => void;
  selected: boolean;
}

const FloatImageComponent = ({
  node,
  updateAttributes,
  deleteNode,
  selected,
}: FloatImageProps) => {
  const [isResizing, setIsResizing] = useState(false);
  const startRef = useRef({ x: 0, width: 0 });
  const { src, alt, width, align } = node.attrs;

  useEffect(() => {
    if (!isResizing) return;
    const handleMove = (e: MouseEvent) => {
      const dx = e.clientX - startRef.current.x;
      // clamp: 80 px min, 680 px max (fits inside A4 page content area)
      const next = Math.max(80, Math.min(680, startRef.current.width + dx));
      updateAttributes({ width: Math.round(next) });
    };
    const handleUp = () => setIsResizing(false);
    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseup", handleUp);
    return () => {
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseup", handleUp);
    };
  }, [isResizing, updateAttributes]);

  const alignJustify =
    align === "left"
      ? "flex-start"
      : align === "right"
        ? "flex-end"
        : "center";

  return (
    <NodeViewWrapper className="float-image-wrapper group">
      <div
        contentEditable={false}
        className="float-image-outer"
        style={{ display: "flex", justifyContent: alignJustify }}
      >
        <div
          className={[
            "float-image-container",
            selected ? "is-selected" : "",
            isResizing ? "is-resizing" : "",
          ]
            .filter(Boolean)
            .join(" ")}
          style={{
            position: "relative",
            display: "inline-block",
            width: `${width}px`,
            maxWidth: "100%",
          }}
        >
          {/* Alignment + delete toolbar */}
          <div className="float-image-controls float-image-hide-in-pdf">
            {(
              [
                ["left", <AlignLeft key="l" className="w-3 h-3" />],
                ["center", <AlignCenter key="c" className="w-3 h-3" />],
                ["right", <AlignRight key="r" className="w-3 h-3" />],
              ] as [string, React.ReactNode][]
            ).map(([dir, icon]) => (
              <button
                key={dir}
                className={`float-img-btn${align === dir ? " active" : ""}`}
                onMouseDown={(e) => {
                  e.preventDefault();
                  updateAttributes({ align: dir });
                }}
                title={`Align ${dir}`}
              >
                {icon}
              </button>
            ))}
            <span className="float-img-divider" />
            <button
              className="float-img-btn"
              onMouseDown={(e) => {
                e.preventDefault();
                deleteNode();
              }}
              title="Delete image"
            >
              <Trash className="w-3 h-3" />
            </button>
          </div>

          {/* Image */}
          <img
            src={src}
            alt={alt || ""}
            draggable={false}
            className="float-image-img"
          />

          {/* Resize handle — bottom-right corner */}
          <div
            className="float-image-resize-handle float-image-hide-in-pdf"
            title="Drag to resize"
            onMouseDown={(e) => {
              e.preventDefault();
              e.stopPropagation();
              startRef.current = { x: e.clientX, width };
              setIsResizing(true);
            }}
          />
        </div>
      </div>
    </NodeViewWrapper>
  );
};

// ---------------------------------------------------------------------------
// Tiptap Node definition
// ---------------------------------------------------------------------------

export const FloatImage = Node.create({
  name: "floatImage",
  // Lives at page level or inside question/instruction bodies
  group: "block paperBlock",
  atom: true,
  draggable: true,
  selectable: true,

  addAttributes() {
    return {
      src:   { default: null },
      alt:   { default: "" },
      width: { default: 300 },  // px
      align: { default: "center" }, // "left" | "center" | "right"
    };
  },

  parseHTML() {
    return [
      {
        tag: 'div[data-type="float-image"]',
        getAttrs: (el) => {
          const e = el as HTMLElement;
          return {
            src:   e.getAttribute("data-src"),
            alt:   e.getAttribute("data-alt") || "",
            width: parseInt(e.getAttribute("data-width") || "300", 10),
            align: e.getAttribute("data-align") || "center",
          };
        },
      },
    ];
  },

  renderHTML({ node }) {
    const { src, alt, width, align } = node.attrs as {
      src: string;
      alt: string;
      width: number;
      align: string;
    };
    const justify =
      align === "left"
        ? "flex-start"
        : align === "right"
          ? "flex-end"
          : "center";

    return [
      "div",
      mergeAttributes({
        "data-type":  "float-image",
        "data-src":   src,
        "data-alt":   alt || "",
        "data-width": String(width),
        "data-align": align,
        class: "float-image-wrapper",
        style: `display:flex;justify-content:${justify}`,
      }),
      [
        "img",
        {
          src,
          alt: alt || "",
          style: `width:${width}px;max-width:100%;height:auto;display:block;`,
        },
      ],
    ];
  },

  addNodeView() {
    return ReactNodeViewRenderer(FloatImageComponent);
  },

  addCommands() {
    return {
      insertFloatImage:
        (attrs: {
          src: string;
          alt?: string;
          width?: number;
          align?: string;
        }) =>
        ({ commands }: any) => {
          return commands.insertContent({
            type: this.name,
            attrs: {
              src:   attrs.src,
              alt:   attrs.alt   ?? "",
              width: attrs.width ?? 300,
              align: attrs.align ?? "center",
            },
          });
        },
    } as any;
  },
});
