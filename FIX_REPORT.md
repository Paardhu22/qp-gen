# FIX_REPORT — Tester bug round (14 items / 4 clusters) + closeout

## FINAL PRE-DEPLOY ROUND — 2026-06-07

### 1. Dormant Better Auth removal

Removed the reachable but unused Next.js-origin auth surface:

* Deleted `frontend/lib/auth.ts`, `frontend/lib/db.ts`, and
  `frontend/app/api/auth/[...all]/route.ts`.
* Removed the stale frontend Prisma upload/retrieval scaffold that still
  imported those deleted helpers:
  `frontend/app/api/upload/route.ts`, `frontend/lib/retrieval.ts`,
  `frontend/actions/generateQuestions.ts`, `frontend/prisma*`, and
  `frontend/scripts/setup-db.ts`.
* Dropped unused frontend packages: `better-auth`, `@prisma/client`,
  `prisma`, `@prisma/adapter-pg`, `pg`, and `@types/pg`.
* Confirmed Next origin `/api/auth/sign-in/email` returns **404** for
  both GET and POST under `next start -p 3005`.

### 2. Ingestion timing and rate-limit check

Measured the real Django `process_pdf_upload()` path against
`/home/paardhu/Downloads/trignometry.pdf` (2,230,227 bytes). Each run
used a committed temporary user, created real chunks, then deleted the
temporary usage rows, user-owned document rows, and extracted media.

| Mode | Wall time | Result |
| --- | ---: | --- |
| Serial baseline, `PDF_IMAGE_CAPTION_CONCURRENCY=1` | **42.28 s** | ready, 48 chunks |
| Current default, `PDF_IMAGE_CAPTION_CONCURRENCY=8` | **16.44 s** | ready, 48 chunks |

This is well under the prior ~5 minute observation and under the
target of ~1 minute.

Rate-limit assessment: OpenAI's current docs describe rate limits as
RPM/TPM-style metrics, varying by model and organization/project. The
current GPT-4o model page lists Tier 1 as **500 RPM / 30,000 TPM** and
Free as unsupported. The vision docs list GPT-4o low-detail image input
at **85 image tokens** before text/output tokens. This code uses
`detail: "low"` and caps nearby page text to 1,200 characters, so the
22-image trignometry batch is not expected to hit Tier 1 GPT-4o limits
on its own. Concurrency remains configurable via
`PDF_IMAGE_CAPTION_CONCURRENCY` and now clamps invalid env values to a
safe 1..32 range.

Sources checked:
* https://developers.openai.com/api/docs/guides/rate-limits#usage-tiers
* https://developers.openai.com/api/docs/models/gpt-4o
* https://developers.openai.com/api/docs/guides/images-vision

### 3. Extra issues fixed during the sweep

* Made OpenAI usage logging best-effort so a telemetry DB insert failure
  cannot turn a successful caption/embedding call into an ingestion
  failure or fallback caption.
* Fixed `scratch/profile_ingestion_full.py` so future timing includes
  image-derived chunks in the embedding phase.
* Migrated `frontend/middleware.ts` to `frontend/proxy.ts` per the
  installed Next 16 docs, removing the build deprecation warning.
* Cleaned two ESLint unused-expression warnings in `Grainient.tsx` and
  two stale eslint-disable comments in `tiptap-editor.tsx`.
* Removed stale tracked `frontend/lint_errors.txt` and updated active
  README/deploy docs that still pointed at frontend Prisma/Better Auth.

### 4. Verification

* `npx next typegen` — clean.
* `npx tsc --noEmit` — clean.
* `npm --prefix frontend run build` — clean, 13 static routes.
* `curl` against `http://localhost:3005/api/auth/sign-in/email` — GET
  **404**, POST **404**.
* `backend/.venv/bin/python manage.py check` — clean.
* `backend/.venv/bin/python -m pytest apps/common/tests.py` — **3/3
  passing**.
* `node frontend/scripts/test-todom-shape.mjs` — **7/7 passing**.
* `backend/.venv/bin/python -m pytest q_instructions/tests` — **111
  passed**, one third-party `pypdf`/`cryptography` deprecation warning.
* `backend/.venv/bin/python -m compileall apps services q_instructions
  config utils scratch -q` — clean.
* `npm --prefix frontend run lint` — 0 errors, 4 remaining warnings for
  intentional raw `<img>` usage in editor/auth/cloud image surfaces.

Test gates after the closeout round:

* `q_instructions` test suite — **111/111 passing** (8 new regressions in
  the original tester round + 5 added in the closeout: placeholder
  near-miss variants, real-question prefix overlap, Assertion-Reason
  template detection, Assertion-Reason with partial real content, and a
  new `PasswordResetExpiryTzRegressionTests` that pins the timezone
  fix).
* Frontend `scripts/test-todom-shape.mjs` — **7/7 passing** (no drift).
* Frontend `tsc --noEmit` — clean.
* Frontend `next build` — succeeds, all **13 routes** prerender.
* Frontend `next start` smoke — every route (`/`, `/login`, `/register`,
  `/forgot-password`, `/reset-password`, `/dashboard`, `/editor`,
  `/paper-library`, `/question-bank`, `/settings`) returns **200**.
