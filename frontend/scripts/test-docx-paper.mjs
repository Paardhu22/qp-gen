#!/usr/bin/env node
// The Word export, end to end in Node — run from frontend/:
//   node scripts/test-docx-paper.mjs
//
// `lib/docx-paper.ts` builds the .docx from the editor's document. The old
// exporter scraped the live DOM instead and silently printed questions with
// no numbers or marks, options run into the stem, and no OR questions at all.
// These checks hold the pieces a teacher would notice missing.

import { fileURLToPath } from "node:url";
import path from "node:path";
import { createJiti } from "jiti";
import JSZip from "jszip";

const here = path.dirname(fileURLToPath(import.meta.url));
const jiti = createJiti(here, {
  interopDefault: true,
  jsx: true,
  extensions: [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"],
  alias: { "@": path.resolve(here, "..") },
});

const { buildPaperDocx } = await jiti.import(path.resolve(here, "../lib/docx-paper.ts"));
const { Packer } = await import("docx");

let failures = 0;
function check(label, condition, detail = "") {
  if (condition) console.log(`PASS  ${label}`);
  else {
    failures += 1;
    console.error(`FAIL  ${label}${detail ? ` — ${detail}` : ""}`);
  }
}

// A 1×1 PNG, reported at a logo's shape: 4:1 is a wordmark, 1:1 a crest.
const PNG = Uint8Array.from(
  Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
    "base64",
  ),
);
const loader = (shape) => async () => ({ data: PNG, type: "png", ...shape });

const text = (t) => ({ type: "text", text: t });
const para = (...content) => ({ type: "paragraph", content });
const question = (number, stem, options, marks = 1) => ({
  type: "questionBlock",
  attrs: { number, marks },
  content: [
    para(text(stem)),
    ...(options
      ? [{ type: "orderedList", content: options.map((o) => ({ type: "listItem", content: [para(text(o))] })) }]
      : []),
  ],
});

const PAPER = {
  type: "doc",
  content: [
    {
      type: "page",
      content: [
        {
          type: "paperHeaderBlock",
          attrs: { logoUrl: "/media/logo.png", logoAlign: "auto", showDate: true, dateValue: "2026-10-04" },
          content: [
            { type: "heading", attrs: { level: 1 }, content: [text("Greenwood School")] },
            { type: "heading", attrs: { level: 2 }, content: [text("Unit Test")] },
            {
              type: "table",
              content: [
                { type: "tableRow", content: ["Subject", "Marks"].map((t) => ({ type: "tableHeader", content: [para(text(t))] })) },
                { type: "tableRow", content: ["ICT", "20"].map((t) => ({ type: "tableCell", content: [para(text(t))] })) },
              ],
            },
          ],
        },
        {
          type: "instructionBlock",
          attrs: { summaryItems: ["This question paper has 1 section."] },
          content: [para(text("All questions are compulsory."))],
        },
        { type: "sectionBlock", attrs: { summaryText: "2 x 1 = 2 Marks", summaryOverride: "Answer any 1" }, content: [text("SECTION A")] },
        question(1, "Which key undoes?", ["Ctrl + Y", "Ctrl + Z", "Ctrl + X", "Ctrl + U"]),
        {
          type: "paragraph",
          content: [text("Simplify "), { type: "inlineMath", attrs: { latex: "\\frac{1}{2} + \\sqrt{x^2} + 2^3" } }],
        },
        {
          type: "questionGroupBlock",
          content: [
            { ...question(2, "Define RAM.", null, 2), attrs: { subLabel: "2(A)", marks: 2 } },
            { ...question(2, "Define ROM.", null, 2), attrs: { subLabel: "2(B)", marks: 2 } },
          ],
        },
      ],
    },
  ],
};

async function documentXml(doc, shape) {
  const built = await buildPaperDocx(doc, loader(shape));
  const zip = await JSZip.loadAsync(await Packer.toBuffer(built));
  return zip.file("word/document.xml").async("string");
}

const plain = (xml) => xml.replace(/<w:tab\/>/g, "\t").replace(/<[^>]+>/g, "");

// ── A crest: logo beside the title ─────────────────────────────────────────
{
  const xml = await documentXml(PAPER, { width: 200, height: 200 });
  const body = plain(xml);

  check("A4 page", /<w:pgSz w:w="11910" w:h="16845"/.test(xml));
  check("the masthead carries the logo", (xml.match(/<w:drawing>/g) || []).length === 1);
  check("the school name prints", body.includes("Greenwood School"));
  check("the details grid prints", body.includes("Subject") && body.includes("ICT"));
  check("the date prints", /Date: .*2026/.test(body));
  check("the instruction lines print, summary and own", body.includes("This question paper has 1 section.") && body.includes("All questions are compulsory."));
  check("the section bar prints with the teacher's own summary", body.includes("SECTION A") && body.includes("(Answer any 1)"));
  check("question numbers print", body.includes("1.") && body.includes("2(A)") && body.includes("2(B)"));
  check("marks print", body.includes("1 M") && body.includes("2 M"));
  check("options are labelled (A)–(D) apart from the stem", ["(A)\tCtrl + Y", "(B)\tCtrl + Z", "(D)\tCtrl + U"].every((o) => body.includes(o)));
  check("an OR prints between the two branches", /2\(A\)[\s\S]*OR[\s\S]*2\(B\)/.test(body));
  check("math is a Word equation: a fraction", xml.includes("<m:f>"));
  check("math is a Word equation: a root", xml.includes("<m:rad>"));
  check("math is a Word equation: a power", xml.includes("<m:sSup>"));
  const equation = plain((xml.match(/<m:oMath>[\s\S]*?<\/m:oMath>/) || [""])[0]);
  // "+ 2^3" raises only the 2: the "+" before it must survive the split.
  check("math keeps its operators", (equation.match(/\+/g) || []).length === 2, `equation text: ${equation}`);
  check("no LaTeX leaks into the text", !body.includes("\\frac") && !body.includes("\\sqrt"));
}

// ── A wordmark: logo above the title, not beside it ────────────────────────
{
  const xml = await documentXml(PAPER, { width: 400, height: 100 });
  // Beside the title the masthead is a 3-column table; above it, no table
  // precedes the logo's paragraph.
  const beforeLogo = xml.slice(0, xml.indexOf("<w:drawing>"));
  check("a wordmark goes on top, not into a side column", !beforeLogo.includes("<w:tbl>"));
}

// ── A paper with nothing in it still makes a valid file ────────────────────
{
  const xml = await documentXml({ type: "doc", content: [] }, { width: 1, height: 1 });
  check("an empty paper still builds", xml.includes("<w:body>"));
}

console.log(failures === 0 ? "\nAll docx-paper cases passed" : `\n${failures} case(s) FAILED`);
process.exit(failures === 0 ? 0 : 1);
