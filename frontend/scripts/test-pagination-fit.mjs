/**
 * Page-fit arithmetic checks — run with `node scripts/test-pagination-fit.mjs`.
 *
 * The regression these guard: the engine decided whether a block could be
 * pulled up from the next page by computing free space as
 * `usableHeight − contentSpan`. A span is measured from the first block's
 * border-box top, so any margin ABOVE the first block is invisible to it —
 * and `.section-block` / `.instruction-block` each carry 10px. On any page
 * opening with one of those, the derivation claimed 10px more room than
 * existed. The engine pulled a block into it, the page overflowed, the split
 * rule pushed the block straight back, and the two rules ping-ponged until the
 * 400-pass ceiling stopped pagination — leaving the document half laid out
 * with pages ending early. That is the "lots of blank space after every
 * section" symptom.
 */
import { execFileSync } from "node:child_process";
import { mkdtempSync, renameSync } from "node:fs";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { join } from "node:path";

const dir = mkdtempSync(join(tmpdir(), "pfit-"));
const sourcePath = fileURLToPath(
  new URL("../components/editor/extensions/pagination-fit.ts", import.meta.url),
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
const file = join(dir, "pagination-fit.mjs");
renameSync(join(dir, "pagination-fit.js"), file);

const { FIT_TOLERANCE, canPullUp, overflowAfterPull, derivedFreeSpace } =
  await import(`file://${file}`);

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
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`${what} expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

// Real values from styles/editor.css and the A4 page geometry.
const USABLE = 1017;      // 1121 page content height − 48 top − 56 bottom padding
const SECTION_MARGIN = 10; // .section-block  { margin: 10px 0 2px }
const QUESTION_MARGIN = 4; // .question-block { margin: 4px 0 }

// ── The invariant ───────────────────────────────────────────────────────

check("a run the engine agrees to pull up never overflows", () => {
  // Exhaustive over a realistic space: if canPullUp says yes, the page must
  // still fit afterwards. This is the property whose violation caused the
  // ping-pong.
  for (let free = 0; free <= 400; free += 7) {
    for (let joinGap = 0; joinGap <= 20; joinGap += 2) {
      for (let runHeight = 0; runHeight <= 400; runHeight += 11) {
        const m = { free, joinGap, runHeight };
        if (canPullUp(m) && overflowAfterPull(m) > 0) {
          throw new Error(
            `pulled up but overflowed by ${overflowAfterPull(m)}px: ${JSON.stringify(m)}`,
          );
        }
      }
    }
  }
});

check("it leaves exactly FIT_TOLERANCE of slack at the boundary", () => {
  const free = 100;
  const runHeight = free - QUESTION_MARGIN - FIT_TOLERANCE;
  eq(canPullUp({ free, joinGap: QUESTION_MARGIN, runHeight }), true, "at limit");
  eq(
    canPullUp({ free, joinGap: QUESTION_MARGIN, runHeight: runHeight + 1 }),
    false,
    "one px over",
  );
});

// ── The bug, reproduced ─────────────────────────────────────────────────

check("the old derivation overstates free space by the leading margin", () => {
  // A page whose first block is a section heading. Content spans 900px from
  // the heading's border-box top; the heading's own 10px top margin sits above
  // that and is part of the page's used height.
  const contentSpan = 900;
  const trueFree = USABLE - SECTION_MARGIN - contentSpan; // 107
  const derived = derivedFreeSpace({ usableHeight: USABLE, contentSpan }); // 117

  eq(derived - trueFree, SECTION_MARGIN, "overstatement");

  // A question that fits under the derived figure but not the real one. The
  // window is `trueFree − joinGap < runHeight <= derived − joinGap − tolerance`
  // — i.e. 103 < h <= 109 here, so the 10px overstatement beats the 4px
  // tolerance by 6px and lands the block past the page bottom.
  const runHeight = 105;
  const joinGap = QUESTION_MARGIN;
  eq(
    canPullUp({ free: derived, joinGap, runHeight }),
    true,
    "old rule pulls it up",
  );
  eq(
    overflowAfterPull({ free: trueFree, joinGap, runHeight }) > 0,
    true,
    "…and it overflows, so the split rule sends it back — the ping-pong",
  );
  // The fixed engine measures trueFree and declines.
  eq(canPullUp({ free: trueFree, joinGap, runHeight }), false, "new rule declines");
});

check("pages of plain questions were never affected", () => {
  // No leading section margin, so the derivation and the measurement agree —
  // which is why the bug looked section-specific.
  const contentSpan = 900;
  const trueFree = USABLE - QUESTION_MARGIN - contentSpan;
  const derived = derivedFreeSpace({ usableHeight: USABLE, contentSpan });
  eq(derived - trueFree, QUESTION_MARGIN, "small overstatement");
  eq(derived - trueFree < FIT_TOLERANCE + 1, true, "within tolerance");
});

// ── Ordinary behaviour still holds ──────────────────────────────────────

check("a block comfortably smaller than the gap moves up", () => {
  eq(canPullUp({ free: 300, joinGap: 4, runHeight: 120 }), true);
});

check("a block larger than the gap stays put", () => {
  eq(canPullUp({ free: 120, joinGap: 4, runHeight: 300 }), false);
});

check("a full page has no room for anything", () => {
  eq(canPullUp({ free: 0, joinGap: 0, runHeight: 0 }), false);
  eq(canPullUp({ free: 3, joinGap: 0, runHeight: 0 }), false);
  eq(canPullUp({ free: 4, joinGap: 0, runHeight: 0 }), true);
});

check("a heading's larger join gap is charged for", () => {
  // Same run height, but arriving as a section heading costs 10px not 4px.
  const free = 100;
  const runHeight = 90;
  eq(canPullUp({ free, joinGap: QUESTION_MARGIN, runHeight }), true, "as question");
  eq(canPullUp({ free, joinGap: SECTION_MARGIN, runHeight }), false, "as heading");
});

if (failures.length > 0) {
  console.error(`\n${failures.length} failed, ${passed} passed\n`);
  for (const f of failures) console.error(`  ✗ ${f}`);
  process.exit(1);
}
console.log(`\n✓ ${passed} passed\n`);
