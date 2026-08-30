# QP-Gen Feature Audit

*Audited at `main@5996aa4`, 2026-08-30. Scope: what the product actually offers, where it offers the same thing twice, what is built but unreachable, and where the scope has drifted. This is a **feature and surface-area** audit — not visual design ([`ui-audit-and-animation-playbook.md`](./ui-audit-and-animation-playbook.md)) and not user guidance ([`ux-guidance-audit.md`](./ux-guidance-audit.md)).*

**Method:** enumerated backend apps, models, and every routed endpoint; matched each against frontend callers; resolved every non-primitive component to its importers. Counts are reproducible — the command shape is stated wherever a number appears.

---

## Table of Contents

1. [Headline](#headline)
2. [Feature inventory](#feature-inventory)
3. [Duplicates and overlaps](#duplicates-and-overlaps)
4. [Built but unreachable](#built-but-unreachable)
5. [Questionable scope](#questionable-scope)
6. [Where the scope can improve](#where-the-scope-can-improve)
7. [Recommendations](#recommendations)
8. [Open questions](#open-questions)

---

## Headline

**Three separate question-generation engines exist in this repository, totalling ~30,000 lines. Two of them are live, one is off by default and reachable only through a hardcoded test endpoint.**

Everything else in this document is smaller than that, and most of it is downstream of the same cause: features got built a second time rather than the first one being extended.

| Generation codebase | LOC | Files | Status |
|---|---:|---:|---|
| `q_instructions/` | 14,173 | 86 | **Live** — `services/generation_router.py:9` imports its facade at module level |
| `backend/services/pool/` | 9,035 | 25 | **Live** — the pool pipeline that actually writes papers |
| `backend/services/generation_router.py` | 3,149 | 1 | **Live** — routing layer over the two above |
| `backend/apps/question_generation/` | 3,737 | 69 | **Dormant** — `QG_NEW_ENGINE_ENABLED` defaults `false` (`config/settings.py:365`) |
| **Total** | **~30,094** | **181** | |

`settings.py:187-192` documents the split candidly:

> `// Embeddings are read only by services/retrieval_service.py (answer-script generation) and the flag-gated apps/question_generation/ engine — the pool pipeline that actually writes papers reads chunk *text* via services/chapter_markdown.py and never touches a vector.`

So the team knows there are parallel paths. What is not written down is that the newest one has no production caller at all.

---

## Feature inventory

Derived from routed endpoints (`grep -oE 'path\("[^"]*"' apps/*/urls.py`) matched against frontend callers.

### Paper generation
| Feature | Endpoint | Frontend entry |
|---|---|---|
| Streamed generation | `POST /api/generation/questions/stream` | Blueprint modal → editor, **and** dashboard chat |
| Build from question bank | `POST /api/generation/paper-from-bank` | `editor/build-from-bank-dialog.tsx` |
| Durable background runs | `/api/generation/runs` | `lib/use-paper-generation.ts` |
| Replace a single question | `POST /api/generation/replace-question` | Editor hover menu |
| Multi-set variants (A/B/C) | inside pool pipeline | Document outline tabs |
| Design brief detection | `POST /api/generation/design-paper` | Blueprint modal |
| Question images | `/api/generation/question-image` | Editor |
| Answer script | `POST /api/generation/papers/<id>/generate-answer-script/` | Question bank |
| Answer key | `POST /api/generation/answer-key` | **none** |

### Templates
Template CRUD, folders, fork, resolve-from-brief, question-type catalogue. Routes: `/api/generation/templates*`, `/api/generation/template-folders*`. Surfaces: `/templates`, blueprint modal step 1.

### Content sources
Upload, presign, confirm, subject detection, PDF analysis, metadata validation, ingest status. `apps/documents` — models `HsatSource`, `PaperHsatSource`, `PdfSource`, `DocumentChunk`. Two picker UIs (see [Overlap 5](#5-two-source-pickers)).

### Papers, questions, drafts
`apps/projects` — `Project`, `Paper`, `PaperSet`, `Draft`, `ExportRecord`, `QuestionFamily`, `QuestionType`, `QuestionTypeAlias`, `Question`. 30-day soft delete with a recycle bin and restore. Server-synced drafts.

### Organizations
`Organization`, `OrganizationInvite`, `Membership`. Email-domain matching, teacher invites with revocation, multi-org membership, active-school switcher, institute crests, usage dashboard with INR pricing. 16 endpoints — the second-largest surface in the app after generation.

### Chat
`Conversation`, `ChatMessage`. Transcript windowing, rolling summarisation, paper-mode handoff into generation.

### Editor
TipTap/ProseMirror A4 pagination, toolbar, outline, find/replace, hover menu, float images, math nodes, header node with brand logo, review tray, comparison workspace, PDF/DOCX export with S3 backup.

### Accounts and brand
Cognito auth, `BrandKit` + `BrandAsset`, institute logo on paper headers, password reset.

---

## Duplicates and overlaps

Ranked by cost to carry.

### 1. Three generation engines
**Cost: ~30,000 LOC · Severity: high**

Covered in [Headline](#headline). The specific problem is `apps/question_generation/`: 3,737 lines across 69 files, flag `QG_NEW_ENGINE_ENABLED` defaulting to `false`, and exactly one non-test caller — `TestScienceEngineView` in `apps/generation/views.py:283-300`, which is itself gated behind `ENABLE_TEST_ENDPOINTS`.

It ships `tests/test_parity.py` comparing itself against `q_instructions`, which identifies it for what it is: **a migration that was started and stalled.** It is not dead code — it is unfinished replacement code, which is worse, because it accrues maintenance while delivering nothing.

The decision this needs is binary: finish the migration and delete `q_instructions`, or delete `apps/question_generation` and stop paying for it. Carrying both indefinitely is the only option with no upside.

### 2. Two PDF/DOCX export implementations — and the fix landed in only one
**Cost: ~120 LOC · Severity: high — this one is a live bug**

Both call `exportToPDF("tiptap-paper-container", filename)`, both `window.prompt` for a filename, both toast, both fire-and-forget to S3:

- `components/editor/toolbar.tsx:810-840` — the toolbar button
- `app/(dashboard)/editor/page.tsx:400-432` — triggered by an `?action=export-pdf` URL param

They have since diverged, and the divergence is a defect. The toolbar carries a fix with the reason written next to it (`:828-831`):

> `// paperId arrives as the per-tab composed id ("{base}_A"); the backend only knows the base row, so send that plus the set this export is of. Sending the composed id 404'd every upload.`

```tsx
// toolbar.tsx:826-833 — fixed
const backupId = persistablePaperId(paperId);
uploadExportToS3(blob, { …, paperId: backupId, setLabel: splitPaperId(paperId).set ?? undefined });
```

```tsx
// editor/page.tsx:412-418 — NOT fixed
const realPaperId = paperId && paperId !== "current" ? paperId : null;
uploadExportToS3(blob, { …, paperId: realPaperId });   // composed id — the 404 case
```

So exports triggered by URL param still send the composed id and, per the toolbar's own comment, still 404 on upload. The local download succeeds, so the failure is silent — the teacher sees "PDF downloaded!" and the cloud backup never lands.

The editor copy's error string is itself an admission: `"PDF export failed. Please try from the toolbar."` The code knows it is the weaker of two copies.

Duplicated again for DOCX (`editor/page.tsx:427+`, `toolbar.tsx:843+`).

### 3. Two answer-generation features
**Cost: ~1,000 LOC · Severity: medium**

- `AnswerKeyView` → `POST /api/generation/answer-key` → `generate_answer_key()` in `openai_service` (`apps/generation/views.py:261-262`). **Zero frontend callers** — verified by grepping `answer-key` across `frontend/lib`, `frontend/app`, `frontend/components`.
- `generate-answer-script` → `services/answer_script_service.py`, 964 lines, retrieval-backed. Live, used from the question bank.

Two answers to "produce the answers for this paper." One is a thin LLM call nobody invokes; the other is the real feature.

### 4. Two `Grainient` components, diverged
**Cost: ~24 KB · Severity: low**

- `components/Grainient.tsx` (11.3 KB) ← `app/page.tsx` (landing)
- `components/ui/grainient.tsx` (12.8 KB) ← `components/dashboard/chat-backdrop.tsx:23` (chat)

`diff` reports **180 differing lines**. Both are WebGL shader components doing the same job against the same palette. The UI audit already records the pain this caused — the palette fix in `cceebf4` had to be applied to *"both Grainient copies."* Every future change to the shader costs double, and the two will keep drifting.

### 5. Two source pickers
**Cost: ~1,000 LOC · Severity: medium**

- `components/hsat-source-picker.tsx` (621 lines) ← `app/(dashboard)/editor/page.tsx:8`
- `components/blueprint/source-panel.tsx` (385 lines) ← `blueprint-modal.tsx:78`

Both select chapters/sources for a paper. They share only the `AppliedHsatSource` **type** — `source-panel.tsx:33` imports the type from the other file while implementing its own UI. A teacher attaching a chapter meets a different interface depending on which door they came through.

### 6. Two template pickers, one dead
**Cost: 199 LOC · Severity: low**

- `components/template-picker.tsx` (199 lines) — **zero importers**
- `components/blueprint/template-picker-grid.tsx` (247 lines) — live, in blueprint step 1

The blueprint version won. The loser was never removed.

### 7. Two consumers of the generation stream
**Cost: state logic, not transport · Severity: low-medium**

`POST /api/generation/questions/stream` has two independent client-side consumers:

- `lib/use-paper-generation.ts:411` — the editor's hook
- `app/(dashboard)/dashboard/page.tsx:507` — the chat

Both correctly share the `streamSse` transport helper (`dashboard/page.tsx:55`), so this is **not** a duplicated network layer. What is duplicated is everything above it: stage mapping, progress accounting, error handling, and cancellation. The dashboard's own header comment (`:15`) notes it calls *"the same `/api/generation/questions/stream` the generator form does"* — and `components/generator-form.tsx`, the form it refers to, has since been deleted. The comment outlived the thing it pointed at.

---

## Built but unreachable

Components with **zero importers**, resolved by matching each basename against every `import`/`from` statement in `app/`, `components/`, `lib/`, `store/`:

| File | LOC | Note |
|---|---:|---|
| `components/GiftOverlay.tsx` | 396 | Full-screen gift reveal, confetti, reduced-motion support. Never wired |
| `components/file-upload.tsx` | 253 | Superseded by the source pickers |
| `components/GooeyNav.tsx` (+ `.css`) | 224 | Particle-burst nav. Also references a `filter: url("#goo")` SVG it never renders |
| `components/editor/extensions/drawing-node.tsx` | 212 | TipTap node, not registered |
| `components/template-picker.tsx` | 199 | See [Overlap 6](#6-two-template-pickers-one-dead) |
| `components/tiptap-viewer.tsx` | 56 | `paper-preview.tsx` is used instead |
| `components/ui/cloud-watch-form.tsx` | — | Second copy of the auth eye-tracking rig |
| **Total** | **~1,340+** | |

Also unreachable at the API layer:

- `POST /api/generation/answer-key` — routed, implemented, no caller.
- `apps/storage` — has `urls.py` and `views.py` but **no models**. Two endpoints, both live (`upload-export`, `export-url`), so this is thin rather than dead. Flagged only because it reads as an app that never grew into one.

Note `GiftOverlay` and `GooeyNav` are also tracked in the UI audit as *unused assets* to be wired. Those two documents disagree with this one on intent — the UI audit proposes wiring them, this audit observes they have sat unwired long enough to count as carried cost. **That is a decision for you, not a contradiction to resolve silently:** wire them or delete them, but pick.

---

## Questionable scope

### `TestScienceEngineView` is a production route
`apps/generation/urls.py:94-101`, `apps/generation/views.py:276-300`

An "isolated integration test view" that runs a **real generation pipeline** with hardcoded parameters — CBSE, Class 10, Science, the Electricity chapter. Its own docstring says:

> `this endpoint triggers REAL LLM calls (it spends OpenAI budget), so it must never be reachable anonymously on a deployed host`

It is gated by `ENABLE_TEST_ENDPOINTS`, which defaults to `str(DEBUG)` (`config/settings.py:370-371`). That is a reasonable default, and the docstring shows the risk was considered. Two things still deserve attention: the gate is only as good as `DEBUG` being false in every deployed environment, and a test fixture is being maintained as routed application code. A management command or a test-suite fixture would carry the same value with none of the exposure.

### The generation surface has four front doors
A teacher can start a paper from: the dashboard chat, the blueprint modal, the build-from-bank dialog, or the templates page. Each is individually reasonable. Collectively they mean four codepaths to keep in sync, and — per the guidance audit — a teacher who learns one may never discover the other three.

This is not necessarily wrong for the product. It is worth an explicit decision rather than an accreted one.

---

## Where the scope can improve

Ranked by value per unit of work.

1. **Consolidate export.** Extract one `useExportPaper()` covering PDF and DOCX, filename prompt, toast lifecycle, and S3 backup. Delete both copies. This *fixes the composed-id bug as a side effect* rather than requiring it to be found and patched twice again.
2. **Decide the engine question.** Finish `apps/question_generation` or delete it. Either outcome removes thousands of lines of standing cost; carrying both removes none.
3. **Merge the source pickers.** One picker, two presentations if the layouts genuinely differ. They already share a type — they should share the component.
4. **Collapse `Grainient`.** One component, props for the two use sites. 180 differing lines is drift, not variation.
5. **Delete or wire the dead components.** ~1,340 lines. Deleting is one commit; git remembers them if `GiftOverlay` is ever wanted.
6. **Remove `answer-key` or use it.** If the answer-script feature supersedes it, drop the endpoint and `generate_answer_key()`.
7. **Lift the shared generation state out of the two SSE consumers.** The transport is already shared; the stage/progress/error handling should follow it.

---

## Recommendations

| # | Action | Effort | Removes | Risk |
|---|---|---|---:|---|
| 1 | Single export hook, both formats | ~2 hr | ~120 LOC + a live bug | Low |
| 2 | Delete the 6 unreferenced components | ~30 min | ~1,340 LOC | Low — recoverable from git |
| 3 | Delete `answer-key` endpoint + service fn | ~30 min | ~80 LOC | Low — verify no external caller first |
| 4 | Merge the two `Grainient` copies | ~1.5 hr | ~12 KB | Low |
| 5 | `TestScienceEngineView` → management command | ~1 hr | a routed LLM-spending endpoint | Low |
| 6 | Merge the source pickers | ~4 hr | ~400 LOC | Medium — two live call sites |
| 7 | Share generation state between SSE consumers | ~4 hr | ~200 LOC | Medium — touches the chat and the editor |
| 8 | **Resolve the engine question** | days | up to ~14,000 LOC | **High — needs your decision, not a refactor** |

Items 1–5 are ~5.5 hours total, remove roughly 1,500 lines and one silent bug, and carry little risk. Item 8 dwarfs everything else and is a product decision.

---

## Open questions

- **Does `GenerationHistory` overlap `projects.Paper`?** Both appear to record generated papers. `apps/generation` owns `GenerationHistory`; `apps/projects` owns `Paper`/`PaperSet`. Whether these are two records of one thing or genuinely different concerns was not traced — worth confirming before either grows further.
- **Is anything outside this repo calling `/api/generation/answer-key`?** The audit only proves the frontend in this repo doesn't. Check deployment logs before deleting.
- **Was `apps/question_generation` intended to replace `q_instructions` wholesale, or only the academic path?** `test_parity.py` compares the two facades, which suggests wholesale, but the scope of the intended migration is not documented anywhere in the repo.
- **Is `ENABLE_TEST_ENDPOINTS` false in production?** Partly answered. `DJANGO_DEBUG` defaults `false` (`config/settings.py:14`), so `ENABLE_TEST_ENDPOINTS` defaults false too — the safe path. But `deployment/qp-gen-backend.service:9` loads `EnvironmentFile=/home/ubuntu/qp-gen/backend/.env`, which is not in the repo, so the deployed values are unverifiable from here. Check that `.env` on the host sets neither flag true.
