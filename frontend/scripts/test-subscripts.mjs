#!/usr/bin/env node
// Indexed variables as maths — run from frontend/:  node scripts/test-subscripts.mjs
//
// The twin of backend/services/generation/rules/tests/test_subscripts.py. Both
// read the SAME hand-written case table, so the two implementations cannot
// drift apart: a case added for one is a case for the other.

import { fileURLToPath } from "node:url";
import { readFileSync } from "node:fs";
import path from "node:path";
import { createJiti } from "jiti";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const jiti = createJiti(here, { interopDefault: true, alias: { "@": root } });
const { typesetIndices, policyFor } = await jiti.import(path.join(root, "features/editor/subscripts.ts"));

const CASES = JSON.parse(
  readFileSync(path.resolve(root, "../backend/services/generation/rules/tests/subscript_cases.json"), "utf8"),
);

let failures = 0;
function check(label, condition, detail = "") {
  if (condition) console.log(`PASS  ${label}`);
  else {
    failures += 1;
    console.error(`FAIL  ${label}${detail ? ` — ${detail}` : ""}`);
  }
}

// ── The shared case table ───────────────────────────────────────────────
let mismatches = 0;
for (const c of CASES) {
  const got = typesetIndices(c.text, c.subject);
  if (got !== c.expected) {
    mismatches += 1;
    console.error(`FAIL  [${c.group}/${c.subject || "-"}] ${JSON.stringify(c.text)}\n        want ${JSON.stringify(c.expected)}\n        got  ${JSON.stringify(got)}`);
  }
}
failures += mismatches;
if (!mismatches) console.log(`PASS  all ${CASES.length} cases in the shared table agree with the backend`);

// ── Idempotence and balance ─────────────────────────────────────────────
check(
  "running twice changes nothing",
  CASES.every((c) => {
    const once = typesetIndices(c.text, c.subject);
    return typesetIndices(once, c.subject) === once;
  }),
);
check(
  "text already typeset is left alone",
  CASES.every((c) => typesetIndices(c.expected, c.subject) === c.expected),
);
check(
  "every output has balanced maths delimiters",
  CASES.every((c) => {
    const out = typesetIndices(c.text, c.subject);
    const count = (s) => out.split(s).length - 1;
    return count("\\(") === count("\\)") && count("\\[") === count("\\]");
  }),
);
check(
  "existing maths spans survive byte for byte",
  (() => {
    const out = typesetIndices("Given \\(x1 + y2 = 3\\) and \\[ a1 b2 \\] find x1, x2.", "Mathematics");
    return out.includes("\\(x1 + y2 = 3\\)") && out.includes("\\[ a1 b2 \\]");
  })(),
);

// ── Subject policy: the same table as the backend ───────────────────────
const POLICY = {
  Mathematics: "maths", "Mathematics Standard": "maths", "Applied Mathematics": "maths", Maths: "maths", Statistics: "maths",
  Science: "science", Physics: "science", Chemistry: "science", Biology: "science",
  "Social Science": "off", English: "off", "English Language & Literature": "off", "Hindi Course B": "off",
  Telugu: "off", Sanskrit: "off", "Computer Science": "off", ICT: "off",
  "": "default", "Something New": "default",
};
for (const [subject, name] of Object.entries(POLICY)) {
  check(`policy for ${JSON.stringify(subject)} is ${name}`, policyFor(subject).name === name, policyFor(subject).name);
}
check("a missing subject is the cautious default", policyFor(undefined).name === "default" && policyFor(null).name === "default");
check("an unknown subject never subscripts a capital", typesetIndices("Points P1 and P2.", "") === "Points P1 and P2.");

// ── Edges ───────────────────────────────────────────────────────────────
check("empty input passes through", typesetIndices("") === "" && typesetIndices(undefined) === undefined);
check("unicode subscripts are left as they are", typesetIndices("x₁ and H₂O", "Mathematics") === "x₁ and H₂O");
check(
  "a long text is not slow",
  (() => {
    const text = "The points x1 and x2, (y1, y2) and 20 m2. ".repeat(2000) + "A1 B2 ".repeat(2000);
    const start = Date.now();
    const out = typesetIndices(text, "Mathematics");
    return out.includes("\\(x_{1}\\)") && Date.now() - start < 3000;
  })(),
);

if (failures) {
  console.error(`\n${failures} check(s) failed`);
  process.exit(1);
}
console.log("\nAll subscript checks passed");
