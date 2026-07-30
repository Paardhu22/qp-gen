"use client";

import { API_BASE_URL } from "@/lib/api-base-url";
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
// deployment where /media/ is routed to Django from the same host).
//
// The origin comes from `lib/api-base-url` — the same value the API client
// uses — so the FE/API and FE/media origins can never drift apart. That
// module also owns the dev fallback and the build-time guard that stops an
// unconfigured origin from shipping.

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

/**
 * Size presets, in px, measured against the A4 content column.
 *
 * The printable width of the A4 page is 794px less its margins, which leaves
 * ~680px — the same ceiling the drag handle already clamps to. "Full" is a
 * little under that so a full-width figure still breathes inside the text
 * block rather than butting against both margins.
 */
export const SIZE_SMALL = 200;
export const SIZE_HALF = 340;
export const SIZE_FULL = 660;

const FloatImageComponent = ({
  node,
  updateAttributes,
  deleteNode,
  selected,
}: FloatImageProps) => {
  const [isResizing, setIsResizing] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const startRef = useRef({ x: 0, width: 0 });
  const { src, alt, width, align } = node.attrs;

  // Cluster B (defense in depth): when the image fails to load — e.g.
  // a stale `/media/...` URL, a private S3 object whose signature
  // expired, or a placeholder src the generation layer didn't catch —
  // delete the node entirely so the editor doesn't render the
  // 1 px-bordered empty box that looks like a horizontal underline.
  // The bordered empty <img> was the visible "Question visual" /
  // figure-placeholder artifact users reported. Without a usable
  // image the question stem must stand on its own.
  useEffect(() => {
    if (loadFailed) {
      try {
        deleteNode();
      } catch {
        // deleteNode can throw if the node was already removed (e.g.
        // during teardown). Swallow — there's nothing left to delete.
      }
    }
  }, [loadFailed, deleteNode]);

  // Reset the failure flag whenever the src attribute changes (e.g.
  // the user re-points the node at a new figure).
  useEffect(() => {
    setLoadFailed(false);
  }, [src]);

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
          {/* Size + alignment + delete toolbar */}
          <div className="float-image-controls float-image-hide-in-pdf">
            {/* Size presets.
                Free-drag resizing already exists (the corner handle), but a
                teacher laying out a paper wants "half the page", not 340
                pixels — and dragging every figure to roughly-the-same-width by
                eye is how a paper ends up with six slightly different column
                widths. The presets are measured against the A4 content column
                so "Full" means full, not "as wide as I could drag it". */}
            {(
              [
                ["S", SIZE_SMALL, "Small"],
                ["½", SIZE_HALF, "Half width"],
                ["W", SIZE_FULL, "Full width"],
              ] as [string, number, string][]
            ).map(([label, px, title]) => (
              <button
                key={title}
                className={`float-img-btn${width === px ? " active" : ""}`}
                onMouseDown={(e) => {
                  e.preventDefault();
                  updateAttributes({ width: px });
                }}
                title={title}
              >
                <span className="text-[10px] font-semibold leading-none">
                  {label}
                </span>
              </button>
            ))}
            <span className="float-img-divider" />
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
            onError={() => setLoadFailed(true)}
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

  // Cluster A.3 — make Backspace / Delete remove the floatImage when it is
  // the selected node. Without an explicit handler the keystroke sometimes
  // bubbles to the surrounding questionBlock, which swallows it and leaves
  // the image in place. We deliberately only intercept when the selection
  // is a NodeSelection over THIS node so we don't break normal Backspace
  // in surrounding text or other selectable atoms.
  addKeyboardShortcuts() {
    const deleteIfSelected = () => {
      const { state } = this.editor;
      const sel: any = state.selection;
      const node = sel?.node;
      if (node && node.type?.name === this.name) {
        return this.editor.commands.deleteSelection();
      }
      return false;
    };
    return {
      Backspace: deleteIfSelected,
      Delete: deleteIfSelected,
    };
  },

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
