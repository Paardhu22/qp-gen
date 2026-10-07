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
  check("legacy details print in the compact header", body.includes("Subject") && body.includes("ICT"));
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

// Optional detail values stay saved but must never leak into the Word file.
{
  const copy = structuredClone(PAPER);
  const header = copy.content[0].content[0];
  header.content = header.content.filter(node => node.type !== "table");
  header.attrs.details = [
    { id: "subject", label: "Subject", value: "Science" },
    { id: "set", label: "Set", value: "PRIVATE-SET-VALUE" },
    { id: "time", label: "Time", value: "PRIVATE-TIME-VALUE" },
    { id: "marks", label: "Max marks", value: "" },
  ];
  header.attrs.hiddenFields = ["set", "time"];
  header.attrs.showDate = false;
  const xml = await documentXml(copy, { width: 200, height: 200 });
  const body = plain(xml);
  check("Word prints the visible subject", body.includes("Subject: Science"));
  check("Word omits hidden set and time values", !body.includes("PRIVATE-SET-VALUE") && !body.includes("PRIVATE-TIME-VALUE"));
  check("Word omits empty marks and disabled date", !body.includes("Max marks:") && !body.includes("Date:"));
  check("the compact header has a separator", /<w:pBdr>/.test(xml));
  header.attrs.hiddenFields = [];
  const restored = plain(await documentXml(copy, { width: 200, height: 200 }));
  check("re-enabled details print their retained values", restored.includes("PRIVATE-SET-VALUE") && restored.includes("PRIVATE-TIME-VALUE"));
  header.attrs.showSchoolName = false;
  const hiddenSchool = plain(await documentXml(copy, { width: 200, height: 200 }));
  check("hidden school name is omitted from Word", !hiddenSchool.includes("Greenwood School"));
  check("custom exam title remains visible", hiddenSchool.includes("Unit Test"));
  header.attrs.showSchoolName = true;
  header.content[1].content = [text("Question Paper")];
  const schoolOnly = plain(await documentXml(copy, { width: 200, height: 200 }));
  check("school name can be restored with its saved value", schoolOnly.includes("Greenwood School"));
  check("legacy generic subtitle is omitted from Word", !schoolOnly.includes("Question Paper"));
}

// Saved composite questions have page-level passage/sub-question siblings.
// The Word table must include them even when the editor split them overleaf.
{
  const head = { ...question(36, "Read the monument case.", null, 4), attrs: { number: 36, marks: 4, questionType: "CASE_STUDY" } };
  const doc = { type: "doc", content: [
    { type: "page", content: [head, para(text("An observer moves 20 m closer."))] },
    { type: "page", content: [para(text("(i) Find the distance. [1]")), para(text("(ii) Find the height. [3]")), question(37, "The next question.", null, 2)] },
  ] };
  const xml = await documentXml(doc, { width: 200, height: 200 });
  const tables = xml.match(/<w:tbl>[\s\S]*?<\/w:tbl>/g) || [];
  check("a case study and the next question have separate ruled boxes", tables.length === 2);
  check("the complete case stays inside its question table across saved pages", ["Read the monument case.", "An observer moves 20 m closer.", "(i) Find the distance.", "(ii) Find the height."].every((t) => plain(tables[0] || "").includes(t)));
  check("the next question is not absorbed into the case study", !plain(tables[0] || "").includes("The next question.") && plain(tables[1] || "").includes("The next question."));
  check("a composite table can flow across Word pages", /<w:cantSplit w:val="(?:false|0)"\/>/.test(tables[0] || ""));
  check("ordinary questions still stay together", /<w:cantSplit\/>/.test(tables[1] || ""));
  doc.content = [{ type: "page", content: [{ type: "questionGroupBlock", content: [head, para(text("First branch passage.")), { ...head, attrs: { ...head.attrs, subLabel: "36(B)" } }, para(text("Second branch passage."))] }] }];
  const branches = await documentXml(doc, { width: 200, height: 200 });
  check("OR composite branches retain both passages in their boxes", /First branch passage\.[\s\S]*OR[\s\S]*Second branch passage\./.test(plain(branches)));
}

console.log(failures === 0 ? "\nAll docx-paper cases passed" : `\n${failures} case(s) FAILED`);
process.exit(failures === 0 ? 0 : 1);
