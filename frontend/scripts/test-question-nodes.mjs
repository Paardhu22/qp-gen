/**
 * Block mapping checks — run with `node scripts/test-question-nodes.mjs`.
 *
 * There is no test runner on the frontend, but this logic is pure and it is
 * where the MCQ bug lived: option lines written into a question's text became
 * paragraphs instead of the orderedList the MCQ block renders as "(A) (B)".
 * The risky part is the guard — a reading passage's "I. / II." sub-questions
 * and a grammar set's twelve items must NOT be mistaken for options.
 */
import { execFileSync } from "node:child_process";
import { mkdtempSync, renameSync } from "node:fs";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { join } from "node:path";

// Transpile with the project's own TypeScript rather than stripping types by
// hand — the module under test is the source of truth for the real editor, so
// the test must run exactly what ships.
const dir = mkdtempSync(join(tmpdir(), "qn-"));
const sourcePath = fileURLToPath(
  new URL("../components/editor/question-nodes.ts", import.meta.url),
);
execFileSync(
  fileURLToPath(new URL("../node_modules/.bin/tsc", import.meta.url)),
  [
    sourcePath,
    "--outDir", dir,
    "--module", "esnext",
    "--target", "es2022",
    "--moduleResolution", "bundler",
    "--skipLibCheck",
  ],
  { stdio: "inherit" },
);
const file = join(dir, "question-nodes.mjs");
renameSync(join(dir, "question-nodes.js"), file);

const {
  splitStemAndOptions,
  resolveStemAndOptions,
  buildQuestionBlock,
  buildQuestionBlocks,
  compositeRunSize,
  buildSlotMeta,
  parseSlotMeta,
} = await import(`file://${file}`);

let passed = 0;
const failures = [];

function check(name, fn) {
  try {
    fn();
    passed += 1;
  } catch (error) {
    failures.push(`${name}\n    ${error.message}`);
  }
}

function eq(actual, expected, what = "") {
  const a = JSON.stringify(actual);
  const b = JSON.stringify(expected);
  if (a !== b) throw new Error(`${what} expected ${b}, got ${a}`);
}

const optionsOf = (block) => {
  const list = block.content.find((n) => n.type === "orderedList");
  if (!list) return null;
  return list.content.map((li) =>
    li.content[0].content.map((t) => t.text ?? "").join(""),
  );
};

// ── The bug: options written into the stem ──────────────────────────────

check("options inlined in the stem are pulled out", () => {
  const { stem, options } = splitStemAndOptions(
    "Which of the following is a good conductor?\nA. Rubber\nB. Copper\nC. Wood\nD. Glass",
  );
  eq(stem, "Which of the following is a good conductor?");
  eq(options, ["Rubber", "Copper", "Wood", "Glass"]);
});

check("bracketed and parenthesised labels work", () => {
  eq(
    splitStemAndOptions("Pick one.\n(a) first\n(b) second\n(c) third").options,
    ["first", "second", "third"],
  );
  eq(splitStemAndOptions("Pick one.\n1) one\n2) two").options, ["one", "two"]);
});

check("a generated MCQ becomes an MCQ block, not paragraphs", () => {
  const block = buildQuestionBlock({
    content: "Which metal is liquid at room temperature?\nA. Iron\nB. Mercury\nC. Zinc\nD. Tin",
    type: "MCQ",
    marks: 1,
  });
  eq(block.attrs.questionType, "MCQ");
  eq(optionsOf(block), ["Iron", "Mercury", "Zinc", "Tin"]);
  const paragraphs = block.content.filter((n) => n.type === "paragraph");
  eq(paragraphs.length, 1, "only the stem should remain a paragraph:");
});

check("structured options still win and are not duplicated", () => {
  const block = buildQuestionBlock({
    content: "Which metal is liquid at room temperature?\nA. Iron\nB. Mercury\nC. Zinc\nD. Tin",
    type: "MCQ",
    options: ["Iron", "Mercury", "Zinc", "Tin"],
    marks: 1,
  });
  eq(block.content.filter((n) => n.type === "orderedList").length, 1);
  eq(block.content.filter((n) => n.type === "paragraph").length, 1);
});

check("a question with only structured options is unchanged", () => {
  const block = buildQuestionBlock({
    content: "Which metal is liquid at room temperature?",
    type: "MCQ",
    options: ["Iron", "Mercury", "Zinc", "Tin"],
    marks: 1,
  });
  eq(optionsOf(block), ["Iron", "Mercury", "Zinc", "Tin"]);
});

