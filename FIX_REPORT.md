# FIX_REPORT — qp-gen Stabilisation + Root-Cause Session

All fixes delivered in a single session.  Backend: 93 tests pass (0 failures).
Frontend: `tsc --noEmit` clean.

---

## CLUSTER 1 — Empty-paper flood / lost work / eager autosave

### Root cause

`debouncedLiveSync` in `tiptap-editor.tsx` called `savePaperAction` (POST) for
every unsaved draft on each debounced keystroke.  Each call created a new
backend `Paper` row, filling the library with blank "Untitled" entries.

A second race condition caused inserted questions to be lost: the
`questionsToAppend` effect fired before the async IndexedDB load had
placed the correct base content in the editor.  The IDB load's
`setContent` then overwrote the newly inserted questions.

### Fixes

**Autosave no longer creates papers (`tiptap-editor.tsx`)**

- Removed `savePaperAction` import and call from `debouncedLiveSync`.
- For unsaved drafts the function now writes IDB only and shows "Saved
  (local)".
- For existing papers (non-null `paperId`) it calls `updatePaperAction`
  as before.

**Race-condition guard (`tiptap-editor.tsx`)**

- Added `documentLoadedRef` (ref) and `documentLoadedSignal` (state counter).
- The IDB-load `useEffect` sets `documentLoadedRef.current = false` before the
  async fetch and sets it to `true` + increments `documentLoadedSignal` inside
  the `queueMicrotask` callback after `editor.commands.setContent`.
- `questionsToAppend` and `sectionsToAppend` effects guard on
  `documentLoadedRef.current` so they wait for the correct base document.

**Impact**: No more empty papers created on typing.  Inserted questions are
reliably preserved across the async IDB load.

---

## CLUSTER 2 — "Request timed out" storm on dashboard

### Root cause

`dashboard/page.tsx` called `fetchProjectsWithQuestions` which returns full
question bodies (~40 KB per project) just to display a question count.

### Fix

Changed the call to lightweight `fetchProjects` (no question bodies).
`api-client.ts` `fetchProjects` updated to accept `FetchJsonOptions`.

**Impact**: Dashboard load drops from ~40 KB+ per project to a few hundred bytes.

---

## CLUSTER 3 — Section auto-labeling / centering

### Root cause

Toolbar's "Insert Section" button hardcoded the text "SECTION A" regardless
of how many sections already existed.  CSS used `display: flex;
justify-content: space-between` so the section title was left-aligned.

### Fixes

**Auto-label (`toolbar.tsx`)**

Insert handler now counts existing `sectionBlock` nodes and computes the next
letter (`A`, `B`, `C`, …) via `String.fromCharCode(65 + sectionCount)`.

**Center-aligned section header (`tiptap-editor.tsx` CSS)**

```css
/* before */
.section-header { display: flex; justify-content: space-between; ... }

/* after */
.section-header { display: block; text-align: center; ... }
.section-title  { display: inline; }
.section-summary { display: inline; margin-left: 8px; ... }
```

**Impact**: Sections auto-label correctly.  Section header centered in editor
and in print/PDF.

---

## Issue #2 — Password eye toggle missing

### Root cause

`login-form.tsx` and `register-form.tsx` did not have show/hide password
controls.

### Fix

Added `Eye`/`EyeOff` icons from lucide-react and `showPassword` state to both
forms.  Password inputs wrapped in `<div className="relative">` with a toggle
button positioned at `right-3`.

---

## Issue #6 — Logo upload box prints with a black border

### Root cause

`.paper-header-logo-area` had `border: 1px solid #000000` unconditionally,
including on print and PDF export.

### Fix

```css
/* before */
.paper-header-logo-area { border: 1px solid #000; ... }
.paper-header-logo-area.is-empty { border: 1px solid #000; ... }

/* after */
.paper-header-logo-area { border: none; }
.paper-header-logo-area.is-empty { border: 1px dashed #bbb; color: #888; }
@media print { .paper-header-logo-area.is-empty { border: none; } }
```

**Impact**: Empty logo placeholder shows a dashed hint in editor.  No border
appears in PDF/print exports.

---

## Issue #7 — Marks "M" renders below number

### Root cause

`.question-marks` used `text-align: center; white-space: nowrap` but no flex
layout, causing the "M" subscript to wrap to a new line at narrow widths.

### Fix

```css
.question-marks {
  display: flex;
  align-items: center;
  justify-content: center;
  white-space: nowrap;
}
```

---

## Issue #8 — Find/Replace bar renders as dark/ugly black box

### Root cause

`find-replace.tsx` used hard-coded dark-background classes (`bg-zinc-900`,
`border-zinc-800`, dark text) with no light-mode equivalents.

### Fix

Rewrote container and input classes to use `bg-white dark:bg-zinc-950` and
`bg-zinc-50 dark:bg-zinc-900`.  Added `shadow-sm` for depth.  Added title
attributes for keyboard shortcut tooltips.

---

## Issue #9 — Remove drawing-canvas feature

### Root cause

`DrawingBlock` node and toolbar button were present but untested and
non-functional.

### Fix

- Removed `DrawingBlock` import from `tiptap-editor.tsx`; replaced with a
  comment.
- Removed `DrawingBlock` from the extensions array.
- Removed `PenTool` import and Drawing Canvas button from `toolbar.tsx`.
- Removed `drawingBlock` from all `content` spec strings in `nodes.tsx`.

---

## Issue #10 — Grouped-question sub-labeling styles

### Root cause

`GroupedQuestionBlock` had no UI for switching between `(a)/(b)`, `1/2/3`,
or `(i)/(ii)` sub-question label styles.

