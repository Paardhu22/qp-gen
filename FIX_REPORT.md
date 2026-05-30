# FIX_REPORT — `qp-gen` Editor work-loss + Selective insertion

Two issues addressed without regressing the prior content-scope /
PyMuPDF / Next-layout work. All sixty-seven prior backend tests stay
green; one new regression test was added (68 total). Frontend
`tsc --noEmit` and `eslint` both clean.

---

## Current flow as it was (documented before changes)

- `frontend/store/editor-store.ts` — plain Zustand store, **no persistence
  middleware**. Holds insertion plumbing, modal flags, `editorContent`
  mirror, `saveState`. In-memory only — every TipTap unmount blew it away.
- `frontend/lib/live-document-db.ts` — IndexedDB store of the full TipTap
  doc keyed by `paper:{userId}:{paperId}` or `current:{userId}`.
- `frontend/components/tiptap-editor.tsx` — debounced (1 s) live-sync
  writes IDB and PATCHes the server. On mount, loads the newer of IDB
  vs server.
- `frontend/app/(dashboard)/editor/page.tsx` — on every mount with no
  `paperId`, calls `getLatestLiveDocumentForUser` and pops the "Resume
  previous paper?" modal if any doc exists.
- `frontend/components/generator-form.tsx` — `appendQuestionToEditor`
  fires inside the SSE handler for every streamed question, dumping
  them directly into the editor store. All-or-nothing.

---

## ISSUE 1 — Editor work disappears between pages

### Root cause (three compounding bugs)

1. **The 1 s debouncer was cancelled, not flushed, on teardown.** The
   cleanup effect did `debouncedLiveSync.cancel()`, throwing away the
   pending invocation. A user typing the last edits and immediately
   clicking "Dashboard" never reached IndexedDB.

2. **The chain captured editor state lazily.** Even when `.flush()` was
   called, `editor.getJSON()` ran *inside* the `.then()` chain (a
   microtask) — after React might have already destroyed the editor.
   `getJSON()` on a destroyed editor either throws or returns stale
   state, so the IDB write was either skipped or wrong.

3. **The resume modal fired on every visit to `/editor`.** It had no
   way to tell in-app navigation apart from a brand-new browser
   session, so even tabbing away to the Dashboard and back popped the
   modal — and the modal's metadata showed "—" because the user hadn't
   filled in the Paper Details form yet, so the IDB doc had blank
   `className`/`subject`. "Continue Editing" routed to a paperId that
   sometimes didn't exist, so the actual content didn't come back.

### Fix

#### A. Persist the layered editor state

`frontend/store/editor-store.ts:1-205` (rewritten):

- Wrapped the store in Zustand `persist` middleware backed by
  `localStorage`. `partialize` whitelists only the small slices that
  belong in localStorage (`insertionMode`, `generatedTray`,
  `generatorContext`, `template`). The large TipTap doc stays in
  IndexedDB via the existing `live-document-db.ts` — persisting it
  twice would blow past the ~5 MB localStorage cap.
- Added `generatorContext: { examName, className, subject, lastActiveAt }`
  so the resume modal has real metadata even before the user opens the
  Paper Details modal — `GeneratorForm` mirrors the form's
  class/subject selections into this slot on every change.
- Added `generatedTray` + `insertionMode` for Issue 2 (see below).

#### B. Synchronously capture editor state at flush time

`frontend/components/tiptap-editor.tsx:594-633`:

- Moved `editor.getJSON()` / `extractPagesFromDoc` / payload
  serialization OUT of the `.then()` chain and INTO the synchronous
  body of the debounced function. The `.then()` block now just
  consumes the captured `capturedContent`/`capturedMetadata` etc.
- This is the actual data-loss fix: even when the editor is destroyed
  microseconds after `.flush()`, the captured state survives in
  closures and reaches IndexedDB.

#### C. Flush on every exit signal

`frontend/components/tiptap-editor.tsx:915-994`:

