#!/usr/bin/env node
// Undo / redo of the paper editor — run from frontend/:
//   node scripts/test-editor-undo.mjs
//
// Runs ProseMirror's real history plugin against the editor's real schema and
// the real derived-update passes (`derived-updates.ts`), headless. What it
// guards is the contract in `features/editor/history.ts`: the editor's own
// bookkeeping (renumbering, page breaks, loading a document) must not become
// undo steps, so that one Ctrl+Z reverts the thing the user just did — a
// deleted question, image or table — exactly, and Ctrl+Z can be repeated.

import { fileURLToPath } from "node:url";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { createJiti } from "jiti";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");

// math-nodes.tsx imports a stylesheet, which Node cannot load.
const stubDir = mkdtempSync(path.join(tmpdir(), "undo-"));
const cssStub = path.join(stubDir, "empty.mjs");
writeFileSync(cssStub, "export {};\n");

const jiti = createJiti(here, {
  interopDefault: true,
  jsx: true,
  extensions: [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"],
  alias: { "@": root, "katex/dist/katex.min.css": cssStub },
});

const { getSchema } = await jiti.import("@tiptap/core");
const StarterKit = await jiti.import("@tiptap/starter-kit");
const { Table } = await jiti.import("@tiptap/extension-table");
const { TableRow } = await jiti.import("@tiptap/extension-table-row");
const { TableCell } = await jiti.import("@tiptap/extension-table-cell");
const { TableHeader } = await jiti.import("@tiptap/extension-table-header");
const { EditorState } = await jiti.import("@tiptap/pm/state");
const { history, undo, redo, undoDepth, redoDepth, closeHistory } = await jiti.import("@tiptap/pm/history");

const nodes = await jiti.import(path.join(root, "features/editor/extensions/nodes.tsx"));
const math = await jiti.import(path.join(root, "features/editor/extensions/math-nodes.tsx"));
const { PaginatedDocument } = await jiti.import(path.join(root, "features/editor/extensions/document-node.ts"));
const { PageNode } = await jiti.import(path.join(root, "features/editor/extensions/page-node.tsx"));
const { FloatImage } = await jiti.import(path.join(root, "features/editor/extensions/float-image.tsx"));
const { PaperHeaderBlock } = await jiti.import(path.join(root, "features/editor/extensions/header-node.tsx"));
const { updateQuestionNumbers } = await jiti.import(path.join(root, "features/editor/derived-updates.ts"));
const { markDerived, loadDocument, undoRedoIntent, shouldTakeOver } = await jiti.import(
  path.join(root, "features/editor/history.ts"),
);

const schema = getSchema([
  PaginatedDocument,
  PageNode,
  StarterKit.configure({ document: false, heading: { levels: [1, 2, 3, 4, 5, 6] } }),
  Table, TableRow, TableHeader, TableCell,
  nodes.QuestionBlock, nodes.SectionBlock, nodes.InstructionBlock, nodes.QuestionGroupBlock, nodes.GroupedQuestionBlock,
  PaperHeaderBlock, math.MathBlock, math.InlineMath, FloatImage,
]);

let failures = 0;
function check(label, condition, detail = "") {
  if (condition) console.log(`PASS  ${label}`);
  else {
    failures += 1;
    console.error(`FAIL  ${label}${detail ? ` — ${detail}` : ""}`);
  }
}

// ── Fixtures ────────────────────────────────────────────────────────────

const text = (t) => ({ type: "text", text: t });
const para = (t) => ({ type: "paragraph", content: t ? [text(t)] : [] });
const question = (number, body, extra = []) => ({
  type: "questionBlock",
  attrs: { number, marks: 2, questionType: "SHORT_ANSWER" },
  content: [para(body), ...extra],
});
const figure = { type: "floatImage", attrs: { src: "data:image/png;base64,AAAA", alt: "fig", width: 200, align: "center" } };
const grid = {
  type: "table",
  content: [
    { type: "tableRow", content: [
      { type: "tableCell", content: [para("a")] },
      { type: "tableCell", content: [para("b")] },
    ] },
  ],
};
const page = (id, ...blocks) => ({ type: "page", attrs: { pageId: id }, content: blocks });
const docOf = (...pages) => ({ type: "doc", content: pages });

function stateFor(json) {
  const doc = schema.nodeFromJSON(json);
  doc.check();
  return EditorState.create({ doc, schema, plugins: [history()] });
}

/** A stand-in for the TipTap editor object the derived passes expect. */
function harness(json) {
  const h = {
    state: stateFor(json),
    view: { dispatch(tr) { h.state = h.state.apply(tr); } },
    apply(tr) { h.state = h.state.apply(tr); },
    // Real actions are more than the 500 ms history grouping delay apart (a
    // click, then another click). The fake ones happen in the same
    // millisecond, which ProseMirror would merge into one step, so close the
    // current event first.
    pause() { h.state = h.state.apply(closeHistory(h.state.tr)); },
    undo() { return undo(h.state, (tr) => { h.state = h.state.apply(tr); }); },
    redo() { return redo(h.state, (tr) => { h.state = h.state.apply(tr); }); },
    json: () => h.state.doc.toJSON(),
    numbers: () => {
      const out = [];
      h.state.doc.descendants((n) => { if (n.type.name === "questionBlock") out.push(n.attrs.number); });
      return out;
    },
    // A minimal TipTap chain: just what loadDocument calls.
    chain() {
      const meta = {};
      let incoming = null;
      const chain = {
        setMeta(k, v) { meta[k] = v; return chain; },
        setContent(content) { incoming = content; return chain; },
        run() {
          const next = schema.nodeFromJSON(incoming);
          const tr = h.state.tr.replaceWith(0, h.state.doc.content.size, next.content);
          for (const [k, v] of Object.entries(meta)) tr.setMeta(k, v);
          h.state = h.state.apply(tr);
          return true;
        },
      };
      return chain;
    },
    get schema() { return schema; },
  };
  return h;
}

function posOf(h, predicate) {
  let found = null;
  h.state.doc.descendants((node, pos) => {
    if (found === null && predicate(node)) found = { node, pos };
  });
  return found;
}
const qByNumber = (h, n) => posOf(h, (node) => node.type.name === "questionBlock" && node.attrs.number === n);
const deleteNode = (h, target) => {
  h.pause();
  h.apply(h.state.tr.delete(target.pos, target.pos + target.node.nodeSize));
};
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

const FOUR = docOf(
  page("p1", question(1, "First"), question(2, "Second", [figure]), question(3, "Third", [grid]), question(4, "Fourth")),
);

// ── A deleted question comes back, exactly, in one Ctrl+Z ───────────────

{
  const h = harness(FOUR);
  const before = h.json();
  deleteNode(h, qByNumber(h, 2));
  updateQuestionNumbers(h); // the editor's debounced renumber
  check("deleting a question and the renumber after it are ONE undo step", undoDepth(h.state) === 1, `depth ${undoDepth(h.state)}`);
  check("the questions renumber after a delete", same(h.numbers(), [1, 2, 3]));

  h.undo();
  updateQuestionNumbers(h);
  check("one Ctrl+Z restores the deleted question, in place and in order", same(h.json(), before));
  check("…and nothing else disappeared", h.numbers().length === 4);
  check("redo is still available after the renumber ran", redoDepth(h.state) === 1);

  h.redo();
  updateQuestionNumbers(h);
  check("redo deletes it again", h.numbers().length === 3 && same(h.numbers(), [1, 2, 3]));
}

// ── Consecutive undos walk back through each action in order ────────────

{
  const h = harness(FOUR);
  const original = h.json();
  const snapshots = [original];
  for (const n of [1, 3, 4]) {
    // delete by current content so numbering shifts underneath us
    const label = { 1: "First", 3: "Third", 4: "Fourth" }[n];
    deleteNode(h, posOf(h, (node) => node.type.name === "questionBlock" && node.textContent.startsWith(label)));
    updateQuestionNumbers(h);
    snapshots.push(h.json());
  }
  check("three deletes are three undo steps (no bookkeeping in between)", undoDepth(h.state) === 3, `depth ${undoDepth(h.state)}`);
  check("only one question is left", h.numbers().length === 1);

  h.undo(); updateQuestionNumbers(h);
  check("undo 1 restores the last delete", same(h.json(), snapshots[2]));
  h.undo(); updateQuestionNumbers(h);
  check("undo 2 restores the one before", same(h.json(), snapshots[1]));
  h.undo(); updateQuestionNumbers(h);
  check("undo 3 returns to the original paper", same(h.json(), original));
  check("a fourth Ctrl+Z has nothing left to undo", h.undo() === false);
}

{
  // The control for the check above: this is how it behaved before. A renumber
  // dispatched as a plain transaction is its own undo step, so the first
  // Ctrl+Z reverts the renumber and the deleted question stays deleted.
  const h = harness(FOUR);
  deleteNode(h, qByNumber(h, 2));
  h.pause();
  const tr = h.state.tr;
  h.state.doc.descendants((node, pos) => {
    if (node.type.name === "questionBlock" && node.attrs.number > 2) {
      tr.setNodeMarkup(pos, undefined, { ...node.attrs, number: node.attrs.number - 1 });
    }
  });
  h.apply(tr); // no markDerived
  check("control: a RECORDED renumber is a second undo step", undoDepth(h.state) === 2);
  h.undo();
  check("control: …so the first Ctrl+Z only undoes the renumber, not the delete", h.numbers().length === 3);
}

// ── Images and tables ──────────────────────────────────────────────────

{
  const h = harness(FOUR);
  const before = h.json();
  deleteNode(h, posOf(h, (n) => n.type.name === "floatImage"));
  updateQuestionNumbers(h);
  check("the image is gone after deleting it", !posOf(h, (n) => n.type.name === "floatImage"));
  h.undo();
  check("Ctrl+Z restores a deleted image where it was", same(h.json(), before));
}
{
  const h = harness(FOUR);
  const before = h.json();
  deleteNode(h, posOf(h, (n) => n.type.name === "table"));
  check("the table is gone after deleting it", !posOf(h, (n) => n.type.name === "table"));
  h.undo();
  check("Ctrl+Z restores a deleted table with its cells", same(h.json(), before));
}

// ── Editing, adding, moving ────────────────────────────────────────────

{
  const h = harness(FOUR);
  const before = h.json();
  const p = posOf(h, (n) => n.type.name === "paragraph" && n.textContent === "Second");
  h.apply(h.state.tr.insertText(" (edited)", p.pos + 1 + p.node.content.size));
  check("the edit shows in the paper", h.json().content[0].content[1].content[0].content[0].text === "Second (edited)");
  h.undo();
  check("Ctrl+Z reverts a text edit", same(h.json(), before));
}
{
  const h = harness(FOUR);
  const before = h.json();
  const added = schema.nodeFromJSON(question(5, "Added"));
  const q4 = qByNumber(h, 4);
  h.apply(h.state.tr.insert(q4.pos + q4.node.nodeSize, added));
  updateQuestionNumbers(h);
  check("adding a question renumbers without adding an undo step", undoDepth(h.state) === 1);
  h.undo();
  updateQuestionNumbers(h);
  check("Ctrl+Z removes an added question", same(h.json(), before));
}
{
  // Move question 1 below question 2: cut and reinsert in one transaction.
  const h = harness(FOUR);
  const before = h.json();
  const q1 = qByNumber(h, 1);
  const q2 = qByNumber(h, 2);
  const tr = h.state.tr;
  const moved = q1.node;
  tr.insert(q2.pos + q2.node.nodeSize, moved);
  tr.delete(q1.pos, q1.pos + q1.node.nodeSize);
  h.apply(tr);
  updateQuestionNumbers(h);
  check("a moved question takes its new place", h.state.doc.textBetween(0, h.state.doc.content.size, "|", "|").indexOf("Second") < h.state.doc.textBetween(0, h.state.doc.content.size, "|", "|").indexOf("First"));
  check("a move is one undo step", undoDepth(h.state) === 1);
  h.undo();
  updateQuestionNumbers(h);
  check("Ctrl+Z puts a moved question back", same(h.json(), before));
}
{
  const h = harness(docOf(page("p1", question(1, "Maths", [{ type: "paragraph", content: [text("Solve "), { type: "inlineMath", attrs: { latex: "x^2=4" } }] }]))));
  const before = h.json();
  const eq = posOf(h, (n) => n.type.name === "inlineMath");
  h.apply(h.state.tr.setNodeMarkup(eq.pos, undefined, { latex: "x^2=9" }));
  h.undo();
  check("Ctrl+Z reverts an edited equation", same(h.json(), before));
  check("…and the equation's attribute is back (what the node view now renders from)", posOf(h, (n) => n.type.name === "inlineMath").node.attrs.latex === "x^2=4");
}

// ── The page engine moving blocks must not eat the user's undo ─────────

function paginate(h, { recorded }) {
  // What `moveLeadingBlocksToPreviousPage` + `splitPageAtIndex` do: join the
  // pages, then split at a new boundary. Q2 moves to the second page.
  const pages = [];
  h.state.doc.forEach((node, offset) => pages.push({ node, pos: offset }));
  const tr = h.state.tr;
  tr.join(pages[1].pos);
  const first = pages[0].node;
  const splitPos = pages[0].pos + 1 + first.child(0).nodeSize;
  tr.split(splitPos, 1, [{ type: first.type, attrs: { pageId: "p2" } }]);
  h.apply(recorded ? tr : markDerived(tr));
}
const TWO_PAGES = docOf(page("p1", question(1, "First"), question(2, "Second")), page("p2", question(3, "Third")));

{
  const h = harness(TWO_PAGES);
  const before = h.json();
  const third = posOf(h, (n) => n.type.name === "paragraph" && n.textContent === "Third");
  h.apply(h.state.tr.insertText("!", third.pos + 1 + third.node.content.size));
  paginate(h, { recorded: false });
  check("re-pagination after an edit adds no undo step", undoDepth(h.state) === 1, `depth ${undoDepth(h.state)}`);
  h.undo();
  const restored = posOf(h, (n) => n.type.name === "paragraph" && n.textContent.startsWith("Third"));
  check("Ctrl+Z still reverts the edit after the pages were rebalanced", restored.node.textContent === "Third");
  check("…and the rebalanced page layout is left alone", h.state.doc.childCount === 2 && h.state.doc.child(0).childCount === 1);
  check("the paper has the same questions as before", h.numbers().length === 3 && before.content.length === 2);
}
{
  // The control: this is how it behaved before — a recorded page move is an
  // undo step of its own, so the first Ctrl+Z reverts the invisible reshuffle.
  const h = harness(TWO_PAGES);
  const third = posOf(h, (n) => n.type.name === "paragraph" && n.textContent === "Third");
  h.apply(h.state.tr.insertText("!", third.pos + 1 + third.node.content.size));
  paginate(h, { recorded: true });
  h.undo();
  const after = posOf(h, (n) => n.type.name === "paragraph" && n.textContent.startsWith("Third"));
  check("control: a RECORDED page move makes the first Ctrl+Z revert the layout, not the edit", after.node.textContent === "Third!");
}

// ── Opening a paper is not an edit ─────────────────────────────────────

{
  const h = harness(docOf(page("p0", para(""))));
  const loaded = loadDocument(h, FOUR);
  check("loading into a fresh editor replaces the document", loaded && h.numbers().length === 4);
  check("…without making the load an undo step", undoDepth(h.state) === 0, `depth ${undoDepth(h.state)}`);
  check("so the first Ctrl+Z after opening a paper does nothing", h.undo() === false && h.numbers().length === 4);
}
{
  const h = harness(docOf(page("p0", para(""))));
  loadDocument(h, FOUR);
  const before = h.json();
  deleteNode(h, qByNumber(h, 2));
  check("an edit after the load IS an undo step", undoDepth(h.state) === 1);
  h.undo();
  check("…and undoing it returns to the loaded paper, not to blank", same(h.json(), before));
}
{
  // A reload into an editor that already has history stays undoable, so older
  // steps never point into text that was silently swapped out.
  const h = harness(FOUR);
  const original = h.json();
  deleteNode(h, qByNumber(h, 1));
  const reloaded = docOf(page("p1", question(1, "Server copy")));
  h.pause();
  loadDocument(h, reloaded);
  check("a reload into a live editor is one ordinary undo step", undoDepth(h.state) === 2);
  h.undo();
  check("Ctrl+Z restores the document from before the reload", h.numbers().length === 3);
  h.undo();
  check("…and the step before that is still valid", same(h.json(), original));
}
{
  const h = harness(FOUR);
  deleteNode(h, qByNumber(h, 3));
  const depth = undoDepth(h.state);
  const replaced = loadDocument(h, h.json());
  check("reloading identical content changes nothing", !replaced && undoDepth(h.state) === depth);
}

// ── Keyboard handling outside the editor ───────────────────────────────

const key = (k, mods = {}) => ({ key: k, ctrlKey: false, metaKey: false, shiftKey: false, altKey: false, ...mods });
check("Ctrl+Z is undo", undoRedoIntent(key("z", { ctrlKey: true })) === "undo");
check("Cmd+Z is undo", undoRedoIntent(key("z", { metaKey: true })) === "undo");
check("Ctrl+Shift+Z is redo", undoRedoIntent(key("Z", { ctrlKey: true, shiftKey: true })) === "redo");
check("Ctrl+Y is redo", undoRedoIntent(key("y", { ctrlKey: true })) === "redo");
check("Cmd+Y is left to the browser", undoRedoIntent(key("y", { metaKey: true })) === null);
check("a bare Z is not undo", undoRedoIntent(key("z")) === null);
check("Ctrl+Alt+Z is not undo", undoRedoIntent(key("z", { ctrlKey: true, altKey: true })) === null);

{
  // shouldTakeOver reads the DOM; give it just enough of one.
  const inside = new Set();
  class El {
    constructor(name, { matches = [] } = {}) { this.name = name; this.matches = matches; }
    closest(selector) { return this.matches.some((m) => selector.includes(m)) ? this : null; }
  }
  globalThis.Element = El;
  const editorDom = { contains: (el) => inside.has(el) };
  const body = new El("body");
  const button = new El("button");
  const field = new El("input", { matches: ["input"] });
  const dropdown = new El("select");
  const inEditor = new El("p");
  inside.add(inEditor);
  const noOverlay = { querySelector: () => null };
  const withDialog = { querySelector: () => ({}) };

  check("focus on the page body → the page undoes", shouldTakeOver(body, editorDom, noOverlay) === true);
  check("focus on a button (a delete control) → the page undoes", shouldTakeOver(button, editorDom, noOverlay) === true);
  check("focus inside the paper → ProseMirror handles it, the page stays out", shouldTakeOver(inEditor, editorDom, noOverlay) === false);
  check("focus in a text field → that field's own undo", shouldTakeOver(field, editorDom, noOverlay) === false);
  check("focus on a dropdown (no undo of its own) → the page undoes", shouldTakeOver(dropdown, editorDom, noOverlay) === true);
  check("a dialog is open → leave the keystroke to it", shouldTakeOver(body, editorDom, withDialog) === false);
}

if (failures) {
  console.error(`\n${failures} check(s) failed`);
  process.exit(1);
}
console.log("\nAll editor undo checks passed");
