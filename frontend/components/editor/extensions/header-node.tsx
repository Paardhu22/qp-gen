import { Node, mergeAttributes } from "@tiptap/core";
import {
  ReactNodeViewRenderer,
  NodeViewWrapper,
  NodeViewContent,
} from "@tiptap/react";
import NextImage from "next/image";
import React from "react";
import { Calendar, Image as ImageIcon, Trash, X } from "lucide-react";

// Cluster C.2 — locale-aware date formatter used by both the editor
// rendering and the printed output. We format from a stable ISO string so
// the persisted value is timezone-neutral; the display string is computed
// fresh on each render against the viewer's locale.
function formatPaperDate(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  try {
    return new Intl.DateTimeFormat(undefined, {
      day: "2-digit",
      month: "short",
      year: "numeric",
    }).format(d);
  } catch {
    return d.toDateString();
  }
}

const PaperHeaderComponent = ({ node, updateAttributes, deleteNode }: any) => {
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const showDate = Boolean(node.attrs.showDate);
  const dateValue = node.attrs.dateValue || "";
  // Default the picker to today when the field is being enabled for the
  // first time. The persisted value never changes implicitly — only on
  // user action — so a draft from yesterday doesn't silently advance.
  const dateInputValue = dateValue || new Date().toISOString().slice(0, 10);
  const handleToggleDate = () => {
    if (showDate) {
      updateAttributes({ showDate: false });
    } else {
      updateAttributes({ showDate: true, dateValue: dateInputValue });
    }
  };
  const handleDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    updateAttributes({ dateValue: e.target.value });
  };

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

        {/* Details Area.
            G — date renders ONCE as a formatted span ("Jun 08, 2026").
            The native `<input type="date">` is overlaid invisibly on
            top of the span so a click anywhere on the date opens the
            picker. This collapses the prior split where some browsers
            also painted the raw `YYYY-MM-DD` next to the formatted
            value, leaving the teacher unable to delete the "written"
            half. PDF/DOCX export keeps the same formatted span. */}
        <div className="flex-1">
          <NodeViewContent className="paper-header-content" />
          {showDate && (
            <div
              className="paper-header-date-row"
              contentEditable={false}
              data-date-value={dateValue || dateInputValue}
            >
              <span className="paper-header-date-label">Date:</span>
              <span className="paper-header-date-picker-wrap">
                <span className="paper-header-date-display">
                  {formatPaperDate(dateValue || dateInputValue) || "—"}
                </span>
                <input
                  type="date"
                  value={dateValue || dateInputValue}
                  onChange={handleDateChange}
                  className="paper-header-date-input"
                  aria-label="Paper date"
                />
              </span>
            </div>
          )}
        </div>

        <div
          className="paper-header-actions print:hidden"
          contentEditable={false}
        >
          <button
            type="button"
            onClick={handleToggleDate}
            className={`paper-header-action ${showDate ? "is-active" : ""}`}
            title={showDate ? "Remove date field" : "Add date field"}
          >
            <Calendar className="w-3 h-3" />
          </button>
          <button
            type="button"
            onClick={deleteNode}
            className="paper-header-delete"
            title="Remove Header"
          >
            <Trash className="w-3 h-3" />
          </button>
        </div>
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
      // Cluster C.2 — optional locale-formatted date field. Persisted as
      // an ISO `YYYY-MM-DD` string so the editor + exports + answer-script
      // generator all read a stable, timezone-neutral value.
      showDate: { default: false },
      dateValue: { default: "" },
    };
  },

  parseHTML() {
    return [
      {
        tag: 'div[data-type="paper-header-block"]',
        getAttrs: (el) => {
          const element = el as HTMLElement;
          return {
            logoUrl: element.getAttribute("data-logo-url") || null,
            showDate: element.getAttribute("data-show-date") === "true",
            dateValue: element.getAttribute("data-date-value") || "",
          };
        },
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    const logoUrl = HTMLAttributes.logoUrl as string | null;
    const showDate = Boolean(HTMLAttributes.showDate);
    const dateValue = (HTMLAttributes.dateValue as string) || "";
    const formattedDate = formatPaperDate(dateValue);

    return [
      "div",
      mergeAttributes(HTMLAttributes, {
        "data-type": "paper-header-block",
        "data-logo-url": logoUrl,
        "data-show-date": String(showDate),
        "data-date-value": dateValue,
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
        [
          "div",
          { class: "paper-header-content-col" },
          ["div", { class: "paper-header-content" }, 0],
          ...(showDate && formattedDate
            ? [[
                "div",
                { class: "paper-header-date-row" },
                ["span", { class: "paper-header-date-label" }, "Date:"],
                ["span", { class: "paper-header-date-display" }, " " + formattedDate],
              ]]
            : []),
        ],
      ],
    ];
  },

  addNodeView() {
    return ReactNodeViewRenderer(PaperHeaderComponent);
  },
});
