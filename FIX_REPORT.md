# FIX_REPORT — Ingestion speed + RAG quality + VI toggle + markitdown reality check

Four clusters, four traceable commits, measurements not guesses.

End-of-round test gates:

* `q_instructions` test suite — **98/98 passing** (`python -m unittest
  discover -s q_instructions/tests`).
* Frontend `scripts/test-todom-shape.mjs` — **7/7 passing** (regression
  for the prior round's ProseMirror content-hole bug, re-run to confirm
  no drift).
* `python manage.py check` — clean.
* Frontend `tsc --noEmit` — clean.
* Frontend `next build` — succeeds (Next 16.2.6 Turbopack), all 11
  routes prerender.

---

## CLUSTER A — Ingestion speed: 250 s → 14.4 s on trignometry.pdf

### Profiling evidence

`backend/scratch/profile_ingestion.py` and
`backend/scratch/profile_ingestion_full.py` time each phase on the
user's actual files (Downloads/trignometry.pdf 2.2 MB,
MathsStandard-SQP.pdf 500 KB, surfaceareavol.pdf 246 KB).

**Pre-fix, trignometry.pdf:**

| phase                          | wall-clock |
|--------------------------------|------------|
| File read                      | 1 ms       |
| PyMuPDF extract                | 1,203 ms   |
| Semantic chunking              | 4 ms       |
| Image captioning (22 images, SERIAL, gpt-5-mini) | **247,148 ms** |
| Embedding (1 batch, 26 chunks) | 1,926 ms   |
| **Total**                      | **~250 s** |

Per-call captioning latency was measured at **11,234 ms/image** because
the captioner was hitting `OPENAI_MODEL=gpt-5-mini`, a reasoning model
that spends ~10 s on internal CoT even for a one-line image caption,
and the loop ran sequentially. The 5-minute symptom the user reported
matches 22 × 11.2 s + extraction + embedding precisely.

### Root cause

`services/document_service._build_image_chunks` looped through every
usable image and called `caption_image_for_embedding` synchronously.
That function pinned `model=settings.OPENAI_MODEL` (gpt-5-mini, the
generation reasoning model). Two compounding defects:

1. **Wrong model for the job** — captioning a textbook visual for
   retrieval is a multimodal-only task. Reasoning models bill
   ~10 s of CoT per call.
2. **No parallelism** — vision API calls are I/O-bound; the GIL
   doesn't block concurrent HTTP, but the code ran them in series.

### Fix

Three coordinated changes in `services/openai_service.py`,
`services/document_service.py`, and `config/settings.py`:

1. **Separate vision model knob**. `caption_image_for_embedding` now
   uses `OPENAI_VISION_MODEL` (default `"gpt-4o"`, fast multimodal).
   `OPENAI_MODEL` (gpt-5-mini) stays the default for generation,
   answer-script, and other reasoning tasks. Override per-deploy via
   env.
2. **`detail: "low"`** on the image_url argument. For gpt-4o this
   bills a flat 85 tokens per image regardless of source resolution,
   so 22 parallel calls add ~1,870 prompt tokens total — comfortably
   inside the 200,000 TPM Tier 1 budget. Comparison probe
   (`scratch/profile_ingestion_full.py` and inline timings):

   | model               | tokens/image | wall-clock/call |
   |---------------------|--------------|-----------------|
   | gpt-5-mini default  | (reasoning)  | ~11,200 ms      |
   | gpt-4o-mini low det.| **2,847**    | ~1,200 ms       |
   | gpt-4o low det.     | **99**       | ~1,230 ms       |
   | gpt-4.1-mini low det.| **73**      | ~1,420 ms       |

   gpt-4o-mini's "low detail" is misleadingly named — OpenAI's mini
   variants re-bucket the image cost to ~2,800 tokens per call
   regardless of `detail`, which saturates TPM after ~5 concurrent
   calls. gpt-4o is **both faster and cheaper** for this workload
   precisely because it spends 30× fewer prompt tokens per image.
3. **Parallel captioning**. `_build_image_chunks` now collects all
   image captions through a `ThreadPoolExecutor` bounded by
   `PDF_IMAGE_CAPTION_CONCURRENCY` (default 8). For 22 images:
   ceil(22/8) × ~1.5 s ≈ 5 s, vs 22 × 11 s = 4 min.
