/**
 * Paper-id / set-suffix checks — run with `node scripts/test-paper-id.mjs`.
 *
 * The regression this guards: the editor composes "{base}_{A|B|C}" per set
 * tab, and that composed id used to be written back into the live document's
 * `paperId`, which the resume flow puts into `?paperId=`. Each visit added a
 * suffix ("current_A" -> "current_A_A") until autosave PUT a row that never
 * existed and the editor logged "Paper not found" on every keystroke.
 */
import { execFileSync } from "node:child_process";
import { mkdtempSync, renameSync } from "node:fs";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { join } from "node:path";

const dir = mkdtempSync(join(tmpdir(), "pid-"));
const sourcePath = fileURLToPath(new URL("../lib/paper-id.ts", import.meta.url));
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
const file = join(dir, "paper-id.mjs");
renameSync(join(dir, "paper-id.js"), file);

const {
  splitPaperId,
  basePaperId,
  withSetSuffix,
  isDraftPaperId,
  isLocalDraftId,
  newLocalDraftId,
  persistablePaperId,
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

check("splits a composed draft id", () => {
  eq(splitPaperId("current_A"), { base: "current", set: "A" });
  eq(splitPaperId("current_B"), { base: "current", set: "B" });
});

check("splits a composed backend id", () => {
  eq(splitPaperId("clx9k2p0000abcd_C"), { base: "clx9k2p0000abcd", set: "C" });
});

check("leaves an unsuffixed id alone", () => {
  eq(splitPaperId("clx9k2p0000abcd"), { base: "clx9k2p0000abcd", set: null });
  eq(splitPaperId("current"), { base: "current", set: null });
});

check("heals an id that already compounded suffixes", () => {
  // The exact shape seen in production before the fix.
  eq(splitPaperId("current_A_A_A"), { base: "current", set: "A" });
  eq(basePaperId("clx9k2p0000abcd_A_B"), "clx9k2p0000abcd");
});

check("reports the outermost set, not the innermost", () => {
  // "…_A_B" was last composed for tab B.
  eq(splitPaperId("current_A_B").set, "B");
});

check("handles null and empty ids", () => {
  eq(splitPaperId(null), { base: null, set: null });
  eq(splitPaperId(""), { base: null, set: null });
  eq(basePaperId(undefined), null);
});

check("composing is idempotent", () => {
  eq(withSetSuffix("current", "A"), "current_A");
  eq(withSetSuffix("current_A", "A"), "current_A");
  eq(withSetSuffix("current_A_A_A", "B"), "current_B");
  eq(withSetSuffix(null, "A"), "current_A");
});

check("lowercase suffixes are not treated as set labels", () => {
  // Only A/B/C uppercase is the tab discriminator; a cuid ending in "_a" is
  // a real id and must survive intact.
  eq(basePaperId("some_paper_a"), "some_paper_a");
  eq(basePaperId("some_paper_D"), "some_paper_D");
});

check("identifies local drafts in both forms", () => {
  eq(isDraftPaperId("current"), true);
  eq(isDraftPaperId("current_B"), true);
  eq(isDraftPaperId("current_A_A"), true);
  eq(isDraftPaperId(null), true);
  eq(isDraftPaperId("clx9k2p0000abcd_A"), false);
});

check("persistable id is null for drafts, base for real rows", () => {
  eq(persistablePaperId("current_A"), null);
  eq(persistablePaperId("current"), null);
  eq(persistablePaperId(null), null);
  eq(persistablePaperId("clx9k2p0000abcd_A"), "clx9k2p0000abcd");
  eq(persistablePaperId("clx9k2p0000abcd"), "clx9k2p0000abcd");
});

check("round trip never grows the id", () => {
  // Simulates the resume loop: store -> URL -> compose -> store …
  let stored = persistablePaperId("clx9k2p0000abcd_A");
  for (let i = 0; i < 5; i++) {
    const url = basePaperId(stored) ?? "current";
    const composed = withSetSuffix(url, "A");
    stored = persistablePaperId(composed);
  }
  eq(stored, "clx9k2p0000abcd");
});

// ── Per-draft local ids ────────────────────────────────────────────────────
// Unsaved papers used to share the single `current` scope, so there was only
// ever one unsaved draft: starting a new paper had to destroy the previous one.
// These ids give each draft its own scope so they can be listed side by side.

check("minted draft ids are local, unique, and never persisted", () => {
  const a = newLocalDraftId();
  const b = newLocalDraftId();
  if (a === b) throw new Error(`ids collided: ${a}`);
  for (const id of [a, b]) {
    eq(isLocalDraftId(id), true, `isLocalDraftId(${id}):`);
    eq(isDraftPaperId(id), true, `isDraftPaperId(${id}):`);
    eq(persistablePaperId(id), null, `persistablePaperId(${id}):`);
  }
});

check("a minted id survives the set-suffix round trip intact", () => {
  // The id must not contain anything `splitPaperId` would chew into — a
  // trailing `_A`-looking tail would silently truncate the draft's scope and
  // point the editor at a different draft.
  const id = newLocalDraftId();
  for (const set of ["A", "B", "C"]) {
    eq(basePaperId(withSetSuffix(id, set)), id, `set ${set}:`);
    eq(splitPaperId(withSetSuffix(id, set)).set, set, `set ${set}:`);
  }
  eq(persistablePaperId(withSetSuffix(id, "B")), null);
});

check("minted ids contain no underscore", () => {
  for (let i = 0; i < 200; i++) {
    const id = newLocalDraftId();
    if (id.includes("_")) throw new Error(`minted id has an underscore: ${id}`);
  }
});

check("the legacy sentinel and real rows are still classified correctly", () => {
  eq(isLocalDraftId("current"), false, "legacy `current` is not a per-draft id:");
  eq(isLocalDraftId("clx9k2p0000abcd"), false);
  eq(isLocalDraftId(null), false);
  // A real backend cuid must never be mistaken for a draft, or it stops syncing.
  eq(isDraftPaperId("clx9k2p0000abcd"), false);
  eq(persistablePaperId("clx9k2p0000abcd"), "clx9k2p0000abcd");
});

check("draft ids are recognised through a composed, doubled suffix", () => {
  const id = newLocalDraftId();
  eq(isDraftPaperId(`${id}_A_A`), true);
  eq(persistablePaperId(`${id}_A_A`), null);
});

if (failures.length > 0) {
  console.error(`\n${failures.length} failed, ${passed} passed\n`);
  for (const f of failures) console.error(`  ✗ ${f}`);
  process.exit(1);
}
console.log(`\n✓ ${passed} passed\n`);
