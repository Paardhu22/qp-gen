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

// Backend emits source-image URLs as relative paths (`/media/pdf_images/...`)
// by default because Django's default_storage.url() returns the MEDIA_URL
// prefix only. Two env knobs make those URLs absolute, and you need EITHER
// (not both):
//
//   • Backend: set `AOS_PUBLIC_MEDIA_BASE_URL` (config/settings.py:110) so
//     `services/document_service.py:_public_media_url` returns an absolute
//     URL up front. This is the preferred prod knob — the doc and the SSE
//     payload stay portable across origins.
//   • Frontend: set `NEXT_PUBLIC_API_BASE_URL`. `resolveFigureSrc` (this
//     file) prefixes it to any leading-slash src at render time. Useful
//     when the FE and BE live on different origins (Next dev :3000 + Django
//     :8000) and you don't want to bake the BE origin into the persisted
//     doc.
//
// If BOTH are unset, source-image URLs stay relative and only render when
// the FE and BE share an origin (typical for an nginx-proxied prod
// deployment where /media/ is routed to Django from the same host). The
// `localhost:8000` fallback here is a dev affordance ONLY — production
// must set one of the two env vars above. We reuse the same fallback as
// `lib/api-client.ts:API_BASE_URL` to keep the FE/API and FE/media origins
// in sync; if api-client can talk to Django, this resolver can too.
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export function resolveFigureSrc(src: string | null | undefined): string {
  if (!src) return "";
  if (
    src.startsWith("data:") ||
    src.startsWith("http://") ||
    src.startsWith("https://") ||
    src.startsWith("blob:")
  ) {
    return src;
  }
  if (src.startsWith("/")) {
    return `${API_BASE_URL}${src}`;
  }
  return src;
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
            src={resolveFigureSrc(src)}
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
          src: resolveFigureSrc(src),
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
