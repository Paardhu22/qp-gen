/**
 * Plan-summary checks — run with `node scripts/test-plan-summary.mjs`.
 *
 * The regression this guards: the dashboard's press-check sheet rendered the
 * generation stream's `plan` event `summary` field directly as its status
 * line. That field is an object, not a sentence, so every paper generation
 * started from the dashboard crashed the route the moment the blueprint
 * landed — "Objects are not valid as a React child (found: object with keys
 * {total_questions, total_marks, or_choices, image_questions,
 * vi_alternatives, exact_counts, section_marks, section_questions})" — which
 * unmounted the page and killed the SSE connection with it.
 *
 * The payloads below are the two real shapes the backend emits:
 * `services/generation_router.py::summarize_question_plan` (eight keys) and
 * the general-instructions branch of `services/pool/pipeline.py` (two keys).
 */
import { execFileSync } from "node:child_process";
import { mkdtempSync, renameSync } from "node:fs";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { join } from "node:path";

const dir = mkdtempSync(join(tmpdir(), "plan-"));
const sourcePath = fileURLToPath(new URL("../lib/plan-summary.ts", import.meta.url));
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
const file = join(dir, "plan-summary.mjs");
renameSync(join(dir, "plan-summary.js"), file);

const { planSummaryLine, asStatusText } = await import(`file://${file}`);

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
  if (actual !== expected) {
    throw new Error(`${what} expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

/** The exact object shape named in the crash, from summarize_question_plan. */
const FULL_SUMMARY = {
  total_questions: 11,
  total_marks: 80,
  or_choices: 4,
  image_questions: 0,
  vi_alternatives: 0,
  exact_counts: ["1 Reading Comprehension (10m)", "3 Short Answer (3m)"],
  section_marks: { "SECTION A": 20, "SECTION B": 20, "SECTION C": 40 },
  section_questions: { "SECTION A": 2, "SECTION B": 3, "SECTION C": 6 },
};

/** The two-key form emitted by the general-instructions branch. */
const MINIMAL_SUMMARY = { total_questions: 5, total_marks: 25 };

check("formats the full blueprint summary", () => {
  eq(
    planSummaryLine(FULL_SUMMARY),
    "Blueprint compiled — 11 questions · 80 marks · 3 sections",
  );
});

check("formats the general-instructions summary", () => {
  eq(planSummaryLine(MINIMAL_SUMMARY), "Blueprint compiled — 5 questions · 25 marks");
});

check("singularises a one-question, one-section paper", () => {
  eq(
    planSummaryLine({ total_questions: 1, total_marks: 1, section_questions: { A: 1 } }),
    "Blueprint compiled — 1 question · 1 marks · 1 section",
  );
});

check("passes a string summary through untouched", () => {
  eq(planSummaryLine("Blueprint ready"), "Blueprint ready");
});

check("returns empty for absent or unusable summaries", () => {
  for (const value of [undefined, null, {}, 42, [], true]) {
    eq(planSummaryLine(value), "", `for ${JSON.stringify(value) ?? "undefined"}:`);
  }
});

check("ignores a section_questions that is not a plain object", () => {
  eq(
    planSummaryLine({ total_questions: 2, total_marks: 10, section_questions: ["A", "B"] }),
    "Blueprint compiled — 2 questions · 10 marks",
  );
});

check("never returns a non-string — the property that stops the crash", () => {
  const inputs = [
    FULL_SUMMARY,
    MINIMAL_SUMMARY,
    "text",
    undefined,
    null,
    0,
    {},
    [],
    { total_questions: "many", total_marks: null },
    { section_questions: FULL_SUMMARY.section_questions },
  ];
  for (const value of inputs) {
    const out = planSummaryLine(value);
    if (typeof out !== "string") {
      throw new Error(`planSummaryLine(${JSON.stringify(value)}) returned ${typeof out}`);
    }
  }
});

check("asStatusText drops every non-string", () => {
  eq(asStatusText("Reading chapters…"), "Reading chapters…");
  for (const value of [undefined, null, 5, {}, [], FULL_SUMMARY]) {
    eq(asStatusText(value), "", `for ${JSON.stringify(value) ?? "undefined"}:`);
  }
});

if (failures.length) {
  console.error(`\n${failures.length} failed, ${passed} passed\n`);
  for (const failure of failures) console.error(`  ✗ ${failure}`);
  process.exit(1);
}
console.log(`${passed} passed`);
