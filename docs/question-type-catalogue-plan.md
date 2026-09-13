# Plan — Question Type Catalogue (core rebuild)

## Context

The spec (*Question Type Catalogue — AOS, Draft 1*) replaces the single flat `type` string with a catalogue of named presets (A–J, ~160 unique codes) built on separate axes: format, task, stimulus, container, options, answer space and marking. It covers CBSE Classes 1–10, for both papers and worksheets.

Today the type vocabulary lives in **five places that have drifted apart**:
- `services/pool/schema.py::QUESTION_TYPES` (22 codes)
- the DB `QuestionType` table (65 rows, migration 0012, a different code set)
- the Builder menu in `services/templates.py::QUESTION_TYPE_CATALOG`
- the designer vocabulary in `services/paper_design.py`
- label maps in about six other files, backend and frontend

Damage this causes today:
- **Designer types silently become short answers.** The designer emits `FILL_BLANK` and `MATCH_FOLLOWING`, which `SlotSpec.from_dict` does not recognise, so they turn into `SHORT_ANSWER`.
- **The bank round trip is lossy.** HOTS, COMPETENCY and SHORT_ANSWER all save as `SA`.
- **Only 4-option MCQs survive.** The normaliser drops every MCQ that doesn't have exactly 4 options.
- **Case studies are flat text.** There are no structured sub-parts.
- **DOCX export prints only the first paragraph of a question.** This already drops the Reason line of Assertion–Reason.

**Your decisions:**
- **Scope:** core rebuild.
- **Figures:** charts only, drawn by the deterministic `services/figures` renderer. Picture, map and cartoon types are listed but disabled, with the reason shown.
- **Multi-correct MCQs:** all-or-nothing marking.
- **Classes 1–9:** my suggestion in §8.

**Spec open questions I'm settling on its own recommendations:**
- Assertion–Reason stays 4-option. The code already stores it verbatim, and it is CBSE's current form.
- Papers and worksheets share one vocabulary.
- The UI shows named presets, with the axes underneath.
- Codes stay "proposals": renaming one later is a data change plus an alias.

**Harmony guarantee.**
- Every paper that generates today keeps its structure.
- Saved templates, bank rows, editor documents and `slotMeta` carrying old codes keep working permanently, through aliases.
- For every non-container shape (MCQ, AR, VSA, SA, LA, NUMERICAL, …), Model 1's prompts stay byte-identical.

**Intended visible changes (the only ones):**
- Case studies gain structured sub-parts.
- Builder-added writing, grammar and passage slots move to the independent generators.
- DOCX export prints complete questions.

---

## 1. Catalogue codes are the identity; the runtime "shape" is derived

New Django-free package **`backend/services/question_types/`**:

- **`spec.py`** defines `TypeSpec`, with these fields:
  - `code`, `label`, `family`, and `status` (LIVE/DB/NEW, from the doc)
  - `availability`: `available` | `needs_picture` | `internal` | `structural`
  - `classes` (min, max) and `subjects`
  - `default_marks` and `marks_range`
  - axes: `format`, `task`, `stimulus` (none|passage|dialogue|notice|table|code|word_bank|chart|image|map|cartoon|audio), `container` (none|sub_parts|word_bank), `options` rule (count or range, `multi_correct`, fixed options), `answer_space`, `marking` (exact|keyword_set|scheme|rubric)
  - `lane`: `textbook` | `original`
  - `brief` and `example`: the structure, rules and example from the doc; required for every `available` entry
  - `shape`: one of today's 22 pool codes, e.g. `MCQ_ODD_ONE_OUT→MCQ` or `NAME_FOLLOWING→CASE_STUDY`
