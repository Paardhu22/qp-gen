import {
  Document,
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

type DocxSource = string | HTMLElement;

export async function exportToDocx(
  source: DocxSource,
  filename: string = "exam-paper.docx",
) {
  // A very basic HTML to DOCX converter logic
  // In a full implementation, we'd use a parser to convert HTML tags to docx elements
  // For the purpose of this engine, we'll extract the text and structure

  const parser = new CustomHtmlToDocxParser(source);
  const children = parser.parse();

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

class CustomHtmlToDocxParser {
  constructor(private source: DocxSource) {}

  parse(): (Paragraph | Table)[] {
    const docxElements: (Paragraph | Table)[] = [];
    
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

    const walk = (node: ChildNode) => {
      if (node.nodeType !== Node.ELEMENT_NODE) return;
      const el = node as HTMLElement;
      if (shouldSkip(el)) return;

      const dataType = el.getAttribute("data-type");
      const hasClass = (name: string) => el.classList.contains(name);

      if (dataType === "page") {
        const content = el.querySelector(".doc-page-content");
        const scope = content || el;
        Array.from(scope.childNodes).forEach(walk);
        return;
      }

      if (dataType === "page-break") return;

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
            return;
          }
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
          const label = el.getAttribute("data-label") || "OR";
          docxElements.push(
            new Paragraph({
              children: [new TextRun({ text: `${label}`, bold: true })],
              alignment: AlignmentType.CENTER,
            }),
          );
          el.querySelectorAll("div[data-type='question-block'], .question-block").forEach((q) => {
            docxElements.push(buildQuestionBlock(q as HTMLElement));
          });
          return;
        }

        Array.from(el.childNodes).forEach(walk);
        return;
      }

      Array.from(el.childNodes).forEach(walk);
    };

    Array.from(container.childNodes).forEach(walk);

    return docxElements;
  }
}
