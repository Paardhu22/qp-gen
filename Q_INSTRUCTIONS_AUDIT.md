# Q_INSTRUCTIONS — Phase 1 Audit (read-only)

Scope: trace the LIVE generation path for streaming question generation,
map blueprinting / validation / routing, and inventory each subject's
blueprint AS CURRENTLY ENCODED in the code. **No CBSE fact-checking in
this phase** — that requires the official 2025-26 SQP + marking-scheme
PDFs and lives in Phase 2.

## 1. The LIVE streaming generation path (one source of truth)

```
HTTP POST /api/generation/papers/stream
  → apps/generation/views.py::QuestionGenerationStreamView.post
    → services/generation_service.py::stream_generated_questions
      ├── (if qpType == "general_instructions") → stream_general_instructions_questions
      │      (does NOT touch q_instructions blueprints — free-text mode)
      │
      └── (default, Board Mode)
        ├── services/generation_router.py::should_use_new_engine(payload)
        │     gate: board == "CBSE" AND (subject, class) is in
        │     _NEW_ENGINE_ELIGIBILITY = {
        │       "science":        classes 1-10,
        │       "social science": classes 1-10,
        │       "mathematics":    [10],
        │       "english":        [10],
        │       "hindi":          [10],
        │       "telugu":         [10],
        │     }
        ├── services/generation_router.py::build_question_plan(...)
        │     → IF class_num == 10 AND no count AND no custom AND no override:
        │         _build_exact_cbse_class10_plan(subject_norm)
        │           → _exact_class10_blueprint_entries(subject_norm)
        │             ├── mathematics → _exact_class10_blueprint_entries_mathematics  (router.py:1330)
        │             ├── english     → _exact_class10_blueprint_entries_english      (router.py:1495)
        │             ├── hindi       → _exact_class10_blueprint_entries_hindi        (router.py:1674)
        │             ├── telugu      → _exact_class10_blueprint_entries_telugu       (router.py:1923)
        │             ├── social science → inline literal (router.py:2207-2244)
        │             └── (default) science → inline literal (router.py:2247-2322)
        │     ELSE (custom count, class < 10, or explicit instruction override):
        │       walks _build_primary_progression OR ScienceOrchestratorV2 /
        │       SocialScienceOrchestratorV2 (only those two are touched here)
        ├── per-slot RAG retrieval (services/retrieval_service.py)
        ├── per-slot LLM call via apps/question_generation/.../openai_provider.OpenAIProvider
        ├── per-slot _coerce_question + validate_language_question
        └── SSE stream → editor
```