- **`catalog/`** holds the data, one module per family (`choice.py`, `supply.py`, `descriptive.py`, `source.py`, `visual.py`, `language.py`, `maths.py`, `practical.py`, `primary.py`, `structural.py`).
  - Cross-referenced entries appear once, with `also_in`: CIRCLE_PICTURE, JOIN_DOTS, TICK_CROSS, GEOM_CONSTRUCTION.
  - Seven existing DB codes that aren't in Draft 1 are kept as hidden `internal` entries: ARTICLE/REPORT/ADVERTISEMENT writing, NOTE_MAKING, ORAL_TASK, PRACTICAL_TASK, PROJECT_WORK. ARTICLE and REPORT stay offered, because the writing generator already writes them.
- **`resolve.py`** provides `resolve(raw)`, which accepts:
  - catalogue codes
  - legacy pool codes: `MCQ→MCQ_SINGLE`, `SHORT_ANSWER→SA`, `READING_COMP→PASSAGE_UNSEEN`, `LETTER→LETTER_WRITING`, `HOTS→SA`+hots, `COMPETENCY→APPLICATION_SCENARIO`+competency, and the rest
  - old DB codes: `STATEMENT_EVAL`, `ODD_ONE_OUT`, `SEQUENCING`, `DRAW_COLOUR_TRACE`, `SPEECH_DEBATE_WRITING`
  - today's LLM synonyms (`schema._TYPE_ALIASES`)
  - teacher phrases ("odd one out", "fill in the blanks")
- **Helpers:** `shape_of`, `legacy_bucket`, `is_option_bearing`, `is_container`, `default_preset(shape)`, `route_for(code)`, `menu(subject, class, generator)`.

**Every existing list is re-derived from this one module:**
- `schema.QUESTION_TYPES / _TYPE_ALIASES / OPTION_BEARING_TYPES / LEGACY_TYPE_ACCEPTS`
- `apps/projects/question_types.py` maps
- `templates.QUESTION_TYPE_CATALOG / _LEGACY_TYPE_MAP / GENERATOR_QUESTION_TYPES`
- `pipeline._legacy_type_for`, `replace._legacy_type_for`
- `generation_router._legacy_question_type / _type_label`
- `recipes._TOKENS_PER_QUESTION`
- the `paper_design` vocabulary and aliases, and the `gim.type_map`
- `answer_script_service._classify_question_type`

`schema.normalize_type` keeps returning the **shape**, so every existing `== "MCQ"` check still holds: set variants, `_exact_pool_target`, editor rendering and the existing test suite. A new `normalize_type_code` returns the catalogue code.

## 2. Type identity carried end to end (lossless)

- **Pool and slots.** `PoolQuestion` gains `type_code` plus `hots`/`competency` attributes. The same fields are added to `QuestionGenerationSlot`, `ResolvedSlot`, `ReplacementSlot` and `_GimSlot`. `question_type` stays the shape; GIM and board slots take `default_preset(shape)`.
- **Builder JSON.** `questionType` holds the catalogue code, with optional `hots` and `competency`. `SlotSpec.from_dict` resolves legacy codes on read, and an unknown code still falls back safely.
- **Wire.** `pipeline._question_to_wire` adds `typeCode`, `typeLabel` and `metadata.typeCode`; `type` is unchanged.
- **Bank.** `to_model_kwargs` writes the exact code, and `from_model` reads it back, so the round trip is lossless. The attributes ride in `metadata`.
- **Editor.** `questionBlock` gains a `typeCode` attribute (`data-type-code` in `extensions/nodes.tsx`), and `buildSlotMeta` carries it. Labels in `paper-breakdown.ts`, `paper-design-panel.tsx`, `generate-dock.tsx` and the papers page come from the generated `frontend/lib/question-types.generated.ts`.
- **Swap.** The dialog sends the code, and `replace.build_slot` resolves it. `set_variants._matches` also requires the same `type_code` when both questions have one, and MCQ-shaped presets stay fixed across sets.

## 3. Database