4. **`max_retries=5`** on the OpenAI client so transient 429/5xx
   pulses during a captioning burst are absorbed by the SDK rather
   than failing the upload.

### Post-fix numbers

| file                       | size   | total | extract | caption | embed |
|----------------------------|--------|-------|---------|---------|-------|
| trignometry.pdf            | 2.2 MB | **14.41 s** | 1.23 s | 11.9 s (22 imgs) | 1.25 s |
| MathsStandard-SQP.pdf      | 500 KB | **6.29 s**  | 0.09 s | 5.35 s (4 imgs)  | 0.85 s |
| surfaceareavol.pdf         | 246 KB | **6.80 s**  | 0.16 s | 5.90 s (1 img)   | 0.74 s |

trignometry.pdf went from ~250 s → **14.4 s** (a 17× speedup) — under
the 30 s target. The remaining time is dominated by the 22 image
captioning round-trips; further gains would require either pushing
concurrency higher (current bottleneck is per-call OpenAI latency,
not TPM) or batching multiple images into a single multimodal call
(future work).

### Files touched (Cluster A)

```
M backend/config/settings.py
M backend/services/openai_service.py
M backend/services/document_service.py
A backend/scratch/profile_ingestion.py
A backend/scratch/profile_ingestion_full.py
```

---

## CLUSTER B — RAG quality: "Curriculum fallback" flood

### What does "Curriculum fallback" actually mean

Answered by reading
`backend/services/generation_service.py:1231-1289`. The badge is set
**only** in the slot allocator's `if not context:` branch — which
fires when, after filtering the cached top-50 retrieval results by
the running `used_chunk_ids` set, **zero chunks remain**. There is
**no similarity threshold**: any chunk is considered "found" as long
as it hasn't been claimed by an earlier slot.

So "Curriculum fallback" reflects **chunk-pool availability**, not
retrieval quality. The label is currently honest about the
mechanism but misleading about the cause — users read "fallback" as
"the retriever couldn't find anything", whereas the actual trigger
is "all chunks already used".

### Extraction quality audit (Cluster B item 2)

`backend/scratch/dump_extraction.py` dumps and signal-counts the
output of `extract_text_from_pdf` for the three user PDFs:

```
trignometry.pdf:         chars=25285  √=0  π=0  ²=0  MCQ_A=9   MCQ_D=8
MathsStandard-SQP.pdf:   chars=16308  √=10 π=0  ²=0  MCQ_A=38  MCQ_D=20  Section_A=True
surfaceareavol.pdf:      chars=23321  √=0  π=33 ²=0  MCQ_A=28  MCQ_D=26
```

Findings:

* All landmark questions the user named are **present and recoverable
  by substring search**: `train` (chunk 9), `Aryan/Babban` (chunk 9),
  `33. Prove BPT` (chunk 10), `35. mode` (chunk 11), `India Gate`
  (chunk 14), `monthly income` (chunk 9), `38.` (chunk 13).
* `√` survives extraction for the SQP; `π` survives for the
  exemplar; `²` and subscripts are uniformly dropped (PyMuPDF text
  layer doesn't preserve them — same is true of markitdown, see
  Cluster D).
* **Chunk 9 of the SQP smashes Q31 + Q32 into one chunk** because the
  semantic chunker's heading patterns don't match SQP-style question
  numbering. This is suboptimal but not fatal — both questions still
  surface in the same chunk and the retrieval probe finds them.

Conclusion: **extraction is fine** for the retrieval task. Math
fidelity is poor for both PyMuPDF and markitdown.

### Chunking boundaries (Cluster B item 3)

The SQP is chunked into 15 segments. Landmark questions land at:

* Q32 train  → chunk 9 (page 6) [shared with Q31]
* Q33 BPT    → chunk 10 (page 6)
* Q35 mode   → chunk 11 (page 7)
* Q38 India Gate → chunk 14 (page 8) [shared with Q37]

The chunker's chapter prefix (`# General Context ## SAMPLE QUESTION
PAPER`) is constant across every SQP chunk and dilutes the embedding
signal. Real-world impact is small because the actual question text
dominates the chunk, but a follow-up cleanup of the chunker's
"Chapter / Heading" heuristics for question-paper-style inputs would
sharpen retrieval.

### Retrieval scores (Cluster B item 4)

`backend/scratch/probe_retrieval.py` embeds all 65 chunks from the
three PDFs and runs landmark queries via L2 distance. Top-3 results:

```
Q32_train      → rank1=MathsStandard-SQP chunk 9   L2=0.9579  sim=0.0421
Q33_BPT        → rank1=trignometry chunk 7         L2=0.9549  sim=0.0451
                 rank2=MathsStandard-SQP chunk 10  L2=0.9662  sim=0.0338
