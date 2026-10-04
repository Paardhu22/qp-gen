/**
 * A paper as a Word document, laid out like the printed PDF.
 *
 * Built from the editor's document, not scraped from its DOM. The DOM is the
 * wrong source: the live node views carry no question numbers or marks as
 * attributes, a question's options sit inside its text, and an OR group's
 * branches are anonymous wrappers — so the old scraper printed questions with
 * no numbers, options run into the stem, and every OR question dropped. The
 * document has all of it explicitly.
 *
 * Geometry follows the editor's A4 sheet (794 px, 56 px margins): 1 px is 15
 * twips, so a 56 px column is 840. Typography is the sheet's: Times New Roman,
 * 12 pt, black.
 *
 * Pure apart from `loadImage`, so `scripts/test-docx-paper.mjs` can build a
 * paper in Node with a stub loader.
 */

import {
  AlignmentType,
  BorderStyle,
  Document,
  HeadingLevel,
  ImageRun,
  LineRuleType,
  Math as DocxMath,
  Paragraph,
  ShadingType,
  Table,
  TableCell,
  TableLayoutType,
  TableRow,
  TabStopType,
  TextRun,
  VerticalAlign,
  WidthType,
  type ParagraphChild,
} from "docx";

import {
  DEFAULT_LOGO_HEIGHT,
  fitLogo,
  formatPaperDate,
  resolveLogoSide,
} from "@/components/editor/masthead";
import { latexToMath } from "./docx-math";

export interface LoadedImage {
  data: Uint8Array;
  type: "png" | "jpg" | "gif" | "bmp";
  /** Intrinsic size in CSS px, for the aspect ratio. */
  width: number;
  height: number;
}

export type ImageLoader = (src: string) => Promise<LoadedImage | null>;

interface Json {
  type: string;
  attrs?: Record<string, any>;
  content?: Json[];
  text?: string;
  marks?: { type: string; attrs?: Record<string, any> }[];
}

type Block = Paragraph | Table;

// ── Geometry and type ──────────────────────────────────────────────────

const TWIPS_PER_PX = 15;
const px = (value: number) => Math.round(value * TWIPS_PER_PX);

/** The editor's printable column: 794 px sheet less two 56 px margins. */
const CONTENT_PX = 682;
const CONTENT = px(CONTENT_PX);

const FONT = "Times New Roman";
/** docx sizes are half-points. */
const pt = (points: number) => Math.round(points * 2);

const BLACK = "000000";
const RULE = { style: BorderStyle.SINGLE, size: 6, color: BLACK };
const NONE = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const ALL_RULED = { top: RULE, bottom: RULE, left: RULE, right: RULE };
const NO_BORDERS = {
  top: NONE,
  bottom: NONE,
  left: NONE,
  right: NONE,
  insideHorizontal: NONE,
  insideVertical: NONE,
};

/** Question row columns, as `.question-row`: 56 px | 1fr | 72 px. */
const NUMBER_COL = px(56);
const MARKS_COL = px(72);
const BODY_COL = CONTENT - NUMBER_COL - MARKS_COL;
const CELL_MARGINS = { top: px(6), bottom: px(6), left: px(8), right: px(8) };

const ALIGN: Record<string, (typeof AlignmentType)[keyof typeof AlignmentType]> = {
  left: AlignmentType.LEFT,
  center: AlignmentType.CENTER,
  right: AlignmentType.RIGHT,
  justify: AlignmentType.JUSTIFIED,
};

/** Run styling a block imposes on all its text. */
interface RunStyle {
  bold?: boolean;
  italics?: boolean;
  allCaps?: boolean;
  size?: number;
  color?: string;
}

// ── Inline content ─────────────────────────────────────────────────────

function textOf(node: Json | undefined): string {
  if (!node) return "";
  if (node.type === "text") return node.text ?? "";
  if (node.type === "inlineMath") return node.attrs?.latex ?? "";
  return (node.content ?? []).map(textOf).join("");
}

