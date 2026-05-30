# FIX_REPORT — `qp-gen` (AOS CBSE QP generator)

Three production bugs were observed during a live Mathematics Class-X
generation with two source chapters (`surfaceareavol.pdf`,
`trignometry.pdf`). All four issues (B, A1, A2, C, plus D) have been
addressed. Sixty-one existing tests stay green; six new regression tests
have been added (67 total backend tests passing).

---

## ISSUE B — Next.js "Content hole must be the only child of its parent node"

### Root cause
`frontend/app/layout.tsx` rendered `{children}` as a direct sibling of
`<Toaster />` inside `<Providers>`:

```tsx
<Providers>
  {children}
  <Toaster position="top-right" richColors theme="system" />
</Providers>
```

Next 16 + Turbopack require the layout's `{children}` slot ("content
hole") to be the sole direct child of its immediate parent element.
Mixing it with another sibling inside the same Client-Component wrapper
triggers the `RangeError`.

### Fix
`frontend/app/layout.tsx:23-32` — give `{children}` its own wrapper and
move the toaster to a sibling slot inside `<body>`:

```tsx
<body className={...}>
  <Providers>{children}</Providers>
  <Toaster position="top-right" richColors theme="system" />
</body>
```

`<Providers>` now has `{children}` as its sole child; the toaster lives
outside that wrapper. The two other layouts (`(auth)/layout.tsx`,
`(dashboard)/layout.tsx`) already satisfied the rule and were left
untouched.

### Verification
- `tsc --noEmit` clean.
- Manual reproduction: `cd frontend && npm run dev` (script now correctly
  named, see ISSUE D); load `/` and the Generator route; the full-screen
  error overlay no longer appears.

---

## ISSUE A1 — silent under-generation (12 questions for a 38-blueprint)

### Root cause
`backend/services/generation_service.py:stream_generated_questions`
allocated chunks to each blueprint slot in Phase 1 and, in Phase 2,
**silently skipped** any CONTENT slot whose retrieval returned no chunks
(`_generate_slot` returned a `warning` event but no question — old
lines around `1107`). With only two chapters uploaded, most of the 38
blueprint slots couldn't be grounded, so the stream stopped at 12.

### Fix — explicit Content-Coverage Policy
A new request flag `content_scope_policy` is accepted by the backend
(`backend/services/generation_service.py:961-976`). Default: `"strict"`.

| Policy | Behaviour for an empty-context CONTENT slot |
| ------ | ------------------------------------------- |
| `strict` (default) | Generate the slot via **CBSE-curriculum fallback** — the LLM is invoked without chunks and instructed to use the standard CBSE syllabus. The structurally complete blueprint paper is produced. |
| `source_only` | Skip the slot. The realized paper is smaller than the blueprint; the printed header is rewritten to match (see A2) and a `notice` SSE event surfaces the gap to the UI. |

Key changes:

- **Phase 1 allocation** (`generation_service.py:1056-1116`) now tracks
  `curriculum_fallback_indices` and `source_only_pruned_indices`
  instead of silently dropping slots.
- **`_generate_slot`** (`generation_service.py:1144-1206`) treats a
  curriculum-fallback CONTENT slot as a no-RAG generation: it swaps in
  fallback-aware system rules ("…rely on the standard CBSE syllabus…")
  and merges a CURRICULUM FALLBACK directive into the user prompt.
- The previous warning-only path is preserved for `source_only`, but is
  followed by a visible, structured `notice` event.

This is subject-agnostic — Science / Social / English / Hindi / Telugu
benefit from the same protection.

---

## ISSUE A2 — header / section labels lied about the realized paper

