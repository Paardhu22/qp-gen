# DEPLOY_CHECKLIST

Pre-deploy verification for the critical fix round (Clusters A–D) + the
closeout round (auth-store determination, live verification, latent-bug
fixes). Run through this list before promoting `main` to production.
Every box must be ticked or the deploy aborts.

---

## 0. Closeout round summary

### 0.1 Auth-store decision — RESOLVED

**Login, register, and password reset all read/write the SAME column**
— `account.password`, in the table created by the (originally
Prisma-authored) better-auth schema but now owned by Django via the
`apps.accounts.models.Account` ORM model.

Trace recorded definitively in `FIX_REPORT.md` §0.0:

* FE `signIn.email` / `signUp.email` / `requestPasswordReset` /
  `resetPassword` POST to `${NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8000"}/api/auth/<endpoint>` — the **Django**
  origin, never the Next.js origin.
* `LoginView` → `authenticate_user` → `Account.check_password`
  against `account.password`.
* `RegisterView` → `register_user` → `account.set_password` →
  `account.save(update_fields=["password"])`.
* `ResetPasswordView` → `consume_reset_token` →
  `account.set_password(new_password)` →
  `account.save(update_fields=["password"])`.

The former dormant Better Auth installation on the Next.js origin has
been removed. `frontend/lib/auth.ts`, `frontend/lib/db.ts`, and
`frontend/app/api/auth/[...all]/route.ts` are deleted, along with the
stale frontend Prisma upload/retrieval scaffold and unused
`better-auth` / Prisma / `pg` dependencies. Production build verification
now confirms the Next.js origin returns **404** for `/api/auth/*`.

### 0.2 Live verification — what actually passed

Captured against the running Django backend during the closeout:

- [x] Register a fresh `welcome.test+<ts>@gmail.com` via HTTP → **201**.
- [x] Welcome email lands in the locmem outbox with subject
      `"Welcome to qp-gen"`.
- [x] Login with the registered password → **200** + token pair.
- [x] `POST /api/auth/forgot-password` → **200** (generic message).
- [x] Reset email lands in the outbox with subject `"Reset your qp-gen
      password"`. Body contains a reset link with `?token=<64 hex>`.
- [x] `POST /api/auth/reset-password` with the captured token →
      **200** `{success: true}`.
- [x] Login with the OLD password → **401** (correct rejection).
- [x] Login with the NEW password → **200** + token pair.
- [x] Stored hash format = `pbkdf2_sha256$720000$…` — Django
      `make_password()` output (no parallel scrypt/bcrypt row).
- [x] `next start` smoke: every FE route (`/`, `/login`, `/register`,
      `/forgot-password`, `/reset-password`, `/dashboard`, `/editor`,
      `/paper-library`, `/question-bank`, `/settings`) returns 200.
- [x] Test gates: backend 111/111 pytest, frontend 7/7 toDOM-shape,
      `tsc --noEmit` clean, `next build` 13 routes.

Re-runnable as `python manage.py shell -c "exec(open('scratch/
verify_auth_e2e.py').read())"` from `backend/`. Update `BASE` to the
prod origin and supply a throwaway test Gmail before promoting.

### 0.3 Bug caught during closeout — FIXED

**Symptom**: `POST /api/auth/reset-password` with a real token →
**HTTP 500**. Pre-fix code at `services/password_reset_service.py:83`
compared `verification.expires_at <= timezone.now()` (naive vs aware
→ `TypeError`). `verification.expiresAt` is `TIMESTAMP WITHOUT TIME
ZONE` in Postgres (Prisma default), so Django reads it as naive.

**Fix**: import `datetime.timezone as dt_timezone`, wrap with
`timezone.make_aware(expires_at, dt_timezone.utc)` if naive. Same
pattern already used at `apps/common/authentication.py:79-81` for
`session.expiresAt`.

**Pinned by**:
`q_instructions/tests/test_tester_round.py::
PasswordResetExpiryTzRegressionTests::
test_consume_reset_token_does_not_crash_on_valid_token`.

### 0.4 Items still requiring a real-browser pass before declaring deploy-ready

These cannot be driven from a headless test harness. The operator
should run them manually against staging before promotion:

- [ ] Editor: insert `-` (horizontal rule) 10+ times across a page
      boundary; verify no crash or layout corruption.
