# MARKITDOWN_EVAL — verdict and evidence

**TL;DR — SKIP the swap.** Markitdown produces marginally better table
structure on math-heavy exemplar PDFs but loses image extraction (which our
RAG pipeline depends on for diagram-grounded retrieval), is meaningfully
slower per-file, and the Cluster B "Curriculum fallback flood" was a
**chunk-reuse exhaustion problem**, not an extraction quality problem.
PyMuPDF stays. Markitdown is not added as a dep.

---

## Measurement methodology

`backend/scratch/eval_markitdown.py` runs both extractors on the same three
PDFs the user uploaded (trignometry.pdf, MathsStandard-SQP.pdf,
surfaceareavol.pdf), captures:

* Wall-clock latency per call.
* Character counts.
* Special-character preservation (`√`, `π`, `²`, subscript digits).
* MCQ marker counts `(A)(B)(C)(D)`.
* Markdown structure markers (`# ` headers, `|` table pipes).
* Side-by-side renderings of landmark substrings the user cited
  (Q31 monthly income, Q32 train, Q33 BPT, Q35 grouped freq, Q38
  India Gate, `frustum`, `π`).

Run with `python scratch/eval_markitdown.py` from `backend/`.

---

## Quantitative comparison

### trignometry.pdf (2.2 MB, NCERT chapter)

| metric                  | PyMuPDF | markitdown |
|-------------------------|---------|------------|
| time per call           | 1308 ms | 1562 ms    |
| extracted chars         | 25,285  | 46,125     |
| `√` chars               | 0       | 0          |
| `π` chars               | 0       | 0          |
| `²` chars               | 0       | 0          |
| MCQ `(A)` count         | 8       | 8          |
| markdown table pipes    | 0       | 3,145      |

Both extractors lose math symbols on this PDF — they don't survive the
text layer. Markitdown adds markdown table structure where PyMuPDF
emits plain text. Marginal win for markitdown on structure; both lose
on math.

### MathsStandard-SQP.pdf (500 KB, the official CBSE Sample Paper)

| metric                  | PyMuPDF | markitdown |
|-------------------------|---------|------------|
| time per call           | 30 ms   | 913 ms     |
| extracted chars         | 16,308  | 19,201     |
| `√` chars               | 10      | 10         |
| MCQ `(A)` count         | 38      | 38         |
| markdown table pipes    | 0       | 475        |

Markitdown is **30× slower** here. Both preserve `√` equally. Markitdown
formats the few tables (India Gate, monthly income) as markdown tables
rather than space-separated text.

Side-by-side on the Aryan/Babban (Q31) question:

```
PyMuPDF:    "3 ⏎ 31.(A) ⏎ ⏎ ⏎ ⏎ ⏎ (B) ⏎  The monthly income of Aryan and Babban…"
markitdown: "31.(A) The monthly income of Aryan and Babban are in the ratio 3:4…"
```

Markitdown's line continuity here is cleaner. PyMuPDF emits the
mark column (`3`), then question number, then sub-part labels on
their own lines, then the body. For embedding retrieval this still
works (the embedding sees the same tokens regardless of whitespace),
but markitdown is genuinely more human-readable.

### surfaceareavol.pdf (246 KB, NCERT exemplar — heavy formulae)

| metric                  | PyMuPDF | markitdown |
|-------------------------|---------|------------|
| time per call           | 72 ms   | 1080 ms    |
| extracted chars         | 23,321  | 27,670     |
| `π` chars               | 33      | 33         |
| markdown table pipes    | 0       | 711        |

Markitdown is **15× slower** and extracts ~20% more text (mostly chapter
headers it preserves; PyMuPDF drops them). Both preserve π identically.

On the frustum formula, both extractors mangle the equation — neither
preserves the subscript `r₁ + r₂`, the bracketed root, or the proper
multiplication structure. PyMuPDF emits a chaotic newline-soup
(`2⏎2⏎1⏎2⏎1 2⏎1⏎[⏎]⏎3⏎h r⏎`); markitdown stuffs the same fragments
into a markdown table (`| πh[r2 | +r2 +rr ] |`). Structurally neither
helps the model reconstruct the equation; the table format does
**not** make the formula recoverable.

