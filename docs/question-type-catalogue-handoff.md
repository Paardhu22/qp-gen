# Session Handoff — Question Type Catalogue (2026-09-13)

## TL;DR

- **What:** implementing the spec *"Question Type Catalogue — AOS (Draft 1)"*. It replaces the flat `type` string with ~160 named presets built on separate axes (format, task, stimulus, container, options, marking).
- **Plan (approved):** [`docs/question-type-catalogue-plan.md`](./question-type-catalogue-plan.md). Read §1–§2 before touching code.
- **Branch:** `feat/question-type-catalogue` (from `main@84204d8`). **Nothing is committed yet.**
- **Progress:** step 1 of 9 is roughly 60% done. Catalogue data for families **A–H** is written; **I**, **J**, the registry, the rewiring and the tests remain.
- **Baseline before any change:** backend **953 tests, all passing** (~21 s).

---

## Before you start (3 things)

1. **Save the spec into the repo** as `docs/question-type-catalogue.md`. It only ever existed in chat. You need it for families I and J, and as the reference for everything else.
2. **Unrelated uncommitted changes are in the tree** from the Lottie cleanup:
   - deleted `frontend/components/ui/RibbonCut.tsx`, `public/animations/Gift.lottie` and `public/dotlottie-player.wasm`
   - edited `frontend/package.json` and `package-lock.json`

   Commit them on their own, or leave them. Either way, **stage catalogue files by path** so the two don't mix.
3. **Commit messages:** no `Co-Authored-By` or `Claude-Session` trailer. This is a standing preference for this repo.

---

## Decisions already made (don't re-open)

| Question | Decision |
|---|---|
| Scope | Core rebuild: plan §1–§9 |
| Figures | **Charts only**, drawn by the deterministic `services/figures` renderer. Picture, map and cartoon types are listed but disabled, with the reason shown. |
| Multi-correct MCQ | **All-or-nothing** marking |
| Classes 1–9 | **Starter templates + class-fit guidance.** Existing defaults and board cards stay untouched (plan §8). |
| Assertion–Reason | Stays **4-option** |
| Papers vs worksheets | One vocabulary |
| Picker UI | Named presets, with the axes underneath |

---

## The core idea

- **The catalogue code is the identity** (`MCQ_ODD_ONE_OUT`).
- **Every entry has a `shape`:** one of today's 22 runtime pool codes (`MCQ`, `SHORT_ANSWER`, `CASE_STUDY`, …). The shape still drives all existing machinery: option handling, legacy buckets and `slot_accepts`, editor layout, set variants, and token budgets.
- **`schema.normalize_type` keeps returning the shape**, so existing code and tests keep working. A new `normalize_type_code` returns the catalogue code.
- **Old codes resolve through aliases, permanently.** That covers pool codes, the old DB codes and teacher phrases.
- **HOTS and COMPETENCY stop being types.** They become slot attributes (`hots`, `competency`); old data still reads, via the `retired` shapes.

---

## What exists now (all untracked, not yet imported anywhere)

`backend/services/question_types/`

| File | Contents |
|---|---|
| `spec.py` | Axis vocabularies, `OptionRule`, `Route`, `Family`, `TypeSpec` (with derived availability/figure properties), `validate_spec()` |
| `shapes.py` | The 22 runtime shapes: bucket, `accepted_by`, tokens, default catalogue type, picker label/group/marks, option-bearing/composite/retired flags. Also `BUCKET_ACCEPTS`, `SHAPE_SYNONYMS` (the LLM synonyms moved from `schema._TYPE_ALIASES`), `bucket_for_shape()` |
| `families.py` | The 10 families A–J. Codes double as `QuestionFamily` primary keys. |
| `catalog/_build.py` | `family_builder()` entry helper; `FOUR` option rule; the fixed AR directions |
| `catalog/choice.py` | **A1–A23** |
| `catalog/supply.py` | **B1–B14** |
| `catalog/descriptive.py` | **C1–C14** |
| `catalog/source.py` | **D1–D13** |
| `catalog/visual.py` | **E1–E16** (E10 is also G15, E13 is also I14, E15 is also I2) |
| `catalog/language.py` | **F1–F18** (grammar and vocabulary) |
| `catalog/writing.py` | **F19–F31**, plus ARTICLE/REPORT (offered; the writing generator writes them) and ADVERTISEMENT/NOTE_MAKING/ORAL (hidden, `internal`) |
| `catalog/maths.py` | **G1–G14** |
| `catalog/practical.py` | **H1–H11**, plus PRACTICAL_TASK/PROJECT_WORK (hidden, `internal`) |