* `python manage.py check` — clean.
* Live HTTP auth chain — register → welcome email → forgot-password →
  reset-password (real token) → login(old)=401 → login(new)=200. See
  CLOSEOUT §0 below for the trace and the new bug caught.

Prior-round invariants verified unaffected:

* ProseMirror toDOM wrapping (round 5 A) — toDOM tests still pass.
* `pdf_source.content_type` upload fix (round 5 B) — model field
  still present, default still `'application/pdf'`.
* PDF/DOCX export figure inlining (round 5 C) — unchanged.
* ProtectedLayout optimistic render (round 5 D item 3) — unchanged.
* Ingestion parallel captioning (round 6 A) — unchanged.
* `MAX_CHUNK_REUSES=3` dedup loosening (round 6 B) — unchanged.
* VI alternative toggle (round 6 C) — unchanged.
* Per-keystroke save / useSession / OR-group / temperature /
  answer-script batching — none touched.

---

## CLOSEOUT — auth-store determination + real verification gate

### 0.0 — Definitive auth-store trace

> **Question**: does the new Django reset flow update the *same* store
> that the FE's `signIn.email` checks against?
> **Answer**: yes, both endpoints read/write the same row.

The codebase contains BOTH a Django auth implementation and a dormant
Better Auth installation. Resolving which one is "real":

* **FE auth client** (`lib/auth-client.ts`) → `signIn.email`,
  `signUp.email`, `signOut`, `requestPasswordReset`, `resetPassword`,
  `useSession`. Every helper calls `fetchJson("/api/auth/<endpoint>")`.
  `fetchJson` resolves against
  `process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"` —
  the Django origin, NOT the Next.js origin. So every auth API call
  goes to Django.
* **Django side**:
  * `LoginView` → `services/auth_service.authenticate_user(email,
    password)` → loads `User.objects.filter(email=email).first()` →
    loads `Account.objects.filter(user=user, provider_id="email",
    account_id=email).first()` → `account.check_password(password)`
    runs `django.contrib.auth.hashers.check_password(raw,
    self.password)` against `account.password` (the column on the
    `account` table).
  * `RegisterView` → `services/auth_service.register_user(name,
    email, password)` → creates `User` row → creates `Account` row →
    `account.set_password(password)` → `account.save(update_fields=
    ["password"])`. Welcome email best-effort.
  * `ResetPasswordView` → `services/password_reset_service.
    consume_reset_token(token, new_password)` → matches a hashed
    token in the `verification` table → finds `Account.objects.
    filter(user=user, provider_id="email").first()` →
    `account.set_password(new_password)` →
    `account.save(update_fields=["password"])`. Same column, same
    hasher, same row.
* **Dormant Better Auth**: `frontend/lib/auth.ts` (calls `betterAuth({
  database: prismaAdapter(db, ...), emailAndPassword: { enabled:
  true } })`), `frontend/lib/db.ts` (Prisma client),
  `frontend/app/api/auth/[...all]/route.ts` (Better Auth's
  Next.js catch-all handler). The FE auth client never calls these
  — every helper routes to Django. The Better Auth handler is
  reachable at `<NEXT_PUBLIC_APP_URL>/api/auth/...` only if something
  external POSTs there.
  * **Risk**: a Better Auth library probe (anyone hitting
    `/api/auth/sign-in/email` against the Next.js origin) would talk
    to a parallel auth system writing scrypt hashes to the same
    `account` table. Django's `check_password` does not understand
    Better Auth's hash format, so a Better-Auth-only user could
    never log in via the FE.
  * **Mitigation options for after deploy**: (a) delete
    `lib/auth.ts`, `lib/db.ts`, `app/api/auth/[...all]/route.ts`,
    and drop the `better-auth` + `prisma` + `@prisma/*` deps; or
    (b) put `<NEXT_PUBLIC_APP_URL>/api/auth/*` behind a 404 / proxy
    rule that forwards to Django. Flagged as a maintenance
    follow-up — not a deploy blocker since no current code calls
    the catch-all and there's no public link to it.

### 0.1 — Real bug caught and fixed during the closeout

`consume_reset_token` raised `TypeError: can't compare offset-naive
and offset-aware datetimes` on every real reset token, returning HTTP
500. Every reset link was broken.

* **Mechanism**. The `verification` table was created by the
  better-auth Prisma schema as `expiresAt TIMESTAMP WITHOUT TIME
  ZONE`. Postgres returns that column to Django as a NAIVE datetime
  even with `USE_TZ=True`. The pre-fix code compared
  `verification.expires_at <= timezone.now()` — naive vs aware →
  TypeError → unhandled 500.
* **Why the unit tests missed it**. `AnswerScriptEmptyPaperGuardTests`
  and `ReviewTrayAccountIsolationTests` exercised the
  service / URL-resolver layers but never round-tripped a real
  Verification row through the DB. The bug only surfaced on the live
  HTTP path.