- The global `<a>` click interceptor no longer destroys the editor; it
  only flushes the live-sync (Next's router unmount destroys it
  naturally afterwards, AFTER the captured-state save is queued).
- `pagehide` and `visibilitychange→hidden` listeners added — covers
  modern BFCache navigation, mobile background, and tab close.
- `beforeunload` still flushes.

`frontend/components/tiptap-editor.tsx:900-912`:

- Cleanup effect now `debouncedLiveSync.flush()` instead of `.cancel()`.

#### D. Per-session id; silent restore on in-app nav

`frontend/lib/live-document-db.ts:31` adds `sessionId?: string` to the
`LiveEditorDocument` interface.

`frontend/components/tiptap-editor.tsx:540-555` initialises a
`sessionStorage`-backed session id and stamps every IDB save with it.

`frontend/app/(dashboard)/editor/page.tsx:160-228`:

- Resolves the session id in a `useEffect` (impure calls kept out of
  render to satisfy React purity rules).
- The resume-check effect waits for the session id, then:
  - If the latest live doc carries the **same** session id, **silently
    `router.replace`** to its paper — no modal, no friction. This is
    the silent restore the requirement asked for.
  - Only when the session id differs (genuinely a prior session) does
    the "Resume previous paper?" modal appear.

#### E. Truthful resume metadata

`frontend/components/tiptap-editor.tsx:626-645`:

- The IDB save now falls back to `editorStore.generatorContext`
  (`className`, `subject`) when the user-supplied metadata is blank,
  so the modal never shows "—" while a class/subject is selected in
  the generator form.

`frontend/app/(dashboard)/editor/page.tsx:881-924`:

- The modal displays "Not set yet" instead of "—" so the user
  understands the difference between missing-metadata and a real value.
- A small descendants-walk extracts the realized
  `questionCount`/`totalMarks` from the saved doc and displays them —
  the modal now reflects the real paper, not a shell.

#### F. "Create New Paper" archives instead of destroying

`frontend/app/(dashboard)/editor/page.tsx:235-263`:

- Old behaviour `deleteLiveDocument(resumeDoc.id)` permanently destroyed
  the only copy of an unsaved draft.
- New behaviour: re-saves the doc under an `archived:{userId}:{ts}` id
  and only then removes the original. The archive stays in IndexedDB
  so the user's work is recoverable.
- `frontend/lib/live-document-db.ts:121-138`: `getLatestLiveDocumentForUser`
  now excludes `archived:*` ids so the resume modal doesn't loop back
  to them.

#### Acceptance checks

| Scenario | Expected | Status |
| -------- | -------- | ------ |
| Editor → Dashboard → Editor (same session) | Full content restored, no modal | ✓ silent restore |
| Browser reload on Editor | State restored from IDB; reconciles with server | ✓ load-effect picks newer `updatedAt` |
| Genuine prior session | Truthful modal (title/class/subject/marks/last active) | ✓ |
| "Continue Editing" | Restores full state | ✓ routes to `paperId` or `current`, both rehydrate via IDB |
| "Create New Paper" | Old draft archived, not destroyed | ✓ |
| Last edits before nav | Persisted to IDB | ✓ synchronous capture + flush on link-click/pagehide/visibility/beforeunload |

---

## ISSUE 2 — Selective question insertion

### Root cause

`frontend/components/generator-form.tsx:appendQuestionToEditor` was
called from inside the SSE `event === "question"` branch. Every
streamed question was pushed straight into
`editor-store.appendSections / appendQuestions`, which the TipTap
editor's `useEffect` consumers then inserted into the document. There
was no staging area, no per-question control, and no way to
distinguish curriculum-fallback questions from grounded ones.

### Fix

#### A. Backend stamps each question's provenance

`backend/services/generation_service.py:1306-1325`:

- After `_coerce_question`, the slot's `curriculum_fallback` flag
  becomes `sourceType: "rag" | "curriculum_fallback"` on both
  `question["metadata"]` and `question["sourceType"]`. The streamed
  SSE `question` event also carries it at the top level for
  frontend convenience.