- **Migration.** `projects/0016_question_type_catalogue` is a data migration that seeds from a frozen snapshot, `apps/projects/migrations/data/question_types_0016.json`:
  - Upsert 10 families (A–J) and every catalogue entry.
  - Fill the model columns that are unused today: `purpose`, `is_container`, `requires_stimulus`, `requires_options`, `requires_figure`, `is_auto_markable`, `is_competency_default`, `needs_answer_space`, `default_answer_space_lines`, `is_internal_only`, `content_schema` (axes), `answer_schema` (marking).
  - For a renamed code: create the new row, move `Question.type` foreign keys to it, add a `QuestionTypeAlias` for the old code, then delete the old row.
  - Seed aliases for the legacy pool codes, delete the old families once empty, and make the reverse a no-op, as in 0012.
- **Export command.** `manage.py export_question_types` writes the migration snapshot and the frontend TS file. A test fails if either is stale.
- **Cache.** Bump the cache key in `QuestionTypeListView` (`all_question_types` → `:v2`).

## 4. Generation

**Model 1** (`services/pool/model1.py`, `recipes.py`):
- **Recipes.** Recipes key on `(type_code, marks, asset_type, hots, competency)`, and `TypeQuota` carries those fields.
- **Batch instruction.** `_batch_instruction` appends the preset's brief, example, option rule and any explicit rule override. That covers option count overriding rule 4, an attached chart or table overriding rule 7, and ORIGINAL overriding rules 1–2. It does this **only for non-default presets**.
- **System prompt.** The system prompt is untouched, so prefix caching and the existing prompts stay identical.
- **Stamping.** `_normalise_batch` stamps the batch's `type_code` onto items of matching shape, the same way it stamps `asset_type` today.
- **Fixed recipes.** The fixed Science/SS/Maths recipes swap `HOTS→SHORT_ANSWER`+hots hint and `COMPETENCY→APPLICATION_SCENARIO`+competency hint.

**Normaliser** (`schema.normalize_pool_question`), per the spec's option rule:
- `MCQ_SINGLE` stays exactly 4 options.
- `CIRCLE_CORRECT` allows 2–3.
- `MCQ_MULTI` allows 4–5 options with ≥2 correct; the answer lists every correct letter, and the answer key states the all-or-nothing rule.
- AR and T/F are unchanged.

**Assembly** (`model2._score_question`):
- An exact `type_code` match scores +12, following the existing `asset_type` preference pattern.
- The gate is still generator → marks → shape/bucket, so a slot short of its exact preset is still filled.
- The `done` event reports how many slots got a fallback preset.

**Routing presets that must never come from the textbook.**
- `blueprint_to_plan` gives Builder slots that have no engine-assigned generator the generator from `route_for(code)`:
  - `PASSAGE_UNSEEN` → `reading_asset_pool`
  - `GAP_FILL_GRAMMAR`, `ERROR_CORRECTION`, `EDITING_OMISSION`, `REPORTED_SPEECH`, `SENTENCE_TRANSFORM`, `ACTIVE_PASSIVE` → `grammar_asset_pool`, using the task kinds already in `GRAMMAR_TASK_GLOSS`
  - `LETTER_WRITING`, `NOTICE_WRITING`, `EMAIL_WRITING`, `STORY_WRITING`, `SPEECH_DEBATE`, `ANALYTICAL_PARAGRAPH`, article, report → `writing_asset_pool`, using the formats already in `WRITING_FORMAT_GLOSS`
- Original-lane presets that no generator writes yet (dialogue-based, news-based, paragraph, diary, …) go to Model 1, marked ORIGINAL.
- Engine routing for English Class 10 is untouched.

## 5. Containers and choice pools (J2/J3)

- **One structure module.** New `services/pool/structure.py` defines `Stimulus`, `Part` (label, prompt, marks, type_code, options, answer, optional OR alternative for Maths Section E) and `ChoicePool(attempt, of)`.
  - `render_structured()` produces `content`, `answer` and `metadata.composite {preamble, body, subQuestions}`.
  - It is generalised from `services/assets/schema.py::SubQuestion.render` and `ReadingAsset.composite_parts`, which are refactored to reuse it.
  - The structure is stored in `Question.metadata["structure"]`, so no column migration is needed; provenance already uses the same precedent.