function runs(nodes: Json[] | undefined, style: RunStyle = {}): ParagraphChild[] {
  const out: ParagraphChild[] = [];
  for (const node of nodes ?? []) {
    if (node.type === "text") {
      const marks = new Map((node.marks ?? []).map((mark) => [mark.type, mark.attrs ?? {}]));
      const textStyle = marks.get("textStyle") ?? {};
      const fontSize = parseFloat(String(textStyle.fontSize ?? ""));
      const color = String(textStyle.color ?? "").replace(/^#/, "");
      out.push(
        new TextRun({
          text: node.text ?? "",
          font: marks.has("code") ? "Courier New" : undefined,
          bold: style.bold || marks.has("bold") || undefined,
          italics: style.italics || marks.has("italic") || undefined,
          underline: marks.has("underline") ? {} : undefined,
          strike: marks.has("strike") || undefined,
          superScript: marks.has("superscript") || undefined,
          subScript: marks.has("subscript") || undefined,
          allCaps: style.allCaps,
          size: Number.isFinite(fontSize) && fontSize > 0 ? pt(fontSize * 0.75) : style.size,
          color: /^[0-9a-f]{6}$/i.test(color) ? color : style.color,
          highlight: marks.has("highlight") ? "yellow" : undefined,
        }),
      );
    } else if (node.type === "inlineMath") {
      out.push(new DocxMath({ children: latexToMath(node.attrs?.latex ?? "") }));
    } else if (node.type === "hardBreak") {
      out.push(new TextRun({ text: "", break: 1 }));
    } else if (node.content) {
      out.push(...runs(node.content, style));
    }
  }
  return out;
}

function paragraph(
  node: Json,
  options: { style?: RunStyle; indent?: number; after?: number; align?: string } = {},
): Paragraph {
  const align = options.align ?? node.attrs?.textAlign;
  return new Paragraph({
    children: runs(node.content, options.style),
    alignment: align ? ALIGN[align] : undefined,
    indent: options.indent ? { left: options.indent } : undefined,
    spacing: { after: options.after ?? 60 },
  });
}

/** A few points of air between two tables, which Word would otherwise merge. */
const spacer = (points = 4) =>
  new Paragraph({
    spacing: { before: 0, after: 0, line: points * 20, lineRule: LineRuleType.EXACT },
    children: [],
  });

// ── Images ─────────────────────────────────────────────────────────────

function imageRun(image: LoadedImage, width: number, height: number) {
  return new ImageRun({
    type: image.type,
    data: image.data,
    transformation: { width: Math.round(width), height: Math.round(height) },
  });
}

async function figure(node: Json, ctx: Context, maxWidth = CONTENT_PX): Promise<Block[]> {
  const image = node.attrs?.src ? await ctx.loadImage(node.attrs.src) : null;
  if (!image || image.width <= 0 || image.height <= 0) return [];
  const width = Math.min(Number(node.attrs?.width) || 300, maxWidth);
  const height = width * (image.height / image.width);
  return [
    new Paragraph({
      alignment: ALIGN[node.attrs?.align ?? "center"] ?? AlignmentType.CENTER,
      spacing: { after: 80 },
      children: [imageRun(image, width, height)],
    }),
  ];
}

// ── Tables ─────────────────────────────────────────────────────────────

function table(
  node: Json,
  width: number,
  options: { headerFill?: string; center?: boolean; cellStyle?: (header: boolean) => RunStyle } = {},
): Table | null {
  const rows = (node.content ?? []).filter((row) => (row.content ?? []).length > 0);
  if (rows.length === 0) return null;
  const columns = Math.max(...rows.map((row) => row.content!.length));
  const column = Math.floor(width / columns);

  return new Table({
    layout: TableLayoutType.FIXED,
    width: { size: column * columns, type: WidthType.DXA },
    columnWidths: Array(columns).fill(column),
    rows: rows.map(
      (row) =>
        new TableRow({
          children: row.content!.map((cell) => {
            const header = cell.type === "tableHeader";
            const span = Number(cell.attrs?.colspan) || 1;
            const blocks = (cell.content ?? []).map((child) =>
              paragraph(child, {
                after: 0,
                align: options.center ? "center" : undefined,
                style: options.cellStyle?.(header) ?? (header ? { bold: true } : {}),
              }),
            );
            return new TableCell({
              columnSpan: span > 1 ? span : undefined,
              width: { size: column * span, type: WidthType.DXA },
              borders: ALL_RULED,
              margins: { top: px(3), bottom: px(3), left: px(6), right: px(6) },
              verticalAlign: VerticalAlign.CENTER,
              shading:
                header && options.headerFill
                  ? { type: ShadingType.CLEAR, color: "auto", fill: options.headerFill }
                  : undefined,
              children: blocks.length > 0 ? blocks : [new Paragraph({ children: [] })],
            });
          }),
        }),
    ),
  });
}

// ── The masthead ───────────────────────────────────────────────────────

/** The header's own heading sizes, as `.paper-header-content` sets them. */
const MASTHEAD: Record<string, RunStyle> = {
  h1: { bold: true, allCaps: true, size: pt(17) },
  h2: { bold: true, allCaps: true, size: pt(12.5) },
  h3: { bold: true, allCaps: true, size: pt(11.5) },
  p: { size: pt(10.5) },
};

async function masthead(node: Json, ctx: Context): Promise<Block[]> {
  const attrs = node.attrs ?? {};
  const children = node.content ?? [];
  // The title lines sit beside the logo; the details grid and anything after
  // it run full width beneath.
  const split = children.findIndex((child) => child.type === "table");
  const titles = split === -1 ? children : children.slice(0, split);
  const rest = split === -1 ? [] : children.slice(split);

  const titleParagraphs = titles.map((child) => {
    const key = child.type === "heading" ? `h${child.attrs?.level ?? 1}` : "p";
    return paragraph(child, { style: MASTHEAD[key] ?? MASTHEAD.p, align: "center", after: 20 });
  });

  const out: Block[] = [];
  const logo = attrs.logoUrl ? await ctx.loadImage(attrs.logoUrl) : null;
  if (logo && logo.width > 0 && logo.height > 0) {
    const ratio = logo.width / logo.height;
    const side = resolveLogoSide(attrs.logoAlign, ratio);
    const box = fitLogo(ratio, Number(attrs.logoHeight) || DEFAULT_LOGO_HEIGHT, side);
    const picture = (align: "left" | "center" | "right") =>
      new Paragraph({ alignment: ALIGN[align], children: [imageRun(logo, box.width, box.height)] });

    if (side === "top") {
      out.push(picture("center"), ...titleParagraphs);
    } else {
      // Logo | title | an empty twin of the logo's column — the same trick
      // as the editor, so the title centres on the page, not beside the logo.
      const side_col = px(box.width + 14);
      const middle = CONTENT - 2 * side_col;
      const logoCell = (align: "left" | "right") =>
        new TableCell({
          width: { size: side_col, type: WidthType.DXA },
          borders: NO_BORDERS,
          children: [picture(align)],
        });
      const emptyCell = () =>
        new TableCell({
          width: { size: side_col, type: WidthType.DXA },
          borders: NO_BORDERS,
          children: [new Paragraph({ children: [] })],
        });
      out.push(
        new Table({
          layout: TableLayoutType.FIXED,
          width: { size: CONTENT, type: WidthType.DXA },
          columnWidths: [side_col, middle, side_col],
          borders: NO_BORDERS,
          rows: [
            new TableRow({
              children: [
                side === "left" ? logoCell("left") : emptyCell(),
                new TableCell({
                  width: { size: middle, type: WidthType.DXA },
                  borders: NO_BORDERS,
                  verticalAlign: VerticalAlign.CENTER,
                  children: titleParagraphs.length > 0 ? titleParagraphs : [new Paragraph({ children: [] })],
                }),
                side === "right" ? logoCell("right") : emptyCell(),
              ],
            }),
          ],
        }),
      );
    }
  } else {
    out.push(...titleParagraphs);
  }

  for (const child of rest) {
    if (child.type === "table") {
      const grid = table(child, CONTENT, {
        headerFill: "F1F1F1",
        center: true,
        cellStyle: (header) =>
          header ? { bold: true, allCaps: true, size: pt(9) } : { size: pt(11) },
      });
      if (grid) out.push(spacer(6), grid);
    } else {
      out.push(...(await blocks([child], ctx)));
    }
  }

  const date = attrs.showDate ? formatPaperDate(attrs.dateValue) : "";
  if (date) {
    out.push(
      new Paragraph({
        alignment: AlignmentType.RIGHT,
        spacing: { before: 60 },
        children: [
          new TextRun({ text: "Date: ", bold: true, size: pt(10.5) }),
          new TextRun({ text: date, size: pt(10.5) }),
        ],
      }),
    );
  }
  out.push(spacer(8));
  return out;
}

// ── Instructions, sections, questions ──────────────────────────────────

/** The grey "General Instructions" box. */
async function instructions(node: Json, ctx: Context): Promise<Block[]> {
  const items: string[] = Array.isArray(node.attrs?.summaryItems) ? node.attrs!.summaryItems : [];
  const inner: Block[] = [
    new Paragraph({
      spacing: { after: 60 },
      children: [new TextRun({ text: "General Instructions", bold: true, size: pt(10) })],
    }),
    ...items.map(
      (item) =>
        new Paragraph({ indent: { left: px(18) }, spacing: { after: 40 }, children: [new TextRun(String(item))] }),
    ),
  ];
  for (const child of node.content ?? []) {
    if (child.type === "orderedList" || child.type === "bulletList") {
      for (const item of child.content ?? []) {
        for (const part of item.content ?? []) inner.push(paragraph(part, { indent: px(18), after: 40 }));
      }
    } else if (!(child.type === "paragraph" && !textOf(child).trim())) {
      inner.push(...(await blocks([child], ctx)));
    }
  }
  const BOX = { style: BorderStyle.SINGLE, size: 6, color: "D1D5DB" };
  return [
    new Table({
      layout: TableLayoutType.FIXED,
      width: { size: CONTENT, type: WidthType.DXA },
      columnWidths: [CONTENT],
      rows: [
        new TableRow({
          children: [
            new TableCell({
              width: { size: CONTENT, type: WidthType.DXA },
              borders: { top: BOX, bottom: BOX, left: BOX, right: BOX },
              shading: { type: ShadingType.CLEAR, color: "auto", fill: "F3F4F6" },
              margins: { top: px(8), bottom: px(8), left: px(10), right: px(10) },
              children: inner,
            }),
          ],
        }),
      ],
    }),
    spacer(8),
  ];
}

/** "SECTION A" on a dark bar, then its summary in italics. */
function section(node: Json): Block[] {
  const title = textOf(node).trim();
  const summary = node.attrs?.summaryOverride ?? node.attrs?.summaryText ?? "";
  const children: ParagraphChild[] = [
    new TextRun({
      // Non-breaking spaces pad the bar, as the label's CSS padding does.
      text: `  ${title}  `,
      bold: true,
      allCaps: true,
      size: pt(11),
      color: "FFFFFF",
      shading: { type: ShadingType.CLEAR, color: "auto", fill: "4B5563" },
    }),
  ];
  if (summary) {
    children.push(new TextRun({ text: `   (${summary})`, italics: true, size: pt(10), color: "4B5563" }));
  }
  return [new Paragraph({ spacing: { before: 160, after: 80 }, children })];
}

const OPTION_LABELS = (index: number) => `(${String.fromCharCode(65 + index)})`;

const SUB_LABELS: Record<string, (index: number) => string> = {
  alpha: (index) => `(${String.fromCharCode(97 + index)})`,
  numeric: (index) => `${index + 1}.`,
  roman: (index) => `(${toRoman(index + 1)})`,
};

function toRoman(value: number): string {
  const numerals: [number, string][] = [
    [10, "x"], [9, "ix"], [5, "v"], [4, "iv"], [1, "i"],
  ];
  let out = "";
  for (const [size, numeral] of numerals) {
    while (value >= size) {
      out += numeral;
      value -= size;
    }
  }
  return out;
}

/** A labelled line: "(A)" in bold, the text hanging beside it. */
function labelled(label: string, item: Json, labelWidth: number): Paragraph[] {
  const parts = (item.content ?? []).filter((part) => part.type === "paragraph");
  const first = parts[0];
  return [
    new Paragraph({
      indent: { left: labelWidth, hanging: labelWidth },
      spacing: { after: 30 },
      children: [new TextRun({ text: `${label}\t`, bold: true }), ...runs(first?.content)],
      tabStops: [{ type: TabStopType.LEFT, position: labelWidth }],
    }),
    ...parts.slice(1).map((part) => paragraph(part, { indent: labelWidth, after: 30 })),
  ];
}

/** MCQ options in two columns, as `.question-body ol` lays them out. */
function options(list: Json, width: number): Table {
  const items = list.content ?? [];
  const column = Math.floor(width / 2);
  const rows: TableRow[] = [];
  for (let i = 0; i < items.length; i += 2) {
    rows.push(
      new TableRow({
        children: [0, 1].map((offset) => {
          const item = items[i + offset];
          return new TableCell({
            width: { size: column, type: WidthType.DXA },
            borders: NO_BORDERS,
            children: item ? labelled(OPTION_LABELS(i + offset), item, px(30)) : [new Paragraph({ children: [] })],
          });
        }),
      }),
    );
  }
  return new Table({
    layout: TableLayoutType.FIXED,
    width: { size: column * 2, type: WidthType.DXA },
    columnWidths: [column, column],
    borders: NO_BORDERS,
    rows,
  });
}

async function questionBody(node: Json, ctx: Context): Promise<Block[]> {
  const width = BODY_COL - CELL_MARGINS.left - CELL_MARGINS.right;
  const grouped = node.type === "groupedQuestionBlock";
  const subLabel = SUB_LABELS[node.attrs?.labelStyle] ?? SUB_LABELS.alpha;
  const out: Block[] = [];
  for (const child of node.content ?? []) {
    if (child.type === "orderedList" || child.type === "bulletList") {
      if (grouped) {
        (child.content ?? []).forEach((item, index) => out.push(...labelled(subLabel(index), item, px(28))));
      } else {
        out.push(options(child, width));
      }
    } else if (child.type === "paragraph") {
      out.push(paragraph(child));
    } else if (child.type === "floatImage") {
      out.push(...(await figure(child, ctx, width / TWIPS_PER_PX)));
    } else if (child.type === "table") {
      const grid = table(child, width);
      if (grid) out.push(grid);
    } else {
      out.push(...(await blocks([child], ctx)));
    }
  }
  // A cell must end in a paragraph; left to Word, the one after a closing
  // options table is a full blank line.
  if (out[out.length - 1] instanceof Table) out.push(spacer(2));
  return out;
}

/** One question: number | body | marks, ruled, as `.question-row`. */
async function question(node: Json, ctx: Context): Promise<Block[]> {
  const attrs = node.attrs ?? {};
  const number = attrs.subLabel || (attrs.number ? `${attrs.number}.` : "");
  const marks = attrs.marks ?? "";
  const body = await questionBody(node, ctx);
  return [
    new Table({
      layout: TableLayoutType.FIXED,
      width: { size: CONTENT, type: WidthType.DXA },
      columnWidths: [NUMBER_COL, BODY_COL, MARKS_COL],
      rows: [
        new TableRow({
          cantSplit: true,
          children: [
            new TableCell({
              width: { size: NUMBER_COL, type: WidthType.DXA },
              borders: ALL_RULED,
              margins: CELL_MARGINS,
              children: [
                new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: number, bold: true })] }),
              ],
            }),
            new TableCell({
              width: { size: BODY_COL, type: WidthType.DXA },
              borders: ALL_RULED,
              margins: CELL_MARGINS,
              children: body.length > 0 ? body : [new Paragraph({ children: [] })],
            }),
            new TableCell({
              width: { size: MARKS_COL, type: WidthType.DXA },
              borders: ALL_RULED,
              margins: CELL_MARGINS,
              verticalAlign: VerticalAlign.CENTER,
              children: [
                new Paragraph({
                  alignment: AlignmentType.CENTER,
                  children: [new TextRun(marks === "" ? "" : `${marks} M`)],
                }),
              ],
            }),
          ],
        }),
      ],
    }),
    spacer(),
  ];
}