- [ ] Editor: insert image inside a question, click to select, press
      Delete; verify it removes cleanly.
- [ ] Editor: bold / italic / underline / strike highlight when the
      cursor is inside marked text.
- [ ] Editor: color and highlight swatches reflect the current
      selection.
- [ ] Editor: Assertion-Reason button inserts the canonical template;
      a generated paper round-trips through answer-script generation.
- [ ] Editor: Date field in header → enable → exported PDF + DOCX
      both render the date.
- [ ] Editor: paste a clipboard image; verify it renders with resize
      handles and can be dragged.
- [ ] Editor: empty paper (only an unedited "Enter question here…"
      block) → click Generate Answer Script → backend returns a clear
      400 with the empty-paper message (no hallucinated answer).
- [ ] Account isolation: sign in as user A → tray has items → sign
      out → sign in as user B → tray is empty.
- [ ] Account isolation: open in a private/clean browser profile →
      register a fresh account → tray is empty on first paint.
- [ ] Search: query the paper library and question library with
      class / subject / topic / "MCQ" tokens; verify expected matches.

---

## 1. Required environment variables

### Backend (Django)

| Var | Required | Purpose | Example |
|-----|----------|---------|---------|
| `DATABASE_URL` | yes | Postgres connection string with `pgvector` extension | `postgres://…?sslmode=require` |
| `FRONTEND_URL` | yes | Origin allowed by CORS + CSRF (must match the actual deployed FE origin, scheme included) | `https://qp.example.com` |
| `AOS_PUBLIC_MEDIA_BASE_URL` | **prod-only** | Absolute base URL that prefixes `/media/...` paths emitted by the backend. **Must be set when FE and BE are on different origins**, otherwise figure URLs persist as relative and the FE prefixes from `NEXT_PUBLIC_API_BASE_URL` instead. Set ONE of the two. | `https://api.qp.example.com` |
| `OPENAI_API_KEY` | yes | Generation + embeddings | `sk-…` |
| `SECRET_KEY` | yes | Django secret | (random 64 chars) |
| `DEBUG` | yes | Must be `False` in prod | `False` |
| `PDF_IMAGE_MIN_BYTES` | optional | Drops noise icons from PDF image extraction | `8192` |
| `PDF_IMAGE_MIN_DIMENSION` | optional | Same | `96` |
| `PDF_IMAGE_MAX_CAPTIONS` | optional | Caps OpenAI vision spend per upload | `40` |
| `OPENAI_VISION_MODEL` | optional | Vision captioning model for ingestion. Default `gpt-4o`. Tune to `gpt-4.1-mini` for slightly cheaper, or `gpt-5-mini` if you specifically want reasoning-grade captions (warning: ~10× slower) | `gpt-4o` |
| `PDF_IMAGE_CAPTION_CONCURRENCY` | optional | Parallel vision calls during ingestion (default `8`) | `8` |
| `MAX_CHUNK_REUSES` | optional | How many slots a single retrieved chunk may ground before being considered exhausted (default `3`). Lower it if generated questions feel too similar; raise it on small source corpora | `3` |
| **Email — Cluster A.1 (round 8)** | | | |
| `EMAIL_BACKEND` | **prod-only** | Django email backend. **Must be overridden in prod** or password-reset and welcome emails silently print to stdout and the user never receives them. Typical: `django.core.mail.backends.smtp.EmailBackend` (SMTP), or any anymail/SES backend you prefer | `django.core.mail.backends.smtp.EmailBackend` |
| `EMAIL_HOST` | prod-only | SMTP relay host | `smtp.sendgrid.net` |
| `EMAIL_PORT` | optional | SMTP port (default `587`) | `587` |
| `EMAIL_HOST_USER` | prod-only | SMTP username (for SendGrid this is the literal `apikey`) | `apikey` |
| `EMAIL_HOST_PASSWORD` | prod-only | SMTP password / API key | `SG.xxxx…` |
| `EMAIL_USE_TLS` | optional | `true` (default) for port 587 STARTTLS | `true` |
| `EMAIL_USE_SSL` | optional | `true` for port 465 implicit TLS — mutually exclusive with `EMAIL_USE_TLS` | `false` |
| `EMAIL_TIMEOUT` | optional | Seconds to wait for SMTP (default `20`) | `20` |
| `DEFAULT_FROM_EMAIL` | yes | From address on every outbound email — must match a verified sender on your email provider | `"qp-gen <no-reply@yourdomain.com>"` |
| `PASSWORD_RESET_TIMEOUT_SECONDS` | optional | TTL of password-reset tokens (default `3600` = 1 h) | `3600` |
| `PASSWORD_RESET_URL_PATH` | optional | Path on the FE that consumes the reset token (default `/reset-password`) | `/reset-password` |

