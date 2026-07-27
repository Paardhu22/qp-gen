/**
 * Editor set-tab content resolution — run with `node scripts/test-set-content.mjs`.
 *
 * The regressions this guards, both reported from the dashboard flow:
 *
 *  1. "I can't see the paper's contents at all." A generation done outside the
 *     review workspace only STAGED its sets (`comparisonSets`). Tab A reads
 *     approvals first and staged sets only for B/C, so Set A — the whole paper
 *     for a single-set request — never reached the document.
 *
 *  2. "I'm seeing the previous paper's contents." With tab A resolving to
 *     `undefined`/`""`, the editor was free to rehydrate that tab's IndexedDB
 *     draft, which is the paper the teacher had open before.
 *
 * The fix is `adoptGeneratedSets` in the store: a generation that happens
 * outside the review workspace approves itself, so it lands in `approvedSets`
 * — the only source `resolveTabContent` consults for tab A.
 */
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { join } from "node:path";

const dir = mkdtempSync(join(tmpdir(), "setc-"));
const root = fileURLToPath(new URL("..", import.meta.url));

// `lib/set-content.ts` pulls `normalizeSetLabel` from the editor store, which
// drags in zustand + persist + localStorage. Copy the source next to a stub of
// just that one export and rewrite the `@/` specifier — tsc takes `--paths`
// only from a tsconfig, and the store's own shape is not what is under test.
// The stub is kept byte-identical to the real implementation on purpose.
const STUB = `export function normalizeSetLabel(label: string): string {
  return label.replace(/^Set\\s+/i, "").trim() || label;
}\n`;
const real = readFileSync(join(root, "store/editor-store.ts"), "utf8");
const realBody = real.slice(
  real.indexOf("export function normalizeSetLabel"),
  real.indexOf("}", real.indexOf("export function normalizeSetLabel")) + 2,
);
if (realBody.replace(/\s+/g, "") !== STUB.replace(/\s+/g, "")) {
  console.error("normalizeSetLabel has changed — update the stub in this test:");
  console.error(realBody);
  process.exit(1);
}
writeFileSync(join(dir, "editor-store.ts"), STUB);
writeFileSync(
  join(dir, "set-content.ts"),
  readFileSync(join(root, "lib/set-content.ts"), "utf8").replace(
    /from ["']@\/store\/editor-store["']/,
    'from "./editor-store"',
  ),
);

execFileSync(
  join(root, "node_modules/.bin/tsc"),
  [
    join(dir, "set-content.ts"),
    join(dir, "editor-store.ts"),
    "--outDir", dir,
    "--module", "esnext",
    "--target", "es2022",
    "--moduleResolution", "bundler",
    "--skipLibCheck",
  ],
  { stdio: "inherit", cwd: root },
);

const file = join(dir, "set-content.mjs");
renameSync(join(dir, "set-content.js"), file);
renameSync(join(dir, "editor-store.js"), join(dir, "editor-store.mjs"));
writeFileSync(
  file,
  readFileSync(file, "utf8").replace(
    /from ["']\.\/editor-store["']/,
    'from "./editor-store.mjs"',
  ),
);

const { resolveTabContent } = await import(`file://${file}`);

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

const PAPER_A = { sections: [{ title: "SECTION A", questions: [{ marks: 1 }] }] };
const PAPER_B = { sections: [{ title: "SECTION A", questions: [{ marks: 2 }] }] };

const base = {
  activeSetTab: "A",
  approvedSets: {},
  comparisonSets: [],
  loadedSets: [],
  paperContent: undefined,
};

check("SYMPTOM 1 — a single approved set fills tab A", () => {
  eq(
    resolveTabContent({ ...base, approvedSets: { A: PAPER_A } }),
    JSON.stringify(PAPER_A),
  );
});

check("SYMPTOM 1 — staging alone still leaves tab A undecided", () => {
  // This is the pre-fix dashboard state, kept as an explicit record of WHY
  // `adoptGeneratedSets` approves rather than merely staging.
  eq(
    resolveTabContent({ ...base, comparisonSets: [{ label: "A", result: PAPER_A }] }),
    undefined,
  );
});

check("SYMPTOM 2 — an approved tab A never falls through to the draft", () => {
  // `paperContent: undefined` is what let the IndexedDB draft (the previous
  // paper) win. An approval must return content, not undefined.
  const out = resolveTabContent({
    ...base,
    approvedSets: { A: PAPER_A },
    paperContent: undefined,
  });
  if (out === undefined) throw new Error("tab A resolved to undefined despite an approval");
  eq(out, JSON.stringify(PAPER_A));
});

check("approvals win over a saved paper's own content", () => {
  eq(
    resolveTabContent({
      ...base,
      approvedSets: { A: PAPER_A },
      paperContent: "{\"old\":true}",
    }),
    JSON.stringify(PAPER_A),
  );
});

check("every tab of a multi-set approval resolves", () => {
  const approvedSets = { A: PAPER_A, B: PAPER_B, C: PAPER_A };
  for (const tab of ["A", "B", "C"]) {
    const out = resolveTabContent({ ...base, activeSetTab: tab, approvedSets });
    if (out === undefined) throw new Error(`tab ${tab} resolved to undefined`);
  }
});

check("'Set A' style labels normalise to the tab letter", () => {
  // `approveComparisonSets` keys by the NORMALISED label; a raw "Set A" key
  // would silently miss the "A" lookup and drop the tab to its draft.
  eq(
    resolveTabContent({
      ...base,
      activeSetTab: "B",
      comparisonSets: [{ label: "Set B", result: PAPER_B }],
    }),
    JSON.stringify(PAPER_B),
  );
});

check("tab A ignores a stale unapproved generation on a saved paper", () => {
  // The gate that makes this work: comparisonSets is persisted, so a generation
  // the teacher never approved outlives the page. Opening a saved paper must
  // still show that paper.
  eq(
    resolveTabContent({
      ...base,
      comparisonSets: [{ label: "A", result: PAPER_A }],
      loadedSets: [{ label: "A", content: "saved-a" }],
      paperContent: "saved-a",
    }),
    "saved-a",
  );
});

check("tabs B/C of a saved paper come from its own rows", () => {
  eq(
    resolveTabContent({
      ...base,
      activeSetTab: "B",
      loadedSets: [{ label: "B", content: "saved-b" }],
      paperContent: "saved-a",
    }),
    "saved-b",
  );
});

check("an unknown tab falls back to the paper's content", () => {
  eq(
    resolveTabContent({ ...base, activeSetTab: "C", loadedSets: [], paperContent: "saved-a" }),
    "saved-a",
  );
});

check("an empty-string paper stays empty, not undefined", () => {
  // "" means "blank document"; undefined means "let the draft decide". The
  // editor treats them differently, so the helper must not conflate them.
  eq(resolveTabContent({ ...base, paperContent: "" }), "");
});

check("an already-serialised approved set is passed through, not double-encoded", () => {
  eq(
    resolveTabContent({ ...base, approvedSets: { A: '{"sections":[]}' } }),
    '{"sections":[]}',
  );
});

if (failures.length) {
  console.error(`\n${failures.length} failed, ${passed} passed\n`);
  for (const failure of failures) console.error(`  ✗ ${failure}`);
  process.exit(1);
}
console.log(`✓ ${passed} passed`);
