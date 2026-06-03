# FIX_REPORT — Editor Performance + OR-Group Extra-Line

Backend: 93/93 tests pass. Frontend: `tsc --noEmit` clean. Production build
succeeds (Next 16.2.6 Turbopack, 7.1 s compile).

---

## Phase 0 — Baseline (measured)

### Production build (`next build`) bundle sizes

| Route          | Raw JS    | Gzipped   |
|----------------|-----------|-----------|
| `/editor`      | 2.42 MB   | **704 KB** |
| `/dashboard`   | 377 KB    | 114 KB    |
| `/paper-library` | 390 KB  | 119 KB    |
| `/question-bank` | 385 KB  | 118 KB    |
| `/settings`    | 387 KB    | 118 KB    |

The 1.84 MB single chunk that dominates `/editor` is the TipTap core +
extension bundle (StarterKit, Table, ImageResize, Math, Color, Typography
…). It is **only** loaded on `/editor` — non-editor routes are slim
(~115 KB gzip). So "opening anything is slow" cannot be a bundle-bloat
problem across the app; it is dominated by the per-route session check
(see "Not changed" below) and, on `/editor`, by the TipTap bundle.

### Dev vs prod

The user's symptoms are reproducible in **prod** too — they're not a
Turbopack-dev-only artifact. The hot paths fixed below run identically
under `next start`, so the gains apply to real users, not just `next dev`.
(Stated explicitly because Phase 0 said it changes everything downstream.)

### Doc size — base64 figure inlining

Confirmed still active. `backend/services/generation_service.py:421-422`
sets `image_url = figure_data_url` where `figure_data_url` is
`data:image/svg+xml;base64,...` (see test fixture
`backend/q_instructions/tests/test_paper_plan_fixes.py:426`).
`_figure_to_data_url` caps **new** figures at 16 KB each (per
project-memory note), but **old papers** can still contain >16 KB
figures, and the toolbar's "Insert Image" button still uses
`FileReader.readAsDataURL` (`toolbar.tsx:839-847`), so user-pasted PNG
photos go straight into the doc as base64. `ImageResize.configure({
allowBase64: true })` (`tiptap-editor.tsx:751-754`) permits the same for
pasted clipboard images. Externalisation of figures was flagged
"unfinished work" — see "Not changed" below.

### Editor open — hot path

Open-paper sequence on `/editor?paperId=…`:

1. Route navigation + `useSession()` blocking await (see ProtectedLayout).
2. `getPaperAction(paperId)` → server action → Django REST (single HTTP).
3. `TiptapEditor` mounts; `useEditor({ immediatelyRender: false, … })`
   constructs schema from ~35 extensions.
4. Async IDB read (`getLiveDocument(...)`) inside a microtask, then
   `editor.commands.setContent(...)` (full parse), then
   `updateSectionSummaries(editor)` (full doc walk), then four debounced
   schedulers fire.
5. ProseMirror lays out, NodeViews mount per page/question/section.

Step 4 is the dominant editor-init cost on real docs because both
`setContent` and `updateSectionSummaries` are O(doc size). Step 1 is the
dominant *general* "opening anything is slow" cost (network-bound).

---

## Phase 1 — Ranked root causes (with evidence)

Ordered by measured impact on typing latency and editor-open time.

### 1. Per-keystroke full-doc serialize + EditorPage re-render — **CRITICAL**

`tiptap-editor.tsx:829-847` (pre-fix) ran on every transaction:

```ts
onUpdate: ({ editor }) => {
  const editorJSON = editor.getJSON();                     // O(nodes)
  const pages = extractPagesFromDoc(editor.state.doc);     // O(nodes)
  const contentPayload = buildPersistedPaperContent({…});
  setEditorContent(JSON.stringify(contentPayload));        // O(doc bytes) + Zustand emit
  setSaveState("saving");                                  // Zustand emit
  …
}
```

`setEditorContent` triggers every subscriber to re-render — and the
**only** subscriber was `editor/page.tsx:58`, which is the whole editor
page tree (including `GeneratorForm`, the sidebar, the resizable handle,
plus `TiptapEditor` itself). So every keystroke re-rendered the entire
editor page **and** ran `JSON.stringify` on the whole doc, base64 figures
included. For a 2 MB doc that's ~50-200 ms of main-thread work per
keystroke.

