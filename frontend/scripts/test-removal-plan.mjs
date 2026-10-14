/**
 * Review-tray undo checks — run with `node scripts/test-removal-plan.mjs`.
 *
 * "Undo all" removes every inserted question; a section header left with no
 * questions must go with them, and one that still holds a question must not.
 */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, renameSync } from "node:fs";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { join } from "node:path";

const dir = mkdtempSync(join(tmpdir(), "rp-"));
execFileSync(
  fileURLToPath(new URL("../node_modules/.bin/tsc", import.meta.url)),
  [
    fileURLToPath(new URL("../features/editor/removal-plan.ts", import.meta.url)),
    "--outDir", dir,
    "--module", "esnext",
    "--target", "es2022",
    "--moduleResolution", "bundler",
    "--skipLibCheck",
    "--ignoreConfig",
  ],
  { stdio: "inherit" },
);
const file = join(dir, "removal-plan.mjs");
renameSync(join(dir, "removal-plan.js"), file);
const { planRemovals } = await import(file);

/** A flat stand-in for a ProseMirror doc: each block is 10 positions wide. */
function doc(...blocks) {
  return {
    descendants(visit) {
      blocks.forEach(([name, text], i) =>
        visit({ type: { name }, textContent: text, nodeSize: 10 }, i * 10),
      );
    },
  };
}
const S = (title) => ["sectionBlock", title];
const Q = (text) => ["questionBlock", text];
const at = (...indexes) => indexes.map((i) => ({ from: i * 10, to: i * 10 + 10 }));
const sorted = (ranges) => [...ranges].sort((a, b) => a.from - b.from);

const paper = doc(S("SECTION A"), Q("What is RAM?"), Q("Name an input device."), S("SECTION B"), Q("Define a URL."));
const req = (sectionTitle, content) => ({ sectionTitle, content });

// Undo all: both sections empty, so both headers go.
assert.deepEqual(
  sorted(planRemovals(paper, [
    req("SECTION A", "What is RAM?"),
    req("SECTION A", "Name an input device."),
    req("SECTION B", "Define a URL."),
  ])),
  at(0, 1, 2, 3, 4),
);

// Undo one: its section still holds a question, so the header stays.
assert.deepEqual(sorted(planRemovals(paper, [req("SECTION A", "What is RAM?")])), at(1));

// Emptying one section leaves the other alone.
assert.deepEqual(sorted(planRemovals(paper, [req("SECTION B", "Define a URL.")])), at(3, 4));

// The same text under another section is not a match.
assert.deepEqual(planRemovals(paper, [req("SECTION B", "What is RAM?")]), []);

// A teacher's own question keeps the header even when every inserted one goes.
const mixed = doc(S("SECTION A"), Q("My own question"), Q("What is RAM?"));
assert.deepEqual(sorted(planRemovals(mixed, [req("SECTION A", "What is RAM?")])), at(2));

// ── Composite questions: a head holding the preamble, then its run ──────
const P = (text) => ["paragraph", text];
const extract = doc(
  S("SECTION C"),
  Q("Extract:"),
  P("Today, all of us do, by our presence here, confer glory and hope."),
  P(""),
  P("(i) What does Mandela mean by a human disaster? (2 marks)"),
  P("My own note to the class."),
  Q("Define a URL."),
);
const extractContent =
  "Extract:\n\nToday, all of us do, by our presence here, confer glory and hope.\n\n" +
  "(i) What does Mandela mean by a human disaster? (2 marks)";

// The head is matched by its run and the run goes with it — but not the
// teacher's own paragraph after it, and the section keeps its other question.
assert.deepEqual(
  sorted(planRemovals(extract, [req("SECTION C", extractContent)])),
  at(1, 2, 3, 4),
);

// Two composites with the same preamble are told apart by what follows.
const twins = doc(
  S("SECTION C"),
  Q("Extract:"), P("First passage about liberty and peace for every nation."),
  Q("Extract:"), P("Second passage about Anne and her teacher Mr Keesing."),
);
assert.deepEqual(
  sorted(planRemovals(twins, [
    req("SECTION C", "Extract:\n\nSecond passage about Anne and her teacher Mr Keesing."),
  ])),
  at(3, 4),
);

// Pagination split the run across two pages: both halves go.
{
  const pageA = { type: { name: "page" } };
  const pageB = { type: { name: "page" } };
  const blocks = [
    [pageA, S("SECTION C")],
    [pageA, Q("Extract:")],
    [pageA, P("A long passage that starts on the first page of the paper.")],
    [pageB, P("And it ends on the second page where pagination moved it.")],
    [pageB, Q("Define a URL.")],
  ];
  const split = {
    descendants(visit) {
      blocks.forEach(([parent, [name, text]], i) =>
        visit({ type: { name }, textContent: text, nodeSize: 10 }, i * 10, parent),
      );
    },
  };
  assert.deepEqual(
    sorted(planRemovals(split, [req("SECTION C",
      "Extract:\n\nA long passage that starts on the first page of the paper. " +
      "And it ends on the second page where pagination moved it.")])),
    at(1, 2, 3),
  );
}

console.log("All removal-plan checks passed");
