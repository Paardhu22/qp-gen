import { Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell, WidthType, AlignmentType } from "docx";
import { saveAs } from "file-saver";

export async function exportToDocx(htmlContent: string, filename: string = "exam-paper.docx") {
  // A very basic HTML to DOCX converter logic
  // In a full implementation, we'd use a parser to convert HTML tags to docx elements
  // For the purpose of this engine, we'll extract the text and structure
  
  const parser = new CustomHtmlToDocxParser(htmlContent);
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
  constructor(private html: string) {}

  parse(): (Paragraph | Table)[] {
    const docxElements: (Paragraph | Table)[] = [];
    
    // Create a temporary DOM element to parse HTML
    if (typeof document === "undefined") return [];
    const container = document.createElement("div");
    container.innerHTML = this.html;

    container.childNodes.forEach((node) => {
      if (node.nodeType === Node.ELEMENT_NODE) {
        const el = node as HTMLElement;
        
        if (el.tagName === "H1") {
          docxElements.push(new Paragraph({ text: el.innerText, heading: HeadingLevel.HEADING_1, alignment: AlignmentType.CENTER }));
        } else if (el.tagName === "H2") {
          docxElements.push(new Paragraph({ text: el.innerText, heading: HeadingLevel.HEADING_2, alignment: AlignmentType.CENTER }));
        } else if (el.tagName === "H3") {
          docxElements.push(new Paragraph({ text: el.innerText, heading: HeadingLevel.HEADING_3, alignment: AlignmentType.CENTER }));
        } else if (el.tagName === "P") {
          docxElements.push(new Paragraph({ 
            children: [new TextRun({ text: el.innerText, bold: el.querySelector("strong") !== null })] 
          }));
        } else if (el.tagName === "HR") {
          docxElements.push(new Paragraph({ text: "__________________________________________________________________________", alignment: AlignmentType.CENTER }));
        } else if (el.tagName === "TABLE") {
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
        } else if (el.tagName === "DIV") {
          const dataType = el.getAttribute("data-type");
          if (dataType === "section-block") {
            docxElements.push(new Paragraph({ text: el.innerText, heading: HeadingLevel.HEADING_3 }));
          } else if (dataType === "instruction-block") {
            docxElements.push(new Paragraph({ children: [new TextRun({ text: "Instructions:", bold: true })] }));
            el.querySelectorAll("p").forEach(p => {
              docxElements.push(new Paragraph({ text: (p as HTMLElement).innerText }));
            });
          } else if (dataType === "question-block") {
            const num = el.getAttribute("data-number") || "";
            const marks = el.getAttribute("data-marks");
            const marksText = marks ? ` [${marks}M]` : "";
            docxElements.push(new Paragraph({
              children: [
                new TextRun({ text: `${num ? num + ". " : ""}`, bold: true }),
                new TextRun({ text: el.innerText.replace(num, "").trim() }),
                new TextRun({ text: marksText, bold: true })
              ]
            }));
          } else if (dataType === "math-block") {
            const latex = el.getAttribute("data-latex") || el.innerText;
            docxElements.push(new Paragraph({ text: `$$ ${latex} $$`, alignment: AlignmentType.CENTER }));
          } else if (dataType === "question-group") {
             const label = el.getAttribute("data-label") || "OR";
             docxElements.push(new Paragraph({ children: [new TextRun({ text: `--- ${label} ---`, bold: true })], alignment: AlignmentType.CENTER }));
             el.querySelectorAll("div[data-type='question-block']").forEach(q => {
                const marks = q.getAttribute("data-marks");
                docxElements.push(new Paragraph({ text: (q as HTMLElement).innerText + (marks ? ` [${marks}M]` : "") }));
             });
          } else {
             // Fallback for normal divs
             docxElements.push(new Paragraph({ text: el.innerText }));
          }
        }
      }
    });

    return docxElements;
  }
}