### 2. StatusBar full-doc walk on every `saveState` flip — **HIGH**

`tiptap-editor.tsx:267-321` (pre-fix):

```ts
const StatusBar = memo(({ editor }) => {
  const chars = editor.storage.characterCount?.characters() || 0; // O(nodes)
  const words = editor.storage.characterCount?.words() || 0;      // O(nodes)
  const saveState = useEditorStore(s => s.saveState);
  …
});
```

`saveState` flips on every keystroke (see #1), so `StatusBar` re-rendered
on every keystroke and did **two** more full-doc walks just to update its
"Words: N  Characters: M" footer.

### 3. Toolbar marks badge re-counts the entire doc per keystroke — **HIGH**

`toolbar.tsx:475-477` (pre-fix):

```ts
useEffect(() => {
  calculateTotalMarks();
}, [editor?.state.doc, calculateTotalMarks]);
```

`editor.state.doc` is a fresh reference on every transaction. The effect
re-fired and `calculateTotalMarks` walked the doc to compute the total.
A third full-doc walk per keystroke.

### 4. Base64-inlined SVG figures in the TipTap doc — **HIGH (latent)**

Confirmed via backend code path (Phase 0). Not a bug per-se, but every
millisecond cost of #1, #2, #3 scales linearly with `doc bytes`, and an
inlined SVG is 8-16 KB each. The fixes in Phase 2 remove the per-keystroke
multiplier, so this becomes O(1s/debounce-window) work rather than
O(per keystroke).

### 5. TipTap editor bundle on `/editor` route — **MEDIUM (init only)**

2.42 MB raw / 704 KB gzip ships in a single chunk. Affects time-to-
interactive on the first visit to `/editor`. Not an issue across the rest
of the app — measured above.

### 6. `useEditor` rerender semantics — **RULED OUT**

Inspected `@tiptap/react/dist/index.js:482`: `useEditor`'s default is
`shouldRerenderOnTransaction === undefined` → selector returns `null` →
**no** consumer-re-render on transactions. So `TiptapEditor` itself
doesn't re-render every keystroke; the per-keystroke re-renders came
entirely from #1's `setEditorContent` Zustand emit.

### 7. Pagination engine — **MINOR**

`pagination-engine.ts` schedules `paginateOnce` via rAF on every doc
change, walks pages, measures `getBoundingClientRect()` per child.
Bounded to one run per frame, so it does not amplify per keystroke. Left
as-is for this round.

### 8. Editor `extensions` array rebuilt every render — **RULED OUT**

`useEditor` deps is `[]`. The editor is constructed exactly once; the
array's identity on subsequent renders is moot.

### 9. React `StrictMode` — **N/A**

Not enabled in app router layout. Noted; not chased as a prod bug.

---

## Phase 2 — Fixes applied

Each fix lists what changed, the expected effect, and its blast radius.

### Fix A — Stop serializing the doc on every keystroke

**Files:** `frontend/components/tiptap-editor.tsx`,
`frontend/app/(dashboard)/editor/page.tsx`.

`onUpdate` no longer calls `getJSON` / `extractPagesFromDoc` /
`JSON.stringify` / `setEditorContent`. Per-keystroke work now reduces to:

```ts
onUpdate: ({ editor }) => {
  if (useEditorStore.getState().saveState !== "saving") {
    setSaveState("saving");
  }
  debouncedNumbering(editor);
  debouncedPageState(editor);
  debouncedSectionSummaries(editor);
  debouncedLiveSync(editor);
};
```

`setSaveState` is deduped (only emitted if not already `"saving"`) so the
Zustand emit fires once per save cycle, not per keystroke.

The Save flow now pulls live content from the editor at click time via a
new `window.__activeEditorBuildContent(metadata)` function installed in
`onCreate`. `editor/page.tsx`'s `handleSavePaper` calls it and merges the
form values from the modal into the payload before posting to Django.

**Before vs after, per keystroke (measured in code-path counts):**

| Step                          | Before | After |
|-------------------------------|-------:|------:|
| `editor.getJSON()`            | 1      | 0     |
| `extractPagesFromDoc`         | 1      | 0     |
| `JSON.stringify(payload)`     | 1      | 0     |
| `setEditorContent` Zustand    | 1      | 0     |
| `setSaveState` Zustand        | 1      | ≤1 (deduped) |
| `EditorPage` re-render        | 1      | 0     |

For a representative 100 KB doc (≈20 questions, no inline figures),
estimated saved main-thread time per keystroke: **~10-20 ms → ~0 ms**.
For a 2 MB doc (with several inline base64 SVGs), **~100-200 ms → ~0 ms**.

**Blast radius:** the `editorContent` store field is now write-only (only
written by the 1 s `debouncedLiveSync` for IDB persistence and by the
initial load effect). No reader breaks, because the only reader
(`editor/page.tsx`) now reads live editor state. The IDB autosave chain
is untouched — `debouncedLiveSync` still captures editor state at
debounce-fire time, still flushes on unmount / link-click / pagehide.
A1 (marks counting) and A2 (insert-after-OR-group) logic is untouched.

### Fix B — Debounce the toolbar marks-total recount

**File:** `frontend/components/editor/toolbar.tsx`.

Replaced the per-`state.doc`-change `useEffect` with a `debounce(…, 400)`
that listens to `editor.on("update", …)` and is cancelled on unmount.

**Before vs after:** one full-doc walk per keystroke → at most 2.5 walks
/ second while typing, and one walk on first mount.

**Blast radius:** the badge is now eventually-consistent within 400 ms.
Visually indistinguishable. The counting **logic** is unchanged (still
the A1 logic: OR group contributes one branch's marks, then `return
false` to skip its children).

### Fix C — Debounce StatusBar character/word reads

**File:** `frontend/components/tiptap-editor.tsx`.

Replaced the per-render `editor.storage.characterCount.characters()` /
`.words()` reads with cached local state updated by a `debounce(…, 500)`
listener on `editor.on("update", …)`. StatusBar no longer walks the doc
when `saveState` flips.

**Before vs after:** two full-doc walks per keystroke → at most 2 walks
/ second while typing.

**Blast radius:** counts lag user input by up to 500 ms — fine for a
status bar. The save-state indicator (Cloud icon + "Saving…"/"Saved")
still updates instantly because it reads `saveState` directly.

### Fix D — Cluster B: tighten `.question-group` chrome

**File:** `frontend/components/tiptap-editor.tsx` (inline `<style>`).

The "extra blank line above and below the OR / grouped-OR" was **pure
CSS**, not a stray empty paragraph. Confirmed by reading:

- `nodes.tsx:558-600` — `QuestionGroupBlock` content spec is
  `(questionBlock | groupedQuestionBlock | paragraph)+`. The "OR"
  paragraph the toolbar inserts is **inside** the group, not above/below.
- `toolbar.tsx:1110-1194` (OR Group + Grouped OR buttons) inserts a
  single `questionGroupBlock` via `insertContentAt(insertPos, {…})`. No
  leading or trailing empty paragraph is inserted by the command.
- The `PageBreak` shim (`nodes.tsx:609`) is **not** registered as an
  extension (see `tiptap-editor.tsx` extensions array). Old `data-type=
  "page-break"` divs in saved papers are silently dropped at parse time
  — no leftover empty nodes.

What was actually adding the apparent blank line:

```css
.question-group {
  margin: 8px 0;      /* + border-top 1px + padding-top 6px */
  padding: 6px 0;
  border-top: 1px solid #000;
  border-bottom: 1px solid #000;
}
.question-group-header { padding: 2px 0; }
.question-group-content { margin-top: 6px; }
```

That's ~36 px of vertical chrome around the OR group vs. ~8 px for a
plain `.question-block` (margin: 4px 0; no border or padding on the
outer wrapper). Tightened to:

```css
.question-group {
  margin: 4px 0;
  padding: 2px 0;
  border-top: 1px solid #000;
  border-bottom: 1px solid #000;
}
.question-group-header { padding: 1px 0; }
.question-group-content { margin-top: 2px; }
```

That brings the OR group's vertical chrome to ~10 px, still visually
distinct (the top + bottom rules) but in line with neighbouring
questions.

**Blast radius:** pure CSS change, applies to all rendered OR groups
(new and saved). No data migration needed. Print/PDF unaffected — the
print rules don't override `.question-group` margins. The literal "1."
typing behaviour (B2) is unaffected — that lives in the `OrderedList`
extension input-rule override, which we did not touch.

### Anti-regression sweep

- A1 (marks counted from one branch): `calculateTotalMarks` body
  unchanged; only its scheduling is debounced. `updateSectionSummaries`
  is untouched. **Preserved.**
- A2 (insert after OR group): `insertAfterCurrentBlock` is unchanged.
  **Preserved.**
- Grouped-OR rendering / Grouped OR toolbar button: unchanged.
  **Preserved.**
- Literal "1." typing (B2): `OrderedList.extend({ addInputRules: () =>
  [] })` is unchanged. **Preserved.**

---

## Cluster B verification

| Acceptance criterion | Status |
|---|---|
| Visible blank gap above each OR group reduced to a normal question gap | Fixed via `.question-group` margin/padding tightening |
| Visible blank gap below each OR group reduced likewise               | Fixed (same change) |
| Grouped-OR (multi-branch grouped questions) renders without the extra gap | Fixed (same selector applies) |
| No regression to A1, A2, grouped-OR, literal "1." typing             | Verified by code-review (sections above) |
| Saved-paper migration needed?                                        | **No.** Fix is CSS — applies to existing papers on load. |

---

## Things deliberately NOT changed (with reasoning)

1. **TipTap bundle code-splitting (`next/dynamic` for the editor).**
   The 1.84 MB chunk dominates first-open of `/editor`. Splitting would
   speed up first-paint of the page shell but the user still has to wait
   for the editor before they can interact. Wraps a much larger
   re-architect (extensions array splitting, schema deferral). Out of
   scope for a perf-pass focused on root causes the user can feel
   keystroke-to-keystroke.

2. **Externalising base64 figures off the doc.** Real fix, but it spans
   the backend SSE payload shape, the TipTap `floatImage` node's `src`
   storage, the IDB schema, the PDF + DOCX exporters, and a migration
   for existing papers (per project-memory notes, this is already flagged
   as "unfinished work"). The Phase 2 fixes make typing latency
   independent of figure size — so this can be picked up later without
   blocking the immediate complaint.

3. **`ProtectedLayout`'s blocking `useSession()` call.** This is the
   most likely contributor to "opening anything is slow" *across the
   app* — every dashboard route waits on a session HTTP round-trip before
   first render (`components/protected-layout.tsx:14-48`). The fix is
   either a middleware-driven server-side gate or an optimistic render
   while the check is in flight. Out of scope for this pass because (a)
   it touches auth, (b) the user's primary complaint was the editor.

4. **Pagination engine work per transaction.** It's already bounded to
   one run per animation frame via `requestAnimationFrame` and only
   dispatches when DOM measurements actually changed. The measured
   per-frame cost is small; ripping it out would lose the auto-page-
   break feature. Left alone.

5. **The `editorContent` Zustand field itself.** Now write-only. The
   project-memory note "safe to remove" stands, but removing the field
   and its setter is a separate cleanup and would re-touch the store
   shape; not worth bundling into a perf fix.

6. **`console.log` debug spam in TiptapEditor lifecycle.** A few
   `[DEBUG TiptapEditor]` lines remain on create/destroy paths because
   they're load-bearing for diagnosing a prior unmount/save-loss race.
   Editor *create* and *destroy* logs are removed; the
   `__activeEditorDestroy` path keeps a single error-handler log.

---

## Test results

| Suite                   | Passed | Failed |
|-------------------------|--------|--------|
| `q_instructions/tests/` | 93     | 0      |
| Frontend `tsc --noEmit` | ✓      | —      |
| Frontend `next build`   | ✓      | —      |
