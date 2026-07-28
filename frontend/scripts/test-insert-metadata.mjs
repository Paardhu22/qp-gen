/**
 * Insert-path metadata guard — run with `node scripts/test-insert-metadata.mjs`.
 *
 * Why this exists
 * ---------------
 * `buildQuestionBlocks` splits a composite question (an unseen reading passage,
 * a grammar task set) into a run of sibling blocks by reading
 * `metadata.composite`. The pagination engine breaks a page only *between*
 * top-level blocks, so a passage that arrives as ONE block has no seam to break
 * at and is clipped at the page edge.
 *
 * That whole mechanism is reached only if `metadata` survives the trip from the
 * SSE payload into the editor store. It did not: `Question` had no `metadata`
 * field and every insert path built its payload field-by-field, silently
 * dropping it. `buildQuestionBlocks` was thoroughly unit-tested and still
 * effectively dead code in production — every English paper rendered as pages
 * of empty placeholder lines.
 *
 * Unit tests on `question-nodes.ts` cannot catch that, because the bug is in
 * the *callers*. This checks the callers: any object literal that looks like a
 * question payload handed to the editor store must carry `metadata`.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

/** Files that build question payloads for `appendQuestions`/`appendSections`. */
const INSERT_PATHS = [
  "../components/review-tray.tsx",
  "../components/generator-form.tsx",
  "../app/(dashboard)/build-paper/page.tsx",
  "../app/(dashboard)/paper-library/page.tsx",
  "../app/(dashboard)/editor/page.tsx",
];

/** Every balanced `{...}` region in `source`, with its start offset. */
function objectLiterals(source) {
  const out = [];
  for (let i = 0; i < source.length; i += 1) {
    if (source[i] !== "{") continue;
    let depth = 0;
    for (let j = i; j < source.length; j += 1) {
      if (source[j] === "{") depth += 1;
      else if (source[j] === "}") {
        depth -= 1;
        if (depth === 0) {
          out.push({ start: i, text: source.slice(i, j + 1) });
          break;
        }
      }
    }
  }
  return out;
}

/**
 * A question payload is an object literal carrying both the question text and
 * its mark value. The size bound keeps whole function bodies (which also
 * mention `content:` and `marks:` somewhere inside) out of the match.
 */
function isQuestionPayload(text) {
  return (
    hasKey(text, "content") && hasKey(text, "marks") && text.length < 900
  );
}

/**
 * Does this literal declare `key`?
 *
 * The `?` is optional so the same check works on a value literal
 * (`metadata: q.metadata`) and on the TypeScript type that describes it
 * (`metadata?: Record<string, any>`). Both matter: a payload cannot forward a
 * field its own type does not admit, which is exactly how the paper-library
 * insert path came to need an `as any` cast.
 */
function hasKey(text, key) {
  return new RegExp(`(^|[\\s{,])${key}\\s*\\??\\s*:`).test(text);
}

const failures = [];
let checked = 0;

for (const relative of INSERT_PATHS) {
  const path = fileURLToPath(new URL(relative, import.meta.url));
  const source = readFileSync(path, "utf8");

  for (const { start, text } of objectLiterals(source)) {
    if (!isQuestionPayload(text)) continue;
    checked += 1;
    if (hasKey(text, "metadata")) continue;

    const line = source.slice(0, start).split("\n").length;
    failures.push(
      `${relative}:${line} builds a question payload without \`metadata\`.\n` +
        "    A composite question (reading passage / grammar set) inserted through\n" +
        "    this path will collapse into one unbreakable block and be clipped at\n" +
        "    the page edge. Forward `metadata` — see `Question.metadata` in\n" +
        "    store/editor-store.ts.\n" +
        `    ${text.replace(/\s+/g, " ").slice(0, 160)}…`,
    );
  }
}

if (checked === 0) {
  console.error(
    "✗ matched no question payloads at all — the detection heuristic has " +
      "drifted from the source and this guard is no longer testing anything.",
  );
  process.exit(1);
}

if (failures.length > 0) {
  console.error(`\n${failures.length} insert path(s) drop question metadata\n`);
  failures.forEach((f) => console.error(`  ✗ ${f}\n`));
  process.exit(1);
}

console.log(`✓ all ${checked} question payload(s) forward metadata`);