// ── The guard: composite questions must survive intact ──────────────────

check("a reading passage's sub-questions are never treated as options", () => {
  const content = [
    "Read the following passage.",
    "",
    "1   Indigenous crafts are a welcome trend.",
    "",
    "Answer the following questions.",
    "",
    "I. Why is the trend welcome?   [1]",
    "II. According to paragraph 1, all EXCEPT:   [1]",
    "      A. handcrafted",
    "      B. rooted in tradition",
    "      C. aesthetic",
    "      D. easily accessible",
  ].join("\n");
  const block = buildQuestionBlock({ content, type: "READING_COMP", marks: 10 });
  eq(block.attrs.questionType, "READING_COMP");
  eq(optionsOf(block), null, "no top-level option list:");
  // Every line survives as its own paragraph.
  const text = block.content
    .filter((n) => n.type === "paragraph")
    .map((n) => (n.content || []).map((t) => t.text ?? "").join(""))
    .join("\n");
  if (!text.includes("easily accessible")) {
    throw new Error("the passage lost its sub-question options");
  }
});

check("a grammar task set keeps all twelve items", () => {
  const content = [
    "Complete any 10 of 12 of the following tasks, as directed.",
    ...Array.from({ length: 12 }, (_, i) => `${i + 1}. Task number ${i + 1}`),
  ].join("\n");
  const block = buildQuestionBlock({ content, type: "GRAMMAR", marks: 10 });
  eq(optionsOf(block), null);
  eq(block.content.filter((n) => n.type === "paragraph").length, 13);
});

check("prose that merely starts with a letter is not an option", () => {
  eq(
    splitStemAndOptions("A wire carries current.\nB is the midpoint.").options,
    [],
  );
});

check("an out-of-sequence trailing run is left alone", () => {
  eq(splitStemAndOptions("Explain.\nA. first\nC. third").options, []);
});

check("more than six trailing items is not an option block", () => {
  const content = [
    "Answer the following.",
    ...Array.from({ length: 8 }, (_, i) => `${String.fromCharCode(97 + i)}. item`),
  ].join("\n");
  eq(splitStemAndOptions(content).options, []);
});

check("a very long trailing line is prose, not an option", () => {
  const long = "D. " + "x".repeat(250);
  eq(splitStemAndOptions(`Stem.\nA. short\nB. short\n${long}`).options, []);
});

check("true/false keeps its own wording", () => {
  const { options } = resolveStemAndOptions({
    content: "The Earth is flat.",
    type: "TF",
    options: ["True", "False"],
  });
  eq(options, ["True", "False"]);
});

// ── Slot metadata, which is what makes Replace possible ─────────────────

check("slot metadata round-trips", () => {
  const meta = buildSlotMeta({
    content: "q",
    type: "SHORT_ANSWER",
    marks: 3,
    metadata: {
      slotIndex: 8,
      section: "Section C",
      generator: "question_pool",
      assetType: "short_answer_bundle",
      inferredChapter: "Bholi",
      difficulty: "medium",
    },
  });
  const parsed = parseSlotMeta(meta);
  eq(parsed.slotIndex, 8);
  eq(parsed.marks, 3);
  eq(parsed.generator, "question_pool");
  eq(parsed.chapter, "Bholi");
});

check("a hand-written question carries no slot metadata", () => {
  eq(buildSlotMeta({ content: "q", marks: 1 }), "");
  eq(parseSlotMeta(""), null);
  eq(parseSlotMeta("not json"), null);
});

check("assertion-reason keeps its four standard options", () => {
  const block = buildQuestionBlock({
    content: "Assertion (A): ...\nReason (R): ...",
    type: "ASSERTION_REASON",
    options: ["Both true, R explains A", "Both true, R does not explain A", "A true R false", "A false R true"],
    marks: 1,
  });
  eq(block.attrs.questionType, "ASSERTION_REASON");
  eq(optionsOf(block).length, 4);
});

// ── Composite questions ─────────────────────────────────────────────────
//
// A passage that arrives as ONE block cannot be broken across pages: the
// pagination engine splits only between a page's top-level children. These
// checks pin the shape that makes it splittable — and, just as importantly,
// that exactly one block in the run is a questionBlock, since every one of
// them would otherwise consume a question number.

const compositeQuestion = {
  content: "ignored when composite parts are present",
  type: "READING_COMP",
  marks: 10,
  metadata: {
    slotIndex: 0,
    section: "A",
    composite: {
      preamble: "Read the following passage.",
      body: ["1   First paragraph.", "2   Second paragraph.", "Answer the questions."],
      subQuestions: ["I. Why?   [1]", "II. How?   [2]"],
    },
  },
};

