# Asset generators — the English pipeline split

## Why this package exists

The pool architecture assumes **every question originates from uploaded textbook
content**:

```
Uploaded Book → Model 1 → Question Pool → assign to sections
```

That assumption holds for Science, Social Science and Mathematics, where every
slot on the paper is a question *about* studied chapters. It is wrong for
English. Only Section C (Literature, 40 of 80 marks) is about the prescribed
text. Section A (Reading, 20 marks) needs **original unseen passages**, and
Section B (Grammar + Writing, 20 marks) needs **rule-based tasks and invented
scenarios**. Routing those slots through a chapter-grounded pool is what
produced papers whose Reading section asked students to "Explain Hari Singh"
and whose Writing section asked for "a letter about Kisa Gotami" — a Literature
paper wearing an English paper's section headings.

The fix is not a better prompt. The section must decide the generator:

```
Blueprint → choose generator → generate/retrieve assets → assemble paper
```

## Where the old assumption lived

| Component | The assumption |
| --- | --- |
| `services/pool/pipeline.py::stream_pool_questions` | Hard-errors when `build_chapters()` returns nothing, for every subject. An English paper could not be generated at all without an upload, even though 40 of its 80 marks need no textbook. |
| `services/pool/model1.py::_system_prompt` | Hard rule #1: *"Every question must be answerable from the chapter provided."* Applied to every shape in the recipe, including `READING_COMP`, `GRAMMAR` and `LETTER`. |
| `services/pool/model1.py::_build_request` | Every batch is prefixed with `# CHAPTER SOURCE MATERIAL`. There is no batch that does not see the textbook. |
| `services/pool/recipes.py` | Recipes are keyed on `(type, marks)` only. A `GRAMMAR 1m` quota and an `MCQ 1m` quota are produced identically, from the same chapter. |
| `services/pool/schema.py::slot_accepts` | Matches on type + marks only. A textbook-derived question is therefore a *legal* fill for a Reading slot. |
| `services/generation_router.py` | `QuestionGenerationSlot.generation_mode` (`PASSAGE`/`GRAMMAR`/`COMPOSITION`) already existed and is honoured by `_slot_instruction`… but only by the retired per-slot engine. The pool pipeline reads `question_type` and `marks` off a slot and discards the rest. |
| `services/pool/store.py`, `from_bank.py` | Bank rows are grouped and filtered by chapter, so a non-textbook question has no coherent home and no way to be selected for the slot it belongs to. |
| `services/pool/set_variants.py` | Parallel-replacement matching had no provenance term. |

## The new shape

```
                       English blueprint (routing engine)
                                     │
        ┌──────────────┬─────────────┴──────────┬───────────────────┐
        │              │                        │                   │
 reading_asset_  grammar_asset_          writing_asset_       question_pool
      pool            pool                    pool          (existing RAG)
        │              │                        │                   │
 ReadingAsset    GrammarAsset            WritingAsset        chapter Markdown
        │              │                        │              → Model 1
        └──────────────┴───────────┬────────────┴───────────────────┘
                                   │
                        merged, provenance-tagged pool
                                   │
                        Model 2 (blueprint resolver)
                                   │
                            Final question paper
```

* The three asset generators **never receive chapter text**. Contamination is
  prevented by construction, not by instruction — there is no code path that
  hands them an upload.
* Literature keeps the existing pipeline unchanged: chapters → Model 1 → pool.
* Everything lands in the same `PoolQuestion` shape, so persistence, the SSE
  contract, the editor, multi-set derivation and answer keys are untouched.

## Contracts

### Blueprint slot (the routing declaration)

`QuestionGenerationSlot` gained seven fields. All default to the pre-existing
behaviour, so a blueprint that declares none of them routes to `question_pool`
exactly as before — that is what keeps Science, Social Science, Mathematics,
Hindi and Telugu bit-for-bit unchanged.

```python
generator     = "reading_asset_pool"   # which generator owns this slot
asset_type    = "discursive_passage"   # what shape that generator must emit
constraints   = {"word_count": (350, 450), "sub_question_marks": (1,1,1,1,1,2,1,2)}
validation    = ("sub_question_marks_sum", "sub_question_count", "passage_word_count")
optionality   = "none"                 # none | internal_choice | any_10_of_12 | …
answer_type   = "mixed"                # objective | descriptive | mixed
output_format = "passage_with_subquestions"
```

`marks` and `choice_required` were already there and keep their meaning.

### Generator (Strategy)

```python
class AssetGenerator(ABC):
    name: str          # the value a slot's `generator` field names
    source_type: str   # stamped on every PoolQuestion it emits
    def generate(self, request: AssetRequest) -> AssetBatchResult: ...
```

`registry.py` is the Factory: `get_generator(name)`, `partition_plan(plan)`.
`question_pool` is a reserved sentinel meaning "the existing chapter pipeline";
it is deliberately *not* an `AssetGenerator`, because that path is owned by the
streaming pipeline (chapter detection, per-chapter concurrency, the image
stage) and wrapping it would invert a lot of machinery for no gain.

### Provenance

`PoolQuestion.generator` / `.asset_type` are set at creation and round-trip
through `metadata` on the persisted row. They do different jobs:

* **`generator` is eligibility.** `slot_accepts` gates on it before anything
  else — `slot.generator == question.generator`, then marks, then type. A
  Reading slot cannot be filled from the textbook pool however well the marks
  line up, and a Literature slot cannot be filled with a grammar task.
* **`asset_type` is preference.** It is scored, not gated (`_score_question`
  weights a match above every diversity term). A prose extract and a poetry
  extract are both 5-mark descriptive questions, so nothing else can tell the
  two slots apart; the same is true of the discursive and case-based passages.
  Weighting rather than gating means a slot short of its exact shape is still
  filled rather than left blank. `batches_from_plan` keys its recipe on
  `(type, marks, asset_type)` and Model 1 stamps it, so the label survives the
  round trip from blueprint to pool.

Rows saved before this change have no `generator` in metadata and default to
`question_pool`, so existing banks keep working, and a question with no
`asset_type` scores neutrally rather than being penalised.

## Adding a language

1. Write the blueprint entries with `generator` / `asset_type` / `constraints`.
2. Reuse `reading_asset_pool` / `grammar_asset_pool` / `writing_asset_pool` —
   they take their language from `AssetRequest.subject` and their shape from
   the slot's constraints, so nothing in them is English-specific.
3. If the language needs a genuinely new asset shape, subclass `AssetGenerator`
   and `register()` it. No pipeline change is required.

Hindi and Telugu are deliberately **not** migrated here. Their blueprints still
route entirely through `question_pool`, exactly as before. They are the obvious
next candidates — their entries already carry the `PASSAGE`/`COMPOSITION`
`mode` hints this design supersedes — but migrating them is a separate change
with its own test surface.

## Cost

Five extra LLM calls per English generation (2 reading, 1 grammar, 2 writing),
each small — no chapter in the prompt. Against that, Model 1's recipe now
covers 6 literature slots instead of 11 mixed ones, so the chapter-bearing
calls (the expensive ones, since the chapter is resent per batch) drop. Net
cost for an English paper goes down, not up.