Each family module exposes `ENTRIES = [...]`. Every `available` entry has a `brief` and `example`, lifted from the spec; `validate_spec` enforces this.

---

## Step 1: remaining work, in order

1. **`catalog/primary.py`** (Family I, `family="PRIMARY_ACTIVITY"`). Entries I1, I3–I13, I15–I19, I21.
   - Skip the cross-references: I2 = `CIRCLE_PICTURE` (E15), I14 = `JOIN_DOTS` (E13), I20 = `TICK_CROSS` (B14).
   - Items marked [BLOCKED] in the spec get `stimulus="IMAGE"`.
   - `CIRCLE_CORRECT` uses `OptionRule(2, 3)` with shape `MCQ`.
   - `COUNT_WRITE`: the spec suggests a ★-character text variant; keep it `IMAGE` for now.
2. **`catalog/structural.py`** (Family J). OR_GROUP, CHOICE_POOL, SUB_QUESTION_SET, COMMON_STEM_GROUP, WORD_BANK_GROUP, VI_ALTERNATIVE, INSTRUCTION_BLOCK, all with `availability="structural"` (no brief needed). Use shape `SHORT_ANSWER` as a placeholder; these are never slot types.
3. **`catalog/__init__.py`.** `ALL_ENTRIES` = every family's `ENTRIES`, in A→J order.
4. **`services/question_types/registry.py`**, re-exported from `__init__.py`:
   - `CATALOG: Dict[code, TypeSpec]`. At import, fail on duplicate codes or aliases, run `validate_spec` on every entry, and check `spec.shape in SHAPE_CODES`.
   - The alias index normalises input (upper case, spaces and hyphens → `_`). Sources:
     - each spec's `code` and `aliases`
     - each shape code → `shape.default_type`, carrying `shape.implies` attributes
     - `SHAPE_SYNONYMS` → shape → its default type
   - `resolve(raw) -> (TypeSpec | None, attributes: frozenset)`.
   - Helpers: `shape_of(raw)`, `legacy_bucket(raw)`, `default_type_for_shape(shape)`, `is_option_bearing`, `is_container`.
5. **Rewire the existing lists to derive from the package. Behaviour must not change.**
   - `services/pool/schema.py`: `QUESTION_TYPES = SHAPE_CODES`, `OPTION_BEARING_TYPES`, `LEGACY_TYPE_ACCEPTS = BUCKET_ACCEPTS`, `_TYPE_ALIASES = SHAPE_SYNONYMS`. `normalize_type` also accepts catalogue codes and returns their shape; add `normalize_type_code`.
   - `apps/projects/question_types.py`: build `LEGACY_TYPE_CODE_MAP` / `CANONICAL_TO_POOL_TYPE` from shapes and the catalogue.
   - `services/templates.py`: `_LEGACY_TYPE_MAP` → `bucket_for_shape`. **Keep** the 22-entry `QUESTION_TYPE_CATALOG`, HOTS/COMPETENCY included, until step 7; the tests pin it.
   - `services/pool/pipeline.py::_legacy_type_for`, `services/pool/replace.py::_legacy_type_for` and `services/generation_router.py::_legacy_question_type` → `bucket_for_shape`.
   - `services/pool/recipes.py::_TOKENS_PER_QUESTION` → from `shape.tokens`.
6. **`services/question_types/test_catalog.py`.** Tests:
   - unique codes and aliases
   - every old DB code from migration 0012 resolves
   - every pool code resolves
   - every available entry has a brief and example
   - all derived lists equal the old literal values; copy those literals into the test before deleting them
7. **Run the full suite** (953 must stay green), then commit, e.g. `feat(question-types): add the question type catalogue`.

**One intended fix in step 1:** COMPOSITION's legacy bucket was SHORT in the router but LONG everywhere else. It is now LONG. No test pins it, and no blueprint emits COMPOSITION.

---

## Tests that pin current behaviour (keep green until the step that changes them)