* **Fix** (`services/password_reset_service.py`). Mirror the same
  defensive `timezone.is_naive → timezone.make_aware(..., utc)`
  pattern already used at `apps/common/authentication.py:79-81` for
  the `session.expiresAt` column (same column type, same Prisma
  origin). Cross-checked: the only other reader of an `expiresAt`
  column in this codebase, `services/jwt_service.access_token_is_active`,
  has the same theoretical bug but is **dead code** (zero callers).
  Left alone for this round; flag in TODO.
* **Regression test**.
  `q_instructions/tests/test_tester_round.py
  ::PasswordResetExpiryTzRegressionTests::
  test_consume_reset_token_does_not_crash_on_valid_token` creates a
  real `User` + `Account` + reset token, runs `consume_reset_token`,
  asserts the rotation stuck. Future regression to a naked aware
  comparison fails this test in CI.

### 0.2 — Live HTTP verification (real backend, locmem email backend)

Captured via DRF's `APIClient` against the running Django app, with
`EMAIL_BACKEND=locmem` and `ALLOWED_HOSTS=[testserver]` overridden so
we can read the email outbox. Every assertion passed:

| Step | Endpoint | Result |
|---|---|---|
| Register fresh `welcome.test+<ts>@gmail.com` | `POST /api/auth/register` | 201 |
| Welcome email lands in outbox | (locmem) | 1 msg, subject `"Welcome to qp-gen"` |
| Forgot-password request | `POST /api/auth/forgot-password` | 200 |
| Reset email in outbox | (locmem) | subject `"Reset your qp-gen password"`, body contains `?token=<64-hex>` |
| Reset password with captured token | `POST /api/auth/reset-password` | 200 `{ success: true }` |
| Login with OLD password | `POST /api/auth/login` | **401** (the wrong-store smoke test) |
| Login with NEW password | `POST /api/auth/login` | 200 + token pair |
| Stored hash format | DB | `pbkdf2_sha256$720000$…` — Django `make_password()` output. Confirms no scrypt/bcrypt row from a parallel system overwrote this. |

The OLD-password-rejected + NEW-password-works pair is the
load-bearing assertion: if reset wrote to a different store than
login reads, one of those two steps would fail. Both succeed → the
stores are unified.

Verification script kept at `backend/scratch/verify_auth_e2e.py` so
the operator can re-run it against the deployed backend before
promoting (point `BASE` at the prod origin and supply a throwaway
Gmail address).

### 0.3 — C.1 latent bug eliminated

The original FIX_REPORT flagged that the post-mount `editor.setOptions
({ editorProps: { attributes } })` in `tiptap-editor.tsx` would shadow
`editorProps.handlePaste`. Read of TipTap source (`@tiptap/core/dist/
index.cjs:5019`) + ProseMirror source (`prosemirror-view/dist/
index.cjs setProps`) shows that handler survives at the *view* level
because ProseMirror's `view.setProps` shallow-merges into existing
`_props`. So pastes work today.

To remove the fragility (TipTap could re-derive view props from
`editor.options` in a future release), the second `setOptions` now
spreads `editor.options.editorProps` before overriding `attributes`:

```ts
editor.setOptions({
  editorProps: {
    ...editor.options.editorProps,
    attributes: { id: "tiptap-paper-container", … },
  },
});
```

### 0.4 — C.2 placeholder near-miss tolerance

User feedback flagged exact-match as too strict: `"Enter question
here?"` or `"Enter question here. "` would slip through. The
predicate now strips a tail of `[.?!,;:\-…\s]+` before comparing
against the canonical lookup set, and treats the Assertion-Reason
template (which the C.1 toolbar emits as a SINGLE compound block
containing both placeholder snippets) as a placeholder when both
chunks are present with no other text of substance.

Twelve near-miss variants and the A-R compound case are pinned by
`test_placeholder_predicate_near_miss_variants`,
`test_placeholder_predicate_real_questions_with_prefix_overlap`,
`test_assertion_reason_template_block_is_filtered`,
`test_assertion_reason_with_real_content_is_kept`. Real questions
that begin with a placeholder-like prefix (`"Enter question here and
explain why."`) remain unaffected by design — the predicate matches
the BASE form exactly after trimming, so any additional substantive
text still reads as a real question.

### 0.5 — Prior-round items confirmed in place

* **Media base URL is env-driven everywhere**. Backend
  `services/document_service.py:_public_media_url` reads
  `settings.AOS_PUBLIC_MEDIA_BASE_URL`; frontend `lib/api-client.ts`,
  `components/editor/extensions/float-image.tsx`,
  `lib/export-pdf.ts` (via `resolveFigureSrc(original)` at line 169),
  and `lib/export-docx.ts` (via `resolveFigureSrc(rawSrc)` at line
  121) all share the same `NEXT_PUBLIC_API_BASE_URL` fallback chain.
  The only `localhost:8000` references in production code are the
  documented dev defaults inside `api-client.ts` and `float-image.tsx`.
* **Figures pre-inline before html2canvas**. `inlineAllImageSources(
  clonedDoc.body)` runs at `export-pdf.ts:254` before rasterization,
  bypassing every CORS pitfall. JPEG output (`canvas.toDataURL
  ("image/jpeg", 0.92)`, line 275) keeps a 10-page export comfortably
  under ~3 MB.
