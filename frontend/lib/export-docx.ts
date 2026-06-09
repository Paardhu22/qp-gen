import {
  Document,
  ImageRun,
  Packer,
  Paragraph,
  TextRun,
  HeadingLevel,
  Table,
  TableRow,
  TableCell,
  WidthType,
  AlignmentType,
  BorderStyle,
} from "docx";
import { saveAs } from "file-saver";
import { resolveFigureSrc } from "@/components/editor/extensions/float-image";

type DocxSource = string | HTMLElement;

export async function exportToDocx(
  source: DocxSource,
  filename: string = "exam-paper.docx",
) {
  // HTML→DOCX converter that handles paper structure (headers, sections,
  // questions, OR groups) and figures (`floatImage`). Figures are loaded
  // asynchronously — SVG data URLs are rasterized to PNG via canvas;
  // /media/... source images are fetched from the resolved Django origin.

  const parser = new CustomHtmlToDocxParser(source);
  const children = await parser.parse();

  const doc = new Document({
    sections: [
      {
        properties: {},
        children: children,
      },
    ],
  });

  const buffer = await Packer.toBlob(doc);
  saveAs(buffer, filename);
}

// ---------------------------------------------------------------------------
// Figure helpers — DOCX needs raw image bytes (PNG/JPEG); the editor's
// floatImage src can be a `data:image/svg+xml;base64,...` URL (the inline-SVG
// figure pipeline) or a `/media/...` path (a real PDF page image). For SVG we
// rasterize via canvas; for raster we fetch through resolveFigureSrc so the
// fetch hits Django, not the FE origin, which would 404.
// ---------------------------------------------------------------------------

type FigureKind = "png" | "jpg" | "gif" | "bmp" | "svg";

interface FigureBytes {
  kind: FigureKind;
  data: Uint8Array;
  /** For SVG, the rasterized PNG fallback (Word fallbacks for older versions). */
  fallback?: Uint8Array;
}

function detectKindFromMime(mime: string): FigureKind | null {
  const m = (mime || "").toLowerCase();
  if (m === "image/png") return "png";
  if (m === "image/jpeg" || m === "image/jpg") return "jpg";
  if (m === "image/gif") return "gif";
  if (m === "image/bmp") return "bmp";
  if (m === "image/svg+xml") return "svg";
  return null;
}

function detectKindFromExtension(url: string): FigureKind | null {
  const u = url.toLowerCase().split("?")[0];
  if (u.endsWith(".png")) return "png";
  if (u.endsWith(".jpg") || u.endsWith(".jpeg")) return "jpg";
  if (u.endsWith(".gif")) return "gif";
  if (u.endsWith(".bmp")) return "bmp";
  if (u.endsWith(".svg")) return "svg";
  return null;
}

async function rasterizeSvgToPng(
  svgUrl: string,
  width: number,
  height: number,
): Promise<Uint8Array> {
  return await new Promise<Uint8Array>((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = async () => {
      try {
        const canvas = document.createElement("canvas");
        // 2× supersample so the rasterized SVG looks sharp in Word.
        canvas.width = Math.max(1, width * 2);
        canvas.height = Math.max(1, height * 2);
        const ctx = canvas.getContext("2d");
        if (!ctx) throw new Error("canvas 2d unavailable");
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        const blob: Blob | null = await new Promise((r) =>
          canvas.toBlob((b) => r(b), "image/png"),
        );
        if (!blob) throw new Error("canvas toBlob returned null");
        const buf = new Uint8Array(await blob.arrayBuffer());
        resolve(buf);
      } catch (err) {
        reject(err);
      }
    };
    img.onerror = () => reject(new Error("svg image failed to load"));
    img.src = svgUrl;
  });
}

