# Question types

The catalogue of question types. It is also the one answer to "what type is this?" for every type string the product has ever stored.

Design and history: [`docs/question-type-catalogue-plan.md`](../../../docs/question-type-catalogue-plan.md).

## Two names for every type

| Name | Example | What it is for |
|---|---|---|
| **Catalogue code** | `MCQ_ODD_ONE_OUT` | The type's identity. Blueprint slots store it as `typeCode`, pool and bank questions in `metadata.typeCode`, and editor blocks as `data-type-code`. |
| **Shape** | `MCQ` | One of the 22 runtime codes the pipeline has always used. The shape decides option handling, which slots may take a question (`slot_accepts`), token budgets, editor layout and set variants. |

- **`schema.normalize_type` still returns the shape**, so every existing `== "MCQ"` check holds.
- **`normalize_type_code` returns the catalogue code.**
- **Old strings resolve forever through the alias index.** That covers shapes, DB codes from before migration 0016, model synonyms and teacher phrases.
- **HOTS and COMPETENCY are slot attributes (`hots`, `competency`), not types.** Their retired shape names still resolve, and carry the attribute.

## Layout

The package is Django-free, so the pool, the blueprint engine, migrations and tests can all import it.

| File | Holds |
|---|---|
| `spec.py` | `TypeSpec`, its axes (format, task, stimulus, container, options, marking, lane, availability), `OptionRule`, `Route` and `validate_spec` |
| `shapes.py` | The 22 shapes, with their buckets, token budgets and the model synonyms |
| `families.py` | Families A–J |
| `catalog/` | The entries, one module per family |
| `registry.py` | `CATALOG`, the alias index and every lookup |
| `export.py` | The projections: the DB seed snapshot and `frontend/lib/question-types.generated.ts` |

## Which lookup to use

| You have | Use |
|---|---|
| A stored or submitted type string | `resolve(raw)` for the catalogue type plus implied attributes, or `shape_of(raw)` for the runtime shape |
| A slot carrying a code *and* a shape | `resolve_slot_type(type_code, question_type, hots=…, competency=…)`. The code wins unless its shape disagrees with a newer shape. |
| A teacher's own words | `find_type_in_text(text)`. It tries the longest phrase first, and returns only types that can be generated. |
| A generator's output format | `type_for_route(generator, asset_type)` |

## Adding or changing a type

1. **Edit the entry** in its family module under `catalog/`.
   - An `available` entry needs a `brief` and an `example`.
   - The registry refuses to import on a missing brief or example, a duplicate code, or an alias claimed by two types.
2. **To rename a code**, keep the old code as an alias. Move existing bank rows in a data migration; 0016 shows how, using `export.RENAMED_CODES`.
3. **Regenerate the frontend module** with `python manage.py export_question_types`. A test fails while it is stale.
4. **If the DB table must change**, write a new data migration from a new snapshot:
   `python manage.py export_question_types --snapshot apps/projects/migrations/data/question_types_00NN.json`.
   Never rewrite the snapshot of a migration that has been applied.
5. **Test** with `python manage.py test services.question_types`.

## What an entry decides downstream

- **Generation.**
  - A type that isn't its shape's default adds its brief, example and option rule to Model 1's batch instruction. A default type adds nothing, so board papers are prompted exactly as before.
  - An `original`-lane type with a `route` is written by that asset generator, not from the textbook.
- **Assembly.**
  - Model 2 prefers the exact type (±12). When the pool lacks it, a slot is still filled from the same shape, and the pipeline reports how often that happened (`presetFallbacks`).
  - HOTS and competency slots prefer questions written for them.
- **Structure.** Container types return a stimulus plus parts (`services/pool/structure.py`). Chart stimuli are drawn by `services/figures`.
- **Picker.**
  - A type whose availability isn't `available` is listed but disabled, with its reason.
  - `classes` ranks a type for the paper's class, and drives the class-fit note on a slot.
- **Prose.** The designer (`services/paper_design.py`) and the General Instructions parser (`services/pool/gim.py`) keep a type the teacher names instead of flattening it.
- **Answer keys.** `answer_script_service._answer_format` picks the marking-scheme format a type needs.