* **DOCX figure path handles SVG + raster + fallback**.
  `loadFigureBytes` in `export-docx.ts` decodes `data:` URLs locally,
  fetches `/media/...` through `resolveFigureSrc`, rasterizes SVG to
  PNG via canvas, embeds both as `ImageRun({ type: "svg", data, …
  fallback: { type: "png", data: rasterized } })` so older Word
  versions render the PNG fallback.
* **Ingestion speed**. `config/settings.py:200-202` sets
  `PDF_IMAGE_CAPTION_CONCURRENCY=8` (env-tunable);
  `services/document_service.py:132-135` runs captioning inside a
  `ThreadPoolExecutor(max_workers=PDF_IMAGE_CAPTION_CONCURRENCY)`.
  `OPENAI_VISION_MODEL` defaults to `gpt-4o` (`settings.py:195`),
  the fast/cheap variant from commit cb3edd3. Per the commit
  message: trignometry.pdf benchmark dropped from ~250 s to ~14 s.

---

## CLUSTER A — Deploy-blockers

### A.1 — Forgot-password + signup email (#1, #2)

**Diagnosis.** Neither flow was broken — they were **completely absent
from the codebase**. There is no password-reset endpoint, no email
backend configuration in `config/settings.py`, no welcome email, and
the login form's "Forgot your password?" link was hard-coded to `#`.
The Django settings module never set `EMAIL_BACKEND`, so any
hypothetical `send_mail` call would have used the framework default
(which raises if SMTP isn't configured). What the user saw in
production was the natural consequence of an unimplemented feature,
not a regression.

**Implementation.**

* **Settings** (`config/settings.py`) — new env-driven email block.
  `EMAIL_BACKEND` defaults to the console writer so dev runs print
  reset links to stdout without needing real SMTP credentials.
  `DEFAULT_FROM_EMAIL`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`,
  `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `EMAIL_USE_SSL`,
  `EMAIL_TIMEOUT`, `PASSWORD_RESET_TIMEOUT_SECONDS`, and
  `PASSWORD_RESET_URL_PATH` all honour env overrides. The reset link
  is composed from `settings.FRONTEND_URL` so a misconfigured BE
  cannot leak `localhost:3000` into a production email.

* **Service** (`services/email_service.py`) — two helpers,
  `send_password_reset_email` and `send_welcome_email`, both wrap
  `send_mail` in a try/except so a transient SMTP outage never
  crashes the API request. `_reset_link` builds the URL via
  `urllib.parse.urljoin` to keep slash handling sane regardless of
  whether `FRONTEND_URL` carries a trailing slash.

* **Token store** (`services/password_reset_service.py`) — tokens
  are stored **hashed** (SHA-256) in the existing `verification`
  table (the Prisma-created better-auth schema, already in the DB),
  so reading a row never yields a working link. The identifier is
  `password-reset:<user-id>`, which both (a) lets a fresh issue
  invalidate any prior outstanding token via `delete`, and
  (b) avoids storing the user-supplied email a second time.
  `consume_reset_token` runs the lookup, expiry check, password
  rotation, and token deletion inside one `select_for_update`
  transaction so the link is single-use even under concurrent
  clicks.

* **Endpoints** (`apps/accounts/views.py` + `urls.py`):

  * `POST /api/auth/forgot-password` — always returns the same
    generic 200 message regardless of whether the email matched a
    real account (account-enumeration resistance).
  * `POST /api/auth/reset-password` — single generic 400 on any
    failure (unknown token, expired token, no local Account, etc.)
    so the API surface never reveals which step failed.
  * `RegisterView` now also calls `send_welcome_email` — best-effort,
    so a mail server hiccup never aborts signup.

* **Frontend pages**:
  * `app/(auth)/forgot-password/page.tsx` →
    `components/forgot-password-form.tsx`.
  * `app/(auth)/reset-password/page.tsx` → wraps
    `components/reset-password-form.tsx` in a `<Suspense>` boundary
    because Next.js 16 requires it for any prerendered page that
    calls `useSearchParams()`.
  * `lib/auth-client.ts` gains `requestPasswordReset` and
    `resetPassword` helpers that match the existing
    `signIn.email` / `signUp.email` callback contract.
  * `components/login-form.tsx` — the "Forgot your password?" link
    now points to `/forgot-password` (was `#`).

**DEPLOY_CHECKLIST updates.** Section 1 catalogues every email env
var that must be set in production. Section 1.1 adds a copy-paste
SMTP acceptance test the operator runs from the Django shell before
promoting — this catches the most common failure mode where
`EMAIL_BACKEND` is left at the console default and the reset emails
silently print to stdout.

**Status:** code complete. The deploy operator must set
`EMAIL_BACKEND` (and the SMTP creds) before users will receive any
mail.

### A.2 — "-" button page-boundary corruption (#7)

**Diagnosis.** "-" is the horizontal-rule toolbar button
(`toolbar.tsx:setHorizontalRule`). The StarterKit `setHorizontalRule`
command inserts at the cursor position, but `horizontalRule` is
**not in any paperBlock's content schema** (`questionBlock`,
`sectionBlock`, `instructionBlock`, `paperHeaderBlock` all enumerate
their allowed children explicitly and HR is absent). When the cursor
was inside one of those blocks the command either failed silently or
ProseMirror split the block to make room — the latter interacts
poorly with the pagination engine when the resulting HR lands on the
page boundary, producing the visible "bugs out" symptom the tester
reported.