Q35_grouped    → rank1=MathsStandard-SQP chunk 11  L2=0.9747  sim=0.0253
Q38_IndiaGate  → rank1=MathsStandard-SQP chunk 14  L2=0.9857  sim=0.0143
Q31_monthly_in → rank1=MathsStandard-SQP chunk 9   L2=1.0586  sim=-0.0586
Q22_prob_dice  → rank1=MathsStandard-SQP chunk 8   L2=1.0024  sim=-0.0024
```

Every landmark the user named lands as **rank-1 or rank-2 of its
query**. Absolute similarity scores are low (0.0–0.05) because
`text-embedding-3-small` produces high-dimensional vectors where
unrelated chunks already sit at ~1.0 L2, so the relative ordering
is what matters — and the ordering is correct.

**There is no similarity threshold gating the fallback**
(`retrieve_relevant_chunks` orders by L2 and returns the top N
unconditionally), which means a threshold change is the wrong
remedy. The right one is dedup.

### Dedup-exhaustion simulation

The probe also simulates a 38-slot CBSE Standard paper with strict
per-chunk dedup (the production behaviour):

```
Total slots simulated: 38
With STRICT dedup (1 reuse):  Curriculum_fallback = 21 (55%)
                              First fallback at slot index 17
With MAX_REUSES=3:            Curriculum_fallback = 0  (0%)
```

55% matches the user-reported "most questions are tagged Curriculum
fallback". The first fallback hits at slot 17 because 16 slots × 4
chunks = 64 of the 65-chunk pool. Allowing each chunk to ground up
to 3 slots gives 65 × 3 = 195 slot-chunks, enough for any plausibly
sized paper.

### Generation grounding (Cluster B item 5)

`generation_service._generate_slot` passes the retrieved chunks
into `PromptAssembler.assemble(retrieved_chunks=...)`. The system
prompt for grounded slots is built by
`_system_rules_for_slot(slot, constraints)` which already requires
the model to anchor against `[CONTEXT]` blocks. Grounding is fine
when chunks ARE supplied; the bug was that strict dedup withheld
chunks from later slots, so they fell through to the
`curriculum_fallback=True` branch and the model was explicitly told
"no chunks for this slot, use CBSE curriculum knowledge"
(lines 1353-1360 of generation_service.py). With dedup loosened,
later slots receive chunks and the grounding path applies as
intended.

### Fix

`backend/services/generation_service.py:1223-1289`. Replaced
`used_chunk_ids: set()` with a per-chunk counter
`chunk_use_count: Dict[str, int]` and a `max_chunk_reuses` cap read
from `settings.MAX_CHUNK_REUSES` (default 3). The valid-chunk
filter changes from "id not in used" to
"use count < max reuses", and the post-allocation update
increments the counter instead of adding to a set.

### Files touched (Cluster B)

```
M backend/services/generation_service.py
A backend/scratch/dump_extraction.py
A backend/scratch/probe_retrieval.py
```

---

## CLUSTER C — VI-alternative toggle

### Where VI alternatives are inserted

* The model is prompted to emit `vi_alternative` for slots with
  `slot.vi_required=True` (e.g. Class-10 Maths SQP map/figure
  questions).
* `_coerce_question` reads the field via `_coerce_vi_alternative`
  (`generation_service.py:306-318`), then `_printable_question_content`
  appends a dashed `Note: ... Visually Impaired Students only ...`
  block beneath the OR choice
  (`generation_service.py:321-334`).
* The metadata flag `metadata["vi_alternative"] = True` is set
  whenever the field has content.

### Fix

Implemented as a **post-generation filter** per the brief, NOT as a
prompt change — so the LLM still sees VI cues in the retrieved source
and grounds correctly when relevant.

* `_coerce_question` gains an `include_vi_alternatives: bool = True`
  parameter. When False, the function drops the VI alternative
  *after* coercion, before computing `printable_content`. The
  metadata marker is also popped so downstream consumers
  (review tray, exporters, answer-script generator) read consistent
  state.
* `stream_generated_questions` parses
  `payload.get("include_vi_alternatives", payload.get("includeViAlternatives", True))`
  with snake/camel/string-false coercion and threads the value
  through to the slot generator closure.

### UI

`frontend/components/generator-form.tsx`:

* `formSchema` gains `includeViAlternatives: z.boolean()` (no
  `.default()` so the inferred type stays `boolean`, not
  `boolean | undefined`).
* `defaultValues` sets it to `true` — matching CBSE Sample Paper
  convention.
* The Generator panel renders a checkbox row beneath the
  "Count Variation" / "Exact Count" controls with explanatory copy:
  > Include Visually Impaired alternatives
  > CBSE Sample Papers attach a VI alternative to every visual
  > question. Leave on to mirror that pattern; turn off to suppress
  > the VI blocks in the generated paper without changing what the
  > model retrieves from your sources.
* The submit handler sends `include_vi_alternatives:
  values.includeViAlternatives` in the SSE start payload.

### Files touched (Cluster C)

```
M backend/services/generation_service.py
M frontend/components/generator-form.tsx
```

---

## CLUSTER D — Markitdown evaluation: SKIP

The evaluation lives in `MARKITDOWN_EVAL.md`. Headline:

* Markitdown is **15–30× slower** per file on the three user PDFs.
* It loses **image extraction** entirely (its PDF backend is
  pdfminer.six → pdfplumber, text-only). That regresses Cluster A's
  image-chunk pipeline and breaks Q23/Q33-style image-grounded
  questions.
* It **does not preserve formulae** any better than PyMuPDF (no √
  / ² / subscript recovery on the user PDFs).
* It does emit slightly better table structure (markdown pipes vs
  whitespace soup) — but the gain is cosmetic for embedding
  retrieval, not semantic.

The dedup-exhaustion fix in Cluster B is the **actual** remedy for
the curriculum-fallback flood the brief framed as a markitdown
problem. PyMuPDF stays. The package was uninstalled after evaluation
to keep the venv lean.

### Files touched (Cluster D)

```
A MARKITDOWN_EVAL.md
A backend/scratch/eval_markitdown.py
```

---

## Verification gate — what the user must confirm

| # | item | status | evidence |
|---|------|--------|----------|
| 1 | Upload trignometry.pdf again. Ingestion < 30 s. | **PASS** (measured 14.4 s in `scratch/profile_ingestion_full.py`); USER-PENDING for end-to-end confirmation via the upload UI | section "Post-fix numbers" above |
| 2 | Curriculum-fallback share for a Math Standard paper over the same 3 sources | **PREDICTED < 25%** (simulated 0% in `scratch/probe_retrieval.py` with `MAX_CHUNK_REUSES=3`); USER-PENDING for the real generation run | Cluster B "Dedup-exhaustion simulation" |
| 3 | VI toggle suppresses VI text in generated output | **CODE-VERIFIED**: `_coerce_question` drops VI when `include_vi_alternatives=False`; checkbox exists in `generator-form.tsx`; USER-PENDING for visual confirmation in the browser | Cluster C |
| 4 | Backend tests stay green | **PASS** — 98/98 q_instructions tests | `python -m unittest discover -s q_instructions/tests` |
| 5 | tsc + next build green | **PASS** | (re-run above) |

Items 1-3 require running the real app against the upload + generation
endpoints, which the agent cannot exercise from its runtime. Please
walk through `DEPLOY_CHECKLIST.md` § 3 (carried over from the prior
round, still current) for the manual gate before promoting.

---

## Files changed (full set)

```
M backend/config/settings.py
M backend/services/openai_service.py
M backend/services/document_service.py
M backend/services/generation_service.py
M frontend/components/generator-form.tsx
A MARKITDOWN_EVAL.md
A backend/scratch/profile_ingestion.py
A backend/scratch/profile_ingestion_full.py
A backend/scratch/dump_extraction.py
A backend/scratch/probe_retrieval.py
A backend/scratch/eval_markitdown.py
M FIX_REPORT.md (this file)
```

No edits to the prior rounds' fixes: ProseMirror toDOM wrapping,
`pdf_source.content_type`, PDF/DOCX export figure inlining, OR-group
logic, autosave gating, useSession optimistic render, dark-theme
paper invariant. All their regression suites still pass.