### Frontend (Next.js)

| Var | Required | Purpose | Example |
|-----|----------|---------|---------|
| `NEXT_PUBLIC_API_BASE_URL` | **prod-only** if FE/BE on different origins; **must** be set whenever the persisted document carries `/media/…` URLs that need to resolve at render time. Mirrors the backend's `AOS_PUBLIC_MEDIA_BASE_URL`. | API + `/media` origin used by `lib/api-client.ts` and `components/editor/extensions/float-image.tsx#resolveFigureSrc` | `https://api.qp.example.com` |

**Audit rule** (Cluster D item 1): grep both repos for `localhost:8000`
before deploy. Only matches in `.env.example`, `README.md`, and the
documented fallback in `float-image.tsx`/`api-client.ts` are allowed
— any other hit is a production bug.

```bash
# Should return only the documented fallbacks + .env.example
grep -RIn "localhost:8000" backend/ frontend/ --include="*.ts" --include="*.tsx" --include="*.py"
```

---

## 1.1 Email backend acceptance test

After setting the SMTP env vars, run a single end-to-end check from the
backend shell before promoting:

```bash
cd backend && source .venv/bin/activate
python manage.py shell -c "
from django.core.mail import send_mail
from django.conf import settings
ok = send_mail(
    'qp-gen deploy smoke',
    'If you can read this, the SMTP relay is wired correctly.',
    settings.DEFAULT_FROM_EMAIL,
    ['<your-personal-address>'],
    fail_silently=False,
)
print('send_mail returned', ok)
"
```

Expected: `send_mail returned 1` AND the email lands in the inbox.
If `EMAIL_BACKEND` is left at the default console writer in prod the
command will print the email body to stdout and return 1, but no
real delivery happens — this is the most common reason teachers report
"the reset link never arrived."

---

## 2. Database migrations

Run **before** deploying the new app version:

```bash
cd backend && source .venv/bin/activate
python manage.py migrate documents
```

This applies:

* `0003_remove_pdfsource_file_fields` — drops the legacy `file` /
  `content_type` columns if Django state had them tracked. Idempotent
  via `DROP COLUMN IF EXISTS`.
* `0004_restore_pdfsource_content_type` — **Cluster B fix**.
  Idempotently restores the `content_type` column with a `NOT NULL
  DEFAULT 'application/pdf'`, then registers the field in Django
  state so `PdfSource.objects.create(content_type=...)` is valid
  Python. Safe to run on databases where the column was already
  dropped (it re-adds it) and on databases where the column survived
  with NOT NULL but no default (it attaches the default).

Migrations to **NOT** rerun manually: any of `accounts`, `projects`,
`generation` — none changed this round.

---

## 3. Verification gate (must all pass)

Run from a clean deploy candidate. State actual results, not predictions.

### A. Editor mount / unmount — Cluster A

- [ ] Open `/editor` on a paper with at least one Section block whose
      `summaryText` is non-empty AND at least one Instruction block
      with a non-empty `summaryItems` list. (The shape that previously
      threw.)
- [ ] In the browser devtools console, set a breakpoint on `RangeError`
      OR watch the live console output.
- [ ] Navigate away (e.g. `/dashboard`) and back to `/editor`.
- [ ] Expected: zero `RangeError: Content hole must be the only child
      of its parent node` messages. Console clean.

Regression coverage: `frontend/scripts/test-todom-shape.mjs` —
exercises every custom `renderHTML` against a recursive validator that
mirrors prosemirror-model's `DOMSerializer.renderSpec` rule. Run with
`node scripts/test-todom-shape.mjs` from `frontend/`.

### B. PDF source upload — Cluster B

- [ ] Migrations applied (section 2 above).
- [ ] Upload a fresh PDF source via the "Source files" panel.
- [ ] Expected: HTTP 200, no "Internal server error" toast.
- [ ] Inspect the row: `SELECT id, name, content_type, status FROM
      pdf_source ORDER BY "createdAt" DESC LIMIT 1;` — `content_type`
      must be a non-null string (e.g. `application/pdf`).