- **Model 1 container contract.** Container presets return `stimulus` + `parts`. The normaliser validates using the existing rules in `services/assets/validation.py`: `sub_question_marks_sum`, `sub_question_count`, `option_completeness`, `answer_key_complete`, `stimulus_present`.
  - Marks are auto-snapped only when the slot's `constraints.sub_question_marks` pattern matches the part count.
  - **The legacy flat case-study text is still accepted**, so no paper gets fewer case studies than today.
- **Choice pools.** A choice pool prints "Attempt any K of the following N." and marks = K × marks per part. `choice_required` (OR group) is unchanged.
- **Tables.** A table stimulus renders into the composite body as a table token. `question-nodes.ts` turns it into TipTap `table` nodes; the editor already registers `@tiptap/extension-table`.

## 6. Charts (your choice: charts only)

- **Presets.** Presets whose stimulus is `chart` are: MCQ_DATA (graph), DATA_INTERPRETATION, GRAPH_READ, ANALYTICAL_PARAGRAPH (chart variant), GRAPHICAL_SOLUTION (coordinate grid) and GRAPH_PLOT (blank grid + data table).
- **Pipeline.**
  - Model 1 emits a `figure` spec, validated with `services/figures/spec.parse_chart_spec`.
  - After normalisation, the pipeline calls `services/figures.render_chart`, which returns a stable `/media/question_figures/*.svg` URL that goes into `PoolQuestion.image`.
  - The "never trust a model URL" invariant holds, because the URL is ours.
  - `show_values=False` whenever the question asks for the values.
  - A render failure drops the question.
- **Blocked types.** Picture, map, cartoon, trace, dots and clock presets appear in the picker disabled, with "Needs a picture — not generated yet".

## 7. UI

- **Picker.** New `frontend/components/question-type-picker.tsx`, a Base UI Combobox inside a Popover (both ship in `@base-ui/react` 1.4.1).
  - Search runs across labels and aliases, with results grouped by family.
  - Each row shows label, default marks, class range and a one-line "tests".
  - Disabled rows show their reason, and presets in the current class sort first.
  - It replaces the native select in `blueprint/slot-editor.tsx` and the button grid in `editor/swap-question-dialog.tsx`.
- **Slot row.** Adds HOTS and Competency toggles, plus a non-blocking class-fit chip, e.g. "Assertion–Reason is usually set from Class 8".
- **API.** `QuestionTypeOption` in `lib/api-client.ts` gains `family`, `classes`, `availability`, `reason`, `tests`, `example`, `marksRange`; the old fields stay. `fetchQuestionTypeMenu(subject, generator, class)` and `QuestionTypeCatalogView` accept `class`.

## 8. Classes 1–9 — suggested: class starter templates + class-fit guidance

**No silent change.** Today's cards, `_build_primary_progression` and every existing default stay exactly as they are.

1. **Starter templates.** New built-in *starter* templates are added to `services/template_catalog.py` (kind `starter`). Each is a pinned slot list authored from catalogue presets, so it never touches the board engine. They appear first under **"Recommended for Class N"** in `template-picker-grid.tsx`, and the teacher reviews every slot in the Builder before generating.
   - **Classes 1–2 worksheet** (EVS, English, Maths): circle-the-correct-answer (3 options), tick/cross, word-bank fill-ups, join-with-lines, name-the-following, count-and-write with ★ characters, opposites/rhymes, missing numbers.
   - **Classes 3–5 unit test** (EVS/Science, Social, English, Maths): MCQ + identify/odd-one-out, fill blanks, true/false-correct, match, give reasons, define, word problems/patterns, unseen passage + grammar + paragraph.
   - **Classes 6–8 periodic test:** correct/incorrect-statement and sequencing MCQs, AR from Class 8, VSA/SA/LA, differentiate, structured case study, experiment/observation, source-based/chronology, solve-equation/mensuration/statistics, notice/letter.
   - **Class 9 Maths and English/Hindi/Telugu** (they have no board card): Class-10-shaped starters.
   - This delivers the spec's *"Maths blueprints for Classes 1–9"* as editable starters rather than hard-coded engine paths.