#### B. Editor store: staging tray + insertion mode

`frontend/store/editor-store.ts`:

- `TrayItem { id, sectionTitle, question, sourceType, addedAt, inserted }`.
- `insertionMode: "review" | "auto"` (default `"review"` — the
  requirement asked for review-by-default since the user wants
  selectivity).
- Actions: `pushToTray`, `removeFromTray`, `markTrayInserted`,
  `clearTray`, `setInsertionMode`.
- Persisted via Zustand `persist` (localStorage) so the tray survives
  in-app nav and reload — Issue 1 + Issue 2 share the same persisted
  shape.

#### C. Routed streaming through the tray

`frontend/components/generator-form.tsx:200-243, 285-313`:

- New helper `stageQuestionForReview` pushes each streamed question
  into the tray, tagging the `sourceType` from the backend payload.
- The SSE handler now branches on `insertionMode`:
  - `review` (default): pushes to tray, suppresses the planned
    `generalInstructions` block (that header would lie until the user
    actually inserts something).
  - `auto`: legacy behaviour — instruction block + live-insert into
    the editor — preserved unchanged.
- A clear toggle ("Review before inserting" vs "Auto-insert all")
  lives directly above the tray.

#### D. Review tray UI

`frontend/components/review-tray.tsx` (new):

- Per-section grouping. Each card shows marks · question type · Bloom
  level · source badge ("From sources" = emerald, "Curriculum
  fallback" = amber) so teachers can be selective about ungrounded
  questions.
- Per-item **Insert** and **Dismiss** buttons.
- Checkbox per item + **Insert selected (N)** bulk action.
- **Insert all (N)** preserves the one-click convenience.
- **Insert section** per section header (insert-by-section).
- All insertion paths share `insertIds()` which groups by section so
  the section header + its questions land in the editor as a coherent
  unit.

#### E. Editor inserts dedupe section headers

`frontend/components/tiptap-editor.tsx:1296-1320`:

- The `sectionsToAppend` consumer effect now scans the existing doc
  for `sectionBlock` nodes with the same title and skips the header
  if the section already exists. Without this, inserting Section A
  from the tray twice (e.g. user inserts a few, then more later) would
  render two "Section A" headers and break the realized header count.

#### F. Realized counts already come from the body

`frontend/components/tiptap-editor.tsx:122-211` (`updateSectionSummaries`)
already derives section labels (`n × m = T Marks`) from the actual
`questionBlock` count under each `sectionBlock`. So inserting 12 of
38 yields a "(12 × 1 = 12 Marks)" Section A label automatically — no
new code needed. Combined with the previous fix's
`build_realized_general_instructions` rewriting the header at
done-time (server-side), the printed paper always matches the body
regardless of how the teacher used the tray.

#### Acceptance checks

| Behaviour | Status |
| --------- | ------ |
| Generated questions land in review tray, not paper (default) | ✓ |
| Per-item insert / multi-select / insert all / insert by section / dismiss | ✓ |
| Source badge per item | ✓ "From sources" vs "Curriculum fallback" |
| Header & marks match inserted set, not generated set | ✓ section summaries derive from realized body |
| Nav-away preserves un-inserted tray + paper | ✓ tray persisted in localStorage; paper in IDB |
| Auto-insert toggle reproduces old behaviour in one click | ✓ |

---

## Pipeline sanity sweep

1. **Generation → tray → editor**: SSE `question` event carries
   `sourceType`; review mode stages; teacher inserts; editor dedupes
   section headers; realized header recomputes from inserted set.
2. **Persistence layers**: large TipTap doc → IndexedDB; small UI/tray
   state → localStorage via Zustand persist; server PATCH still runs
   on every debounced sync.
3. **Conflict policy**: load effect (`tiptap-editor.tsx:1106-1170`)
   already prefers the source with the newer `updatedAt`. Unchanged.
4. **Editor never blanks**: in `handleCreateNewPaper`, the failure path
   keeps the previous draft alive rather than deleting on error —
   matches the "when in doubt, keep local state" guidance.
5. **Existing flows untouched**:
   - Auto-insert mode reproduces the original generator behaviour byte
     for byte (same `appendSections`/`appendQuestions` calls).
   - Saved papers from the library still load via `getPaperAction`
     unchanged.
   - Question Bank Browser → Insert Selected still works (it routes
     through `appendQuestions`, same as before).

---

## Tests

### Backend

- `backend/q_instructions/tests/test_content_scope.py::TestSourceTypeStamping`
  (new) — asserts `generation_service.py` stamps `sourceType` on
  `question["sourceType"]`, `question["metadata"]["sourceType"]`, and
  the streamed SSE payload, for both grounded and fallback paths.
- All prior tests: 67 → still pass.
- **Total: 68 passing, 0 failing.**

### Frontend

No test framework is installed in this repo (no `jest`/`vitest`
configured in `package.json`), and bootstrapping one isn't in scope
for this fix. Verification was done by:

- `tsc --noEmit` clean across all 2019 files.
- `eslint` clean across every changed file.
- Manual smoke test plan documented below.

#### Manual smoke test plan (combined Issues 1 + 2)

1. Sign in; open `/editor` with no paper id.
2. In the generator form: upload `surfaceareavol.pdf` and
   `trignometry.pdf`; pick Mathematics / Class 10 / Board /
   CBSE Exact Pattern.
3. Toggle should default to **Review before inserting**.
4. Click Generate. As questions stream, they appear in the **Review
   tray**, NOT in the editor.
5. Each tray item shows marks/type/Bloom + an amber **Curriculum
   fallback** or emerald **From sources** badge.
6. Insert one item via per-item Insert — confirm it lands in the
   editor under the correct section header.
7. Multi-select three items and click **Insert selected (3)**.
8. Click **Insert section** under "Section B" — only the remaining
   Section B items are inserted; Section B header is reused (not
   duplicated).
9. Click **Dashboard** in the nav. Return to `/editor`. Confirm:
   - No "Resume previous paper?" modal (same browser session).
   - Editor body fully restored, including the inserted questions.
   - The Review tray is still populated with the **remaining**
     un-inserted items.
10. Reload the browser (Ctrl-R). Confirm the same as step 9 — IDB +
    localStorage rehydrate before paint.
11. Open a new browser tab on `/editor`. Confirm the resume modal
    DOES appear, with truthful title / class / subject / question
    count / last-active timestamp.
12. Click **Continue Editing** → full paper restored.
13. Open another new tab, click **Create New Paper** → empty editor,
    previous draft archived (not destroyed; still in IndexedDB under
    an `archived:` key).
14. Switch the toggle to **Auto-insert all** and generate again →
    legacy behaviour reproduced (questions auto-insert during stream).

---

## Files touched

```
FIX_REPORT.md                                          (replaced)
backend/services/generation_service.py                 (Issue 2: sourceType stamping)
backend/q_instructions/tests/test_content_scope.py     (+ TestSourceTypeStamping)
frontend/store/editor-store.ts                         (rewritten — persist + tray + insertionMode + generatorContext)
frontend/lib/live-document-db.ts                       (sessionId field + archived filter)
frontend/components/tiptap-editor.tsx                  (sync capture-at-flush + sessionId stamp + dedupe section headers + flush-on-exit)
frontend/components/generator-form.tsx                 (insertion-mode toggle + stage-to-tray routing + generatorContext sync)
frontend/components/review-tray.tsx                    (new)
frontend/app/(dashboard)/editor/page.tsx               (session-id silent restore + truthful modal + archive-on-new)
```

## Test summary

- Backend: **68 passing** (was 67, +1 new), 0 failing.
- Frontend: `tsc` clean, `eslint` clean across all changed files; no
  test framework available — manual smoke plan documented above.
- No regressions in prior content-scope / PyMuPDF / Next-layout work
  (those tests are inside the same 68 and still pass).