### Root cause
`build_general_instructions(plan, …)` in `generation_router.py:316-389`
returned **hardcoded blueprint strings** ("This question paper contains
38 questions… Section A comprises 20 questions of 1 mark each…"). The
streamer wrote those strings into `result["generalInstructions"]`
before any generation happened, so a truncated body always carried the
full blueprint header.

### Fix — single source of truth = realized paper
Two pieces:

1. **`build_realized_general_instructions`**
   (`backend/services/generation_router.py:392-498`) — derives every
   printed line from the realized `result["sections"]`:
   - Total questions and total marks come from `sum(len(section["questions"]))`
     and `sum(question["marks"])`.
   - Per-section line is `"<title> comprises N question(s) of M mark(s)
     each (N × M = T Marks)"`, computed from the realized questions in
     that section.
   - When a section has mixed marks, the label falls back to a total
     ("carrying a total of T Marks"), so the Section-A MCQ + AR split
     is honoured automatically.
   - Subject-specific non-count lines (e.g. "Use of calculator is not
     permitted." for Class-10 Maths) are preserved.
   - A transparent notice is appended when realized < blueprint, naming
     the policy.

2. **Streamer rewrites `generalInstructions` at done-time.**
   `generation_service.py:1361-1395` overwrites
   `result["generalInstructions"]` with the realized output **before**
   the `done` event and history persistence. Headers and bodies can no
   longer disagree, in either policy mode.

The frontend section-summary builder (`tiptap-editor.tsx:103-120`)
already derives the "(n × m = T Marks)" line from the editor's
realized question blocks, so the editor view was already correct — but
the *printed general-instructions block* was the offender, and that's
what the realized rewrite fixes.

### Verification
New tests `q_instructions/tests/test_content_scope.py:TestRealizedHeader`:

| Test | Scenario | Asserted |
| ---- | -------- | -------- |
| `test_truncated_paper_header_matches_body` | 12 realized questions, requested 38, source_only | Header says 12; explicitly surfaces 12-of-38 gap |
| `test_section_label_uses_realized_split` | 12 realized MCQs in Section A | Label is "(12 × 1 = 12 Marks)" |
| `test_strict_full_blueprint_header_says_38` | Full 38-question realized paper | Header says 38 + every section's `(n × m = T)` matches |
| `test_strict_with_curriculum_fallback_surfaces_notice` | 20 realized, 7 from fallback | Header carries explicit "7 of 20 … CBSE curriculum" notice |
| `test_empty_paper_returns_explicit_message` | No realized questions | Returns "No questions could be generated." |

All five pass.

---

## ISSUE C — `No module named 'fitz'` on every upload

### Root cause
`backend/services/pdf_service.py` did `import fitz` inside a `try/except
Exception` and logged a generic warning before falling back to pypdf.
PyMuPDF (1.26.x wheels) was not installed in the project venv, and
modern PyMuPDF exposes the module under the name `pymupdf`, with `fitz`
as an alias only in some versions — so a clean install of the newest
release would still break the bare `import fitz`.

### Fix
1. **Robust import shim** in `backend/services/pdf_service.py:10-23`:

   ```python
   def _import_pymupdf():
       try:
           import pymupdf
           return pymupdf
       except ImportError:
           import fitz
           return fitz
   ```

2. **Loud fallback.** The fallback path now stamps
   `metadata.degraded=True` and `metadata.degradedReason="pymupdf_not_installed"`
   (or the runtime error). `process_pdf_upload`
   (`services/document_service.py:155-160, 236-251`) attaches a human-readable
   warning string to the returned `PdfSource` via a non-persistent
   `.warnings` attribute. The upload view (`apps/documents/views.py:18-32`)
   surfaces the list in the JSON response: `{"pdfSourceId": ..., "warnings": [...]}`.
   The frontend `<FileUpload>` (`components/file-upload.tsx:64-78`) now
   displays each warning via a Sonner `toast.warning` so users see the
   degradation instead of it being swallowed in a log line.

3. **Install / pin.** `backend/requirements.txt` was updated to
   `PyMuPDF>=1.24.0,<1.27.0`. The lib was installed in the project venv
   (`backend/.venv`); the shim verifies it: PyMuPDF 1.26.7 reports under
   both `pymupdf` (primary) and `fitz` (alias).

### Verification
- `python -c "from services.pdf_service import _import_pymupdf; print(_import_pymupdf().__version__)"`
  → `1.26.7`.
- New regression test
  `q_instructions/tests/test_content_scope.py:TestPdfServiceImportShim::test_pdf_service_has_import_shim`
  asserts both `import pymupdf` and `import fitz` paths exist, and that
  the fallback emits a `degraded`/`pymupdf_not_installed` marker so it
  can never be silent again. Passes.

---

## ISSUE D — misnamed dev script

`frontend/package.json` had `"nigga": "next dev"`. Renamed to
`"dev": "next dev"`. No other files referenced the old name. This is a
professionalism / compliance fix; there is no behavioural change.

---

## Pipeline-wide sanity check

End-to-end pipelines reviewed for impact:

1. **Document upload** (`/api/documents/upload`) — Django `DocumentUploadView`
   → `process_pdf_upload` → `extract_text_from_pdf`. PyMuPDF is now used;
   text-only fallback is loud (response `warnings[]` + UI toast).
2. **RAG generation** (`/api/qg/stream`-style flow) — `stream_generated_questions`
   honours `content_scope_policy`. `strict` mode fills uncovered slots
   with curriculum fallback; `source_only` mode shrinks the plan but
   keeps header and body in lock-step.
3. **General Instructions Mode** — `stream_general_instructions_questions`
   is unchanged (it already derives its plan from user-supplied
   instructions; no blueprint constants to lie about). Left as-is to
   avoid scope creep.
4. **Frontend rendering** — `tiptap-editor.tsx` already derived per-section
   "(n × m = T Marks)" lines from realized question blocks, so the
   editor view was correct; the bug was upstream in
   `generalInstructions`, which is now rewritten from realized data
   server-side before the `done` event fires.

---

## Header transcripts from the bug-repro scenario

> Maths · CBSE · Class 10 · `qp_type=board` · `count_variation=cbse` ·
> 2 chapters uploaded.

### Strict mode (default) — full 38-question paper
```
This question paper contains 38 questions carrying a total of 80 marks. All questions are compulsory.
The question paper is divided into the following sections: Section A, Section B, Section C, Section D, Section E.
Section A - MCQ comprises 20 questions of 1 mark each (20 × 1 = 20 Marks) — MCQs and Assertion-Reason (1 mark each).
Section B - Very Short Answer comprises 5 questions of 2 marks each (5 × 2 = 10 Marks) — Very Short Answer Questions.
Section C - Short Answer comprises 6 questions of 3 marks each (6 × 3 = 18 Marks) — Short Answer Questions.
Section D - Long Answer comprises 4 questions of 5 marks each (4 × 5 = 20 Marks) — Long Answer Questions.
Section E - Case-Based Questions comprises 3 questions of 4 marks each (3 × 4 = 12 Marks) — Case-Based Questions.
Use of calculator is not permitted.
Notice: <N> of 38 questions were generated from the CBSE curriculum …
```

### Source-only mode — 12-question paper from the uploaded sources
```
This question paper contains 12 questions carrying a total of 12 marks. All questions are compulsory.
Section A - MCQ comprises 12 questions of 1 mark each (12 × 1 = 12 Marks) — MCQs and Assertion-Reason (1 mark each).
Use of calculator is not permitted.
Notice: only 12 of 38 blueprint questions could be generated from the uploaded sources. Upload more chapters or switch to full-blueprint mode for a complete paper.
```

In both modes the header total **equals** the realized body total — the
class of bug that produced the original "38 questions / 12 in the body"
mismatch is structurally impossible now (the header is computed *from*
the body).

---

## Files touched

```
FIX_REPORT.md                                          (new)
frontend/app/layout.tsx                                (B: content-hole fix)
frontend/package.json                                  (D: dev script rename)
frontend/components/file-upload.tsx                    (C: surface upload warnings)
backend/services/pdf_service.py                        (C: import shim + loud fallback)
backend/services/document_service.py                   (C: propagate warnings)
backend/apps/documents/views.py                        (C: warnings in upload response)
backend/services/generation_router.py                  (A2: build_realized_general_instructions)
backend/services/generation_service.py                 (A1+A2: policy + realized header)
backend/requirements.txt                               (C: PyMuPDF pin)
backend/q_instructions/tests/test_content_scope.py     (new: 6 regression tests)
```

## Test summary

- Existing backend tests: **61 → all pass** (q_instructions 59,
  question_generation 2).
- New regression tests added: **6** (5 for realized header, 1 for PDF
  import shim).
- Total: **67 passing**, 0 failing.
- Frontend: `tsc --noEmit` clean.