- [ ] Try a fresh paper-generation flow against the new source.
      Verify chunks are produced.

Regression coverage: `backend/apps/documents/tests.py` —
`PdfSourceContentTypeRegressionTests` covers the three relevant
paths (explicit content type, missing content type, direct create
omitting the field). Run with `python manage.py test apps.documents`
in an env where a `test_*` DB can be created (CI / clean dev).

### C. Image-based questions render — Cluster C

- [ ] Generate a paper with at least two image-based questions
      (Class 10 Maths, topics that trigger `requires_figure`:
      Triangles/Thales, Circles, Statistics—any chapter with
      diagrammed Q23 / Q33-style slots).
- [ ] Open the editor. Every image-based question must show its
      figure inline (not an empty bordered box).
- [ ] Export to PDF.
- [ ] Open the PDF in a viewer.
- [ ] Expected: **every** figure is visible. Triangles, circles,
      labels, the lot.

### D. PDF size — Cluster C

- [ ] Same paper, ~10 pages.
- [ ] `ls -lh exam-paper.pdf` → record actual size in megabytes.
- [ ] Expected: **< 5 MB** for ~10 pages. (Pre-fix benchmark from the
      brief: 90 MB / 8 pages → expect ~11 MB/page. Post-fix
      expectation: 0.2–0.5 MB/page.)
- [ ] If > 5 MB, capture the file and check it in DevTools'
      `pdf.js`: rasterised page images should be JPEG, not PNG. Look
      at any single page's `addImage` call in `lib/export-pdf.ts`.

### E. DOCX export — Cluster C

- [ ] Same paper, export to DOCX.
- [ ] Open in Word / LibreOffice.
- [ ] Expected: every figure renders. Inline SVG figures embed as
      vector (`ImageRun({ type: "svg", … })` with the rasterised
      PNG fallback); source-PDF images embed as their raster type.
- [ ] If figures are missing, the `fetch()` in `loadFigureBytes`
      most likely returned null. Check the browser network tab for
      `/media/...` requests during export: 4xx/5xx ⇒ media route
      misconfigured (nginx or CDN), CORS error ⇒ FE/BE are on
      different origins and `Access-Control-Allow-Origin` isn't set
      on the media path.

### F. Answer-script generation — Cluster D item 2

- [ ] Generate a paper with **at least 30 questions**.
- [ ] Generate the answer script.
- [ ] Expected: every answer slot has a real model answer. **Zero**
      `[Answer to be filled by teacher]` placeholders.

Regression coverage: `q_instructions/tests/test_paper_plan_fixes.py
::AnswerScriptServiceTests::test_thirty_question_paper_has_no_placeholder_answers`
— passing as of this round.

### G. Expired-session flash — Cluster D item 3

- [ ] In a logged-in session, copy the value of the `refresh_token`
      key in `localStorage`.
- [ ] Sign out via the UI. (Refresh token is cleared.)
- [ ] Manually put the **stale** refresh token back via DevTools
      `localStorage.setItem("refresh_token", "<old value>")` so the
      optimistic-render path in `ProtectedLayout` thinks the user
      is logged in.
- [ ] Visit `/editor`.
- [ ] Expected: the layout shell may render briefly (header,
      sidebar) while the session check is in flight, but the actual
      editor content **must not** show user-scoped data
      (paper title, question list, etc.) before the redirect to
      `/login` fires.
- [ ] If user-scoped content does flash, file a bug — the children
      of `ProtectedLayout` are expected to guard on
      `useSession().data?.user`. Current consumers
      (`/editor`, `/question-bank`, `/settings`) do guard correctly.

---

## 4. Post-deploy smoke (production)

After the deploy is live:

1. Hit `/api/auth/session` while logged in. Expect 200 + a user
   object.
2. Upload a tiny test PDF (1 page). Expect 200 + `pdfSourceId`.
3. Open any saved paper. Expect zero `RangeError` in the console.
4. Export the saved paper to PDF. Expect a sane file size
   (< 1 MB per page on average) and every figure present.
5. Hit `/api/generation/sse?...` to confirm SSE streaming still works.
6. Hit `/api/documents/<id>` to confirm media-served URLs resolve.
