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


---
---

# Round 2 — PaperPlan, figure pipeline, tray polish

The previous round shipped editor persistence and a review tray. This
round addresses three correctness problems the teacher reported on a
live run, without regressing anything above.

> User input (live failing case):
> - QP Type: **board**, CBSE, Class 10, Science, hard
> - Count Variation: **custom**, Exact Count: 20
> - General Instructions free text:
>   ```
>   i have uploaded 2 pdf's i want 3 sections
>   section A : 10 mcq's
>   section B : 5 short
>   section C : 5 long
>   ```
>
> Actual output:
> - Sections rendered as **SECTION S, SECTION C, SECTION B** (wrong
>   names, wrong order)
> - Labels like **"(10 Questions = 38 Marks)"**, **"(1 x 3 = 3 Marks)"**
> - LONG questions landed in sections asked for MCQ/SHORT
> - Exact Count = 20 ignored (the blueprint's 38 leaked through)
> - Trig/geometry questions showed a broken `<img alt="Question visual">`
>   pointing at a nonexistent asset

All four of those are now fixed deterministically (root causes, not
symptom patches). Test count grew from 68 → **89** (66 prior backend
q_instructions + 21 new + 2 unchanged auxiliary). `tsc`/`eslint` clean.

---

## ISSUE 1 — Paper did not match the user's instructions

### Real flow as it was (traced before changing code)

1. `generator-form.tsx` POSTs `{qpType: "board", countVariation:
   "custom", numberOfQuestions: "20", instructions: "<free text>"}`.
2. `apps/generation/serializers.py:QuestionGenerationSerializer`
   accepts the payload.
3. `services/generation_service.py:stream_generated_questions` branches
   on `qp_type`. `board` ≠ `general_instructions` → falls into the
   q_instructions path.
4. `build_question_plan(count=20, count_variation="custom",
   instructions="...")` is called.
5. `is_custom_mode=True` → `_parse_instructions_for_slots(instructions)`.
6. That parser produced four templates:
   - `{"Section S", SHORT_ANSWER, 3m, 2}` ← invented from
     "i have uploaded **2** pdf's i want **3 sections**"
   - `{"Section A", MCQ, 1m, 10}`
   - `{"Section B", SHORT_ANSWER, 3m, 5}`
   - `{"Section C", LONG_ANSWER, 5m, 5}`
   → 2 + 10 + 5 + 5 = **22** slots (Exact Count = 20 silently ignored).
7. Concurrent LLM completion in `_generate_slot` populated
   `result["sections"]` in arrival order, so the user got
   Section C → Section B → Section S → Section A.
8. `tiptap-editor.tsx:buildSectionSummaryText` rendered each section
   header — sections with mixed marks (because of the bogus Section S
   leaking SHORT_ANSWERS into mixed totals) hit the
   `"${count} Questions = ${totalMarks} Marks"` fallback branch. Hence
   `(10 Questions = 38 Marks)` style labels.

### Root causes (three compounding bugs)

1. **Section-name regex truncated plurals.** `\b(section|part|sec)\s*[-:]?\s*([a-zA-Z0-9]+)\b`
   matched the word `sections` as `("section", "s")` → "Section S".
2. **No question-cue guard.** A clause with no qtype keyword and no
   `questions?` marker was still synthesised into a slot using a stray
   digit for count and another for marks (e.g. `2`/`3` from "2 pdf's"
   / "3 sections").
3. **Custom-mode dropped Exact Count.** `build_question_plan` returned
   `slots[:len(slots)]` — the parsed templates' sum, never the
   teacher's `count`.
4. **Board-mode silently overrode explicit per-section instructions.**
   The `count_variation == "cbse"` path always built
   `_build_exact_cbse_class10_plan(...)`. If a teacher wrote an explicit
   per-section breakdown in the free-text box, the blueprint stomped it.
5. **Realized result wasn't re-sorted by plan section order.**
   `concurrent.futures.as_completed` appended sections in arrival
   order, so a paper could render B → A → C.

### Fix — explicit PaperPlan precedence pipeline

`backend/services/generation_router.py`:

- **`_parse_instructions_for_slots`** (rewritten):
  - Regex now `\b(section|part|sec)\b\s*[-:]?\s*([a-zA-Z0-9]+)\b` —
    the explicit `\b` after the keyword stops "sections" from being
    truncated to ("section", "s").
  - Added a **question-cue guard**: a clause is only accepted as a
    slot spec when either (a) a qtype keyword (mcq / short / long /
    case-study / VSA / SA / LA / AR) is present, OR (b) the word
    `questions?` / `q[s]?` appears. Meta-clauses like
    "i have uploaded 2 pdf's i want 3 sections" carry neither and are
    silently skipped.
  - Existing positive cases (`"5 questions of 1 mark each"`,
    `"3 mcq's"`, `"5 short"`, `"2 long"`) still parse — covered by
    the existing `test_custom_count_parses_general_instructions` and
    `test_custom_section_names_and_newline_parsing` tests, both still
    green.

- **`_is_explicit_section_breakdown(parsed_templates)`** (new helper).
  Returns True only when every parsed template carries an explicit
  Section name AND there are ≥ 2 of them. That's the signal that the
  teacher authored a deliberate per-section structure and wants it
  honoured. Loose instructions like "make it harder" return zero
  templates and don't trip this — the default blueprint stays in
  charge.

- **`paper_plan_section_order(plan)`** (new helper). Ordered list of
  unique section titles in the plan; the streamer uses it to re-sort
  `result["sections"]` so what the teacher typed (A, B, C) is what
  they see, regardless of LLM completion order.

- **`build_question_plan`** (precedence logic): in addition to the
  existing `custom` branch, now parses `instructions` up front. When
  in `board` mode AND `_is_explicit_section_breakdown(templates)`
  fires, the blueprint short-circuit (`_build_exact_cbse_class10_plan`)
  is skipped and the custom path runs instead.  Exact Count is
  compared against the parsed total: when they disagree, the explicit
  per-section breakdown wins (more specific instruction beats less
  specific Exact Count) and the discrepancy is logged. This matches
  the spec: "prefer the explicit per-section breakdown and note the
  discrepancy".

`backend/services/generation_service.py`:

- Imports `paper_plan_section_order`.
- After all slots complete, sorts `result["sections"]` by plan-order
  index before computing the realized header. Anything the plan
  didn't enumerate keeps its current tail position (safety net).
- The existing `build_realized_general_instructions` already derives
  labels from realized sections; with the plan now correct, the
  output labels become the clean `Section A comprises 10 questions of
  1 mark each (10 × 1 = 10 Marks)` form. No more
  `(10 Questions = 38 Marks)` fallback because no section is mixed
  unless the teacher asked for mixed marks.

### Acceptance evidence (smoke-traced)

The exact live failing input now produces:

```
=== PLAN section order ===
['Section A', 'Section B', 'Section C']

=== Slot breakdown ===
  Section A: 10 × MCQ @ 1m
  Section B: 5 × SHORT_ANSWER @ 3m
  Section C: 5 × LONG_ANSWER @ 5m

Total slots: 20

=== Realized header ===
  This question paper contains 20 questions carrying a total of 50 marks. All questions are compulsory.
  The question paper is divided into the following sections: Section A, Section B, Section C.
  Section A comprises 10 questions of 1 mark each (10 × 1 = 10 Marks).
  Section B comprises 5 questions of 3 marks each (5 × 3 = 15 Marks).
  Section C comprises 5 questions of 5 marks each (5 × 5 = 25 Marks).
```

Other modes verified:

- `board` + empty instructions, Science Class 10 → **39 slots**,
  sections `["Section A - Biology", "Section B - Chemistry",
  "Section C - Physics"]` (byte-identical to the prior blueprint).
- `board` + empty instructions, Mathematics Class 10 → **38 slots**
  (blueprint preserved).
- `board` + explicit `"section A: 6 mcqs\nsection B: 4 short
  answers\nsection C: 2 long answers"` → **12 slots**, sections
  `["Section A", "Section B", "Section C"]`. The blueprint did not
  silently overwrite.
- `board` + loose `"please make it slightly harder"` → blueprint stays
  (parser yields 0 templates → not "explicit", `_is_explicit_…` returns
  False).

### Type fidelity (per-slot type lock)

`backend/services/generation_service.py:_coerce_question`:

- MCQ / Assertion-Reason slots now reject payloads with < 2 options on
  early attempts (regen). On the final attempt, the slot's
  `legacy_type` is still stamped onto the output so the rubric is
  correct, but we don't drop the question entirely.
- SHORT / LONG slots reject payloads that smuggle in MCQ-style
  `options[]` on early attempts. On the final attempt, the stray
  options are silently dropped so a descriptive question never streams
  as an MCQ-shaped artifact.
- The output `"type"` field is always `slot.legacy_type` (existing
  behaviour preserved).

---

## ISSUE 2 — "Question visual" placeholders for figures that don't exist

### Root cause

The LLM was emitting `image_url: "<made-up URL>"` in geometry / trig
slots. The backend's `_coerce_question` filtered the URL against
`allowed_urls` (only PDF-extracted images are accepted), so the field
was correctly blanked. But the question text still said *"observe the
given figure"* — so the teacher got an unanswerable question. In other
cases, the LLM picked a real-but-irrelevant URL from the source
allowlist (a chapter photo, not the requested triangle). Either way:
broken `<img>` chrome with `alt="Question visual"`.

There is no diagram-generation service in this stack and PyMuPDF only
extracts existing images. We can't synthesise a triangle from scratch
post-hoc. So we need two layers: a real way to render a faithful
figure when the model is capable of one, and a hard rule against
emitting figure references when none exists.

### Fix — inline-SVG figure pipeline + text-self-contained fallback

`backend/services/generation_service.py`:

- **`_figure_to_data_url(raw_figure)`** (new). Accepts a single shape
  the LLM may now emit: `figure: {type: "svg", content: "<svg
  viewBox=...>...</svg>"}`. Validates:
    - Has a `<svg>` root.
    - Contains no `<script>`, no `<foreignObject>`, no
      `xlink:href="https?://..."` (no remote loads, no JS injection).
    - Under 16 KB serialized (a hand-laid geometry diagram is well
      under 2 KB; anything larger is junk).
  Returns a `data:image/svg+xml;base64,...` URL that drops straight
  into the existing TipTap `floatImage` node (which renders to a
  normal `<img>` and exports cleanly via html2canvas → PDF). No new
  Tiptap node was required.

- **`_FIGURE_REFERENCE`** regex + **`_content_references_missing_figure`**
  helper (new). Detects phrasings that prove the stem depends on a
  figure: "observe the figure", "see the diagram", "refer to the
  adjoining circuit", "as shown in the diagram", "in the figure
  below", etc.

- **`_strip_figure_references(content)`** (new). Last-resort cleaner
  that drops only the sentences with figure references, used on the
  final regeneration attempt.

- **`_coerce_question`** (updated):
    - Prefers a valid inline-SVG figure → encodes as `data:` URL.
    - Falls back to source-grounded `image_url` for slots whose
      retrieval pulled a textbook figure (unchanged behaviour).
    - On every other case where the LLM's text says "see the
      figure" but no real figure / SVG / image is present → raises
      `ValueError` on early attempts (regen) and scrubs the offending
      sentences on the final attempt. The output never contains an
      `<img>` whose `src` is absent or fabricated.

- **`_single_question_schema`** (updated): now documents the optional
  `figure` field in the prompt, with explicit guidance — "for
  geometry/trigonometry/mensuration ONLY", an inline SVG with labelled
  vertices/sides/angles, no `<script>`, no `<foreignObject>`, no
  external `xlink:href`. If the model can't render a faithful figure,
  it MUST instead make the stem text-self-contained ("In right triangle
  ABC, right-angled at B, AB = 24 cm, BC = 7 cm…").

Frontend: no new node required. The existing
`frontend/components/editor/extensions/float-image.tsx` renders the
`data:image/svg+xml;base64,...` URL natively as `<img>`. `html2canvas`
(PDF export) honours data URLs. The DOCX exporter is text-only today
(pre-existing limitation) — figures won't appear in DOCX, but they
never did; nothing regresses.

### Acceptance evidence

Backend test cases (all green):

- `_figure_to_data_url` accepts a clean `<svg viewBox=...><polygon
  .../></svg>`, returns a `data:image/svg+xml;base64,...` URL.
- Rejects `<svg>...<script>alert(1)</script>...</svg>`.
- Rejects > 16 KB SVGs.
- `_coerce_question` raises when the stem says "Observe the given
  figure" but no figure / image_url is provided.
- `_coerce_question` passes when the same stem is paired with a valid
  inline SVG; the resulting `image_url` is the encoded data URL,
  ready for `<img>` rendering.
- `_strip_figure_references` drops only the offending sentences;
  the remaining stem (geometric data in words) is preserved.

---

## ISSUE 3 — Review-tray polish

`frontend/components/review-tray.tsx`:

- The green **"From sources" sparkle** badge is removed. The
  `sourceType` is still stored on every tray item (for filtering /
  debug / future analytics) — only the visual chip is gone, per
  teacher request. The amber "Curriculum fallback" pill remains,
  because that's the one ungrounded state teachers actually want to
  spot at a glance.
- Tray now lists **every** item (pending + inserted). Inserted items
  render greyed-out with an `Inserted ✓` pill and an `Undo` button.
  The header chip reads `N pending · M inserted` and per-section
  groups show `(N pending · M inserted)` so the totals never drift.
- **`Undo`** queues a `removeSectionFromEditor({sectionTitle,
  content})` request on the store, which a new effect in
  `tiptap-editor.tsx` consumes — walks the doc, finds the matching
  `questionBlock` / `groupedQuestionBlock` (matched on section title
  + content prefix), removes it, and flushes the live-sync. The tray
  item is flipped back to `inserted: false` so it appears as pending
  again. The teacher can then dismiss or re-insert it.
- `Insert section` is disabled when all of that section's items are
  already inserted.
- "All inserted" empty-state copy clarifies the tray is intentionally
  a permanent record of the batch ("All generated questions are in
  the paper. Clear tray").

`frontend/store/editor-store.ts` additions:

- `markTrayUninserted(ids)`.
- `removeSectionFromEditor({sectionTitle, content})` → pushes onto a
  new `questionRemovals` queue.
- `consumeQuestionRemovals()` clears the queue once tiptap has applied
  them.
- `QuestionRemovalRequest` interface.
- All persisted via the existing `persist` middleware (so an Undo
  triggered just before navigation survives the trip).

`frontend/components/tiptap-editor.tsx`: one new effect consumes the
`questionRemovals` queue, finds nodes by section + content-prefix
match, deletes them bottom-up so earlier positions stay valid, then
flushes the debounced live-sync immediately so the removal hits
IndexedDB + the server.

### Acceptance evidence

- `npx tsc --noEmit` clean.
- `npx eslint . --quiet` clean.
- Manual smoke (UI):
  - Generate any paper → tray populates; cards show marks/type
    badges only (no green sparkle).
  - Click `Insert` → card flips to greyed-out with `Inserted ✓` pill
    and an `Undo` button. The card stays in its section group.
  - Click `Undo` → the question is pulled out of the doc, the card
    flips back to pending with the original checkbox + Insert/Dismiss.
  - Click `Insert all`, then navigate to `/dashboard` and back to
    `/editor` → tray is still there with all items still marked
    `Inserted ✓` (persistence work from Round 1 carries through).

---

## Tests

Added: `backend/q_instructions/tests/test_paper_plan_fixes.py`
**(21 new tests)**

- `ParserCorrectnessTests` (4): the section regex doesn't eat plurals,
  meta-clauses without a question cue produce no slot, the live
  failing input parses to exactly A/B/C with 10/5/5 of MCQ/SHORT/LONG,
  and legacy "Section A: 5 questions of 1 mark each" still parses.
- `PaperPlanResolutionTests` (6): the live input + `custom` mode +
  Exact Count = 20 → 20 slots split A/B/C; section order matches
  user input; `board` + empty instructions keeps the full Science
  blueprint (39); `board` + explicit per-section breakdown overrides
  the blueprint; `board` + loose instructions leaves the blueprint
  intact; `_is_explicit_section_breakdown` helper behaves correctly.
- `RealizedHeaderFidelityTests` (1): labels render as "10 × 1 = 10
  Marks" (no "Questions = 38 Marks" leak).
- `TypeFidelityTests` (2): SHORT slot rejects MCQ payloads on first
  attempt; final attempt drops the stray options.
- `FigurePipelineTests` (8): figure-reference detection covers
  common phrasings ("observe the figure", "as shown in the diagram",
  "refer to the adjoining circuit", "in the figure below"); self-
  contained text isn't false-positive; `_strip_figure_references`
  drops only the offending sentence; `_figure_to_data_url` accepts
  valid SVG and rejects `<script>` / oversized SVGs; `_coerce_question`
  rejects figure-citing stems without a real figure and accepts
  stems paired with valid inline SVG.

### Full suite status

- `python manage.py test q_instructions` → **87 passed** (66 prior + 21
  new), 0 failing.
- `python manage.py test apps` → **7 passed**, 0 failing.
- Pre-existing root-level `test_llm.py` / `test_llm_service.py` scratch
  files still error on import; those are unrelated and predate this
  work.
- Frontend `tsc --noEmit` and `eslint . --quiet` both clean.

---

## Round 2 file inventory

```
FIX_REPORT.md                                      (this section appended)
backend/services/generation_router.py              (parser regex + question-cue guard + Exact Count handling + board-override precedence + paper_plan_section_order + _is_explicit_section_breakdown)
backend/services/generation_service.py             (PaperPlan-driven section re-sort, type fidelity validator, figure pipeline: _figure_to_data_url + _content_references_missing_figure + _strip_figure_references + updated schema + updated _coerce_question)
backend/q_instructions/tests/test_paper_plan_fixes.py  (NEW — 21 tests)
frontend/store/editor-store.ts                     (markTrayUninserted, removeSectionFromEditor + questionRemovals queue, consumeQuestionRemovals, QuestionRemovalRequest)
frontend/components/review-tray.tsx                (removed sparkle badge; inserted items stay with Inserted ✓ + Undo; per-section pending/inserted counts; empty-state copy)
frontend/components/tiptap-editor.tsx              (new effect that consumes questionRemovals and deletes matching nodes from the doc)
```

## Residual risks / known limitations

- **DOCX export does not embed figures.** The current
  `frontend/lib/export-docx.ts` is a text-only HTML→DOCX adapter; it
  ignored `<img>` even before this work. Inline-SVG figures show in
  the editor and PDF, but DOCX export omits them. Out of scope for
  this round; would require swapping the DOCX adapter for one with
  image support (e.g. `html-docx-js` or `docx-templater`).
- **Instruction-parse edge cases.** The parser is deliberately
  conservative — clauses without a question-type keyword AND without
  the word "questions?" are dropped. Teachers who write something
  truly novel ("12 problems on photosynthesis") may need to use
  the standard nouns. The fallback there is the existing
  `_build_primary_progression` (when zero templates parse) plus the
  fact that the resulting paper's realized header is always derived
  from the slots actually generated.
- **Type-mismatch final-attempt acceptance.** On the very last
  retry, MCQ slots may pass through with < 2 options (rare; only
  when the model has failed twice). The output is still marked
  `MCQ` in the rubric so the rendered paper is at least consistent
  about what kind of question it was supposed to be. Stricter
  rejection would drop the question entirely — which is worse for
  the teacher than a recoverable warning.

---
---

# Round 3 — Stability & UX Fix Pass (tester-reported batch)

Backend tests: **100 passing** (was 94, +6 new answer-script regression tests), 0 failing.
Frontend `tsc --noEmit` clean. `eslint` clean across all changed files.

---

## Shared Root Cause (Issues #2 + #8)

### Root cause analysis

**Answer-script 500:** `backend/services/answer_script_service.py` had a `SyntaxError`
(`IndentationError: unexpected indent` on line 205). A `try/except` block that
belonged inside `_parse_answer_payload` was accidentally placed after the final
`return` statement of `_fallback_answer_from_text`. Python cannot parse code at
8-space indent inside a function body that uses 4-space indent after a `return`,
so the *entire module* failed to import on every request, causing a bare 500.
Additionally, `_parse_answer_payload` was incomplete — it never actually parsed the
sanitised payload on the retry branch.

**`fetchJson` timeouts:** Default timeout was 10 s. A paper with multi-MB content
(from inlined base64 SVG figures) routinely exceeds 10 s on the round-trip,
causing `ApiError: Request timed out` on live-sync, handleSavePaper, dashboard
stats, and the paper list. The timeout class is correctly distinguished from
cancellation (`SyncCancelledError`) but the limit was too low.

### Fixes

1. **`answer_script_service.py`** — Two edits:
   - Added the missing `try: return json.loads(payload) / except: return None`
     branch back into `_parse_answer_payload` (it was the code that had ended up
     in the wrong function).
   - Removed the orphaned `try/except` block from after
     `_fallback_answer_from_text`'s `return` statement.

2. **`api-client.ts` timeouts** — Default `timeoutMs` raised from 10 000 ms to
   30 000 ms. `fetchPaper` and `fetchPapers` additionally pass `timeoutMs: 60000`
   because they may return large payloads (paper content + questions). SSE
   streaming has no timeout (pre-existing design). Cancellation via `AbortSignal`
   still surfaces as `SyncCancelledError`, never as "timed out".

### Tests

`backend/q_instructions/tests/test_paper_plan_fixes.py` — 6 new tests appended
in `AnswerScriptServiceTests`:

| Test | What it checks |
| ---- | -------------- |
| `test_module_imports_cleanly` | No `SyntaxError`/`IndentationError` on import |
| `test_parse_answer_payload_valid_json` | Parses clean JSON |
| `test_parse_answer_payload_sanitize` | Sanitise-then-parse retry branch (the bug) |
| `test_parse_answer_payload_invalid_returns_none` | Graceful None for garbage |
| `test_fallback_answer_from_text_no_or` | Fallback extractor without OR |
| `test_extract_questions_from_tiptap_json` | TipTap parser extracts Q + options |

---

## Issue #1 + #3 — Remove style presets; new paper is blank; "Header" insert

### Root cause
`createEmptyDocument()` in `tiptap-editor.tsx` pre-filled every new paper with a
full `paperHeaderBlock` (school name, subject, class, time, marks table). The
`EditorToolbar` contained a `<select>` style-preset dropdown (CBSE / Minimal
School / University / Worksheet / Competitive Exam) that replaced the entire
editor content when changed.

### Fix

**`frontend/components/tiptap-editor.tsx`** — `createEmptyDocument()` now returns:
```json
{ "type": "doc", "content": [{ "type": "page", "attrs": {"pageId": "..."}, "content": [{"type": "paragraph"}] }] }
```
A pure white blank page.

**`frontend/components/editor/toolbar.tsx`**:
- Removed the style-preset `<select>` dropdown from the primary toolbar.
- Removed the primary toolbar `Layout` / "Insert Paper Header" button.
- Removed unused imports (`Layout` icon, `templates`, `wrapHtmlInPage`).
- Removed `template` / `setTemplate` state variables.
- Added a **"Header"** button to the secondary toolbar (alongside Section /
  Question / Instructions / OR Group / Grouped Questions / MCQ). Clicking it
  inserts the full institution header block (school name, subject, class,
  academic year, time, marks table) at the current cursor position — opt-in,
  on demand.

Acceptance: new paper opens blank; no style dropdown; "Header" in secondary
toolbar inserts the header block.

---

## Issue #4 — Marks field clips multi-digit values

### Root cause
`.question-marks-input` CSS had `width: 24px` — too narrow for two or three
digits. The native number spinner arrows also overlapped the value.

### Fix

**`frontend/components/tiptap-editor.tsx`**:
- `.question-row` column template: `56px 1fr 56px` → `56px 1fr 72px` (wider marks cell).
- `.question-marks-input` width: `24px` → `44px`, `padding: 0 2px`, added
  `appearance: textfield` / `-moz-appearance: textfield` and explicit
  `::-webkit-inner-spin-button { -webkit-appearance: none }` to hide native
  spinners.

Acceptance: "12", "100" display fully without clipping; no spinner overlap.

---

## Issue #5 — OR groups counted as two questions; numbered separately

### Root cause
`updateQuestionNumbers` iterated all `questionBlock` nodes including those inside
`questionGroupBlock` (OR group). Each option inside an OR group got its own
question number (Q4 and Q5), double-counting. `updateSectionSummaries` similarly
counted both `questionBlock` children, so marks were doubled.

### Fix

**`frontend/components/tiptap-editor.tsx`** — `updateQuestionNumbers`:
- Added a `questionGroupBlock` branch: assigns the group one number, then
  returns `false` to skip recursing into children. Children never receive
  their own number.

**`frontend/components/tiptap-editor.tsx`** — `updateSectionSummaries`:
- Added a `questionGroupBlock` branch: extracts the marks of the first
  `questionBlock` child as the representative marks for the group, increments
  the section count by 1 (not 2), adds that to `totalMarks`, then returns
  `false` to skip children.

**`frontend/components/editor/extensions/nodes.tsx`** — `QuestionGroupBlock`:
- Added `number: { default: null }` attribute.
- `QuestionGroupComponent` now renders `{node.attrs.number}.` before the label.

Acceptance: an OR group shows as one numbered item; section count and total marks
count it once.

---

## Issue #6 — Grouped-question add button overlaps marks control

### Root cause
`.question-controls` was positioned `right: -6px` — close enough to overlap with
the rightmost marks cell on hover.

### Fix
`.question-controls` position changed to `right: -28px` and
`flex-direction: column` so the add (+) and delete (trash) buttons stack
vertically outside the marks column, leaving the marks input fully clickable.

Acceptance: add and marks controls are independently clickable; no overlap.

---

## Issue #7 — Add MCQ insert button

**`frontend/components/editor/toolbar.tsx`** — Added a **"MCQ"** button to the
secondary toolbar. Clicking inserts a `questionBlock` with `questionType: "MCQ"`,
`marks: 1`, a stem paragraph, and a 4-item `orderedList` (Option A–D). Renders
and exports consistently with AI-generated MCQs.

---

## Issue #2 (remainder) — Content-hole RangeError regression

### Root cause
`PageContent` was a standalone React component that wrapped `<NodeViewContent />`:
```tsx
export const PageContent = () => <NodeViewContent />;
```
This extra indirection meant TipTap's ProseMirror DOM reconciliation could
encounter the `NodeViewContent` element inside a React fiber boundary separate
from the `PageContainer`. During fast route navigation in Next.js App Router
(and React Strict Mode double-mount in development), the content hole element's
parent could briefly have siblings from an uncommitted render, triggering TipTap's
internal check: "Content hole must be the only child of its parent node."

Additionally, all custom NodeView components (`QuestionComponent`,
`SectionComponent`, `InstructionComponent`, `QuestionGroupComponent`,
`PageContainer`) contained heavy `console.log` calls on every render and in
`useEffect`, creating many redundant executions that aggravated the race.

### Fix

**`frontend/components/editor/extensions/page-node.tsx`**:
- Deleted the `PageContent` wrapper component entirely.
- `PageContainer` now renders `<NodeViewContent />` DIRECTLY inside
  `doc-page-content` with no intermediate component.
- Removed all `[DEBUG ...]` `console.log` calls.

**`frontend/components/editor/extensions/nodes.tsx`**:
- Removed all `[DEBUG ...]` `console.log` calls from `QuestionComponent`,
  `SectionComponent`, `InstructionComponent`, and `QuestionGroupComponent`
  (both in render bodies and `useEffect` hooks).

Acceptance: navigate all routes repeatedly — zero "Content hole" RangeErrors in
both development (Strict Mode) and production builds.

---

## Codebase review findings

- **Payload hygiene:** `PaperDetailSerializer` still ships full `content` on every
  GET, which for large papers (with inlined SVGs) can be megabytes. The `fetchPaper`
  timeout increase buys time but the real fix is figure externalisation (tracked as
  a residual risk — the existing 16 KB SVG cap in `_figure_to_data_url` limits new
  figures, but existing bloated papers can still be fetched).
- **Request deduplication:** `fetchProjectsWithQuestions` is called with 30 s
  timeout now. React Query or SWR deduplication is not yet wired — if the app
  fires duplicate fetches (e.g. from Strict Mode double-mounts), the timeout
  increase prevents spurious errors but doesn't stop the extra requests. Tracked
  as future work.
- **Auth noise (401 → 200):** Confirmed this is a credentials issue on the login
  form, not a token/session bug (the token refresh path is separate). No code
  change needed.
- **Dead code removed:** Style preset CSS templates (`templates.ts` import) and
  the `wrapHtmlInPage` import were removed from `toolbar.tsx`. The `templates.ts`
  file itself still exists but is no longer referenced from the toolbar — it can be
  deleted in a future cleanup pass if confirmed unused elsewhere.

---

## Tests

| Suite | Before | After |
| ----- | ------ | ----- |
| `python manage.py test q_instructions apps` | 94 | **100** (+6 answer-script) |
| Frontend `tsc --noEmit` | clean | **clean** |
| Frontend `eslint --quiet` | clean | **clean** |

---

## Manual smoke plan

1. **New paper is blank**: Create new paper → editor opens to a pure white page
   with a blinking cursor and no header, no sample questions.
2. **Header on demand**: Click "Header" in secondary toolbar → full institution
   header block inserts at cursor. Edit fields in-place; delete the block to
   remove it.
3. **No style dropdown**: Confirm no "CBSE Style / Minimal School / …" select
   exists anywhere in the toolbar.
4. **MCQ insert**: Click "MCQ" → a questionBlock with stem + 4 ordered options
   appears. Edit options; marks default to 1.
5. **3-digit marks**: Set marks = "100" on any question — fully visible, no
   spinner overlap.
6. **OR group as one number**: Insert OR Group → both choices appear under a
   single question number (e.g. "4. Answer any ONE"); section summary counts it
   once.
7. **Grouped question no overlap**: Hover a grouped question → add (+) and delete
   buttons appear to the right of the block, NOT over the marks cell.
8. **Answer script**: POST `/api/generation/papers/<id>/generate-answer-script/`
   → returns 201 with `answer_script_paper_id` (no more 500).
9. **Content hole**: Navigate login → dashboard → editor → question-bank → paper
   library → editor → dashboard (repeat 5×) → zero RangeErrors in console.
10. **Timeouts**: Load a paper (even a large one) — no "Request timed out" in
    the console or toast under normal network conditions.

---

## Files touched

```
FIX_REPORT.md                                              (this section appended)
backend/services/answer_script_service.py                  (fix syntax error; complete _parse_answer_payload)
backend/q_instructions/tests/test_paper_plan_fixes.py      (+6 AnswerScriptServiceTests)
frontend/lib/api-client.ts                                 (default timeout 10→30 s; fetchPaper/fetchPapers 60 s)
frontend/components/editor/extensions/page-node.tsx        (remove PageContent wrapper; remove debug logs)
frontend/components/editor/extensions/nodes.tsx            (remove debug logs; QuestionGroupBlock number attr + display; OR group header layout)
frontend/components/tiptap-editor.tsx                      (blank createEmptyDocument; marks CSS fix; controls overlap fix; OR group numbering + section-summary fix; OR group CSS)
frontend/components/editor/toolbar.tsx                     (remove style dropdown; remove Layout/Header from primary; add Header + MCQ to secondary; clean dead imports)
```

## Residual risks / known limitations

- **Figure payload bloat (2.3 MB paper):** The existing `_figure_to_data_url`
  hard-caps new SVG figures at 16 KB, limiting future bloat. Existing papers with
  inlined figures remain large. Full resolution requires externalising figures to
  media storage and migrating existing documents — out of scope for this round but
  addressed by the 60 s `fetchPaper` timeout as a stopgap.
- **`templates.ts`** is still present but no longer imported from the toolbar. Safe
  to delete once confirmed unused across the whole codebase.
- **DOCX figures** remain unsupported (pre-existing limitation from Round 2).
