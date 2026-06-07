# ISSUE_AUDIT — Pre-deploy tester round (Phase 1)

Phase 1 cross-check of the 14 tester-reported issues. Each entry records
the reproduction, the file+line responsible, the *mechanism* (not the
symptom) behind it, severity, and the proposed fix + blast radius. Phase
2 implementations and verification evidence live in `FIX_REPORT.md`;
environment + verification steps live in `DEPLOY_CHECKLIST.md`.

## Shared-root flags (fix once, not three times)

| Shared root cause                                                        | Tester issues |
|---|---|
| No email backend / endpoints / FE forms ever shipped                     | #1, #2 |
| Editor toolbar never subscribed to TipTap `selectionUpdate` / `transaction` — every read of `editor.isActive()` / `getAttributes()` was stuck at first-mount state | #5, #6 |
| Zustand `useEditorStore` persisted `generatedTray` + `generatorContext` slice in localStorage; auth flows never wiped it on signOut/signIn/signUp | #11, #12 |
| `FloatImage` paste path + image deletion both blocked by the same missing NodeView wiring (`handlePaste` absent; `Backspace` swallowed by parent block) | #9, #15 |
| Two pages parse `projectName` with literal em-dash `split(" — ")` and index only ~3 fields of ~10 the backend returns | #14 (paper search + question search) |

---

## Issue #1 — Forgot-password sends no email

* **Reproduced**: yes. UI submission resolves to a generic "if an
  account exists…" message but no email ever arrives; no row appears in
  outbox; SMTP credentials nowhere in `config/settings.py`.
* **Responsible code (before)**: nothing. Search proves the absence:

  ```
  grep -RIn "send_password_reset\|password.?reset\|EMAIL_BACKEND" backend/  →  no hits
  grep -RIn "forgot-password" frontend/  →  only the `<a href="#">` in login-form.tsx
  ```

  `frontend/components/login-form.tsx` line of the "Forgot your password?"
  link previously pointed at `#`; there were no `/forgot-password` or
  `/reset-password` routes; no `ForgotPasswordView` /
  `ResetPasswordView` in `backend/apps/accounts/views.py`; no
  `EMAIL_BACKEND` line in `backend/config/settings.py`.
* **Root cause**: the feature was never implemented — neither endpoint,
  template, FE form, nor email backend ever shipped. The Django default
  email backend (`smtp.EmailBackend`) raises on send when no SMTP creds
  are set, so even a hypothetical hand-rolled call would silently fail.
* **Severity**: deploy-blocker.
* **Proposed fix**: implement the entire flow.
  - Settings: env-driven `EMAIL_BACKEND` (default console for dev),
    `EMAIL_HOST/PORT/USER/PASSWORD/TLS/SSL/TIMEOUT`,
    `DEFAULT_FROM_EMAIL`, `PASSWORD_RESET_TIMEOUT`,
    `PASSWORD_RESET_URL_PATH`. Build the reset URL from `FRONTEND_URL`
    so prod emails never bake `localhost:3000`.
  - `services/email_service.py`: `send_password_reset_email`,
    `send_welcome_email`, both wrapping `send_mail` in try/except.
  - `services/password_reset_service.py`: SHA-256-hashed tokens stored
    in the existing `verification` table, identifier
    `password-reset:<user-id>`, single-use via
    `select_for_update` + delete. New token deletes the prior one.
  - `apps/accounts/views.py`: `ForgotPasswordView` (always 200 generic
    — account-enumeration resistance), `ResetPasswordView` (single
    generic 400 on any failure). `RegisterView` invokes
    `send_welcome_email` best-effort.
  - Frontend: `app/(auth)/forgot-password/page.tsx`,
    `app/(auth)/reset-password/page.tsx` (Suspense-wrapped because
    Next.js 16 requires it for any prerendered page calling
    `useSearchParams`); `components/forgot-password-form.tsx`,
    `components/reset-password-form.tsx`;
    `lib/auth-client.ts` gains `requestPasswordReset` + `resetPassword`;
    login-form's link points to `/forgot-password`.