2. **Class-fit guidance** in the picker and slot rows (§7).
3. **Class-aware Bloom/difficulty targets** in Model 2 for every paper. `model2._BLOOM_TARGET_WEIGHTS` and `_DIFFICULTY_TARGET_WEIGHTS` are banded by class (1–2, 3–5, 6–8, 9–10). This changes selection preference only, never structure; a HOTS slot prefers Bloom ANALYZE and above.

## 9. Exports, answer keys, prose parsers

- **DOCX.** `lib/export-docx.ts::buildQuestionBlock` exports every paragraph and table in a question block, not just the first `<p>`.
- **Options.** In `question-nodes.ts`, `OPTION_LINE_RE` and `OPTION_SEQUENCES` accept a 5th option (E).
- **Answer keys.** `answer_script_service` classifies types via the catalogue; container keys list per-part answers with marks.
- **Prose parsers.** The designer (`paper_design.py`), the GIM parser (`gim.py`) and `generation_router._parse_instructions_for_slots` take their vocabulary and phrases from the catalogue. This fixes the FILL_BLANK/MATCH_FOLLOWING → SHORT_ANSWER loss.

## Order of work (one commit each; full suite green after every step)

1. Catalogue package, derived lists and integrity tests (no behaviour change).
2. Migration 0016, export command, generated TS file and sync tests.
3. Identity end to end (§2) and HOTS/COMPETENCY → attributes.
4. Model 1 briefs, recipe keying, option rules, preset scoring and original-lane routing (§4).
5. Containers, choice pools, table stimuli, editor tables and the DOCX fix (§5, §9).
6. Charts (§6).
7. Picker, slot toggles, swap dialog and class-fit guidance (§7).
8. Class-aware targets and starter templates (§8).
9. Designer/GIM/parser vocabulary and answer keys; `services/question_types/README.md`; memory notes.

## Out of scope this round

- Generating pictures, maps and cartoons.
- Choice pools across separately numbered questions, and COMMON_STEM_GROUP.
- Audio/visual stimulus.
- Crossword generation, which is a constraint-solver problem.
- Paired VI-alternative content (it stays a flag).
- Retiring `q_instructions` or `apps/question_generation`.

## Verification

- **Backend.** `cd backend && source venv/bin/activate && python manage.py test`: all existing tests pass at every step. New tests cover:
  - catalogue integrity: unique codes, every legacy/DB/alias code resolves, every available preset has brief, example and marks, valid shapes
  - a lossless bank round trip for every code
  - option rules: 3-option, 5-option multi, and 4-option single still enforced
  - container validation, rendering and choice pools; the flat case-study fallback
  - **byte-identical batch instructions for a Class 10 Science recipe**, compared before and after
  - `type_code` preference, set variants, and replace with both catalogue and legacy codes
  - `SlotSpec` reading legacy codes
  - the migration: all catalogue codes exist and old codes are aliases
  - the chart render path, with storage mocked
  - the generated TS file being in sync
  - class-banded targets, and starter templates resolving with correct totals
- **Frontend.** `npx tsc --noEmit`, `npm run lint`, and `node scripts/test-question-nodes.mjs`, extended for `typeCode`, 5-option extraction, table nodes and composites built from a structure.
- **End to end.** Needs local Postgres on :5433, the backend and the frontend, and it spends OpenAI credits:
  1. The CBSE Class 10 Science card gives the same 38 slots and 80 marks as today.
  2. A Class 7 Builder paper with odd-one-out, a word-bank fill-up, a structured case study, a data-interpretation chart and notice writing fills every slot and renders correctly.
  3. Swap a question to "Correct statement".
  4. Sets B and C still work.
  5. Build from bank preserves exact types.
  6. PDF and DOCX exports show every paragraph, table and chart.
  7. The Class 2 starter template generates.
