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
import {
  DEFAULT_LOGO_HEIGHT,
  fitLogo,
  formatPaperDate,
  resolveLogoSide,
  type LogoAlign,
} from "@/components/editor/masthead";

function logoHeightOf(value: unknown): number {
  const height = Number(value);
  return Number.isFinite(height) && height > 0 ? height : DEFAULT_LOGO_HEIGHT;
}

const PaperHeaderComponent = ({ node, updateAttributes, deleteNode, editor }: any) => {
  const showDate = Boolean(node.attrs.showDate);
  const dateValue = node.attrs.dateValue || "";
  const logoUrl: string = node.attrs.logoUrl || "";
  const logoHeight = logoHeightOf(node.attrs.logoHeight);
  const logoAlign: LogoAlign = node.attrs.logoAlign || "auto";
  const [pickerOpen, setPickerOpen] = React.useState(false);
  // The logo's shape, read once it loads. Until then it shows at its height
  // cap, and "auto" assumes a crest. Keyed by URL, so a new logo is measured
  // afresh without an effect racing a cached image's load event.
  const [measured, setMeasured] = React.useState<{ url: string; ratio: number } | null>(null);
  const ratio = measured?.url === logoUrl ? measured.ratio : null;
  const side = resolveLogoSide(logoAlign, ratio);
  const box = ratio ? fitLogo(ratio, logoHeight, side) : null;

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
    <div className="paper-header-logo-wrap" contentEditable={false} data-side={side}>
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
        onLoad={(e) => {
          const { naturalWidth, naturalHeight } = e.currentTarget;
          if (naturalWidth > 0 && naturalHeight > 0) {
            setMeasured({ url: logoUrl, ratio: naturalWidth / naturalHeight });
          }
        }}
        // Explicit width AND height once the shape is known: html2canvas
        // cannot do `object-fit`, and the DOCX export reads this box back.
        style={box ? { width: box.width, height: box.height } : { maxHeight: logoHeight }}
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

  // The logo's invisible twin on the far side, so the title centres on the
  // page rather than in whatever width the logo leaves.
  const mirror =
    logo && box && side !== "top" ? (
      <div
        className="paper-header-logo-mirror"
        contentEditable={false}
        aria-hidden="true"
        data-side={side === "left" ? "right" : "left"}
        style={{ width: box.width, height: box.height }}
      />
    ) : null;

  return (
    <NodeViewWrapper className="paper-header-block group">
      <div className="paper-header-shell">
        {logo}
        {mirror}
        <NodeViewContent className="paper-header-content" />
        {/* G — date renders ONCE as a formatted span ("Jun 08, 2026").
            The native `<input type="date">` is overlaid invisibly on top of
            the span so a click anywhere on the date opens the picker. PDF/DOCX
            export keeps the same formatted span. */}
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

        {editor?.isEditable && (
          <div className="paper-header-actions print:hidden" contentEditable={false}>
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
          height={logoHeight}
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
      // Printed HEIGHT in px; the width follows from the logo's shape, capped
      // (`fitLogo`). Papers saved with the old `logoWidth` take the default.
      logoHeight: { default: DEFAULT_LOGO_HEIGHT },
      // "auto" | "left" | "right" | "top". Auto puts a wordmark on top and a
      // crest at the left; a school's own choice is a house style.
      logoAlign: { default: "auto" },
    };
  },

  parseHTML() {
    return [
      {
        tag: 'div[data-type="paper-header-block"]',
        getAttrs: (el) => {
          const element = el as HTMLElement;
          const align = element.getAttribute("data-logo-align");
          return {
            showDate: element.getAttribute("data-show-date") === "true",
            dateValue: element.getAttribute("data-date-value") || "",
            logoUrl: element.getAttribute("data-logo-url") || "",
            logoHeight: logoHeightOf(element.getAttribute("data-logo-height")),
            logoAlign:
              align === "left" || align === "right" || align === "top" ? align : "auto",
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
    const logoHeight = logoHeightOf(HTMLAttributes.logoHeight);
    const logoAlign = (HTMLAttributes.logoAlign as string) || "auto";
    // Static markup cannot read the logo's shape, so "auto" assumes a crest.
    const side = resolveLogoSide(logoAlign, null);

    // The logo is emitted as a real <img> in the serialized HTML, not as a
    // background or a NodeView-only flourish: the DOCX walker looks for
    // `.paper-header-logo`, and a crest that exists only in the React view
    // would vanish from any file built from this markup.
    const logoNode = logoUrl
      ? [
          "div",
          { class: "paper-header-logo-wrap", "data-side": side },
          [
            "img",
            {
              src: resolveFigureSrc(logoUrl),
              class: "paper-header-logo",
              alt: "",
              style: `max-height:${logoHeight}px;`,
            },
          ],
        ]
      : null;

    return [
      "div",
      mergeAttributes(HTMLAttributes, {
        "data-type": "paper-header-block",
        "data-show-date": String(showDate),
        "data-date-value": dateValue,
        "data-logo-url": logoUrl,
        "data-logo-height": String(logoHeight),
        "data-logo-align": logoAlign,
        class: "paper-header-block",
      }),
      [
        "div",
        { class: "paper-header-shell" },
        ...(logoNode ? [logoNode] : []),
        // ProseMirror's rule: the content hole is its parent's only child.
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
    ];
  },

  addNodeView() {
    return ReactNodeViewRenderer(PaperHeaderComponent);
  },
});
