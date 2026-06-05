# DEPLOY_CHECKLIST

Pre-deploy verification for the critical fix round (Clusters A–D).
Run through this list before promoting `main` to production. Every box
must be ticked or the deploy aborts.

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

### Frontend (Next.js)

| Var | Required | Purpose | Example |
|-----|----------|---------|---------|
| `NEXT_PUBLIC_API_BASE_URL` | **prod-only** if FE/BE on different origins; **must** be set whenever the persisted document carries `/media/…` URLs that need to resolve at render time. Mirrors the backend's `AOS_PUBLIC_MEDIA_BASE_URL`. | API + `/media` origin used by `lib/api-client.ts` and `components/editor/extensions/float-image.tsx#resolveFigureSrc` | `https://api.qp.example.com` |
| `NEXT_PUBLIC_APP_URL` | yes | Better Auth `baseURL` | `https://qp.example.com` |
| `BETTER_AUTH_URL` | yes | Better Auth server URL | `https://qp.example.com` |
| `DATABASE_URL` | yes | Prisma connection (shared with Django) | `postgres://…?sslmode=require` |

**Audit rule** (Cluster D item 1): grep both repos for `localhost:8000`
before deploy. Only matches in `.env.example`, `README.md`, and the
documented fallback in `float-image.tsx`/`api-client.ts` are allowed
— any other hit is a production bug.

```bash
# Should return only the documented fallbacks + .env.example
grep -RIn "localhost:8000" backend/ frontend/ --include="*.ts" --include="*.tsx" --include="*.py"
```

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