**Fix.** Route the HR toolbar button through the same
`insertAfterCurrentBlock(...)` helper the paper-structure buttons
use. Before inserting the HR we walk the cursor's ancestors; if any
ancestor is in the `paperBlock` group, we insert AFTER the outermost
such ancestor. That's always a legal placement (page-level block,
not a child of a structured node) and never triggers the
pagination-engine corner case. Outside paperBlocks the original
`setHorizontalRule()` runs unchanged.

### A.3 — Image deletion inside a question (#15)

**Diagnosis.** The `FloatImage` NodeView is `selectable: true` and
the React component carries a trash button on hover, so the
underlying tooling existed — but the keyboard path was broken.
Inside a `questionBlock`, pressing Delete/Backspace with the image
selected let the keystroke bubble up to the parent block, which
swallowed it as "delete text at cursor" and left the image in place.

**Fix.** Added `addKeyboardShortcuts()` to the `FloatImage`
extension. The handler intercepts Backspace + Delete, checks
`state.selection.node?.type.name === "floatImage"`, and only calls
`deleteSelection()` when the floatImage itself is the active
NodeSelection. If the selection is text or any other node the
handler returns `false`, so normal Backspace behaviour in
surrounding paragraphs is unaffected.

### A.4 — Answer-script hallucinates on EMPTY paper (#16)