async function loadFigureBytes(
  rawSrc: string,
  width: number,
  height: number,
): Promise<FigureBytes | null> {
  const src = resolveFigureSrc(rawSrc);
  if (!src) return null;

  // data: URLs — decode bytes directly so we don't need a fetch.
  if (src.startsWith("data:")) {
    const match = src.match(/^data:([^;]+);base64,(.*)$/);
    if (!match) return null;
    const [, mime, b64] = match;
    const kind = detectKindFromMime(mime);
    if (!kind) return null;
    const raw = atob(b64);
    const bytes = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
    if (kind === "svg") {
      try {
        const fallback = await rasterizeSvgToPng(src, width, height);
        return { kind, data: bytes, fallback };
      } catch {
        return null;
      }
    }
    return { kind, data: bytes };
  }

  // Network fetch (raster source images via Django). Falls back silently
  // if CORS / 404 / network — we drop the figure rather than blow up the
  // whole export.
  try {
    // `credentials: "include"` would force the server to echo a specific
    // Access-Control-Allow-Origin AND set Access-Control-Allow-Credentials:
    // true. Media files don't need cookies, and many production deployments
    // serve /media/ via nginx without a credentials-allow header — that
    // mismatch silently drops every figure. "same-origin" lets cookies flow
    // when FE+BE share an origin (the common nginx-proxy deploy) and avoids
    // the preflight rejection on split-origin deploys.
    const response = await fetch(src, { mode: "cors", credentials: "same-origin" });
    if (!response.ok) return null;
    const blob = await response.blob();
    let kind = detectKindFromMime(blob.type);
    if (!kind) kind = detectKindFromExtension(src);
    if (!kind) return null;
    const bytes = new Uint8Array(await blob.arrayBuffer());
    if (kind === "svg") {
      // Rasterize the fetched SVG too (older Word renders the fallback).
      const objectUrl = URL.createObjectURL(blob);
      try {
        const fallback = await rasterizeSvgToPng(objectUrl, width, height);
        return { kind, data: bytes, fallback };
      } catch {
        return null;
      } finally {
        URL.revokeObjectURL(objectUrl);
      }
    }
    return { kind, data: bytes };
  } catch {
    return null;
  }
}

function buildImageParagraph(
  fig: FigureBytes,
  width: number,
  height: number,
): Paragraph {
  if (fig.kind === "svg" && fig.fallback) {
    return new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [
        new ImageRun({
          type: "svg",
          data: fig.data,
          transformation: { width, height },
          fallback: {
            type: "png",
            data: fig.fallback,
          },
        }),
      ],
    });
  }
  // For SVG without a fallback we drop the figure (we couldn't rasterize).
  // For raster, embed directly.
  const rasterKind = fig.kind === "svg" ? null : fig.kind;
  if (!rasterKind) {
    return new Paragraph({ children: [] });
  }
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    children: [
      new ImageRun({
        type: rasterKind,
        data: fig.data,
        transformation: { width, height },
      }),
    ],
  });
}

class CustomHtmlToDocxParser {
  constructor(private source: DocxSource) {}