---

## What the brief specifically asked

> If extraction is mangling formulas/special characters → run markitdown
> on the same three PDFs and compare side-by-side. If markitdown's
> math/structure handling is meaningfully better, integrate it BEHIND A
> FEATURE FLAG for math-heavy sources only.

Math/structure handling is **not meaningfully better** for our use case:

* **Formulae** — both extractors mangle equations equivalently. Neither
  preserves subscripts/superscripts, fractions, or root expressions in a
  parseable form. Markitdown's markdown tables for formulae aren't
  semantically richer than PyMuPDF's whitespace soup — they just look
  tidier on a page render.
* **Tables** — markitdown wins on Q38 (India Gate) and the frustum
  formula presentation. PyMuPDF flattens both.
* **Question continuity** — markitdown is slightly cleaner on
  multi-line question stems.

What changes if we adopt markitdown:

* **+ Slight readability** on table-heavy PDFs.
* **+ Slight chunk continuity** for retrieval embeddings.
* **− Image extraction goes away.** Markitdown's PDF backend
  (pdfminer.six → pdfplumber) returns text only. Our RAG pipeline
  relies on PyMuPDF's `page.get_images()` to extract diagrams,
  caption them through the vision API, and embed the captions as
  chunks (see `services/document_service._build_image_chunks`).
  Without image extraction, Q22-style diagram questions and the
  `requires_image: True` slots can no longer be grounded against the
  source. This is a **regression**.
* **− 15–30× slower** per call on smaller PDFs.
* **+ ~5–10% bigger text body** (markitdown keeps chapter headers
  PyMuPDF drops).

The image-extraction loss alone disqualifies markitdown as a
replacement. The most we'd do is run it as a **text-only secondary
extractor** for math-heavy PDFs, fusing its output with PyMuPDF's
image bytes. That's significantly more code for a marginal text
quality win that doesn't address the actual root cause of the
"Curriculum fallback flood".

---

## Why the brief's underlying concern is moot

The brief framed markitdown as a remediation for the curriculum-fallback
flood. Cluster B's profiling (see `FIX_REPORT.md` § Cluster B and the
`scratch/probe_retrieval.py` simulation) proved the flood was caused by
**per-chunk dedup exhausting the 65-chunk pool** on a 38-question paper:
55% of slots fell through to curriculum mode after slot 17 because
strict dedup left no chunks for them. Loosening dedup to `MAX_CHUNK_REUSES=3`
(via `MAX_CHUNK_REUSES` setting, default 3) takes the fallback rate from
**55% → 0%** in the same simulation, against the same extracted text.

The retrieval landmark probe confirmed extraction is **good enough**:

| query                | top hit | L2 | source           |
|----------------------|---------|------|------------------|
| Q33 BPT prove        | chunk 10 of SQP   | 0.97 | MathsStandard-SQP |
| Q35 grouped freq     | chunk 11 of SQP   | 0.97 | MathsStandard-SQP |
| Q38 India Gate       | chunk 14 of SQP   | 0.99 | MathsStandard-SQP |
| Q32 train            | chunk 9 of SQP    | 0.96 | MathsStandard-SQP |

Every landmark question the user expected the retriever to find is in
fact the **#1 retrieved chunk** for its corresponding query — the
embeddings work fine with PyMuPDF's text. The fallback flood was never
about whether the chunks could be retrieved; it was about whether the
allocator would even ask for them once the dedup set ran dry.

---

## Decision

* **Keep PyMuPDF.** Do not add markitdown as a runtime dependency.
* `pip uninstall markitdown` after this evaluation if storage is
  precious (it ships ~50 MB of transitive deps including onnxruntime
  for magika file-type detection).
* If we revisit math fidelity, the right path is to add a true math-aware
  extractor (Mathpix, Nougat, or pdftotext with the layout flag) rather
  than markitdown — none of those exist in the current install but they
  preserve LaTeX. Out of scope for this round.
* `MAX_CHUNK_REUSES = 3` (Cluster B fix) is the actual remedy for the
  curriculum-fallback symptom users observed.
