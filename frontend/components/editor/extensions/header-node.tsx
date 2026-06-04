import { Node, mergeAttributes } from "@tiptap/core";
import {
  ReactNodeViewRenderer,
  NodeViewWrapper,
  NodeViewContent,
} from "@tiptap/react";
import NextImage from "next/image";
import React from "react";
import { Image as ImageIcon, Trash, X } from "lucide-react";

const PaperHeaderComponent = ({ node, updateAttributes, deleteNode }: any) => {
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    console.log("[DEBUG PaperHeaderComponent] MOUNT");
    return () => {
      console.log("[DEBUG PaperHeaderComponent] UNMOUNT");
    };
  }, []);

  console.log("[DEBUG PaperHeaderComponent] RERENDER");

  const handleLogoClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = () => {
        updateAttributes({ logoUrl: reader.result });
      };
      reader.readAsDataURL(file);
    }
  };

  const removeLogo = (e: React.MouseEvent) => {
    e.stopPropagation();
    updateAttributes({ logoUrl: null });
  };

  return (
    <NodeViewWrapper className="paper-header-block group">
      <div className="paper-header-shell">
        {/* Logo Area */}
        <div
          className={`paper-header-logo-area ${
            node.attrs.logoUrl
              ? "has-logo"
              : "is-empty print:hidden"
          }`}
          onClick={handleLogoClick}
          contentEditable={false}
        >
          {node.attrs.logoUrl ? (
            <div className="flex h-full w-full flex-col items-center justify-center gap-2">
              <NextImage
                src={node.attrs.logoUrl}
                alt="School Logo"
                width={128}
                height={128}
                unoptimized
                className="max-h-24 w-full object-contain"
              />
              <button
                type="button"
                className="opacity-0 group-hover:opacity-100 hover:bg-accent rounded p-0.5"
                onClick={removeLogo}
              >
                <X className="w-3 h-3 text-muted-foreground" />
              </button>
            </div>
          ) : (
            <div className="logo-placeholder print:hidden">
              <ImageIcon className="w-6 h-6" />
              <span className="text-[10px] uppercase font-bold tracking-wider">
                Logo
              </span>
            </div>
          )}
          <input
            type="file"
            ref={fileInputRef}
            className="hidden"
            accept="image/*"
            onChange={handleFileChange}
          />
        </div>

        {/* Details Area */}
        <div className="flex-1">
          <NodeViewContent className="paper-header-content" />
        </div>

        <button
          type="button"
          onClick={deleteNode}
          className="paper-header-delete print:hidden"
          title="Remove Header"
          contentEditable={false}
        >
          <Trash className="w-3 h-3" />
        </button>
      </div>
    </NodeViewWrapper>
  );
};

export const PaperHeaderBlock = Node.create({
  name: "paperHeaderBlock",
  group: "block paperBlock",
  content: "block+",
  draggable: true,
  isolating: true,

  addAttributes() {
    return {
      logoUrl: { default: null },
    };
  },

  parseHTML() {
    return [
      {
        tag: 'div[data-type="paper-header-block"]',
        getAttrs: (el) => {
          const element = el as HTMLElement;
          return { logoUrl: element.getAttribute("data-logo-url") || null };
        },
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    const logoUrl = HTMLAttributes.logoUrl as string | null;

    return [
      "div",
      mergeAttributes(HTMLAttributes, {
        "data-type": "paper-header-block",
        "data-logo-url": logoUrl,
        class: "paper-header-block",
      }),
      [
        "div",
        { class: "paper-header-layout" },
        logoUrl
          ? [
              "div",
              { class: "paper-header-logo" },
              [
                "img",
                {
                  src: logoUrl,
                  alt: "School Logo",
                  class: "paper-header-logo-image",
                },
              ],
            ]
          : ["div", { class: "paper-header-logo paper-header-logo-empty" }],
        ["div", { class: "paper-header-content" }, 0],
      ],
    ];
  },

  addNodeView() {
    return ReactNodeViewRenderer(PaperHeaderComponent);
  },
});
