#!/usr/bin/env node
// Regression test for Cluster A: ProseMirror "Content hole must be the only
// child of its parent node" RangeError that previously surfaced from
// SectionBlock + InstructionBlock toDOM specs that emitted siblings next to
// the `0` placeholder.
//
// Walks the toDOM spec returned by every custom NodeView's renderHTML and
// asserts that any occurrence of the integer `0` is the only non-tag-name,
// non-attrs entry in its containing array, recursively.
//
// Run from frontend/: `node scripts/test-todom-shape.mjs`

import { fileURLToPath } from "node:url";
import path from "node:path";
import { createJiti } from "jiti";

const here = path.dirname(fileURLToPath(import.meta.url));
const jiti = createJiti(here, {
  interopDefault: true,
  jsx: true,
  extensions: [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"],
  // Mirror the `@/*` path alias from tsconfig. nodes.tsx started importing
  // `@/lib/api-client` when the per-question Replace button was added, and
  // without this the whole script died with MODULE_NOT_FOUND — silently
  // leaving the content-hole invariant unguarded.
  alias: {
    "@": path.resolve(here, ".."),
  },
  transformOptions: {
    babel: {
      plugins: [],
    },
  },
});

const nodes = await jiti.import(
  path.resolve(here, "../components/editor/extensions/nodes.tsx"),
);

function validateSpec(spec, path = "$") {
  if (!Array.isArray(spec)) return;
  let start = 1;
  if (
    spec.length > 1 &&
    spec[1] !== null &&
    typeof spec[1] === "object" &&
    !Array.isArray(spec[1])
  ) {
    start = 2;
  }
  const children = spec.slice(start);
  const holeIdx = children.indexOf(0);
  if (holeIdx !== -1 && children.length > 1) {
    throw new Error(
      `Content hole rule violated at ${path}: spec[${start + holeIdx}] === 0 but parent array has ${children.length} children. Spec: ${JSON.stringify(spec)}`,
    );
  }
  for (let i = start; i < spec.length; i++) {
    validateSpec(spec[i], `${path}[${i}]`);
  }
}

function fakeNode(name, attrs) {
  return { type: { name }, attrs, content: { size: 0, forEach() {} } };
}

const exts = [
  ["QuestionBlock", nodes.QuestionBlock],
  ["GroupedQuestionBlock", nodes.GroupedQuestionBlock],
  ["SectionBlock", nodes.SectionBlock],
  ["InstructionBlock", nodes.InstructionBlock],
  ["QuestionGroupBlock", nodes.QuestionGroupBlock],
];

const cases = [];
for (const [name, ext] of exts) {
  if (!ext || !ext.config || !ext.config.renderHTML) {
    throw new Error(`extension ${name} has no renderHTML — import failed?`);
  }
}

// SectionBlock — both branches matter (with & without summaryText).
cases.push({
  name: "SectionBlock summaryText=set",
  spec: nodes.SectionBlock.config.renderHTML.call(
    { type: { name: "sectionBlock" } },
    {
      node: fakeNode("sectionBlock", {
        summaryText: "20 marks",
        title: "SECTION A",
      }),
      HTMLAttributes: {},
    },
  ),
});
cases.push({
  name: "SectionBlock summaryText=empty",
  spec: nodes.SectionBlock.config.renderHTML.call(
    { type: { name: "sectionBlock" } },
    {
      node: fakeNode("sectionBlock", {
        summaryText: "",
        title: "SECTION A",
      }),
      HTMLAttributes: {},
    },
  ),
});

// InstructionBlock — both branches matter (with & without summaryItems).
cases.push({
  name: "InstructionBlock summaryItems=[]",
  spec: nodes.InstructionBlock.config.renderHTML.call(
    { type: { name: "instructionBlock" } },
    {
      node: fakeNode("instructionBlock", { summaryItems: [] }),
      HTMLAttributes: {},
    },
  ),
});
cases.push({
  name: "InstructionBlock summaryItems=[3]",
  spec: nodes.InstructionBlock.config.renderHTML.call(
    { type: { name: "instructionBlock" } },
    {
      node: fakeNode("instructionBlock", {
        summaryItems: ["a", "b", "c"],
      }),
      HTMLAttributes: {},
    },
  ),
});

cases.push({
  name: "QuestionBlock",
  spec: nodes.QuestionBlock.config.renderHTML.call(
    { type: { name: "questionBlock" } },
    {
      node: fakeNode("questionBlock", { marks: 2, number: 5 }),
      HTMLAttributes: { marks: 2, number: 5 },
    },
  ),
});

cases.push({
  name: "GroupedQuestionBlock",
  spec: nodes.GroupedQuestionBlock.config.renderHTML.call(
    { type: { name: "groupedQuestionBlock" } },
    {
      node: fakeNode("groupedQuestionBlock", { marks: 5, number: 31 }),
      HTMLAttributes: { marks: 5, number: 31, labelStyle: "alpha" },
    },
  ),
});

cases.push({
  name: "QuestionGroupBlock",
  spec: nodes.QuestionGroupBlock.config.renderHTML.call(
    { type: { name: "questionGroupBlock" } },
    {
      node: fakeNode("questionGroupBlock", { label: "OR", number: 1 }),
      HTMLAttributes: { label: "OR", number: 1 },
    },
  ),
});

let failed = 0;
for (const tc of cases) {
  try {
    validateSpec(tc.spec, tc.name);
    console.log(`PASS  ${tc.name}`);
  } catch (e) {
    console.error(`FAIL  ${tc.name}: ${e.message}`);
    failed += 1;
  }
}

if (failed > 0) {
  console.error(`\n${failed} case(s) failed`);
  process.exit(1);
} else {
  console.log(`\nAll ${cases.length} cases passed`);
}
