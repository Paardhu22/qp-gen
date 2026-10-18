#!/usr/bin/env node
// Questions from a teacher's own image — run from frontend/:
//   node scripts/test-image-question.mjs
//
// The edit rules must agree with the backend's (`services/generation/image_question.py`
// sanitises the same list), the geometry behind the editor must keep every edit
// inside the picture, and a generated question must land in the paper as a valid
// node with its picture above the options and the teacher's description as alt text.

import { fileURLToPath } from "node:url";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { createJiti } from "jiti";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const stub = path.join(mkdtempSync(path.join(tmpdir(), "imgq-")), "empty.mjs");
writeFileSync(stub, "export {};\n");
const jiti = createJiti(here, {
  interopDefault: true,
  jsx: true,
  extensions: [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"],
  alias: { "@": root, "katex/dist/katex.min.css": stub },
});

const E = await jiti.import(path.join(root, "features/editor/image-edits.ts"));
const { imageQuestionBlocks, questionInsertPos, getLastPageInsertPos } = await jiti.import(
  path.join(root, "features/editor/insert-image-question.ts"),
);
const { buildFigureNode } = await jiti.import(path.join(root, "features/editor/question-nodes.ts"));
const { getSchema } = await jiti.import("@tiptap/core");
const StarterKit = await jiti.import("@tiptap/starter-kit");
const { Table } = await jiti.import("@tiptap/extension-table");
const { TableRow } = await jiti.import("@tiptap/extension-table-row");
const { TableCell } = await jiti.import("@tiptap/extension-table-cell");
const { TableHeader } = await jiti.import("@tiptap/extension-table-header");
const { EditorState, TextSelection } = await jiti.import("@tiptap/pm/state");
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
const near = (a, b, eps = 1e-6) => Math.abs(a - b) < eps;
const ops = (list) => list.map((e) => e.op).join();

// ── Sanitising: the same rules as the backend ───────────────────────────
{
  const out = E.sanitizeEdits([
    { op: "highlight", x: 0.1, y: 0.2, w: 0.3, h: 0.1 },
    { op: "arrow", x1: 0.1, y1: 0.1, x2: 0.5, y2: 0.5 },
    { op: "label", x: 0.4, y: 0.4, text: "R2" },
    { op: "cover", x: 0, y: 0, w: 0.2, h: 0.2 },
    { op: "crop", x: 0.1, y: 0.1, w: 0.8, h: 0.8 },
  ]);
  check("valid edits pass through", ops(out) === "highlight,arrow,label,cover,crop");
  check("default colours are filled in (none on a cover or crop)", out[0].color === "#ffd400" && out[1].color === "#e11d48" && out[3].color === undefined);
}
{
  const [e] = E.sanitizeEdits([{ op: "box", x: -0.5, y: 0.9, w: 3, h: 3 }]);
  check("coordinates are clamped to the picture", e.x === 0 && e.y === 0.9 && e.x + e.w <= 1 && e.y + e.h <= 1);
}
check(
  "nonsense is dropped, never thrown",
  E.sanitizeEdits([
    "text", null, 3, {}, { op: "explode" }, { op: "box" }, { op: "box", x: "a", y: 0, w: 1, h: 1 },
    { op: "box", x: 0.5, y: 0.5, w: 0, h: 0.5 }, { op: "box", x: NaN, y: 0, w: 0.5, h: 0.5 },
    { op: "arrow", x1: 0.5, y1: 0.5, x2: 0.5, y2: 0.5 }, { op: "label", x: 0.5, y: 0.5, text: "   " },
  ]).length === 0 && E.sanitizeEdits("nope").length === 0 && E.sanitizeEdits(null).length === 0,
);
check("a colour must be plain hex", E.sanitizeEdits([{ op: "box", x: 0.1, y: 0.1, w: 0.2, h: 0.2, color: "url(javascript:alert(1))" }])[0].color === "#e11d48" && E.sanitizeEdits([{ op: "box", x: 0.1, y: 0.1, w: 0.2, h: 0.2, color: "#00aa00" }])[0].color === "#00aa00");
{
  const [e] = E.sanitizeEdits([{ op: "label", x: 0.1, y: 0.1, text: "  a   b  " + "z".repeat(200) }]);
  check("labels are trimmed and capped", e.text.startsWith("a b ") && e.text.length <= E.MAX_LABEL_CHARS);
}
{
  const out = E.sanitizeEdits([
    { op: "crop", x: 0, y: 0, w: 0.5, h: 0.5 },
    { op: "box", x: 0.1, y: 0.1, w: 0.2, h: 0.2 },
    { op: "crop", x: 0.2, y: 0.2, w: 0.5, h: 0.5 },
  ]);
  check("only the last crop counts", out.filter((e) => e.op === "crop").length === 1 && out.find((e) => e.op === "crop").x === 0.2);
}
check("the number of edits is bounded", E.sanitizeEdits(Array(100).fill({ op: "box", x: 0.1, y: 0.1, w: 0.1, h: 0.1 })).length === E.MAX_EDITS);

// ── Building and cropping ───────────────────────────────────────────────
{
  const crop1 = { op: "crop", x: 0.1, y: 0.1, w: 0.5, h: 0.5 };
  const crop2 = { op: "crop", x: 0.3, y: 0.3, w: 0.4, h: 0.4 };
  const list = E.addEdit(E.addEdit([], crop1), { op: "box", x: 0.1, y: 0.1, w: 0.2, h: 0.2 });
  const replaced = E.addEdit(list, crop2);
  check("a new crop replaces the old one", replaced.filter((e) => e.op === "crop").length === 1 && E.cropRect(replaced).x === 0.3);
  check("a stray click is not added", E.addEdit(list, { op: "box", x: 0.5, y: 0.5, w: 0.001, h: 0.001 }).length === list.length);
  check("an edit can be removed by position", ops(E.removeEdit(list, 0)) === "box");
  check("no crop means no crop rect", E.cropRect([]) === null);
  const size = E.outputSize(2000, 1000, [{ op: "crop", x: 0, y: 0, w: 0.5, h: 1 }]);
  check("the output is the crop's share of the original", size.width === 1000 && size.height === 1000);
  const big = E.outputSize(8000, 4000, [], 2400);
  check("a large picture is scaled down to fit", big.width === 2400 && big.height === 1200);
  check("a small picture is never scaled up", E.outputSize(300, 200, [], 2400).width === 300);
  check("a drag in any direction is the same rectangle", JSON.stringify(E.rectFromDrag(0.6, 0.7, 0.2, 0.1)) === JSON.stringify({ x: 0.2, y: 0.1, w: 0.4, h: 0.6000000000000001 }) || near(E.rectFromDrag(0.6, 0.7, 0.2, 0.1).h, 0.6));
}

// ── Moving, resizing, hitting ───────────────────────────────────────────
{
  const box = { op: "box", x: 0.2, y: 0.2, w: 0.3, h: 0.3 };
  const moved = E.moveEdit(box, 0.1, -0.1);
  check("a box moves by the drag", near(moved.x, 0.3) && near(moved.y, 0.1) && moved.w === 0.3);
  const pinned = E.moveEdit(box, 5, 5);
  check("a box cannot be dragged off the picture", near(pinned.x + pinned.w, 1) && near(pinned.y + pinned.h, 1));
  const arrow = { op: "arrow", x1: 0.1, y1: 0.1, x2: 0.5, y2: 0.4 };
  const slid = E.moveEdit(arrow, 5, 5);
  check("an arrow keeps its shape when pinned to the edge", near(slid.x2 - slid.x1, 0.4) && near(slid.y2 - slid.y1, 0.3) && slid.x2 <= 1 && slid.y2 <= 1);
  check("a label moves too", near(E.moveEdit({ op: "label", x: 0.5, y: 0.5, text: "a" }, 0.2, 0).x, 0.7));
}
{
  const box = { op: "box", x: 0.2, y: 0.2, w: 0.3, h: 0.3 };
  const se = E.resizeEdit(box, "se", 0.8, 0.9);
  check("dragging the lower-right corner keeps the upper-left fixed", near(se.x, 0.2) && near(se.y, 0.2) && near(se.w, 0.6) && near(se.h, 0.7));
  const nw = E.resizeEdit(box, "nw", 0.1, 0.05);
  check("dragging the upper-left corner keeps the lower-right fixed", near(nw.x + nw.w, 0.5) && near(nw.y + nw.h, 0.5) && near(nw.x, 0.1));
  const flipped = E.resizeEdit(box, "se", 0.05, 0.05);
  check("dragging a corner past the opposite one flips the box, never negative", flipped.w >= 0 && flipped.h >= 0 && near(flipped.x, 0.05) && near(flipped.w, 0.15));
  const ar = E.resizeEdit({ op: "arrow", x1: 0.1, y1: 0.1, x2: 0.5, y2: 0.5 }, "p2", 0.9, 0.2);
  check("an arrow's head moves while its tail stays", near(ar.x1, 0.1) && near(ar.x2, 0.9) && near(ar.y2, 0.2));
  check("handles are offered for boxes (4) and arrows (2) but not labels", E.handlesOf(box).length === 4 && E.handlesOf({ op: "arrow", x1: 0, y1: 0, x2: 1, y2: 1 }).length === 2 && E.handlesOf({ op: "label", x: 0, y: 0, text: "a" }).length === 0);
  check("resizing clamps to the picture", E.resizeEdit(box, "se", 5, 5).w <= 0.8 + 1e-9);
}
{
  const list = [
    { op: "highlight", x: 0.1, y: 0.1, w: 0.5, h: 0.5 },
    { op: "box", x: 0.3, y: 0.3, w: 0.2, h: 0.2 },
    { op: "arrow", x1: 0.7, y1: 0.7, x2: 0.9, y2: 0.9 },
    { op: "label", x: 0.7, y: 0.1, text: "R2" },
  ];
  check("a click picks the topmost edit under it", E.hitTest(list, 0.4, 0.4) === 1);
  check("…or the one beneath where only it reaches", E.hitTest(list, 0.15, 0.15) === 0);
  check("an arrow is hit near its line, not near its bounding box", E.hitTest(list, 0.8, 0.8) === 2 && E.hitTest(list, 0.9, 0.7) === -1);
  check("a label is hit on its text", E.hitTest(list, 0.72, 0.12) === 3);
  check("empty space hits nothing", E.hitTest(list, 0.95, 0.3) === -1);
}
check(
  "edits are described for a list, with where they are",
  E.describeEdit({ op: "highlight", x: 0.05, y: 0.05, w: 0.2, h: 0.2 }) === "Highlight · upper-left" &&
    E.describeEdit({ op: "label", x: 0.5, y: 0.5, text: "θ" }) === "Label “θ” · centre" &&
    E.describeEdit({ op: "arrow", x1: 0, y1: 0, x2: 0.9, y2: 0.1 }) === "Arrow · to upper-right",
);

// ── A generated question lands in the paper ─────────────────────────────
const schema = getSchema([
  PaginatedDocument, PageNode,
  StarterKit.configure({ document: false, heading: { levels: [1, 2, 3, 4, 5, 6] } }),
  Table, TableRow, TableHeader, TableCell,
  nodes.QuestionBlock, nodes.SectionBlock, nodes.InstructionBlock, nodes.QuestionGroupBlock, nodes.GroupedQuestionBlock,
  PaperHeaderBlock, math.MathBlock, math.InlineMath, FloatImage,
]);

const wire = {
  content: "In the circuit shown, find the total resistance if \\(R_1 = 2\\,\\Omega\\) and \\(R_2 = 4\\,\\Omega\\).",
  type: "MCQ",
  options: ["2 Ω", "4 Ω", "6 Ω", "8 Ω"],
  answer: "6 Ω",
  marks: 1,
  image_url: "/media/user_images/u1/abc-original.png",
  image_alt: "A series circuit with a battery and two resistors",
  metadata: { difficulty: "easy", sourceType: "image", imageQuestion: true },
};

const names = (list) => list.map((n) => n.type);
{
  const blocks = imageQuestionBlocks(wire);
  check("one question block", blocks.length === 1 && blocks[0].type === "questionBlock");
  const q = blocks[0];
  const kinds = names(q.content);
  check("the picture sits between the stem and the options", kinds.indexOf("floatImage") > 0 && kinds.indexOf("floatImage") < kinds.indexOf("orderedList"), kinds.join());
  const fig = q.content.find((n) => n.type === "floatImage");
  check("it is the stored picture", fig.attrs.src === wire.image_url);
  check("the description is the alt text", fig.attrs.alt === wire.image_alt);
  check("the options are a list of four", q.content.find((n) => n.type === "orderedList").content.length === 4);
  check("the question is an MCQ worth its marks", q.attrs.questionType === "MCQ" && q.attrs.marks === 1);
  check("it cannot be 'swapped' like a pool question (no slot)", q.attrs.slotMeta === "");
  check("maths in the stem is an equation node", JSON.stringify(q.content[0]).includes('"inlineMath"'));
}
{
  const fig = buildFigureNode("/media/x.png", "A graph");
  check("a figure node carries its alt text", fig.attrs.alt === "A graph" && buildFigureNode("/media/x.png").attrs.alt === "");
  check("a bad URL still yields no figure", buildFigureNode("javascript:alert(1)") === null && buildFigureNode("") === null);
}

const doc = (...content) => ({
  type: "doc",
  content: [{ type: "page", attrs: { pageId: "p1" }, content }],
});
const para = (t) => ({ type: "paragraph", content: [{ type: "text", text: t }] });
const question = (n, t) => ({ type: "questionBlock", attrs: { number: n, marks: 1, questionType: "SHORT" }, content: [para(t)] });

function editorFor(json, at) {
  const d = schema.nodeFromJSON(json);
  d.check();
  let state = EditorState.create({ doc: d, schema });
  if (at !== undefined) state = state.apply(state.tr.setSelection(TextSelection.create(state.doc, at)));
  return { get state() { return state; }, set(next) { state = next; } };
}
function posInside(editor, text) {
  let found = -1;
  editor.state.doc.descendants((node, pos) => {
    if (found < 0 && node.isText && node.text === text) found = pos + 1;
  });
  return found;
}

{
  const base = doc(question(1, "First"), question(2, "Second"), question(3, "Third"));
  const probe = editorFor(base);
  const ed = editorFor(base, posInside(probe, "First"));
  const pos = questionInsertPos(ed);
  const tr = ed.state.tr.insert(pos, imageQuestionBlocks(wire).map((n) => schema.nodeFromJSON(n)));
  const after = tr.doc;
  after.check();
  const order = [];
  after.descendants((n) => { if (n.type.name === "questionBlock") order.push(n.textContent.slice(0, 6)); });
  check("it lands right after the question the cursor is in", order.join() === "First,In the,Second,Third", order.join());
}
{
  // A cursor in a plain paragraph, outside any question, has nothing to follow.
  const base = doc(question(1, "First"), para("Loose note"), question(2, "Second"));
  const probe = editorFor(base);
  const ed = editorFor(base, posInside(probe, "Loose note"));
  const pos = questionInsertPos(ed);
  check("with the cursor outside any question it goes at the end of the paper", pos === getLastPageInsertPos(ed));
  const tr = ed.state.tr.insert(pos, imageQuestionBlocks(wire).map((n) => schema.nodeFromJSON(n)));
  tr.doc.check();
  const order = [];
  tr.doc.descendants((n) => { if (n.type.name === "questionBlock") order.push(n.textContent.slice(0, 6)); });
  check("…after every existing question", order.join() === "First,Second,In the", order.join());
}
{
  const withImage = doc({ type: "questionBlock", attrs: { number: 1, marks: 1, questionType: "SHORT" }, content: imageQuestionBlocks({ ...wire, options: [], type: "SHORT_ANSWER" })[0].content });
  let valid = true;
  try { schema.nodeFromJSON(withImage).check(); } catch { valid = false; }
  check("a question with a picture is a valid document", valid);
}

if (failures) {
  console.error(`\n${failures} check(s) failed`);
  process.exit(1);
}
console.log("\nAll image-question checks passed");
