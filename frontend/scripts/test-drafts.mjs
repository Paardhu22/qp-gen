/**
 * Saved-drafts grouping and retention — `node scripts/test-drafts.mjs`.
 *
 * These back the Saved Drafts strip on the Papers page, which replaced the
 * "Resume previous paper?" modal. The things that must hold:
 *
 *  - One card per draft, not one per set tab. The editor writes a separate
 *    IndexedDB row for each of A/B/C, so a 3-set paper is three rows.
 *  - A saved paper never appears as a draft. It is listed from the backend;
 *    showing it in both places gives the teacher two copies of one paper with
 *    no way to tell which is current.
 *  - Retention runs from the LAST edit to any of a draft's tabs, so touching
 *    Set C keeps the whole draft alive.
 */
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { join } from "node:path";

const dir = mkdtempSync(join(tmpdir(), "drafts-"));
const root = fileURLToPath(new URL("..", import.meta.url));

// `lib/drafts.ts` owns the retention policy and depends only on `paper-id`,
// which is pure — no IndexedDB in the graph. Copy both flat and rewrite the
// `@/` specifier; tsc only honours `--paths` from a tsconfig.
const DAY = 24 * 60 * 60 * 1000;
writeFileSync(
  join(dir, "paper-id.ts"),
  readFileSync(join(root, "lib/paper-id.ts"), "utf8"),
);
writeFileSync(
  join(dir, "drafts.ts"),
  readFileSync(join(root, "lib/drafts.ts"), "utf8")
    .replace(/from ["']@\/lib\/paper-id["']/, 'from "./paper-id"'),
);

execFileSync(
  join(root, "node_modules/.bin/tsc"),
  [
    join(dir, "drafts.ts"),
    join(dir, "paper-id.ts"),
    "--outDir", dir,
    "--module", "esnext",
    "--target", "es2022",
    "--moduleResolution", "bundler",
    "--skipLibCheck",
  ],
  { stdio: "inherit", cwd: root },
);

for (const name of ["drafts", "paper-id"]) {
  renameSync(join(dir, `${name}.js`), join(dir, `${name}.mjs`));
}
const entry = join(dir, "drafts.mjs");
writeFileSync(
  entry,
  readFileSync(entry, "utf8").replace(
    /from ["']\.\/paper-id["']/,
    'from "./paper-id.mjs"',
  ),
);

const { summarizeDrafts, daysUntilExpiry, draftScopeOfDocument, isExpiredDraft } =
  await import(
  `file://${entry}`
  );

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

const USER = "u1";
const NOW = 1_800_000_000_000;

/** One question block worth `marks`. */
function docWith(count, marks) {
  return {
    type: "doc",
    content: [
      {
        type: "page",
        content: Array.from({ length: count }, () => ({
          type: "questionBlock",
          attrs: { marks },
          content: [{ type: "paragraph" }],
        })),
      },
    ],
  };
}

function row(scope, set, overrides = {}) {
  return {
    id: `paper:${USER}:${scope}_${set}`,
    userId: USER,
    paperId: null,
    title: "",
    editorJSON: docWith(3, 2),
    metadata: { title: "Term 1 Science", className: "10", subject: "Science" },
    updatedAt: NOW,
    ...overrides,
  };
}

check("three set rows fold into one draft card", () => {
  const drafts = summarizeDrafts([
    row("draft-abc", "A"),
    row("draft-abc", "B"),
    row("draft-abc", "C"),
  ], { now: NOW });
  eq(drafts.length, 1);
  eq(drafts[0].id, "draft-abc");
  eq(drafts[0].setLabels, ["A", "B", "C"]);
  eq(drafts[0].documentIds.length, 3, "delete must remove every row:");
});

check("counts come from Set A, not the sum of all sets", () => {
  // B and C are variants of the same blueprint. Summing them would report a
  // 3-set 20-mark paper as 60 marks.
  const drafts = summarizeDrafts([
    row("draft-abc", "A", { editorJSON: docWith(5, 4) }),
    row("draft-abc", "B", { editorJSON: docWith(5, 4) }),
  ], { now: NOW });
  eq(drafts[0].questionCount, 5);
  eq(drafts[0].totalMarks, 20);
});

check("Set A's counts win regardless of row order", () => {
  const forward = summarizeDrafts([
    row("d1", "A", { editorJSON: docWith(2, 5) }),
    row("d1", "B", { editorJSON: docWith(9, 9) }),
  ], { now: NOW });
  const reverse = summarizeDrafts([
    row("d1", "B", { editorJSON: docWith(9, 9) }),
    row("d1", "A", { editorJSON: docWith(2, 5) }),
  ], { now: NOW });
  eq(forward[0].questionCount, 2);
  eq(reverse[0].questionCount, 2, "order must not change the counts:");
});

check("separate draft scopes stay separate", () => {
  const drafts = summarizeDrafts([
    row("draft-one", "A", { updatedAt: NOW - 1000 }),
    row("draft-two", "A", { updatedAt: NOW }),
  ], { now: NOW });
  eq(drafts.length, 2);
  eq(drafts.map((d) => d.id), ["draft-two", "draft-one"], "newest first:");
});

check("a saved paper is NOT listed as a draft", () => {
  eq(
    summarizeDrafts([
      row("clx9k2p0000abcd", "A", { paperId: "clx9k2p0000abcd" }),
    ], { now: NOW }).length,
    0,
  );
});

check("legacy `archived:` leftovers are not listed", () => {
  eq(
    summarizeDrafts([
      { ...row("draft-x", "A"), id: `archived:${USER}:12345` },
    ], { now: NOW }).length,
    0,
  );
});

check("the legacy shared `current` scope is still listed", () => {
  const drafts = summarizeDrafts([row("current", "A")], { now: NOW });
  eq(drafts.length, 1);
  eq(drafts[0].id, "current");
});

check("the pre-set-tabs un-suffixed key is listed", () => {
  const drafts = summarizeDrafts([
    { ...row("current", "A"), id: `current:${USER}` },
  ], { now: NOW });
  eq(drafts.length, 1);
  eq(drafts[0].id, "current");
});

check("empty untitled drafts are hidden unless asked for", () => {
  // The editor writes a row the moment it mounts; listing those would fill the
  // strip with blank cards the teacher never created.
  const blank = row("draft-blank", "A", {
    editorJSON: docWith(0, 0),
    metadata: { title: "", className: "", subject: "" },
  });
  eq(summarizeDrafts([blank], { now: NOW }).length, 0);
  eq(summarizeDrafts([blank], { includeEmpty: true, now: NOW }).length, 1);
});

check("an empty draft with a title is kept", () => {
  const named = row("draft-named", "A", {
    editorJSON: docWith(0, 0),
    metadata: { title: "Half-written paper", className: "", subject: "" },
  });
  eq(summarizeDrafts([named], { now: NOW }).length, 1);
});

check("retention runs from the LAST edit to any set", () => {
  // Touching Set C must keep the whole draft alive, not just that tab.
  const drafts = summarizeDrafts([
    row("draft-abc", "A", { updatedAt: NOW - 9 * DAY }),
    row("draft-abc", "C", { updatedAt: NOW }),
  ], { now: NOW });
  eq(drafts[0].updatedAt, NOW);
  eq(drafts[0].expiresAt, NOW + 10 * DAY);
  eq(daysUntilExpiry(drafts[0].expiresAt, NOW), 10);
});

check("days-until-expiry counts down and floors at zero", () => {
  eq(daysUntilExpiry(NOW + 10 * DAY, NOW), 10);
  eq(daysUntilExpiry(NOW + 1 * DAY, NOW), 1);
  eq(daysUntilExpiry(NOW + 1000, NOW), 1, "part of a day still shows as 1:");
  eq(daysUntilExpiry(NOW, NOW), 0);
  eq(daysUntilExpiry(NOW - 5 * DAY, NOW), 0, "an overdue draft never goes negative:");
});

check("another user's documents are never folded in", () => {
  const drafts = summarizeDrafts([
    row("draft-abc", "A"),
    { ...row("draft-abc", "A"), userId: "u2", id: "paper:u2:draft-abc_A" },
  ], { now: NOW });
  // The other user's row has a different id marker, so it cannot merge into u1's
  // draft. It becomes its own entry at worst — never a silent merge.
  for (const draft of drafts) {
    if (draft.documentIds.some((id) => id.startsWith("paper:u2:")) &&
        draft.documentIds.some((id) => id.startsWith("paper:u1:"))) {
      throw new Error("documents from two users merged into one draft");
    }
  }
});

check("draftScopeOfDocument reads the scope out of the id", () => {
  eq(draftScopeOfDocument({ id: `paper:${USER}:draft-abc_B`, userId: USER }), "draft-abc");
  eq(draftScopeOfDocument({ id: `paper:${USER}:draft-abc`, userId: USER }), "draft-abc");
  eq(draftScopeOfDocument({ id: `current:${USER}`, userId: USER }), "current");
  eq(draftScopeOfDocument({ id: "something-else", userId: USER }), null);
});

check("a malformed document does not crash the list", () => {
  const drafts = summarizeDrafts([
    row("draft-ok", "A"),
    row("draft-bad", "A", { editorJSON: { type: "doc", content: "not-an-array" } }),
    row("draft-null", "A", { editorJSON: null, metadata: { title: "Kept" } }),
  ], { now: NOW });
  if (drafts.length < 2) throw new Error("valid drafts were dropped alongside the bad one");
});

// ── Retention: what the 10-day purge is allowed to delete ─────────────────
// This predicate deletes the teacher's only copy of unsaved work. Every case
// below is a thing it must NOT touch.

check("an unsaved draft expires only after the full window", () => {
  eq(isExpiredDraft(row("draft-a", "A", { updatedAt: NOW }), NOW), false);
  eq(isExpiredDraft(row("draft-a", "A", { updatedAt: NOW - 9 * DAY }), NOW), false);
  eq(
    isExpiredDraft(row("draft-a", "A", { updatedAt: NOW - 10 * DAY - 1 }), NOW),
    true,
  );
});

check("the boundary is exactly the window, not a day either side", () => {
  // At exactly 10 days the draft has had its 10 days and goes. The card agrees:
  // `daysUntilExpiry` reads 0 there, which the UI renders "Deletes today".
  const exactly = row("draft-a", "A", { updatedAt: NOW - 10 * DAY });
  eq(isExpiredDraft(exactly, NOW), true, "exactly 10 days:");
  eq(daysUntilExpiry(exactly.updatedAt + 10 * DAY, NOW), 0, "card agrees:");
  eq(
    isExpiredDraft({ ...exactly, updatedAt: NOW - 10 * DAY + 1 }, NOW),
    false,
    "a millisecond inside 10 days:",
  );
});

check("a SAVED paper's local cache is never purged, however old", () => {
  // It may hold edits that have not synced, and the server copy is not ours to
  // second-guess. This is the case that would silently lose real work.
  for (const age of [11, 100, 5000]) {
    eq(
      isExpiredDraft(
        row("clx9k2p0000abcd", "A", {
          paperId: "clx9k2p0000abcd",
          updatedAt: NOW - age * DAY,
        }),
        NOW,
      ),
      false,
      `${age} days old:`,
    );
  }
});

check("legacy `archived:` leftovers do expire", () => {
  const archived = {
    ...row("draft-x", "A"),
    id: `archived:${USER}:12345`,
    updatedAt: NOW - 11 * DAY,
  };
  eq(isExpiredDraft(archived, NOW), true);
  // …but not before the window is up.
  eq(isExpiredDraft({ ...archived, updatedAt: NOW }, NOW), false);
});

check("the legacy shared `current` scope expires like any draft", () => {
  eq(
    isExpiredDraft(
      { ...row("current", "A"), paperId: "current", updatedAt: NOW - 11 * DAY },
      NOW,
    ),
    true,
  );
  eq(
    isExpiredDraft(
      { ...row("current", "A"), paperId: "current", updatedAt: NOW },
      NOW,
    ),
    false,
  );
});

check("a listed draft and an expired draft are mutually exclusive", () => {
  // Whatever the strip shows must survive the purge that runs beside it — the
  // Papers page purges first, then lists, and a card that appears only to be
  // deleted on refresh is worse than not showing it.
  const ages = [0, 1, 5, 9, 10, 11, 30];
  for (const age of ages) {
    const document = row("draft-a", "A", { updatedAt: NOW - age * DAY });
    const listed = summarizeDrafts([document], { now: NOW }).length > 0;
    const expired = isExpiredDraft(document, NOW);
    if (listed && expired) {
      throw new Error(`a ${age}-day-old draft is both listed and expired`);
    }
  }
});

if (failures.length > 0) {
  console.error(`\n${failures.length} failed, ${passed} passed\n`);
  for (const f of failures) console.error(`  ✗ ${f}`);
  process.exit(1);
}
console.log(`✓ ${passed} passed`);