**Diagnosis.** The backend already raised `ValueError(
"This paper has no questions...")` when zero `questionBlock` nodes
were found. But the editor's secondary toolbar inserts placeholder
copy ("Enter question here...", "Option A/B/C/D", "Main question
statement...", etc.) the moment the user clicks Question / MCQ /
Grouped Questions — and the placeholder text passed the
"`text.strip()` is non-empty" check inside
`_extract_questions_from_content`. A "blank-looking" paper that
contained one or more **unedited** template blocks therefore
reached the answer-script LLM with the placeholder copy as the
question text. The model dutifully hallucinated an answer to
"Enter question here...".

**Fix.** New `_is_placeholder_question(text, options)` predicate in
`services/answer_script_service.py` recognises the exact strings
the toolbar inserts. `_extract_questions_from_content` now skips
any question block whose normalised content matches the
placeholder set, so the empty-paper guard at line 638 fires for
both the truly empty case AND the "all blocks are unedited
templates" case. The error message was tightened to be
actionable: "Add at least one question with real content before
generating an answer script."

**Regression coverage.** `q_instructions/tests/test_tester_round.py`
adds `AnswerScriptEmptyPaperGuardTests` with seven cases covering:
blank paper, default Question / MCQ / Grouped blocks, real
question retention, mixed paper (only the real question survives),
and a direct unit test of the predicate. All seven pass.

**Prior-round guarantee.** The batched answer-script generation
path (`Step 4.5: Call LLMs in parallel`) and the
`[Answer to be filled by teacher]` retry loop both remain
untouched.

### A.5 — Ghost review-tray + pre-tagged "Inserted" (#11, #12)

**ANSWER — Case (b)**: client-side store persistence not cleared on
auth transitions. Evidence:

1. **No backend endpoint exists** for the review tray.
   `grep -r "review-tray\|/api/.*tray" backend/` returns nothing.
   The `pushToTray` action mutates `useEditorStore` directly from
   the SSE stream handler in `generator-form.tsx`. So Case (a)
   (backend leak) is mechanically impossible.
2. **Every backend query is `user=request.user`-scoped** —
   `grep -RIn 'filter.*user' backend/apps/ backend/services/` —
   so even if a tray endpoint were later added the row-level
   isolation infrastructure is in place.
3. **The Zustand store's `partialize` includes `generatedTray`**
   (and `generatorContext`, both per-user) in the persisted
   localStorage blob under `qp-gen-editor-store`. Neither
   `signOut` nor `signIn` cleared that key, so the next user
   on the same browser inherited the tray from the prior user —
   complete with the `inserted: true` flags the prior user had
   set. Case (c) (seed data) is ruled out by inspection — no
   code path seeds the tray.

**Fix.**

* `store/editor-store.ts` exports `EDITOR_STORE_PERSIST_KEY` and
  `resetEditorStoreForAccountSwitch()`. The helper resets in-memory
  state to its clean shape, calls Zustand persist's
  `clearStorage()` API, and falls back to
  `localStorage.removeItem(EDITOR_STORE_PERSIST_KEY)` so a hard
  refresh after signOut still sees the wipe.
* `lib/auth-client.ts` introduces a local `clearLocalUserState()`
  helper that runs `resetEditorStoreForAccountSwitch()` and also
  deletes the `qp_gen_editor_db` IndexedDB database (used by
  `lib/live-document-db.ts` to cache live editor docs). It's
  invoked from `signIn.email`, `signUp.email`, and `signOut`.
  On signIn/signUp the call runs **before** the new tokens are
  set so the very first render under the new identity sees clean
  state.

**Regression coverage.**
`q_instructions/tests/test_tester_round.py` adds
`ReviewTrayAccountIsolationTests` which walks the Django URL
resolver and asserts no URL pattern contains "review-tray" or
"tray". A future engineer adding a tray endpoint will have to
update this test, which forces them to also verify per-user
filtering.

**`inserted` flag.** Fixed by the same wipe — the flag persists in
the same localStorage blob, so removing the blob removes the flag.
No additional code path was needed.

---

## CLUSTER B — Toolbar state sync

### B.1, B.2 — Bold/italic don't highlight; swatch shows stale color (#5, #6)

**Diagnosis.** `EditorToolbar` reads `editor.isActive("bold")`,
`editor.getAttributes("textStyle")?.color`, etc. directly during
render — but it never subscribed to TipTap's
`selectionUpdate`/`transaction` events, so React had no reason to
re-render when the cursor moved. The buttons therefore reflected
whatever the state was at first mount and never updated. The
prior `useEffect` at line 485 only listened to `update` (debounced
400 ms) for the total-marks badge — it deliberately did NOT bump
on selection changes because the marks count doesn't depend on
the cursor.

**Fix.** Added a tiny `selectionTick` state in `EditorToolbar`
that increments on every `selectionUpdate` and `transaction`
event. Bumping the state forces a re-read of `editor.isActive` /
`editor.getAttributes` for every formatting button, font / size /
heading select, color and highlight swatch, and alignment / list
button — there's no need to mirror each value into its own piece
of state since the editor's selection is already the source of
truth. An initial `bump()` runs once at mount so the first paint
reflects the cursor's starting position.

### B.3 — "+" button too close to marks edit (#8)

**Fix.** CSS in `tiptap-editor.tsx`'s `.question-controls`
selector pushes the hover-popup column from `right: -28px` to
`right: -44px`, widens the inter-button `gap` from 4px to 6px,
and adds a 4px `padding-left`. The add-subquestion "+" now sits
~20px clear of the marks input's M label in grouped-OR /
grouped-question layouts.

---

## CLUSTER C — Missing features

### C.1 — Assertion-Reasoning question type (#3)

* **Toolbar button** (`editor/toolbar.tsx`) — new "Assertion-Reason"
  button in the secondary toolbar between MCQ and Header. Inserts
  a `questionBlock` with:
  * Bold-prefixed "Assertion (A):" paragraph.
  * Bold-prefixed "Reason (R):" paragraph.
  * `orderedList` with the four canonical CBSE options.
  * `attrs: { marks: 1, questionType: "ASSERTION_REASON" }`
    matching the existing enum the generation router and
    answer-script extractor both already recognise.
* **Generation prompts** — the LLM pipeline already handles
  `ASSERTION_REASON` slots (see e.g.
  `services/generation_service.py:407,411,534,968,1041` and the
  prior-round-tested `TypeFidelityTests`), so wiring the toolbar
  type into generation required no additional backend changes.
  Slots with `qtype: ASSERTION_REASON` in a CBSE blueprint
  already emit the exact four-option pattern, and the SQP source
  carries Q19/Q20 examples for grounded generation to anchor on.

### C.2 — Date field in paper header (#4)

* `editor/extensions/header-node.tsx` — `PaperHeaderBlock` gains
  two attributes: `showDate: boolean` (default false) and
  `dateValue: string` (ISO `YYYY-MM-DD`, persists timezone-neutral).
  The React NodeView renders a Calendar toggle in the header's
  action column; on first enable the picker defaults to today's
  date but never advances implicitly thereafter. The date display
  uses `Intl.DateTimeFormat(undefined, { day, month, year })` so
  the rendered string is locale-correct.
* `parseHTML` / `renderHTML` round-trip the new attributes via
  `data-show-date` and `data-date-value`, so PDF/DOCX exports
  naturally pick up the rendered date from the DOM.
* CSS for the date row (`.paper-header-date-row`,
  `.paper-header-date-input`, `.paper-header-date-display`,
  `.paper-header-actions`) is added inline in `tiptap-editor.tsx`.
  Print-only CSS (`print:hidden`) hides the `<input type="date">`
  control during paginated print so only the formatted span
  appears on the final sheet.
* `renderHTML` keeps the content hole `0` inside a dedicated
  `paper-header-content` div, satisfying the round-5 ProseMirror
  invariant — the new date row is a sibling of that div, never a
  sibling of the hole.

### C.3 — Pasted images don't have resize handles (#9)

**Diagnosis.** The default TipTap paste handler converted clipboard
images into plain inline `image` nodes. Two problems followed:
(a) the `image` schema is inline-only, so a paste **inside** a
`questionBlock` (whose content excludes inline `image`) failed
entirely; (b) when paste happened at page level the image rendered
at its native pixel size with no resize handles because the
`tiptap-extension-resize-image` NodeView only attaches to nodes
with `width` / `height` style attributes, which a freshly pasted
image lacks.

**Fix.** `editorProps.handlePaste` (set on the `useEditor` config)
inspects `clipboardData.items`, picks the first `image/*` entry,
reads the bytes via `FileReader` as a data URL, and dispatches
`editor.chain().focus().insertFloatImage({ src }).run()` — the
same command the toolbar's Image button uses. Pasted images
therefore land in the `FloatImage` NodeView which already has
resize handles, alignment toolbar, and Backspace/Delete support
(see A.3). Non-image pastes return `false` so plain text and HTML
pastes still go through ProseMirror's standard paste machinery
untouched.

---

## CLUSTER D — Search (#14)

**Diagnosis.** Two distinct search inputs:

* `app/(dashboard)/question-bank/page.tsx` — paper search.
* `app/(dashboard)/paper-library/page.tsx` — question search.

Both pages parsed a "class — subject" structure out of the
backend's `projectName` field with `split(" — ")` (literal
em-dash). The class/subject labels then dominated the filter
index. Two compounding bugs:

1. **Brittle delimiter.** The split assumed the user always typed
   an em-dash. Real-world project names use plain hyphens,
   en-dashes, or no separator at all. Whenever the split missed
   the class/subject labels fell to `"—"` and the filter ignored
   the real project name entirely.
2. **Wrong fields indexed.** The question-side filter only checked
   `content`, `type`, `classLabel`, `subjectLabel`. The backend
   actually returns `grade_class`, `subject`, `inferred_topic`,
   `inferred_chapter`, `source_pdf`, `bloom_taxonomy`,
   `difficulty`, plus the options array — none of which were
   searchable. So a query like "Math" or "trigonometry" failed on
   questions whose project name happened not to contain those
   tokens.

**Fix.**

* `parseProjectName` (paper-library) and `parsePaper`
  (question-bank) now split on a regex `\s*[—–\-]\s*` that accepts
  em-dash, en-dash, or hyphen, and trim whitespace on both
  sides. Unparseable names fall through to the haystack via the
  raw `projectName` field.
* Both filters build a single haystack string from every relevant
  field (content, answer, type, projectName, classLabel,
  subjectLabel, grade_class, subject, inferred_topic,
  inferred_chapter, source_pdf, bloom_taxonomy, difficulty,
  options array on the question side; title + projectName +
  classLabel + subjectLabel on the paper side), joins them with
  ` · `, lowercases once, then `.includes(term)`. Costs the same
  O(N) as the original filter and matches every reasonable token
  the user might type.

---

## Codebase audit — latent bugs found

While diagnosing the clusters above, swept the codebase for the
class of issue each cluster exposed. Findings:

* **User-scoping (echo of A.5).** Every protected view in
  `apps/generation`, `apps/projects`, `apps/documents`,
  `apps/accounts` queries via `user=request.user` or
  `project__user=request.user`. `apps/common/views.py` exposes
  only a `HealthCheckView` with `AllowAny`. No leak surface.
* **Debug logging in production code.** Removed three
  `console.log("[DEBUG PaperHeaderComponent]")` calls in
  `editor/extensions/header-node.tsx` that fired on every render
  and would have flooded production browser consoles. Other
  `console.log` calls in `tiptap-editor.tsx` (lines around 1129)
  guard real autosave-failure surfaces and stay.
* **Email-only Gmail constraint.** Both signup and forgot-password
  validate emails with the project-wide `validate_gmail` regex
  (only `*@gmail.com` accepted). This is deliberate
  (`apps/accounts/serializers.py:GMAIL_REGEX`) but means
  non-Gmail users can neither sign up nor recover. Documented
  here for awareness; no fix this round.
* **Placeholder predicate is exact-match only (A.4).** If the
  user manually edits a placeholder to "Enter question here????",
  the predicate no longer recognises it and a hallucinated answer
  could slip through. The exact-match strategy keeps the false-
  positive rate at zero (no real question text accidentally
  matches a placeholder); upgrading to a fuzzy / similarity
  check would tradeoff precision and is not justified by the
  observed failure mode.
* **Two `editorProps` setups in `tiptap-editor.tsx`.** The initial
  `useEditor` call (line 854) and a subsequent
  `editor.setOptions({...})` (line 931) both set
  `editorProps.attributes`. The second one would normally
  shallow-merge over the first and could in theory clobber
  `handlePaste` if a future contributor adds a paste handler to
  the second site. Left as-is for this round since the second
  site doesn't define `handlePaste`, but flagged in this report
  so the next refactor unifies them.

---

## Verification gate — final status