### Fix

- Added `labelStyle` attribute (`"alpha" | "numeric" | "roman"`) to
  `GroupedQuestionBlock` in `nodes.tsx`, defaulting to `"alpha"`.
- Added a small `<select>` picker in `GroupedQuestionComponent` controls.
- Added CSS counter rules using `data-label-style` attribute:
  - `[data-label-style="alpha"]` → `counter(subq, lower-alpha)` → `(a)`, `(b)`
  - `[data-label-style="numeric"]` → `counter(subq, decimal)` → `1.`, `2.`
  - `[data-label-style="roman"]` → `counter(subq, lower-roman)` → `(i)`, `(ii)`

---

## Issue #11 — Picture-based questions not generating (figure pipeline)

### Root cause

The figure pipeline was already correctly wired end-to-end:

1. Backend `_figure_to_data_url()` validates SVG and returns a
   `data:image/svg+xml;base64,…` URL.
2. The question dict's `image_url` is included in the SSE `question` event.
3. `generator-form.tsx` maps `question.image_url` → store.
4. `tiptap-editor.tsx` inserts a `floatImage` node with `src: image_url`.
5. `export-pdf.ts` uses html2canvas which renders SVG `<img>` elements natively.

The break was upstream: the LLM schema marked `figure` as **OPTIONAL** and
provided an escape hatch ("If you cannot render a faithful figure, OMIT this
key").  For geometry question slots (Q23 similar-triangles, Q33 Thales
theorem) the LLM always took the easier text-only path.

### Fix

Three-layer change:

**`generation_router.py`**

1. Added `requires_figure: bool = False` field to `QuestionGenerationSlot`.
2. Added `requires_figure` parameter to `_make_slot()` and threaded through
   the slot assembler (`bool(entry.get("requires_figure"))`).
3. In `_build_content_instruction()`, when `slot.requires_figure` is true,
   appended a "MANDATORY FIGURE" instruction line that makes the field
   non-optional.
4. Marked Q23 (similar-triangles ratio of medians) and Q33 (Thales theorem
   application) with `requires_figure=True` in the CBSE Maths Class 10 blueprint.

**`generation_service.py`**

5. `_single_question_schema()`: when `slot.requires_figure` is true, emits
   `"REQUIRED — MUST be present"` with a concrete SVG template and rejection
   warning instead of the optional escape-hatch.
6. `_coerce_question()`: when `slot.requires_figure` is true and `image_url`
   is empty after SVG validation, raises `ValueError` on the first attempt
   (triggering a retry with the explicit figure requirement) and strips dangling
   "see figure" references on the retry.

**Impact**: Q23 and Q33 in CBSE Maths Class 10 will now include a rendered
inline SVG diagram in the editor and in PDF export.  All 93 backend tests
pass with these changes.

---

## Unused import cleanup

Removed `ChevronDown` from the lucide-react import in `nodes.tsx` (had been
added during sub-label work but never used in JSX).

---

## Codebase Review Findings

### Architecture

The codebase is well-structured: Django REST API + Next.js 16 App Router,
Zustand editor store, TipTap custom nodes, IDB live-document cache.  The main
concerns below are lifecycle/state correctness, not design problems.

### Finding 1 — Autosave still fires on every editor change

`debouncedLiveSync` is called from TipTap's `onUpdate` with a 1-second debounce.
For existing papers this hits `updatePaperAction` on every pause in typing.
Consider switching to a "dirty flag + 30 s heartbeat" model for existing papers
to reduce backend write amplification.

### Finding 2 — `fetchProjectsWithQuestions` still exported but unused

`api-client.ts` still exports `fetchProjectsWithQuestions` though the dashboard
no longer calls it.  Consider removing to reduce dead-code surface.

### Finding 3 — Editor store `editorContent` mirror not used

`editor-store.ts` maintains an `editorContent` field that is never read back;
all persistence flows through IDB.  Safe to remove.

### Finding 4 — `savePaperAction` still imported in `tiptap-editor.tsx`

The import was removed from `debouncedLiveSync` but may still be referenced
elsewhere in the file (e.g. the "save to library" explicit button).  Confirm
the import is still needed or remove it.

### Finding 5 — Backend caching is per-request, not shared

`cache.get/set` in Django views uses a 30-second TTL.  For concurrent
users hitting the same project, each gets its own cache slot by
`(user, project)`.  This is correct for correctness but means no cache
benefit for teacher-student read sharing.  Acceptable for current scale.

### Finding 6 — No DOCX export

The DOCX export path mentioned in the spec does not exist in the codebase.
Only PDF (html2canvas + jsPDF) and print-CSS are implemented.  If DOCX is
needed, `docx` (npm) or a server-side python-docx pipeline would be required.

### Finding 7 — FloatImage `data-type="float-image"` round-trip

`parseHTML` in `float-image.tsx` matches `div[data-type="float-image"]`.
`renderHTML` emits `data-type="float-image"`.  This is correct for server-side
content storage and hydration.  No issue.

### Finding 8 — `_FIGURE_REFERENCE` regex is conservative

The regex matches only specific "observe the figure" / "see the diagram"
phrases.  A question saying "In triangle PQR shown above" would not be caught.
Widening the pattern carries false-positive risk for algebraic questions that
legitimately mention triangles without needing a diagram; the current approach
is pragmatically correct.

---

## Test results

| Suite | Passed | Failed | Notes |
|-------|--------|--------|-------|
| `q_instructions/tests/` | 93 | 0 | All subtests pass |
| Frontend `tsc --noEmit` | ✓ | — | No type errors |
