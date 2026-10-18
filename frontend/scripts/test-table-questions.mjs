#!/usr/bin/env node
// Table-based questions, editor to Word — run from frontend/:
//   node scripts/test-table-questions.mjs
//
// A Statistics question that gives class intervals and frequencies must reach
// the paper as a real table (column headings, aligned figures, equations typeset
// in cells), not as a run of plain text, and the Word export must print that
// table. The backend writes tables as pipe rows (`services/generation/rules/
// tables.py`); `question-nodes.ts` turns them into table nodes. This holds the
// seam between the two, and the export behind it.

import { fileURLToPath } from "node:url";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { createJiti } from "jiti";
import JSZip from "jszip";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const stubDir = mkdtempSync(path.join(tmpdir(), "tables-"));
const cssStub = path.join(stubDir, "empty.mjs");
writeFileSync(cssStub, "export {};\n");

const jiti = createJiti(here, {
  interopDefault: true,
  jsx: true,
  extensions: [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"],
  alias: { "@": root, "katex/dist/katex.min.css": cssStub },
});

const { buildQuestionContentNodes, splitTableCells } = await jiti.import(
  path.join(root, "features/editor/question-nodes.ts"),
);
const { buildPaperDocx } = await jiti.import(path.join(root, "features/export/docx-paper.ts"));
const { Packer } = await import("docx");
const { getSchema } = await jiti.import("@tiptap/core");
const StarterKit = await jiti.import("@tiptap/starter-kit");
const { Table } = await jiti.import("@tiptap/extension-table");
const { TableRow } = await jiti.import("@tiptap/extension-table-row");
const { TableCell } = await jiti.import("@tiptap/extension-table-cell");
const { TableHeader } = await jiti.import("@tiptap/extension-table-header");
const nodes = await jiti.import(path.join(root, "features/editor/extensions/nodes.tsx"));
const math = await jiti.import(path.join(root, "features/editor/extensions/math-nodes.tsx"));
const { PaginatedDocument } = await jiti.import(path.join(root, "features/editor/extensions/document-node.ts"));
const { PageNode } = await jiti.import(path.join(root, "features/editor/extensions/page-node.tsx"));
const { FloatImage } = await jiti.import(path.join(root, "features/editor/extensions/float-image.tsx"));
const { PaperHeaderBlock } = await jiti.import(path.join(root, "features/editor/extensions/header-node.tsx"));

let failures = 0;
function check(label, condition, detail = "") {
  if (condition) console.log(`PASS  ${label}`);
  else {
    failures += 1;
    console.error(`FAIL  ${label}${detail ? ` — ${detail}` : ""}`);
  }
}

const types = (list) => list.map((n) => n.type);
const rowsOf = (table) => table.content;
const cellsOf = (row) => row.content;
const paragraphOf = (cell) => cell.content[0];
const textOf = (node) =>
  node.type === "text" ? node.text : node.type === "inlineMath" ? `\\(${node.attrs.latex}\\)` : (node.content ?? []).map(textOf).join("");

// ── The statistics question the user asked for ─────────────────────────

const STATS =
  "Find the mean of the following distribution.\n" +
  "| Class interval | Frequency |\n| --- | --- |\n| 0–10 | 5 |\n| 10–20 | 8 |\n| 20–30 | 12 |\n| 30–40 | 5 |";

{
  const blocks = buildQuestionContentNodes(STATS);
  check("the instruction is a paragraph and the data is a table", types(blocks).join() === "paragraph,table", types(blocks).join());
  const table = blocks[1];
  check("one row per line: a header and four classes", rowsOf(table).length === 5);
  check("two columns", cellsOf(rowsOf(table)[0]).length === 2);
  check("the first row is the heading row", types(cellsOf(rowsOf(table)[0])).every((t) => t === "tableHeader"));
  check("the rest are data cells", rowsOf(table).slice(1).every((r) => types(cellsOf(r)).every((t) => t === "tableCell")));
  check("the headings read Class interval / Frequency", textOf(cellsOf(rowsOf(table)[0])[0]) === "Class interval" && textOf(cellsOf(rowsOf(table)[0])[1]) === "Frequency");
  check("no pipe or separator row leaks into a cell", !JSON.stringify(table).includes("---") && !JSON.stringify(table).includes("|"));
  check("headings are centred", paragraphOf(cellsOf(rowsOf(table)[0])[0]).attrs?.textAlign === "center");
  check("class intervals and frequencies are centred", rowsOf(table).slice(1).every((r) => cellsOf(r).every((c) => paragraphOf(c).attrs?.textAlign === "center")));
}

// ── Cells: maths, bars, gaps ───────────────────────────────────────────

{
  const t = buildQuestionContentNodes("| x | f(x) |\n| --- | --- |\n| 1 | \\( \\frac{1}{2} \\) |")[0];
  const cell = paragraphOf(cellsOf(rowsOf(t)[1])[1]);
  check("an equation in a cell is an equation node", cell.content.length === 1 && cell.content[0].type === "inlineMath" && cell.content[0].attrs.latex === "\\frac{1}{2}");
  check("a cell that is one equation is centred like the figures around it", cell.attrs?.textAlign === "center");
  const wordy = buildQuestionContentNodes("| Step | Working |\n| --- | --- |\n| Put the values into \\( x^2 \\) and simplify | done |")[0];
  check("words with an equation in them are left aligned", paragraphOf(cellsOf(rowsOf(wordy)[1])[0]).attrs === undefined);
}
{
  const t = buildQuestionContentNodes("| x | abs |\n| --- | --- |\n| -3 | \\( |-3| \\) |")[0];
  check("a bar inside an equation does not split the cell", cellsOf(rowsOf(t)[1]).length === 2, `${cellsOf(rowsOf(t)[1]).length} cells`);
  check("…and the equation keeps its bars", paragraphOf(cellsOf(rowsOf(t)[1])[1]).content[0].attrs.latex === "|-3|");
}
{
  const t = buildQuestionContentNodes("| Set | n |\n| --- | --- |\n| A \\| B | 3 |")[0];
  check("an escaped bar prints as a bar", textOf(cellsOf(rowsOf(t)[1])[0]) === "A | B");
}
{
  const t = buildQuestionContentNodes("| a | b | c |\n| --- | --- | --- |\n| 1 | 2 |")[0];
  check("a short row is padded to the table's width", cellsOf(rowsOf(t)[1]).length === 3);
  check("…with an empty cell", paragraphOf(cellsOf(rowsOf(t)[1])[2]).content === undefined);
}
{
  const t = buildQuestionContentNodes("| Class interval | 0–10 | 10–20 |\n| Frequency | 5 | 8 |")[0];
  check("a row-wise table without a separator has no heading row", types(cellsOf(rowsOf(t)[0])).every((x) => x === "tableCell"));
}
{
  const blocks = buildQuestionContentNodes("Use a | b to mean either.");
  check("prose with a bar is still a paragraph", types(blocks).join() === "paragraph");
  const lone = buildQuestionContentNodes("| only | one |");
  check("a single barred line is not a table", types(lone).join() === "paragraph");
}
check(
  "splitTableCells follows the backend's rules",
  JSON.stringify(splitTableCells("| \\( |x| \\) | a \\| b | 3 |")) === JSON.stringify(["\\( |x| \\)", "a \\| b", "3"]),
);
check("an unclosed equation cannot swallow the row", splitTableCells("| \\( x | 3 | 4 |").length === 3);

// ── The editor's schema accepts it ─────────────────────────────────────

const schema = getSchema([
  PaginatedDocument, PageNode,
  StarterKit.configure({ document: false, heading: { levels: [1, 2, 3, 4, 5, 6] } }),
  Table, TableRow, TableHeader, TableCell,
  nodes.QuestionBlock, nodes.SectionBlock, nodes.InstructionBlock, nodes.QuestionGroupBlock, nodes.GroupedQuestionBlock,
  PaperHeaderBlock, math.MathBlock, math.InlineMath, FloatImage,
]);

const paperWith = (...content) => ({
  type: "doc",
  content: [{ type: "page", attrs: { pageId: "p1" }, content: [{ type: "questionBlock", attrs: { number: 1, marks: 3, questionType: "SHORT_ANSWER" }, content }] }],
});
const questionDoc = paperWith(...buildQuestionContentNodes(STATS));

{
  let ok = true;
  let detail = "";
  try {
    schema.nodeFromJSON(questionDoc).check();
  } catch (error) {
    ok = false;
    detail = String(error.message ?? error);
  }
  check("a question holding a table is a valid document", ok, detail);
}
{
  // What the backend writes into an answer script (`typesetting._table_node`).
  const cell = (kind, text, centred) => ({
    type: kind,
    content: [{ type: "paragraph", ...(centred ? { attrs: { textAlign: "center" } } : {}), content: [{ type: "text", text }] }],
  });
  const answerTable = {
    type: "table",
    content: [
      { type: "tableRow", content: [cell("tableHeader", "Class interval", true), cell("tableHeader", "Cumulative frequency", true)] },
      { type: "tableRow", content: [cell("tableCell", "0–10", true), cell("tableCell", "5", true)] },
    ],
  };
  let ok = true;
  try {
    schema.nodeFromJSON(paperWith({ type: "paragraph", content: [{ type: "text", text: "1. Working:" }] }, answerTable)).check();
  } catch {
    ok = false;
  }
  check("a table written by the answer script is a valid document too", ok);
}

// ── Word export ─────────────────────────────────────────────────────────

async function docxXml(doc) {
  const built = await buildPaperDocx(doc, async () => null);
  const zip = await JSZip.loadAsync(await Packer.toBuffer(built));
  return zip.file("word/document.xml").async("string");
}

{
  const doc = paperWith(
    ...buildQuestionContentNodes(
      "Find the mean.\n| Class interval | Frequency | Midpoint |\n| --- | --- | --- |\n| 0–10 | 5 | \\( \\frac{0+10}{2} \\) |\n| 10–20 | 8 | \\( \\frac{10+20}{2} \\) |",
    ),
  );
  const xml = await docxXml(doc);
  // A question is laid out in a table of its own (number | text | marks), so the
  // data table is the innermost one, around the headings.
  const heading = xml.indexOf("Class interval");
  const start = xml.lastIndexOf("<w:tbl>", heading);
  const data = heading >= 0 && start >= 0 ? xml.slice(start, xml.indexOf("</w:tbl>", start) + 8) : undefined;
  check("the data is printed as a Word table", !!data && (data.match(/<w:tbl>/g) ?? []).length === 1);
  const rows = data?.match(/<w:tr[ >][\s\S]*?<\/w:tr>/g) ?? [];
  check("with a heading row and two data rows", rows.length === 3, `${rows.length} rows`);
  check("three columns", (data?.match(/<w:gridCol /g) ?? []).length === 3);
  check("the heading row is bold", /<w:b\/>|<w:b /.test(rows[0] ?? ""));
  check("figures are centred", /<w:jc w:val="center"\/>/.test(rows[1] ?? ""));
  check("equations in cells are Word equations", (data?.match(/<m:oMath>/g) ?? []).length === 2);
  check("a fraction in a cell is a Word fraction", (data?.match(/<m:f>/g) ?? []).length === 2);
  const words = [...(data ?? "").matchAll(/<w:t(?: [^>]*)?>([^<]*)<\/w:t>/g)].map((m) => m[1]).join(" ");
  check("no pipe, separator or LaTeX source in the printed table", !/[|]|---|\\\(|\\frac/.test(words), words);
}

if (failures) {
  console.error(`\n${failures} check(s) failed`);
  process.exit(1);
}
console.log("\nAll table-question checks passed");