/** "Answer any one": the branches with a bold OR between each pair. */
async function orGroup(node: Json, ctx: Context): Promise<Block[]> {
  const branches = (node.content ?? []).filter(
    (child) => child.type === "questionBlock" || child.type === "groupedQuestionBlock",
  );
  const out: Block[] = [];
  for (const [index, branch] of branches.entries()) {
    if (index > 0) {
      out.push(
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { before: 40, after: 80 },
          children: [new TextRun({ text: "OR", bold: true, size: pt(11) })],
        }),
      );
    }
    out.push(...(await question(branch, ctx)));
  }
  return out;
}

// ── Dispatch ───────────────────────────────────────────────────────────

interface Context {
  loadImage: ImageLoader;
}

const HEADINGS = [
  HeadingLevel.HEADING_1,
  HeadingLevel.HEADING_2,
  HeadingLevel.HEADING_3,
  HeadingLevel.HEADING_4,
  HeadingLevel.HEADING_5,
  HeadingLevel.HEADING_6,
];

async function blocks(nodes: Json[] | undefined, ctx: Context): Promise<Block[]> {
  const out: Block[] = [];
  for (const node of nodes ?? []) {
    switch (node.type) {
      case "page":
        out.push(...(await blocks(node.content, ctx)));
        break;
      case "paperHeaderBlock":
        out.push(...(await masthead(node, ctx)));
        break;
      case "instructionBlock":
        out.push(...(await instructions(node, ctx)));
        break;
      case "sectionBlock":
        out.push(...section(node));
        break;
      case "questionBlock":
      case "groupedQuestionBlock":
        out.push(...(await question(node, ctx)));
        break;
      case "questionGroupBlock":
        out.push(...(await orGroup(node, ctx)));
        break;
      case "paragraph":
        out.push(paragraph(node, { after: 80 }));
        break;
      case "heading": {
        const level = Math.min(Math.max(Number(node.attrs?.level) || 1, 1), 6);
        out.push(
          new Paragraph({
            heading: HEADINGS[level - 1],
            alignment: node.attrs?.textAlign ? ALIGN[node.attrs.textAlign] : undefined,
            children: runs(node.content),
          }),
        );
        break;
      }
      case "orderedList":
      case "bulletList":
        // The sheet prints lists without markers (the app's CSS reset), indented.
        for (const item of node.content ?? []) {
          for (const part of item.content ?? []) out.push(paragraph(part, { indent: px(18), after: 40 }));
        }
        break;
      case "table": {
        const grid = table(node, CONTENT);
        if (grid) out.push(grid, spacer());
        break;
      }
      case "floatImage":
        out.push(...(await figure(node, ctx)));
        break;
      case "mathBlock":
        out.push(
          new Paragraph({
            alignment: AlignmentType.CENTER,
            spacing: { before: 60, after: 60 },
            children: [new DocxMath({ children: latexToMath(node.attrs?.latex ?? "") })],
          }),
        );
        break;
      case "horizontalRule":
        out.push(new Paragraph({ border: { bottom: RULE }, children: [] }));
        break;
      default:
        if (node.content) out.push(...(await blocks(node.content, ctx)));
    }
  }
  return out;
}

/** The whole paper as a Word document. */
export async function buildPaperDocx(doc: Json, loadImage: ImageLoader): Promise<Document> {
  const children = await blocks(doc.content, { loadImage });
  const heading = (size: number) => ({
    run: { font: FONT, size: pt(size), bold: true, color: BLACK },
    paragraph: { spacing: { before: 120, after: 60 } },
  });
  return new Document({
    styles: {
      default: {
        document: {
          run: { font: FONT, size: pt(12), color: BLACK },
          paragraph: { spacing: { line: 300 } },
        },
        // Word's own headings are blue Calibri; the sheet's are black Times.
        heading1: heading(16),
        heading2: heading(13),
        heading3: heading(12),
        heading4: heading(12),
        heading5: heading(12),
        heading6: heading(12),
      },
    },
    sections: [
      {
        properties: {
          page: {
            size: { width: px(794), height: px(1123) },
            margin: { top: px(48), bottom: px(56), left: px(56), right: px(56) },
          },
        },
        children: children.length > 0 ? children : [new Paragraph({ children: [] })],
      },
    ],
  });
}