  async parse(): Promise<(Paragraph | Table)[]> {
    const docxElements: (Paragraph | Table)[] = [];

    // Async figure loads need to happen IN ORDER so the resulting docx
    // preserves the source DOM order. We push a tagged sentinel into the
    // element array during the synchronous walk, then resolve all sentinels
    // and splice the resulting Paragraphs in their original positions.
    type FigureTask = {
      sentinelIndex: number;
      src: string;
      width: number;
      height: number;
    };
    const figureTasks: FigureTask[] = [];

    // Create a temporary DOM element to parse HTML
    if (typeof document === "undefined") return [];
    const container =
      typeof this.source === "string"
        ? (() => {
            const node = document.createElement("div");
            node.innerHTML = this.source;
            return node;
          })()
        : this.source;

    const shouldSkip = (el: HTMLElement) => {
      if (el.matches("button, input, select, textarea")) return true;
      if (el.closest(
        ".question-controls, .section-controls, .instruction-controls, .question-group-controls, .paper-header-delete, .logo-remove-btn, .block-drag-handle",
      )) {
        return true;
      }
      return false;
    };

    const paragraph = (
      text: string,
      options: { bold?: boolean; indentLeft?: number; spacingAfter?: number } = {},
    ) =>
      new Paragraph({
        children: [new TextRun({ text, bold: options.bold })],
        indent: options.indentLeft ? { left: options.indentLeft } : undefined,
        spacing: options.spacingAfter ? { after: options.spacingAfter } : undefined,
      });

    const cellBorder = {
      top: { style: BorderStyle.SINGLE, size: 1, color: "000000" },
      bottom: { style: BorderStyle.SINGLE, size: 1, color: "000000" },
      left: { style: BorderStyle.SINGLE, size: 1, color: "000000" },
      right: { style: BorderStyle.SINGLE, size: 1, color: "000000" },
    };

    const buildQuestionTable = (
      numberText: string,
      marksText: string,
      body: Paragraph[],
    ) => {
      const numCell = new TableCell({
        width: { size: 8, type: WidthType.PERCENTAGE },
        borders: cellBorder,
        children: [
          new Paragraph({
            text: numberText,
            alignment: AlignmentType.CENTER,
          }),
        ],
      });

      const bodyCell = new TableCell({
        width: { size: 84, type: WidthType.PERCENTAGE },
        borders: cellBorder,
        children: body,
      });

      const marksCell = new TableCell({
        width: { size: 8, type: WidthType.PERCENTAGE },
        borders: cellBorder,
        children: [
          new Paragraph({
            text: marksText,
            alignment: AlignmentType.CENTER,
          }),
        ],
      });

      return new Table({
        rows: [new TableRow({ children: [numCell, bodyCell, marksCell] })],
        width: { size: 100, type: WidthType.PERCENTAGE },
      });
    };

    const extractOptions = (listEl: HTMLElement | null) => {
      if (!listEl) return [] as Paragraph[];
      const items = Array.from(listEl.querySelectorAll("li"));
      return items.map((li, index) => {
        const label = String.fromCharCode(65 + index);
        return paragraph(`${label}) ${(li as HTMLElement).innerText}`, {
          indentLeft: 360,
        });
      });
    };

    const extractSubQuestions = (listEl: HTMLElement | null) => {
      if (!listEl) return [] as Paragraph[];
      const items = Array.from(listEl.querySelectorAll("li"));
      return items.map((li, index) => {
        const label = String.fromCharCode(97 + index);
        return paragraph(`${label}) ${(li as HTMLElement).innerText}`, {
          indentLeft: 360,
        });
      });
    };

    const buildQuestionBlock = (el: HTMLElement) => {
      const num = el.getAttribute("data-number") || "";
      const marks = el.getAttribute("data-marks");
      const marksText = marks ? `${marks} M` : "";

      const contentRoot =
        el.querySelector(".question-content") || el;
      const stem = contentRoot.querySelector("p");
      const stemText = stem ? (stem as HTMLElement).innerText : "";
      const list = contentRoot.querySelector("ol, ul");
      const options = extractOptions(list as HTMLElement | null);

      const body: Paragraph[] = [];
      if (stemText) {
        body.push(paragraph(stemText, { spacingAfter: 120 }));
      }
      if (options.length > 0) {
        body.push(...options);
      }

      const numberText = num ? `${num}.` : "";
      return buildQuestionTable(numberText, marksText, body);
    };

    const buildGroupedQuestionBlock = (el: HTMLElement) => {
      const num = el.getAttribute("data-number") || "";
      const marks = el.getAttribute("data-marks");
      const marksText = marks ? `${marks} M` : "";

      const contentRoot =
        el.querySelector(".question-content") || el;
      const stem = contentRoot.querySelector("p");
      const stemText = stem ? (stem as HTMLElement).innerText : "";
      const list = contentRoot.querySelector("ol, ul");
      const subQuestions = extractSubQuestions(list as HTMLElement | null);

      const body: Paragraph[] = [];
      if (stemText) {
        body.push(paragraph(stemText, { spacingAfter: 120 }));
      }
      if (subQuestions.length > 0) {
        body.push(...subQuestions);
      }

      const numberText = num ? `${num}.` : "";
      return buildQuestionTable(numberText, marksText, body);
    };

    const enqueueFigure = (el: HTMLElement) => {
      const rawSrc =
        el.getAttribute("data-src") ||
        el.querySelector("img")?.getAttribute("src") ||
        "";
      if (!rawSrc) return;
      const width = Math.max(
        80,
        Math.min(520, parseInt(el.getAttribute("data-width") || "320", 10) || 320),
      );
      // Maintain a sensible aspect — without intrinsic height info we
      // assume 4:3 for source PDF images and let SVG rasterization pick.
      const height = Math.round(width * 0.75);
      // Reserve a slot in the output array; we'll splice the resolved
      // Paragraph in by index after all figures are loaded.
      const placeholderParagraph = new Paragraph({ children: [] });
      docxElements.push(placeholderParagraph);
      const sentinelIndex = docxElements.length - 1;
      figureTasks.push({ sentinelIndex, src: rawSrc, width, height });
    };

    const walk = (node: ChildNode) => {
      if (node.nodeType !== Node.ELEMENT_NODE) return;
      const el = node as HTMLElement;
      if (shouldSkip(el)) return;

      const dataType = el.getAttribute("data-type");
      const hasClass = (name: string) => el.classList.contains(name);

      // Figure (inline-SVG or /media/ source image). Must be handled BEFORE
      // the generic DIV branch so we capture the floatImage NodeView wrapper.
      if (dataType === "float-image" || hasClass("float-image-wrapper")) {
        enqueueFigure(el);
        return;
      }

      if (dataType === "page") {
        const content = el.querySelector(".doc-page-content");
        const scope = content || el;
        Array.from(scope.childNodes).forEach(walk);
        return;
      }

      if (el.tagName === "H1") {
        docxElements.push(new Paragraph({ text: el.innerText, heading: HeadingLevel.HEADING_1, alignment: AlignmentType.CENTER }));
        return;
      }
      if (el.tagName === "H2") {
        docxElements.push(new Paragraph({ text: el.innerText, heading: HeadingLevel.HEADING_2, alignment: AlignmentType.CENTER }));
        return;
      }
      if (el.tagName === "H3") {
        docxElements.push(new Paragraph({ text: el.innerText, heading: HeadingLevel.HEADING_3, alignment: AlignmentType.CENTER }));
        return;
      }
      if (el.tagName === "P") {
        docxElements.push(new Paragraph({ 
          children: [new TextRun({ text: el.innerText, bold: el.querySelector("strong") !== null })] 
        }));
        return;
      }
      if (el.tagName === "HR") {
        docxElements.push(new Paragraph({ text: "__________________________________________________________________________", alignment: AlignmentType.CENTER }));
        return;
      }
      if (el.tagName === "TABLE") {
        const rows: TableRow[] = [];
        el.querySelectorAll("tr").forEach(tr => {
          const cells: TableCell[] = [];
          tr.querySelectorAll("td, th").forEach(td => {
            cells.push(new TableCell({
              children: [new Paragraph({ children: [new TextRun({ text: (td as HTMLElement).innerText, bold: td.tagName === "TH" })] })],
              width: { size: 100 / tr.children.length, type: WidthType.PERCENTAGE }
            }));
          });
          rows.push(new TableRow({ children: cells }));
        });
        docxElements.push(new Table({ rows, width: { size: 100, type: WidthType.PERCENTAGE } }));
        return;
      }

      if (el.tagName === "DIV") {
        if (dataType === "paper-header-block") {
          const headerContent = el.querySelector(".paper-header-content");
          if (headerContent) {
            Array.from(headerContent.childNodes).forEach(walk);
          }
          // Issue 1 — emit the date row exactly once, as the formatted string.
          // The editor view shows only the `<input type="date">`, so the DOCX
          // walker must look up the persisted `data-date-value` rather than
          // any visible "Jun 08, 2026" sibling (which no longer exists in
          // the editor DOM).
          const dateRow = el.querySelector<HTMLElement>(
            ".paper-header-date-row",
          );
          if (dateRow) {
            const input = dateRow.querySelector<HTMLInputElement>(
              "input.paper-header-date-input",
            );
            const iso =
              dateRow.getAttribute("data-date-value") ||
              input?.value ||
              input?.getAttribute("value") ||
              "";
            if (iso) {
              const d = new Date(iso);
              if (!Number.isNaN(d.getTime())) {
                let pretty: string;
                try {
                  pretty = new Intl.DateTimeFormat(undefined, {
                    day: "2-digit",
                    month: "short",
                    year: "numeric",
                  }).format(d);
                } catch {
                  pretty = d.toDateString();
                }
                docxElements.push(
                  new Paragraph({
                    children: [
                      new TextRun({ text: "Date: ", bold: true }),
                      new TextRun({ text: pretty }),
                    ],
                  }),
                );
              }
            }
          }
          return;
        }
        if (dataType === "section-block" || hasClass("section-block")) {
          docxElements.push(new Paragraph({ text: el.innerText, heading: HeadingLevel.HEADING_3 }));
          return;
        }
        if (dataType === "instruction-block" || hasClass("instruction-block")) {
          docxElements.push(new Paragraph({ children: [new TextRun({ text: "Instructions:", bold: true })] }));
          const listItems = el.querySelectorAll("li");
          if (listItems.length > 0) {
            listItems.forEach((li, index) => {
              const text = `${index + 1}. ${(li as HTMLElement).innerText}`;
              docxElements.push(new Paragraph({ text }));
            });
          } else {
            el.querySelectorAll("p").forEach(p => {
              docxElements.push(new Paragraph({ text: (p as HTMLElement).innerText }));
            });
          }
          return;
        }
        if (dataType === "question-block" || hasClass("question-block")) {
          docxElements.push(buildQuestionBlock(el));
          return;
        }
        if (dataType === "grouped-question-block" || hasClass("grouped-question-block")) {
          docxElements.push(buildGroupedQuestionBlock(el));
          return;
        }
        if (dataType === "math-block") {
          const latex = el.getAttribute("data-latex") || el.innerText;
          docxElements.push(new Paragraph({ text: `$$ ${latex} $$`, alignment: AlignmentType.CENTER }));
          return;
        }
        if (dataType === "question-group" || hasClass("question-group")) {
          // Issue 4 — emit the GROUP HEADER (e.g. "Answer any ONE of the
          // following:") exactly once at the top, then walk the immediate
          // question siblings, interleaving a bold-centred "OR" between
          // each consecutive pair. The OR is not a child node in the
          // document any more (see or-group-invariant.ts), so the DOCX
          // pipeline must reconstruct it the same way the editor's CSS
          // pseudo-element does.
          const groupLabel = el.getAttribute("data-label");
          if (groupLabel) {
            docxElements.push(
              new Paragraph({
                children: [new TextRun({ text: groupLabel, bold: true })],
              }),
            );
          }
          const questionSiblings = Array.from(
            el.querySelectorAll<HTMLElement>(
              ":scope > div[data-type='question-block'], :scope > div[data-type='grouped-question-block'], :scope > .question-block, :scope > .grouped-question-block",
            ),
          );
          questionSiblings.forEach((q, idx) => {
            if (idx > 0) {
              docxElements.push(
                new Paragraph({
                  children: [new TextRun({ text: "OR", bold: true })],
                  alignment: AlignmentType.CENTER,
                }),
              );
            }
            const isGrouped =
              q.getAttribute("data-type") === "grouped-question-block" ||
              q.classList.contains("grouped-question-block");
            docxElements.push(
              isGrouped ? buildGroupedQuestionBlock(q) : buildQuestionBlock(q),
            );
          });
          return;
        }

        Array.from(el.childNodes).forEach(walk);
        return;
      }

      Array.from(el.childNodes).forEach(walk);
    };

    Array.from(container.childNodes).forEach(walk);

    // Resolve all figures in parallel and replace the placeholder
    // Paragraphs at their reserved indices. Failed loads keep the empty
    // placeholder (an empty paragraph) so the surrounding question text
    // still surfaces — matches the "text-self-contained fallback"
    // contract from the backend figure pipeline.
    const figureResults = await Promise.all(
      figureTasks.map(async (task) => {
        const fig = await loadFigureBytes(task.src, task.width, task.height);
        return { task, fig };
      }),
    );
    for (const { task, fig } of figureResults) {
      if (!fig) continue;
      try {
        docxElements[task.sentinelIndex] = buildImageParagraph(
          fig,
          task.width,
          task.height,
        );
      } catch {
        // ImageRun construction can throw on malformed bytes; leave the
        // empty placeholder rather than aborting the whole export.
      }
    }

    return docxElements;
  }
}