* **Blast radius**: zero impact on existing endpoints — additive only.
  New rows in the `verification` table (already Prisma-created). Two
  new client routes; both prerender at build time. Pulls
  `PASSWORD_RESET_URL_PATH`, `PASSWORD_RESET_TIMEOUT` env reads — both
  have safe defaults so unset env doesn't crash.
* **DEPLOY_CHECKLIST callout**: `EMAIL_BACKEND` *must* be overridden in
  prod (default console writer prints to stdout and "delivers"
  nothing). Section 1 + 1.1 of `DEPLOY_CHECKLIST.md` enumerate every
  required var and ship a one-line SMTP acceptance test.

## Issue #2 — New-account confirmation email not sent

* **Reproduced**: yes. POST `/api/auth/register` returns 201 with token
  pair; no email arrives.
* **Responsible code (before)**: `backend/apps/accounts/views.py
  RegisterView.post` — registers + token-pairs only, no welcome-email
  call.
* **Root cause**: same as #1 — no email infrastructure existed, plus the
  registration view never attempted to send a welcome email anyway.
* **Severity**: deploy-blocker.
* **Proposed fix**: piggyback on #1's `send_welcome_email`. Call it
  *after* token issuance, best-effort, never aborts the 201 response.
* **Blast radius**: signup HTTP contract unchanged. One extra outbound
  message per successful signup; SMTP backend rate limits are the only
  ceiling.
* **Shared root with #1** — fix lands in the same patch.

## Issue #3 — Assertion-Reasoning question type missing

* **Reproduced**: yes. Toolbar has Question / MCQ / Grouped Questions /
  Header — no A-R button. Generation router *already* understands the
  `ASSERTION_REASON` enum (see `services/generation_service.py:407,
  411, 534, 968, 1041` plus `TypeFidelityTests` from a prior round) and
  Q19/Q20 of the uploaded CBSE SQP are exactly A-R, so the generator
  side is wired — only the editor entry point is missing.
* **Responsible code (before)**: `frontend/components/editor/toolbar.tsx`
  secondary toolbar (~line 1108 onward) — no A-R button next to MCQ.
* **Root cause**: feature gap. The editor never offered a way to insert
  an A-R block; users had to hand-craft one via plain paragraphs +
  ordered list and remember to set `questionType: "ASSERTION_REASON"`
  by editing the JSON.
* **Severity**: high (CBSE pattern; tester explicitly flagged it).
* **Proposed fix**: new "Assertion-Reason" button in the secondary
  toolbar (between MCQ and Header). Inserts a `questionBlock` with:
  bold "Assertion (A):" paragraph, bold "Reason (R):" paragraph,
  `orderedList` with the four canonical CBSE options, attrs
  `{ marks: 1, questionType: "ASSERTION_REASON" }`. No backend changes
  needed.
* **Blast radius**: one new button. The inserted block conforms to the
  existing `questionBlock` schema and the existing extractor in
  `services/answer_script_service.py` already classifies
  `ASSERTION_REASON` via `_classify_question_type` (see line 105). Zero
  risk to OR-group / pagination / answer-script paths.

## Issue #4 — Date field missing in header options

* **Reproduced**: yes. `PaperHeaderBlock` has logo upload + heading
  rows; no date picker, no exported date.
* **Responsible code (before)**: `frontend/components/editor/extensions/
  header-node.tsx`. `addAttributes()` carries only `logoUrl`.
* **Root cause**: feature gap.
* **Severity**: high.
* **Proposed fix**: add `showDate: boolean` (default false) and
  `dateValue: string` (ISO `YYYY-MM-DD`) attributes. React NodeView
  gains a Calendar toggle; first enable defaults to today, never
  advances implicitly. `parseHTML` / `renderHTML` round-trip the attrs
  via `data-show-date` and `data-date-value` so PDF + DOCX exports
  naturally pick up the rendered date from the DOM. Display uses
  `Intl.DateTimeFormat(undefined, { day, month, year })` for locale
  correctness.