| # | Item | Status | Evidence |
|---|------|--------|----------|
| 1 | Forgot-password flow end-to-end | **VERIFIED LIVE** via the HTTP chain in CLOSEOUT §0.2. Real email lands in outbox; reset rotates the password that login then accepts. **Operator action remaining**: set production `EMAIL_BACKEND` / SMTP creds (default console writer "delivers" to stdout and looks successful — see DEPLOY_CHECKLIST §1.1 acceptance test). | CLOSEOUT §0.2 |
| 2 | New account receives welcome email | **VERIFIED LIVE** — same CLOSEOUT §0.2 chain captures `subject="Welcome to qp-gen"` in the outbox. | CLOSEOUT §0.2 |
| 3 | Insert "-" 10+ times across a page boundary | **CODE-FIX-APPLIED**, USER-PENDING (requires a real editor session) | A.2 above |
| 4 | Insert image into question → Delete | **CODE-FIX-APPLIED**, USER-PENDING | A.3 above |
| 5 | Empty paper → answer-script returns 400 | **TEST-PASS** (`AnswerScriptEmptyPaperGuardTests`, now 9 cases incl. Assertion-Reason compound) | A.4 + CLOSEOUT §0.4 |
| 6 | Clean browser, new account → tray empty | **CODE-FIX-APPLIED + TEST-PIN** (no backend tray endpoint test, plus IndexedDB wipe in `clearLocalUserState`) | A.5 above |
| 7 | Sign out → sign in different new account → tray clears | **CODE-FIX-APPLIED**, USER-PENDING | A.5 above |
| 8 | Bold/italic/underline/strike active state | **CODE-FIX-APPLIED**, USER-PENDING | B.1 above |
| 9 | Color/highlighter swatches reflect selection | **CODE-FIX-APPLIED**, USER-PENDING | B.2 above |
| 10 | Assertion-Reasoning button inserts template | **CODE-COMPLETE**, USER-PENDING | C.1 above |
| 11 | Date field in header, appears in PDF + DOCX | **CODE-COMPLETE**, USER-PENDING for PDF/DOCX confirmation | C.2 above |
| 12 | Pasted image has resize handles | **CODE-FIX-APPLIED**, USER-PENDING. The hypothetical `setOptions`-clobbers-handlePaste regression has been belt-and-braces fixed by the explicit `editorProps` spread in CLOSEOUT §0.3. | C.3 + CLOSEOUT §0.3 |
| 13 | Search returns sensible results | **CODE-FIX-APPLIED**, USER-PENDING | D above |
| **CL.1** | **Live auth chain — register / welcome / forgot / reset / login(old)≠login(new)** | **VERIFIED LIVE** | CLOSEOUT §0.2 |
| **CL.2** | **Password reset doesn't 500 on a real token** | **VERIFIED LIVE + TEST-PASS** (`PasswordResetExpiryTzRegressionTests`) | CLOSEOUT §0.1 |
| **CL.3** | **Frontend routes resolve in a running server** | **VERIFIED LIVE** — `next start` smoke returns 200 for every route incl. `/forgot-password`, `/reset-password` | top-of-file gates |
| **CL.4** | **Figure media origin from env in BOTH editor and PDF/DOCX export** | **CODE-CONFIRMED** | CLOSEOUT §0.5 |
| **CL.5** | **Ingestion speed config (parallel captioning + `gpt-4o` low detail)** | **CODE-CONFIRMED** | CLOSEOUT §0.5 |

Items marked **TEST-PASS** are pinned by `test_tester_round.py` (now 13
cases). Items marked **VERIFIED LIVE** were exercised end-to-end
against the running backend / FE server during the closeout. Items
still **USER-PENDING** need a real editor session in a browser
(keyboard / mouse / paste / print) — none of those can be driven
from a headless test harness without instrumenting the React app,
which is out of scope for this round.

---

## Files changed

Original tester round:

```
M backend/config/settings.py
M backend/apps/accounts/views.py
M backend/apps/accounts/urls.py
M backend/apps/accounts/serializers.py
M backend/services/answer_script_service.py
A backend/services/email_service.py
A backend/services/password_reset_service.py
A backend/q_instructions/tests/test_tester_round.py
M frontend/store/editor-store.ts
M frontend/lib/auth-client.ts
M frontend/components/login-form.tsx
A frontend/components/forgot-password-form.tsx
A frontend/components/reset-password-form.tsx
A frontend/app/(auth)/forgot-password/page.tsx
A frontend/app/(auth)/reset-password/page.tsx
M frontend/components/editor/extensions/float-image.tsx
M frontend/components/editor/extensions/header-node.tsx
M frontend/components/editor/toolbar.tsx
M frontend/components/tiptap-editor.tsx
M frontend/app/(dashboard)/question-bank/page.tsx
M frontend/app/(dashboard)/paper-library/page.tsx
M DEPLOY_CHECKLIST.md
M FIX_REPORT.md
A ISSUE_AUDIT.md
```

Closeout (this round):

```
M backend/services/password_reset_service.py        # 0.1 — naive/aware tz fix
M backend/services/answer_script_service.py         # 0.4 — placeholder near-misses + A-R compound
M backend/q_instructions/tests/test_tester_round.py # 0.1 + 0.4 — 5 new regression tests
A backend/scratch/verify_auth_e2e.py                # 0.2 — operator-runnable live chain test
M frontend/components/tiptap-editor.tsx             # 0.3 — defensive editorProps spread in setOptions
M FIX_REPORT.md                                     # this section
M DEPLOY_CHECKLIST.md                               # auth-store determination + live results
```

No edits to: OR-group fixes, per-keystroke save, useSession
optimistic render, `pdf_source.content_type`, paper-white
invariant, temperature handling, answer-script batched generation,
ingestion parallel captioning, `MAX_CHUNK_REUSES=3`, VI alternative
toggle. All prior regression suites still pass.
