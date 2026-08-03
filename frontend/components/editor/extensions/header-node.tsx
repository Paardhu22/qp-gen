import { Node, mergeAttributes } from "@tiptap/core";
import {
  ReactNodeViewRenderer,
  NodeViewWrapper,
  NodeViewContent,
} from "@tiptap/react";
import React from "react";
import { Calendar, Image as ImageIcon, Trash } from "lucide-react";

import { HeaderLogoPicker } from "@/components/editor/header-logo-picker";
import { resolveFigureSrc } from "@/components/editor/extensions/float-image";

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

const PaperHeaderComponent = ({ node, updateAttributes, deleteNode, editor }: any) => {
  const showDate = Boolean(node.attrs.showDate);
  const dateValue = node.attrs.dateValue || "";
  const logoUrl: string = node.attrs.logoUrl || "";
  const logoWidth: number = Number(node.attrs.logoWidth) || 72;
  const logoAlign: "left" | "right" =
    node.attrs.logoAlign === "right" ? "right" : "left";
  const [pickerOpen, setPickerOpen] = React.useState(false);
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

  const logo = logoUrl ? (
    <div
      className="paper-header-logo-wrap"
      contentEditable={false}
      data-logo-align={logoAlign}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        // The stored URL is relative (`/media/...`), which only resolves when
        // the frontend and Django share an origin. `resolveFigureSrc` prefixes
        // the API origin otherwise — same helper the figure images use, so the
        // two cannot drift. Deliberately NO `crossOrigin` attribute: setting it
        // against a media host that returns no CORS headers makes the image
        // fail to load outright, and the PDF path does not need it because it
        // inlines every <img> as a data URL before rasterising.
        src={resolveFigureSrc(logoUrl)}
        alt=""
        className="paper-header-logo"
        style={{ width: `${logoWidth}px` }}
      />
      {editor?.isEditable ? (
        <button
          type="button"
          onClick={() => updateAttributes({ logoUrl: "" })}
          className="logo-remove-btn print:hidden"
          title="Remove logo"
        >
          <Trash className="w-2.5 h-2.5" />
        </button>
      ) : null}
    </div>
  ) : null;

  return (
    <NodeViewWrapper className="paper-header-block group">
      <div className="paper-header-shell">
        {logoAlign === "left" ? logo : null}
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
                {editor?.isEditable && (
                  <input
                    type="date"
                    value={dateValue || dateInputValue}
                    onChange={handleDateChange}
                    className="paper-header-date-input"
                    aria-label="Paper date"
                  />
                )}
              </span>
            </div>
          )}
        </div>

        {logoAlign === "right" ? logo : null}

        {editor?.isEditable && (
          <div
            className="paper-header-actions print:hidden"
            contentEditable={false}
          >
            <button
              type="button"
              onClick={() => setPickerOpen(true)}
              className={`paper-header-action ${logoUrl ? "is-active" : ""}`}
              title={logoUrl ? "Change logo" : "Add your institute's logo"}
            >
              <ImageIcon className="w-3 h-3" />
            </button>
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
        )}
      </div>

      {pickerOpen ? (
        <HeaderLogoPicker
          currentUrl={logoUrl}
          width={logoWidth}
          align={logoAlign}
          onClose={() => setPickerOpen(false)}
          onApply={(next) => {
            updateAttributes(next);
            setPickerOpen(false);
          }}
        />
      ) : null}
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
      // Cluster C.2 — optional locale-formatted date field. Persisted as
      // an ISO `YYYY-MM-DD` string so the editor + exports + answer-script
      // generator all read a stable, timezone-neutral value.
      showDate: { default: false },
      dateValue: { default: "" },
      // The institute's logo. Persisted as the app's own stable `/media/...`
      // URL (see backend `services/media_urls.py`), never a presigned S3 link
      // — a saved paper outlives any signature, and a paper reopened next term
      // must not show a broken crest.
      logoUrl: { default: "" },
      // Printed width in px. Height follows from the intrinsic aspect ratio, so
      // there is one number to store and no way for the two to disagree.
      logoWidth: { default: 72 },
      // "left" | "right" — which end of the masthead the crest sits at. Indian
      // question papers use both, and a school's choice is a house style.
      logoAlign: { default: "left" },
    };
  },

  parseHTML() {
    return [
      {
        tag: 'div[data-type="paper-header-block"]',
        getAttrs: (el) => {
          const element = el as HTMLElement;
          const width = parseInt(
            element.getAttribute("data-logo-width") || "",
            10,
          );
          return {
            showDate: element.getAttribute("data-show-date") === "true",
            dateValue: element.getAttribute("data-date-value") || "",
            logoUrl: element.getAttribute("data-logo-url") || "",
            logoWidth: Number.isFinite(width) && width > 0 ? width : 72,
            logoAlign:
              element.getAttribute("data-logo-align") === "right"
                ? "right"
                : "left",
          };
        },
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    const showDate = Boolean(HTMLAttributes.showDate);
    const dateValue = (HTMLAttributes.dateValue as string) || "";
    const formattedDate = formatPaperDate(dateValue);
    const logoUrl = (HTMLAttributes.logoUrl as string) || "";
    const logoWidth = Number(HTMLAttributes.logoWidth) || 72;
    const logoAlign =
      HTMLAttributes.logoAlign === "right" ? "right" : "left";

    // The logo is emitted as a real <img> in the serialized HTML, not as a
    // background or a NodeView-only flourish. Both export paths read this
    // markup — html2canvas rasterises it and the DOCX walker looks for
    // `.paper-header-logo` — so a crest that exists only in the React view
    // would print on screen and vanish from every file the teacher sends out.
    const logoNode = logoUrl
      ? [
          "img",
          {
            src: resolveFigureSrc(logoUrl),
            class: "paper-header-logo",
            alt: "",
            style: `width:${logoWidth}px;height:auto;`,
          },
        ]
      : null;

    const contentCol = [
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
    ];

    return [
      "div",
      mergeAttributes(HTMLAttributes, {
        "data-type": "paper-header-block",
        "data-show-date": String(showDate),
        "data-date-value": dateValue,
        "data-logo-url": logoUrl,
        "data-logo-width": String(logoWidth),
        "data-logo-align": logoAlign,
        class: "paper-header-block",
      }),
      [
        "div",
        { class: `paper-header-layout paper-header-logo-${logoAlign}` },
        ...(logoNode && logoAlign === "left" ? [logoNode] : []),
        contentCol,
        ...(logoNode && logoAlign === "right" ? [logoNode] : []),
      ],
    ];
  },

  addNodeView() {
    return ReactNodeViewRenderer(PaperHeaderComponent);
  },
});