- **`q_instructions/tests/test_new_subjects.py::TestLegacyTypeMapping`** pins READING_COMP→CASE_STUDY, GRAMMAR→SHORT, LETTER→LONG, MCQ, AR, LONG_ANSWER→LONG, SHORT_ANSWER→SHORT.
- **`services/test_templates.py`, `QuestionTypeMenuTests`** (two classes) pins:
  - the 22-entry menu, with groups Objective and Descriptive
  - generator menus: reading→`{READING_COMP}`, grammar→`{GRAMMAR}`, writing→`{LETTER, COMPOSITION, ANALYTICAL_PARAGRAPH}`
  - that the textbook menu excludes READING_COMP and LETTER
  - that every option code is in `QUESTION_TYPES`

  Update these deliberately in **step 7**.
- **`services/pool/test_model1.py`** expects a 3-option MCQ to be dropped. That stays true for `MCQ_SINGLE`.

---

## Steps 2–9 (details in the plan)

2. **DB and export.** Migration `projects/0016_question_type_catalogue`, seeded from a frozen JSON snapshot; `manage.py export_question_types` writes that snapshot and `frontend/lib/question-types.generated.ts`; sync tests; bump the `all_question_types` cache key in `QuestionTypeListView`.
3. **Lossless identity end to end.** `type_code` on the pool, slots, wire, bank, editor attribute and slotMeta; HOTS/COMPETENCY → attributes.
4. **Model 1.** Batch briefs only for non-default presets (the system prompt stays byte-identical), recipes keyed by code, option rules, a +12 preset preference in `model2._score_question`, and original-lane routing to the reading/grammar/writing generators.
5. **Structured containers.** `services/pool/structure.py` with parts, choice pools and table stimuli, rendered as TipTap tables. **Also fix DOCX export**, which prints only a question's first paragraph.
6. **Charts.** Model 1 emits a figure spec → `services/figures.render_chart` → `PoolQuestion.image`.
7. **Picker.** A searchable Base UI Combobox picker for the Builder and the swap dialog, plus HOTS/Competency toggles and class-fit chips.
8. **Classes.** Class-banded Bloom/difficulty targets in Model 2, and class starter templates.
9. **Vocabulary and docs.** Designer, GIM and instruction-parser vocabulary from the catalogue; answer keys; `services/question_types/README.md`; memory notes.

---

## Code facts found during exploration (saves re-reading)

- **Plan precedence in `stream_pool_questions`:** submitted Builder blueprint → GIM/design brief → board engine. The app always sends a blueprint now, and then **Model 1's recipe is derived from the plan for every subject** (`recipe_plan`), so new presets reach generation without touching the fixed recipes.
- **`slot_accepts` gates in this order:** generator → exact marks → shape/bucket. `asset_type` is **scored, not gated** (`model2._score_question`, ±10). Preset matching should follow the same pattern.
- **Independent generators already write:**
  - writing: 5 letter kinds, article, speech, report, notice, email, story, debate, analytical paragraph (`WRITING_FORMAT_GLOSS`)
  - grammar: gap-fills, error correction, editing, reported speech, transformation (`GRAMMAR_TASK_GLOSS`)
  - reading: unseen passages with 17 sub-question skills
- **Composite questions already render in the editor** via `metadata.composite {preamble, body, subQuestions}` (`frontend/components/editor/question-nodes.ts::buildQuestionBlocks`).
- **The editor already registers `@tiptap/extension-table`.** `@base-ui/react` 1.4.1 ships `combobox` and `popover`.
- **`frontend/lib/export-docx.ts::buildQuestionBlock`** reads only the first `<p>` of a question. That already drops the Reason line of Assertion–Reason.
- **Figures:** `services/figures/spec.parse_chart_spec` (Django-free) and `services/figures.render_chart(spec)` return a stable `/media/question_figures/*.svg` URL.
- **Designer drift bug** (fixed in step 9): `services/paper_design.py` emits `FILL_BLANK`/`MATCH_FOLLOWING`, which `SlotSpec.from_dict` does not recognise, so they silently become `SHORT_ANSWER`.

---

## Commands

```bash
# Backend: Django TestCase; settings switch to in-memory SQLite automatically
cd backend && source venv/bin/activate
python manage.py test                     # full suite (953 at baseline)
python manage.py test services.pool       # one package

# Frontend
cd frontend
npx tsc --noEmit
npm run lint
node scripts/test-question-nodes.mjs
```