* **Blast radius**: must preserve the round-5 ProseMirror toDOM
  invariant — *the content hole `0` must be the only child of its
  parent node*. The date row must be a sibling of the
  `paper-header-content` div (which is the hole's wrapper), not a
  sibling of the hole itself. Failing this breaks every paper that
  uses a header. `scripts/test-todom-shape.mjs` catches the regression.

## Issue #5 — Bold / italic buttons don't highlight when active

* **Reproduced**: yes. Cursor inside bold text → Bold button stays
  un-highlighted. Click formats — but the button never reflects the
  current state.
* **Responsible code (before)**: `frontend/components/editor/toolbar.tsx`
  `EditorToolbar` reads `editor.isActive("bold")` during render but
  only subscribes to `editor.on("update", debouncedRecount)` (the
  total-marks badge, 400 ms debounce). No subscription to
  `selectionUpdate` / `transaction` — so React has no reason to
  re-render when the cursor moves.
* **Root cause**: missing TipTap event subscription. The toolbar reads
  live editor state but never asks React to redraw when that state
  changes.
* **Severity**: high (visible to every user, every session).
* **Proposed fix**: add a `selectionTick` state that increments on
  `editor.on("selectionUpdate", bump)` and `editor.on("transaction",
  bump)`. Bumping forces a re-read of every `isActive` / `getAttributes`
  call. No need to mirror each attribute into its own state — editor
  selection is already the source of truth.
* **Blast radius**: one extra setState per transaction. The existing
  `debouncedRecount` (400 ms `update` listener) is unaffected. Re-render
  is cheap because the toolbar is small.
* **Shared root with #6**.

## Issue #6 — Color / highlighter swatch shows the old color

* **Reproduced**: yes. Apply color → swatch lags one selection behind
  the actual applied color. Real text color is correct; only the
  toolbar icon's visual is wrong.
* **Responsible code (before)**: same toolbar file, same root cause as
  #5 — `ColorPicker currentColor={editor.getAttributes("textStyle")?.color}`
  reads stale state because the toolbar doesn't re-render on
  selection change.
* **Root cause**: same missing `selectionUpdate` / `transaction`
  subscription as #5.
* **Severity**: high (visible polish bug; functional behaviour OK).
* **Proposed fix**: same `selectionTick` bump as #5 — the color swatch
  is one of many readers that snap back to correct as soon as the
  toolbar re-renders.
* **Blast radius**: zero additional code beyond #5's fix.
* **Shared root with #5** — single patch.

## Issue #7 — "-" button crashes/glitches near a page boundary

* **Reproduced**: yes. Insert HR repeatedly until it lands on a page
  break — layout corrupts.
* **Responsible code (before)**: `frontend/components/editor/
  toolbar.tsx` HR button → `editor.chain().setHorizontalRule().run()`.
  StarterKit's command inserts at the cursor position, but
  `horizontalRule` is *not in the content schema* of any paperBlock
  (`questionBlock`, `sectionBlock`, `instructionBlock`,
  `paperHeaderBlock` all enumerate their allowed children and HR is
  absent — see `frontend/components/editor/extensions/nodes.tsx`).
* **Root cause**: schema/insertion mismatch. When the cursor was
  inside a paperBlock the command either failed silently or
  ProseMirror split the block to fit the HR — the latter places the
  HR at the page boundary, interacting badly with the pagination
  engine. (FIX_REPORT clears the earlier hypothesis that the
  pagination logic still referenced a removed `pageBreak` node;
  that's not the mechanism here.)
* **Severity**: deploy-blocker (crashes the editor).
* **Proposed fix**: route HR through the same `insertAfterCurrentBlock`
  helper the structural buttons use. Walk ancestors → if any is in the
  `paperBlock` group, insert AFTER the outermost such ancestor;
  otherwise call the original `setHorizontalRule`. Always a legal
  placement, never triggers the pagination corner case.
* **Blast radius**: HR behaviour changes only inside paperBlocks; loose
  HR insertions at page level are unchanged. The
  `insertAfterCurrentBlock` helper is exactly the same one used by the
  Section / Question / Instruction / OR-Group / Grouped / MCQ / Header
  buttons, so the risk is bounded to whatever those already do.

## Issue #8 — "+" button too close to marks edit

* **Reproduced**: yes. In grouped / grouped-OR layouts the
  add-subquestion "+" sits ~4 px from the marks input "M" label.
* **Responsible code (before)**: `frontend/components/tiptap-editor.tsx`
  `.question-controls` CSS — `right: -28px; gap: 4px;` and no
  `padding-left`.
* **Root cause**: CSS spacing.
* **Severity**: polish.
* **Proposed fix**: push to `right: -44px`, widen `gap: 6px`, add
  `padding-left: 4px`. Bumps the control column ~20 px clear of the M
  label.
* **Blast radius**: visual only. No layout reflow at print scale
  because the controls have `print:hidden`-equivalent styling
  (`.float-image-hide-in-pdf` analog).

## Issue #9 — Pasted images can't be resized

* **Reproduced**: yes. Toolbar-inserted images get the FloatImage
  NodeView (resize + align + delete); clipboard-pasted images render
  as raw inline `image` nodes at native pixel size with no handles,
  and a paste *inside* a `questionBlock` fails entirely because
  `image` is inline-only and the questionBlock content schema
  excludes inline images.
* **Responsible code (before)**: `frontend/components/tiptap-editor.tsx`
  `useEditor({ editorProps: { attributes: ... } })` — no
  `handlePaste` is set, so TipTap's default paste handler runs.
* **Root cause**: two compounding bugs:
  - default paste creates an inline `image` node, not a `FloatImage`;
  - schema mismatch makes inline `image` illegal inside
    `questionBlock`.
* **Severity**: high.
* **Proposed fix**: add `editorProps.handlePaste`. Inspect
  `clipboardData.items`, take the first `image/*` entry, read bytes
  with `FileReader` as a data URL, dispatch
  `editor.chain().focus().insertFloatImage({ src }).run()` — same path
  the toolbar Image button uses. Non-image pastes return `false` so
  text / HTML pastes work normally.
* **Blast radius**: only affects image pastes. The handler returns
  `false` on non-image clipboard items so ProseMirror's paste machinery
  for text / HTML is untouched. Note: `tiptap-editor.tsx` also calls
  `editor.setOptions({ editorProps: { attributes: ... } })` once after
  mount; the second site does not set `handlePaste`, so the merged
  `editorProps` retains the initial paste handler — verified by
  inspection. A future contributor adding `handlePaste` to the second
  site would clobber this; flagged in `FIX_REPORT.md` "latent bugs"
  section.

## Issue #11 — Fresh account shows random questions (review tray)

* **Reproduced**: yes. Create new account on a browser that previously
  used another account → review tray contains questions the new user
  never generated.
* **Investigation matrix (the prompt's (a)/(b)/(c) question)**:
  - **(a) Backend leak?** Mechanically impossible. `grep -r
    "review-tray\|/api/.*tray" backend/` → no hits. The tray is purely
    client-side: `pushToTray` is called from the SSE handler in
    `generator-form.tsx`, mutating `useEditorStore` directly. No
    backend round trip exists, so account scoping can't fail at the
    server.
  - **(b) Client cache?** YES — see below.
  - **(c) Seed / dev data leakage?** No code path seeds the tray; ruled
    out by inspection.
* **Responsible code (before)**: `frontend/store/editor-store.ts`
  `persist({..., partialize: state => ({ insertionMode, generatedTray,
  generatorContext, template }), name: "qp-gen-editor-store" })`.
  `frontend/lib/auth-client.ts` `signIn.email`, `signUp.email`,
  `signOut` — none of them clear that localStorage key.
* **Root cause**: **Case (b)** — Zustand's `persist` middleware writes
  the `generatedTray` slice to localStorage under the
  `qp-gen-editor-store` key; auth transitions never delete it, so the
  next user inherits the prior user's tray.
* **Severity**: deploy-blocker (data hygiene / privacy concern even
  without a backend leak).
* **Proposed fix**:
  - `store/editor-store.ts`: export `EDITOR_STORE_PERSIST_KEY` +
    `resetEditorStoreForAccountSwitch()`. Helper resets in-memory state
    to clean shape, calls Zustand persist's `clearStorage()`, falls
    back to `localStorage.removeItem(EDITOR_STORE_PERSIST_KEY)` so a
    hard refresh after signOut still sees the wipe.
  - `lib/auth-client.ts`: local `clearLocalUserState()` runs the reset
    helper AND deletes the `qp_gen_editor_db` IndexedDB database (used
    by `live-document-db.ts` to cache live editor docs). Invoked from
    `signIn.email`, `signUp.email`, `signOut`. On signIn/signUp the
    call runs *before* tokens are set so the first render under the
    new identity sees clean state.
* **Blast radius**: any user who legitimately keeps a tray across
  navigations within a single session is unaffected — the wipe only
  triggers at auth transitions. IndexedDB wipe is best-effort
  (`onblocked` resolves silently); a stuck connection just delays the
  delete until next mount.
* **Regression test**: `ReviewTrayAccountIsolationTests` walks Django's
  URL resolver and asserts no pattern contains "review-tray" / "tray".
  Future engineer who adds a tray endpoint must update the test, which
  forces them to verify per-user filtering.

## Issue #12 — Pre-tagged "Inserted" blocking real inserts

* **Reproduced**: yes — same conditions as #11.
* **Responsible code (before)**: same `qp-gen-editor-store`
  localStorage blob. The `inserted: boolean` flag on each `TrayItem` is
  part of the persisted slice; once persisted, restored at next mount.
* **Root cause**: same as #11. The flag persists in the same
  localStorage blob.
* **Severity**: deploy-blocker.
* **Proposed fix**: deleted by the same wipe that fixes #11. No
  additional code path needed — removing the persisted blob removes
  every persisted flag.
* **Blast radius**: zero beyond #11.
* **Shared root with #11** — single patch handles both.

## Issue #14 — Search broken / illogical results

* **Reproduced**: yes. Two distinct broken searches:
  - `app/(dashboard)/question-bank/page.tsx` — paper search.
  - `app/(dashboard)/paper-library/page.tsx` — question search.
* **Responsible code (before)**: both pages parsed
  `projectName` via `split(" — ")` (literal em-dash). The
  question-side filter then matched only on `content`, `type`,
  `classLabel`, `subjectLabel`. The backend actually returns
  `grade_class`, `subject`, `inferred_topic`, `inferred_chapter`,
  `source_pdf`, `bloom_taxonomy`, `difficulty`, and `options` — none
  of which were searchable.
* **Root cause**: two compounding bugs.
  - **Brittle delimiter** — split assumed em-dash; real project names
    use plain hyphens, en-dashes, or no separator. When the split
    missed, `classLabel` / `subjectLabel` fell to "—" and the filter
    ignored the real project name entirely.
  - **Wrong fields indexed** — questions with subject "Math" or topic
    "trigonometry" never matched those queries because the search index
    only looked at content + parsed project labels.
* **Severity**: high (broken core UX).
* **Proposed fix**:
  - `parseProjectName` (paper-library) + `parsePaper` (question-bank)
    split on `\s*[—–\-]\s*` (em-dash, en-dash, hyphen) with whitespace
    trim. Unparseable names fall through to the haystack via raw
    `projectName`.
  - Both filters build a single lowercased haystack joined with `·`
    across every relevant field (content, answer, type, projectName,
    classLabel, subjectLabel, grade_class, subject, inferred_topic,
    inferred_chapter, source_pdf, bloom_taxonomy, difficulty, options
    array on the question side; title + projectName + classLabel +
    subjectLabel on the paper side), `.includes(term)` once. Same O(N).
* **Blast radius**: search-only. No backend, no schema changes. Results
  may include more rows than before (haystack is wider) but never
  fewer.

## Issue #15 — Inserted image can't be deleted (from within a question)

* **Reproduced**: yes. Image inside a `questionBlock` is *selectable*
  (FloatImage already declares `selectable: true`) and the React
  NodeView already has a trash button — but Delete / Backspace keyboard
  shortcut does nothing.
* **Responsible code (before)**: `frontend/components/editor/
  extensions/float-image.tsx`. The Node definition had no
  `addKeyboardShortcuts()`; the keystroke bubbled to the surrounding
  `questionBlock`, which swallowed it as "delete text at cursor" and
  left the image in place.
* **Root cause**: missing keyboard handler. The trash button works;
  only the keyboard path is broken.
* **Severity**: high.
* **Proposed fix**: `addKeyboardShortcuts()` returns
  `{ Backspace, Delete }` handlers. Both check
  `state.selection.node?.type.name === "floatImage"`; only on a
  NodeSelection over THIS node do they `deleteSelection()`. Otherwise
  return `false` so normal Backspace in surrounding text is unaffected.
* **Blast radius**: scoped to floatImage. Other selectable atoms keep
  their default behaviour. Trash button path unchanged.

## Issue #16 — Answer script hallucinates on an EMPTY paper

* **Reproduced**: yes. Open editor → click "Question" toolbar button
  once → don't edit the placeholder → save → generate answer script →
  model invents an answer to "Enter question here…".
* **Responsible code (before)**: `backend/services/answer_script_service.py
  generate_answer_script` raised `ValueError("This paper has no
  questions…")` only when zero `questionBlock` nodes were extracted.
  `_extract_questions_from_content` accepted any block whose
  `text.strip()` was non-empty. The editor's secondary toolbar inserts
  placeholder copy (`"Enter question here..."`, `"Option A/B/C/D"`,
  `"Main question statement..."`, `"Sub-question (a)..."`, etc.) the
  moment the user clicks Question / MCQ / Grouped Questions. The
  placeholder passed the non-empty check.
* **Root cause**: extractor treats unfilled template copy as a real
  question. The LLM is then asked to answer "Enter question here…" and
  dutifully hallucinates.
* **Severity**: deploy-blocker.
* **Proposed fix**:
  - Add `_PLACEHOLDER_QUESTION_TEXTS` (exact-match set covering every
    string the toolbar buttons emit).
  - Add `_is_placeholder_question(text, options)` predicate.
  - Update `_extract_questions_from_content` to skip placeholder
    blocks. The empty-paper guard at the public-API boundary therefore
    fires both for truly empty papers AND for papers full of unedited
    templates. Error message tightened to be actionable.
* **Blast radius**: backend-only. Cannot regress the prior round's
  batched generation (Step 4.5 parallel LLM calls) or the
  `[Answer to be filled by teacher]` retry — both happen *after* the
  extractor returns. Real questions are unaffected (exact-match
  predicate has zero false-positive risk on any plausible real
  question). Regression test
  `AnswerScriptEmptyPaperGuardTests` (7 cases) pins the behaviour.
* **Caveat**: if the user manually edits a placeholder to
  `"Enter question here????"`, the exact-match predicate no longer
  recognises it and a hallucinated answer can slip through. Fuzzy
  matching would trade precision for recall; not justified by the
  observed failure mode. Flagged in `FIX_REPORT.md` "latent bugs"
  section.

---

## Severity roll-up

| Severity | Issues | Count |
|---|---|---|
| Deploy-blocker | #1, #2, #7, #11, #12, #16 | 6 |
| High | #3, #4, #5, #6, #9, #14, #15 | 7 |
| Polish | #8 | 1 |
| **Total** | | **14** |

Issues #1 + #2 fix as one auth patch; #5 + #6 as one toolbar patch;
#11 + #12 as one store-wipe patch. Net distinct patches: 11.

## Phase-2 status

All 14 issues are implemented and committed. Implementation details
and code-vs-claim verification are in `FIX_REPORT.md`. Email-env
requirements and operator acceptance test are in
`DEPLOY_CHECKLIST.md`. Test gates (106/106 q_instructions, 7/7
toDOM-shape, `tsc --noEmit` clean, `next build` succeeds with 13
prerendered routes, Django `check` clean) all green.