check("an ordinary question is still exactly one block", () => {
  const blocks = buildQuestionBlocks({ content: "Define inertia.", marks: 2 });
  eq(blocks.length, 1);
  eq(blocks[0].type, "questionBlock");
});

check("a composite becomes a head block plus splittable siblings", () => {
  const blocks = buildQuestionBlocks(compositeQuestion);
  // head + 3 body paragraphs + 2 sub-questions
  eq(blocks.length, 6);
  eq(blocks[0].type, "questionBlock");
  eq(
    blocks.slice(1).map((n) => n.type),
    ["paragraph", "paragraph", "paragraph", "paragraph", "paragraph"],
  );
});

check("only the head of a composite consumes a question number", () => {
  const blocks = buildQuestionBlocks(compositeQuestion);
  eq(blocks.filter((n) => n.type === "questionBlock").length, 1);
});

check("the head of a composite carries the marks and the replace context", () => {
  const [head] = buildQuestionBlocks(compositeQuestion);
  eq(head.attrs.marks, 10);
  eq(head.attrs.questionType, "READING_COMP");
  eq(parseSlotMeta(head.attrs.slotMeta).section, "A");
});

check("the head of a composite holds only the preamble", () => {
  const [head] = buildQuestionBlocks(compositeQuestion);
  const text = head.content
    .map((n) => (n.content || []).map((t) => t.text ?? "").join(""))
    .join("\n");
  eq(text, "Read the following passage.");
});

check("no passage text is lost on the way into blocks", () => {
  const blocks = buildQuestionBlocks(compositeQuestion);
  const text = blocks
    .flatMap((n) => (n.type === "questionBlock" ? n.content : [n]))
    .map((n) => (n.content || []).map((t) => t.text ?? "").join(""))
    .join("\n");
  for (const expected of [
    "First paragraph.",
    "Second paragraph.",
    "I. Why?",
    "II. How?",
  ]) {
    if (!text.includes(expected)) {
      throw new Error(`the composite lost "${expected}"`);
    }
  }
});

check("a composite with nothing after its preamble stays one block", () => {
  const blocks = buildQuestionBlocks({
    content: "Read the passage.",
    type: "READING_COMP",
    marks: 5,
    metadata: { composite: { preamble: "Read the passage.", body: [], subQuestions: [] } },
  });
  eq(blocks.length, 1);
});

check("malformed composite metadata falls back to a single block", () => {
  for (const composite of [null, "nonsense", { body: "not an array" }, {}]) {
    const blocks = buildQuestionBlocks({ content: "q", marks: 1, metadata: { composite } });
    eq(blocks.length, 1, `composite=${JSON.stringify(composite)}:`);
  }
});

// `compositeRunSize` is what Replace uses to overwrite a whole composite
// rather than just its head. It is fed a ProseMirror parent, so the stub
// mirrors the two methods it touches.
const fakeParent = (children) => ({
  childCount: children.length,
  child: (i) => children[i],
});
const stub = (name, nodeSize) => ({ type: { name }, nodeSize });

check("a composite run stops at the next question", () => {
  const parent = fakeParent([
    stub("questionBlock", 10), // the composite head
    stub("paragraph", 5),
    stub("paragraph", 7),
    stub("questionBlock", 4), // the next question — not part of the run
    stub("paragraph", 3),
  ]);
  eq(compositeRunSize(parent, 0), 22);
});

check("a composite run stops at a section heading", () => {
  const parent = fakeParent([
    stub("questionBlock", 10),
    stub("paragraph", 5),
    stub("sectionBlock", 6),
    stub("paragraph", 3),
  ]);
  eq(compositeRunSize(parent, 0), 15);
});

check("a run that reaches the end of the page is bounded by it", () => {
  const parent = fakeParent([stub("questionBlock", 10), stub("paragraph", 5)]);
  eq(compositeRunSize(parent, 0), 15);
});

check("an ordinary question's run is just itself", () => {
  const parent = fakeParent([stub("questionBlock", 9), stub("questionBlock", 4)]);
  eq(compositeRunSize(parent, 0), 9);
});

// ── Report ──────────────────────────────────────────────────────────────

if (failures.length > 0) {
  console.error(`\n${failures.length} failed, ${passed} passed\n`);
  failures.forEach((f) => console.error(`  ✗ ${f}\n`));
  process.exit(1);
}
console.log(`✓ ${passed} block-mapping checks passed`);