**Confirmation of the brief's hypothesis** ("Class-10 language blueprints
are believed to live INLINE in the router, while subjects/*/orchestrator.py
may be dead for streaming"): **CORRECT.**

- For the most common case — Board Mode, Class 10, no Custom Count, no
  per-section instruction override — *every* blueprint (all six subjects)
  is read from the inline functions at the top of
  `services/generation_router.py`. No `q_instructions/subjects/*/` file
  is consulted on this hot path.
- `q_instructions/subjects/{science,social_science}/orchestrator.py` are
  only touched on the secondary path: Board Mode with a custom count, or
  class ≠ 10. They wire up stream allocation + tier progression — they
  don't ship a Class-10 blueprint.
- `q_instructions/subjects/{mathematics,english,hindi,telugu}/orchestrator.py`
  and the corresponding `blueprint.py` registries
  (`MathematicsBlueprintRegistry`, `EnglishBlueprintRegistry`, etc.) are
  defined but **never imported by any live module**. They are dead-code
  duplicates of the inline router entries.

## 2. Dead / duplicated code (drift risk)

This is where Phase 3 should consolidate.

### 2.1 Per-subject `blueprint.py` registries

| File | Class | Live consumer outside the file itself |
|---|---|---|
| `q_instructions/subjects/mathematics/blueprint.py` | `MathematicsBlueprintRegistry` | **none** |
| `q_instructions/subjects/english/blueprint.py` | `EnglishBlueprintRegistry` | **none** |
| `q_instructions/subjects/hindi/blueprint.py` | `HindiBlueprintRegistry` | **none** |
| `q_instructions/subjects/telugu/blueprint.py` | `TeluguBlueprintRegistry` | **none** |
| `q_instructions/subjects/social_science/blueprint.py` | `SocialScienceBlueprintRegistry` | only `q_instructions/subjects/social_science/blueprint.py` itself |
| `q_instructions/subjects/science/blueprint.py` | `ExamBlueprintRegistry` | `q_instructions/generation/blueprint_compiler.py` (legacy/debug only) |

Drift risk: the math blueprint registry says "38 questions, 80 marks"
in its docstring (matches the live inline); but if anyone updates one
they will forget the other. There is currently no test that pins the
registry to the inline entries.

### 2.2 Per-subject `orchestrator.py` modules

| File | Live consumer |
|---|---|
| `q_instructions/subjects/mathematics/orchestrator.py` | **none** |
| `q_instructions/subjects/english/orchestrator.py` | **none** |
| `q_instructions/subjects/hindi/orchestrator.py` | **none** |
| `q_instructions/subjects/telugu/orchestrator.py` | **none** |
| `q_instructions/subjects/science/orchestrator.py::ScienceOrchestratorV2` | `generation_router._build_question_plan` (custom-count branch only) |
| `q_instructions/subjects/social_science/orchestrator.py::SocialScienceOrchestratorV2` | same |

### 2.3 The "legacy" master engine

`q_instructions/master/facade.py::AcademicGenerationFacade` →
`q_instructions/master/orchestrator.py::MasterAcademicOrchestrator` →
`q_instructions/generation/blueprint_compiler.py::BlueprintCompiler` →
`q_instructions/subjects/science/blueprint.py::ExamBlueprintRegistry`

Used by:
- `services/generation_router.py::route_and_execute_new_engine` —
  itself a compatibility wrapper whose docstring says "The streaming
  generation path now uses build_question_plan instead."
  (router.py:2796-2823)
- `config/debug_views.py::science_engine_health` — admin debug endpoint
- `apps/question_generation/tests/test_parity.py` — parity test fixture

Verdict: live streaming does **not** read from this path. It exists as
a parallel codebase ("new engine v2"), tracked in `apps/question_generation/`
and the `q_instructions/master/` tree, that the brief flags as dead for
streaming.

### 2.4 `legacy/` folder

`q_instructions/legacy/` — explicitly marked legacy. No live consumer
(verified by grep). Cleanup is out of scope but should land in a future
pass.

## 3. Validation pipeline (what runs after the LLM responds)

The post-LLM gates, in order, are:

1. **`_coerce_question`** (`services/generation_service.py:366`) — coerces
   the raw JSON into the editor schema. Hard-rejects:
   - empty `content`
   - type mismatch (MCQ slot returning no options; non-MCQ slot returning
     options)
   - figure references in stem without a figure (regenerate with
     `_strip_figure_references` on the last attempt)
   - `slot.requires_image` true but no image_url in the LLM payload
   - `slot.requires_figure` true but no valid inline SVG
   - missing `or_choice` when `slot.choice_required`
   - missing `vi_alternative` when `slot.vi_required`
2. **`validate_language_question`** (`services/language_validation.py:162`) —
   dispatches by `slot.generation_mode`:
   - `CONTENT` → no-op (Science / Social Science / Maths / literature)
   - `GRAMMAR` → script ratio + Telugu chandas gaṇa↔metre table cross-check
   - `COMPOSITION` → script ratio + word-limit presence + Hindi anuched
     "exactly 3 संकेत-बिन्दु per topic" + English analytical "≥ 2
     comparable options" gate
   - `PASSAGE` → script ratio

No Pydantic anywhere. No mark-to-difficulty enforcement at validation
time — `difficulty` is a string that flows from the form into the slot
contract and gets quoted into the system prompt. The blooms_engine.py
files under `subjects/*` define difficulty-coefficient ranges per Bloom
level but are dead for streaming (see §2.2).

### Gaps surfaced by the audit

| Gap | Where it bites |
|---|---|
| No Pydantic schema for the LLM JSON output — only a hand-written `_single_question_schema(...)` STRING printed into the prompt. Parse errors fall back to regex extraction in `_coerce_question` + `_fallback_answer_from_text`. | `services/generation_service.py:499-564`, `services/answer_script_service.py:_parse_answer_payload` |
| No mark-to-difficulty mapping on the streaming path. A 5-mark LA in an "easy" paper is still treated as "easy" in the prompt, which conflicts with CBSE expectation that LA is HOTS / multi-step. | `services/generation_router.py::_make_slot` passes `difficulty` verbatim. |
| OR-pair language parity (both branches same Bloom + mark + difficulty) is enforced in the prompt prose but not validated post-generation. `validate_language_question` covers script + format but not OR-pair parity. | `validate_language_question`, no parity check |
| Per-Bloom output-length / sub-question count is described in the `hint` strings but never machine-checked. The hint is prose: "Generate 4 questions; student answers any 3." A model emitting 3 questions instead of 4 is currently accepted. | All inline blueprint entries |
| Telugu chandas table (`TELUGU_METRE_GANA`) covers 4 metres only. Class-10 SQP can reference others — those would never trigger the validation. | `services/generation_router.py:871-876` |
| `default_cbse_question_count` lives next to the inline blueprints but is independent of them — if either drifts, custom-count generation can disagree with exact-mode totals. | `services/generation_router.py:793` |
| The hint strings hard-code SQP-specific question stems (e.g. Maths Q1 "LCM/HCF by prime factorisation"). These are likely lifted from one specific SQP and now drift if CBSE changes patterns year-on-year. There is no machine link from a hint to the source PDF + page. | All inline blueprint entries |
| `content_scope_policy` (strict / source_only) is read from the payload but defaults to "strict" silently. Field is undocumented in the form. | `stream_generated_questions:1143-1149` |

## 4. Hardcoded constants that should be config

| Constant | File:line | Reason |
|---|---|---|
| `_NEW_ENGINE_ELIGIBILITY = {"science": 1..10, "social science": 1..10, "mathematics": [10], "english": [10], "hindi": [10], "telugu": [10]}` | generation_router.py:21-28 | Class-range support per subject. Should be one config entry per subject; adding Class 9 means editing the matrix. |
| `_SUBJECT_ALIASES` | generation_router.py:31-43 | Cross-cutting; should live with the subject's own config (e.g. a per-subject `aliases: ["maths","math"]`). |
| `_GRAMMAR_TASK_PLAN` (any-N-of-M counts) | generation_router.py:879-882 | Only English + Hindi here; Telugu's split (e.g. Q4 any 4 / 4 marks) is inlined into the entry `hint` strings. |
| `TELUGU_METRE_GANA` | generation_router.py:871-876 | Should be a per-language phonological config — Hindi has similar prosody. |
| `CBSE_TOTAL_MARKS = 80`, `CBSE_INTERNAL_CHOICE_MIN_PAIRS = 3`, `CBSE_COMPETENCY_MINIMUM_RATIO = 0.50`, `CBSE_MCQ_MINIMUM_RATIO = 0.20`, `CBSE_LONG_ANSWER_MAX_RATIO = 0.20` | q_instructions/core/constants.py:12-18 + duplicate in apps/question_generation/domain/constants.py | Two copies of the same constants. Streaming reads neither — these are referenced only by the dead legacy engine. |
| Section title strings ("Section A - Biology", "खण्ड क - अपठित बोध", "విభాగం ఎ") | inline in every `_exact_class10_*` entry | Section labels per subject should live with the subject. |

## 5. Per-subject blueprint inventory (AS ENCODED)

All six tables are pinned by `test_new_subjects.py` and
`test_hybrid_routing.test_cbse_exact_{science,social_science}_plan_is_80_marks`.
Counts match `_check`: `sum(marks*count) == 80` and `sum(count) == N`.

### 5.1 Mathematics Standard (Code 041)

Source: `services/generation_router.py:1330-1492` (
`_exact_class10_blueprint_entries_mathematics`).
Docstring claims: "38 questions, 80 marks — CBSE Class 10 Mathematics
Standard (Code 041) SQP 2025-26."

| Section | Q range | Type | Marks/Q | Count | Section marks | OR placement | Notes |
|---|---|---|---:|---:|---:|---|---|
| A — Objective Questions | Q1–Q18 | MCQ | 1 | 18 | 18 | none | Each Q has a topic hint baked into the entry |
| A — Objective Questions | Q19–Q20 | ASSERTION_REASON | 1 | 2 | 2 | none | Q19 Real Numbers, Q20 Trigonometry |
| B — Very Short Answer | Q21–Q25 | SHORT_ANSWER | 2 | 5 | 10 | Q21 ✓, Q24 ✓ (others none) | Q23 marks `requires_figure: True` |
| C — Short Answer | Q26–Q31 | SHORT_ANSWER | 3 | 6 | 18 | Q29 ✓, Q31 ✓ | |
| D — Long Answer | Q32–Q35 | LONG_ANSWER | 5 | 4 | 20 | Q34 ✓, Q35 ✓ | Q33 `requires_figure: True` |
| E — Case Based Questions | Q36–Q38 | CASE_STUDY | 4 | 3 | 12 | all 3 ✓ (on sub-part iii) | AP / Coord. Geometry / Heights & Distances |
| **Total** | | | | **38** | **80** | **8 OR pairs** (4 outer + 3 inner case-study + 1 within E) | |

Competency / MCQ / descriptive split (as encoded):
- MCQ + AR (objective): 20 marks / 80 = **25%**
- LA descriptive (5-mark): 20 marks / 80 = **25%**
- Competency / case-based (Section E + the case-study-style sub-parts): 12 marks / 80 = **15%**
- SA / VSA + competency context blended: remaining 28 marks / 80 = **35%**

Note: the 50% competency / 20% MCQ / 30% descriptive split called out in
the brief is not directly verifiable from the entries — the entries
classify by *question type* (MCQ / AR / SA / LA / CS), not by *cognitive
tier* (competency / descriptive). Phase 2 must read the SQP marking
scheme to confirm the typology mapping.

### 5.2 English Language & Literature (Code 184)

Source: `services/generation_router.py:1495-1671`.
Docstring: "11 questions, 80 marks — CBSE Class 10 English Language &
Literature (Code 184) SQP 2025-26."

| Section | Q | Type / mode | Marks | Internal sub-parts | OR | Notes |
|---|---|---|---:|---|---|---|
| A — Reading | Q1 | READING_COMP / PASSAGE | 10 | 8 (1+1+1+1+1+2+1+2) | — | Original ~400-word factual/discursive passage |
| A — Reading | Q2 | READING_COMP / PASSAGE | 10 | 9 (7×1m + 1×2m + 1×1m) | — | Original ~250-word data/infographic passage |
| B — Grammar/Writing | Q3 | GRAMMAR | 10 | 12 tasks, attempt 10 | — | Tense / reported speech / error correction / preposition / modal / determiner / quantifier / participle |
| B — Grammar/Writing | Q4 | LETTER / COMPOSITION | 5 | — | ✓ | Formal letter (A) OR Letter to Editor (B), ~120 words |
| B — Grammar/Writing | Q5 | SHORT_ANSWER / COMPOSITION | 5 | — | ✓ | Analytical paragraph, 120-150 words |
| C — Literature | Q6 | SHORT_ANSWER | 5 | 4 (2+1+1+1) | ✓ | Two prose extract options from First Flight |
| C — Literature | Q7 | SHORT_ANSWER | 5 | 4 (1+2+1+1) | ✓ | Two poetry extract options |
| C — Literature | Q8 | SHORT_ANSWER | 12 | 5 questions × 3m, attempt 4 | — | ≥2 First Flight Prose + ≥1 Poetry + ≥1 Footprints |
| C — Literature | Q9 | SHORT_ANSWER | 6 | 3 questions × 3m, attempt 2 | — | Footprints Without Feet only |
| C — Literature | Q10 | LONG_ANSWER | 6 | — | ✓ | Two options First Flight, ~100-120 words |
| C — Literature | Q11 | LONG_ANSWER | 6 | — | ✓ | Two options Footprints |
| **Total** | **11 Qs** | | **80** | | **6 OR pairs** | |

Section marks: A = 20 (Reading), B = 20 (Grammar+Writing), C = 40
(Literature).

### 5.3 Hindi Course B (Code 085)

Source: `services/generation_router.py:1674-1920`.
Docstring: "16 questions, 80 marks — CBSE Class 10 Hindi Course B (Code 085) SQP 2025-26."

| Section (खण्ड) | Q | Type / mode | Marks | OR | Notes |
|---|---|---|---:|---|---|
| क — अपठित बोध | Q1 | CASE_STUDY / PASSAGE | 7 | — | Original ~250-300 word passage; 7 sub-parts (all 1m) |
| क — अपठित बोध | Q2 | CASE_STUDY / PASSAGE | 7 | — | Same shape as Q1, different theme |
| ख — व्याकरण | Q3 | GRAMMAR / GRAMMAR | 4 | — | पदबंध, 5 tasks attempt 4 |
| ख — व्याकरण | Q4 | GRAMMAR / GRAMMAR | 4 | — | वाक्य रूपांतरण, 5 tasks attempt 4 |
| ख — व्याकरण | Q5 | GRAMMAR / GRAMMAR | 4 | — | समास, 5 tasks attempt 4 |
| ख — व्याकरण | Q6 | GRAMMAR / GRAMMAR | 4 | — | मुहावरे, 5 tasks attempt 4 |
| ग — पाठ्यपुस्तक | Q7 | MCQ | 5 | — | स्पर्श गद्यांश extract, 5 MCQs |
| ग — पाठ्यपुस्तक | Q8 | SHORT_ANSWER | 6 | — | 4 गद्य Qs × 2m, attempt 3 |
| ग — पाठ्यपुस्तक | Q9 | MCQ | 5 | — | स्पर्श काव्यांश extract, 5 MCQs |
| ग — पाठ्यपुस्तक | Q10 | SHORT_ANSWER | 6 | — | 4 काव्य Qs × 2m, attempt 3 |
| ग — पाठ्यपुस्तक | Q11 | SHORT_ANSWER | 6 | — | संचयन: 3 Qs × 3m, attempt 2 |
| घ — रचनात्मक लेखन | Q12 | LONG_ANSWER / COMPOSITION | 5 | — | अनुच्छेद: 3 topics, each with EXACTLY 3 संकेत-बिन्दु, attempt 1 |
| घ — रचनात्मक लेखन | Q13 | LETTER / COMPOSITION | 5 | ✓ | औपचारिक पत्र — two options |
| घ — रचनात्मक लेखन | Q14 | SHORT_ANSWER / COMPOSITION | 4 | ✓ | सूचना — two options |
| घ — रचनात्मक लेखन | Q15 | SHORT_ANSWER / COMPOSITION | 3 | ✓ | विज्ञापन — two options |
| घ — रचनात्मक लेखन | Q16 | LONG_ANSWER / COMPOSITION | 5 | ✓ | लघुकथा / ई-मेल — two options |
| **Total** | **16 Qs** | | **80** | **5 OR pairs** | |

Section marks: क = 14, ख = 16, ग = 28, घ = 22.

### 5.4 Telugu Telangana (Code 089)

Source: `services/generation_router.py:1923-2194`.
Docstring: "18 questions, 80 marks — CBSE Class 10 Telugu Telangana (Code 089) SQP 2025-26."

⚠️ **Phase 2 risk flag**: official CBSE 2025-26 SQP coverage for code
089 is sparse on cbseacademic.nic.in. The blueprint here lists topic
hints rooted in Telugu literary tradition (గోలకొండ, కొత్తబాట,
కాళహస్తీశ్వర శతకం, రామాయణం) and very specific structural counts.
Verifying these against the official SQP is the single subject most
likely to need an alternative authoritative source — flag explicitly
in Phase 2 if not obtainable.

| Section (విభాగం) | Q | Type / mode | Marks | OR | Notes |
|---|---|---|---:|---|---|
| ఎ | Q1 | READING_COMP / PASSAGE | 10 | — | Original ~300-word Telugu passage; 5 MCQs × 2m |
| బి | Q2 | LETTER / COMPOSITION | 6 | — | లేఖా-రచన, ~100 words, full Telugu format |
| బి | Q3 | LONG_ANSWER / COMPOSITION | 5 | ✓ | దినచర్య (diary) OR వార్తా (news report), ~100 words |
| సి | Q4 | MCQ / GRAMMAR | 4 | — | సంధి — 4 MCQs |
| సి | Q5 | MCQ / GRAMMAR | 4 | — | ఛందస్సు — 4 MCQs, gates against `TELUGU_METRE_GANA` |
| సి | Q6 | MCQ / GRAMMAR | 4 | — | సమాసం — 4 MCQs |
| సి | Q7 | MCQ / GRAMMAR | 4 | — | అలంకారాలు — 4 MCQs |
| సి | Q8 | MCQ / GRAMMAR | 2 | — | పర్యాయ పదాలు |
| సి | Q9 | MCQ / GRAMMAR | 2 | — | జాతీయాలు |
| సి | Q10 | MCQ / GRAMMAR | 2 | — | సామెతలు |
| సి | Q11 | MCQ / GRAMMAR | 2 | — | పాఠ్యాంశ ప్రక్రియ |
| సి | Q12 | MCQ | 5 | — | పరిచిత గద్యాంశం — 5 MCQs |
| డి | Q13 | SHORT_ANSWER | 4 | — | సంగ్రహ జవాబులు: 4 Qs × 2m, attempt 2 |
| డి | Q14 | SHORT_ANSWER | 4 | — | సంగ్రహ జవాబులు-2: 4 Qs × 2m, attempt 2 |
| డి | Q15 | LONG_ANSWER | 4 | ✓ | విపులంగా — two options, ~120 words |
| డి | Q16 | LONG_ANSWER | 4 | ✓ | విపులంగా-2 — two options |
| డి | Q17 | LONG_ANSWER | 6 | ✓ | పద్యం అన్వయ క్రమం + ప్రతిపదార్థాలు — two options |
| డి | Q18 | LONG_ANSWER | 8 | — | ఉపవాచకం (Ramayanam): 4 Qs × 4m, attempt 2 |
| **Total** | **18 Qs** | | **80** | **4 OR pairs** | |

Section marks: ఎ = 10, బి = 11, సి = 29, డి = 30.

### 5.5 Science (Code 086 General)

Source: `services/generation_router.py:2247-2322` (inline literal in
`_exact_class10_blueprint_entries`).
Pinned by `test_cbse_exact_science_plan_is_80_marks`.

| Section | Stream | Q types | Per-Q marks × count | Section marks | OR | requires_image / vi |
|---|---|---|---|---:|---|---|
| A — Biology | BIOLOGY | 7 MCQ + 2 AR + 3 SA(2m, 1 with choice) + 2 SA(3m) + 1 CASE(4m, choice + vi) + 1 LA(5m, choice) | 7×1 + 2×1 + 3×2 + 2×3 + 1×4 + 1×5 | 30 | 3 | CASE has vi_required |
| B — Chemistry | CHEMISTRY | 7 MCQ + 1 AR + 1 SA(2m) + 2 SA(3m, 1 with choice) + 1 CASE(4m, vi) + 1 LA(5m, choice) | 7×1 + 1×1 + 1×2 + 2×3 + 1×4 + 1×5 | 25 | 2 | CASE has vi_required |
| C — Physics | PHYSICS | 2 MCQ + 1 AR + 1 SA(2m, choice) + 1 SA(2m, vi) + 1 SA(3m, numerical) + 2 SA(3m, vi) + 1 CASE(4m, choice + vi) + 1 LA(5m, choice + vi) | 2×1 + 1×1 + 1×2 + 1×2 + 1×3 + 2×3 + 1×4 + 1×5 | 25 | 3 | many vi_required |
| **Total** | | **39 Qs** | | **80** | **8** | |

The OR count matches `test_cbse_exact_science_plan_is_80_marks` —
`summary["or_choices"] == 8`. Sections sum: 30 + 25 + 25 = 80.

### 5.6 Social Science (Code 087)

Source: `services/generation_router.py:2207-2244` (inline literal).
Pinned by `test_cbse_exact_social_science_plan_is_80_marks`.

| Section | Stream | Q types | Per-Q marks × count | Section marks | OR | image / vi |
|---|---|---|---|---:|---|---|
| A — History | HISTORY | 4 MCQ (Q1 match-the-following; Q2 image+vi; Q3 standard; Q4 quotation) + 1 SA(2m, choice) + 1 SA(3m, choice) + 1 LA(5m, choice) + 1 CASE(4m) + 1 DIAGRAM(2m, image+vi) | 4×1 + 1×2 + 1×3 + 1×5 + 1×4 + 1×2 | 20 | 3 | Q2 + map Q9 |
| B — Geography | GEOGRAPHY | 6 MCQ + 1 SA(2m) + 1 LA(5m, choice) + 1 CASE(4m) + 1 DIAGRAM(3m, choice + image+vi) | 6×1 + 1×2 + 1×5 + 1×4 + 1×3 | 20 | 2 | Map Q19 |
| C — Political Science | CIVICS | 3 MCQ + 1 AR + 2 SA(2m) + 1 SA(3m) + 1 LA(5m, choice) + 1 CASE(4m) | 3×1 + 1×1 + 2×2 + 1×3 + 1×5 + 1×4 | 20 | 1 | Q21 cartoon image+vi |
| D — Economics | ECONOMICS | 6 MCQ + 3 SA(3m) + 1 LA(5m, choice) | 6×1 + 3×3 + 1×5 | 20 | 1 | — |
| **Total** | | **38 Qs** | | **80** | **7** | 4 image |

Matches `test_cbse_exact_social_science_plan_is_80_marks`:
`total_questions == 38`, `total_marks == 80`, `or_choices == 7`,
`image_questions == 4`, all section_marks == 20.

## 6. What Phase 2 needs (per subject)

The brief is correct that aggregator sites disagree on the typology
split. The only valid source for Phase 2 is the official CBSE
2025-26 PDFs from `cbseacademic.nic.in`. Per subject, the artefacts
to obtain:

| Subject | Required SQP + marking-scheme | Notes |
|---|---|---|
| Science (086) | SQP_2025-26_Science.pdf + MS_2025-26_Science.pdf | Verify section split, OR count = 8, image questions, CASE_STUDY = 1 per section |
| Social Science (087) | SQP_2025-26_SocialScience.pdf + MS | Verify 4 sections × 20 marks, History map (2m) + Geography map (3m), Civics Assertion-Reason placement |
| Mathematics Standard (041) | SQP_2025-26_Maths_Standard.pdf + MS | Verify Q1-Q18 MCQ + Q19-Q20 AR; OR placements; Section E CASE_STUDY topics (AP / Coord Geo / Heights & Distances) |
| English Lang & Lit (184) | SQP_2025-26_English_LangLit.pdf + MS | Verify Q1+Q2 reading mark distribution, Q3 grammar split, Q8 12-marker structure (5 Qs × 3m attempt 4) |
| Hindi Course B (085) | SQP_2025-26_Hindi_CourseB.pdf + MS | Verify खण्ड sums (14+16+28+22), Q12 anuched "exactly 3 sankel-bindu" rule, Q14/Q15 word counts |
| Telugu Telangana (089) | SQP_2025-26_Telugu_Telangana.pdf + MS | **Flag**: sparse SQP coverage expected. If unavailable from cbseacademic.nic.in, list the Phase-2 fallback (NCERT / SCERT Telangana board) and proceed with explicit "unverified" labels in the discrepancy report. |

The 50/20/30 typology split (competency / MCQ / descriptive) is not
mechanically checkable from the entries alone (see §5.1 note). Phase 2
will need to read the marking scheme to classify each entry by tier.

---

*End of Phase 1. No code modified in this phase.*
