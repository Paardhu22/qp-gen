#!/usr/bin/env node
// An answer script with maths, through the Word export — run from frontend/:
//   node scripts/test-answer-script-math.mjs
//
// `backend/services/papers/answer_script.py` writes the marking scheme as
// editor nodes: a `questionBlock` per answer holding a paragraph per line,
// `inlineMath` for \( … \) and `mathBlock` for \[ … \]. The fixture below has
// exactly that shape. The export must turn the maths into Word equations and
// keep numbered points on separate lines — the failure this guards against is
// an answer script that reads as raw LaTeX source.

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

const { buildPaperDocx } = await jiti.import(path.resolve(here, "../features/export/docx-paper.ts"));
const { Packer } = await import("docx");

let failures = 0;
function check(label, condition, detail = "") {
  if (condition) console.log(`PASS  ${label}`);
  else {
    failures += 1;
    console.error(`FAIL  ${label}${detail ? ` — ${detail}` : ""}`);
  }
}

const text = (t) => ({ type: "text", text: t });
const inline = (latex) => ({ type: "inlineMath", attrs: { latex } });
const para = (...content) => ({ type: "paragraph", content });
const answer = (number, marks, ...content) => ({
  type: "questionBlock",
  attrs: { number, marks, questionType: "SHORT_ANSWER", aiGenerated: true },
  content,
});

const DOC = {
  type: "doc",
  content: [
    {
      type: "page",
      attrs: { pageId: "page-1" },
      content: [
        { type: "heading", attrs: { level: 1, textAlign: "center" }, content: [text("MARKING SCHEME")] },
        answer(
          1,
          3,
          para(text("1. Given "), inline("ax^{2}+bx+c=0"), text(", the roots are")),
          { type: "mathBlock", attrs: { latex: "x = \\frac{-b \\pm \\sqrt{b^{2}-4ac}}{2a}", displayMode: true } },
          para(text("2. Here "), inline("a=1"), text(" and "), inline("x = 2"), text(" or "), inline("x = 3"), text(".")),
          para(text("(Any 2 points to be considered)")),
        ),
        answer(
          2,
          5,
          para(text("Area = "), inline("25\\pi"), text(" cm")),
          para({ type: "text", marks: [{ type: "bold" }], text: "OR" }),
          para(text("By symmetry "), inline("\\int_0^1 x\\,dx = \\frac{1}{2}"), text(".")),
        ),
      ],
    },
  ],
};

const loader = async () => null;
const built = await buildPaperDocx(DOC, loader);
const zip = await JSZip.loadAsync(await Packer.toBuffer(built));
const xml = await zip.file("word/document.xml").async("string");

const equations = xml.match(/<m:oMath>[\s\S]*?<\/m:oMath>/g) ?? [];
// 4 inline in Q1 (ax²…, a=1, x=2, x=3) + 1 display + 2 inline in Q2.
check("every equation is a Word equation", equations.length === 7, `found ${equations.length}`);

const words = [...xml.matchAll(/<w:t(?: [^>]*)?>([^<]*)<\/w:t>/g)].map((m) => m[1]).join(" ");
check("no raw LaTeX delimiters reach the page", !/\\\(|\\\)|\\\[|\\\]/.test(words), words);
check("no LaTeX commands reach the page as text", !/\\(frac|sqrt|pi|int|pm)/.test(words), words);
check("the prose around the maths is kept", /Area = /.test(words) && /By symmetry/.test(words));

const frac = equations.find((e) => e.includes("<m:f>"));
check("a fraction is built as a Word fraction", !!frac);
check("a root is built as a Word radical", equations.some((e) => e.includes("<m:rad>")));
check(
  "an integral keeps its sign and both limits",
  equations.some((e) => e.includes("∫") && e.includes("<m:sub>") && e.includes("<m:sup>")),
);

// Numbered points are separate paragraphs, not one run with a newline in it.
const paragraphs = xml.match(/<w:p[ >][\s\S]*?<\/w:p>/g) ?? [];
check(
  "each numbered point sits in its own paragraph",
  paragraphs.some((p) => p.includes("1. Given")) &&
    paragraphs.some((p) => p.includes("2. Here")) &&
    !paragraphs.some((p) => p.includes("1. Given") && p.includes("2. Here")),
);

if (failures) {
  console.error(`\n${failures} check(s) failed`);
  process.exit(1);
}
console.log("\nAll answer-script maths checks passed");
