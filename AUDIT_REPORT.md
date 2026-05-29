# AOS Language-Subject Audit & Grammar/Writing Engine — Audit Report

> Scope: CBSE Class‑10 language subjects (English 184, Hindi 085, Telugu 089).
> Method: read‑only mapping of the **live generation path** first, then surgical fixes.
> Rule observed: **do not change Science / Social Science / Mathematics behaviour.**

---

## 0. Where the code actually lives (spec vs. reality)

The task brief assumes a file layout that does **not** match this repo. The real
architecture had to be mapped before any fix. Key divergences (important for every
finding below):

| Spec assumption | Reality in this repo |
|---|---|
| `QuestionSlot` in `q_instructions/core/datatypes.py` | The runtime slot is `QuestionGenerationSlot` in `services/generation_router.py:46`. `datatypes.py` has no slot type. |
| Language blueprints in `q_instructions/subjects/<subj>/orchestrator.py` | Live blueprints are **inline** in `generation_router.py` (`_exact_class10_blueprint_entries_{english,hindi,telugu}`). The `*OrchestratorV2` classes and `SubjectPlugin`s are **not used by the streaming path** — only by `route_and_execute_new_engine`/`AcademicGenerationFacade`, which `apps/generation/views.py` reaches only via the `TestScienceEngineView` debug endpoint. |
| `build_retrieval_query(slot, subject)` function | No such function. The query was built **inline** inside `_make_slot` (`generation_router.py:844`) and duplicated in the GIM path (`generation_service.py:668`). |
| Structured `sub_parts` with `correct_option` / `answer_key` per task | **Do not exist.** A slot produces a single question object whose `content` is a free‑text blob and `answer` is a free‑text key (`generation_service.py:_single_question_schema:322`, `_coerce_question:250`). Grammar tasks and reading sub‑questions are rendered as text inside `content`. |

The **live path** is: `QuestionGenerationStreamView` → `stream_generated_questions`
(`generation_service.py:907`) → `build_question_plan` (`generation_router.py:2105`) →
`_build_exact_cbse_class10_plan` → per‑slot retrieval + LLM stream in `_generate_slot`
(`generation_service.py:1061`).

Because the spec's `sub_parts`/`correct_option` schema does not exist and adding it would
require a frontend editor rewrite (high blast radius), this work honours the **intent** of
the spec within the real free‑text model: the “n of m” count and answer key are emitted as
text driven by the blueprint hint, and validation operates on that text.

---

## 1. 🔴 RAG misrouting — grammar/writing/passage slots pull irrelevant chunks (CORE BUG)

**Files/lines**
- `generation_router.py:844-858` — `_make_slot` builds a non‑empty `retrieval_query` for **every** slot, including `GRAMMAR`, `LETTER`, `READING_COMP`, and the analytical‑paragraph `SHORT_ANSWER`.
- `generation_router.py:737` — `_slot_instruction` injects the global line *“Use only the retrieved textbook chunks. Do not introduce unsupported facts.”* for all types.
- `apps/question_generation/services/prompting/assembler.py:29` — assembler appends a `CONTEXT` block whenever `retrieved_chunks` is non‑empty.
- `apps/question_generation/services/prompting/assembler.py:44` — `default_system_rules` hardcodes *“Generate one CBSE question from the provided chunks only.”*

**Why it's wrong vs. SQP** — Grammar is rule‑based, composition is scenario‑based, and the
English/Hindi/Telugu reading passages must be **original/unseen**. None of these should be
retrieved from the educator's uploaded text. Injecting chunks makes the model either ignore
them (wasted tokens/latency) or hallucinate grammar/writing prompts *about* the textbook.

**Fix (applied)** — Introduced `GenerationMode {CONTENT, PASSAGE, GRAMMAR, COMPOSITION}`
(`q_instructions/core/enums.py`). Tagged every language blueprint entry with a mode.
`build_retrieval_query()` now returns `""` for `PASSAGE/GRAMMAR/COMPOSITION` and a real query
only for `CONTENT`. The assembler receives no chunks for non‑CONTENT slots, and
`_slot_instruction` + system rules are mode‑specific (no “use retrieved chunks” line outside
CONTENT). Regression test asserts `build_retrieval_query` is empty for every
GRAMMAR/COMPOSITION/PASSAGE slot across all three subjects.

## 2. 🔴 Empty context blocks grammar/composition and makes no‑PDF papers impossible

**Files/lines**
- `generation_service.py:1066-1070` — `_generate_slot` returns the warning *“No relevant textbook chunks found …”* and refuses to generate whenever `context` is empty.
- `retrieval_service.py:27-28` — `retrieve_relevant_chunks` returns `[]` when `pdf_source_ids` is empty.

**Why it's wrong** — A grammar/letter/passage slot needs **no** PDF. With the old guard, a
teacher generating an English/Hindi/Telugu paper **without** uploading a textbook gets zero
questions, and even with a PDF the grammar/writing slots fail when no chunk happens to match
their (irrelevant) query.

**Fix (applied)** — In the allocation loop, non‑CONTENT slots skip retrieval entirely
(empty query ⇒ `context = []`, no embedding call). In `_generate_slot`, the empty‑context
hard error fires **only for CONTENT** slots; PASSAGE/GRAMMAR/COMPOSITION proceed without chunks.

## 3. 🔴 / 🟡 Stale, contradictory “Only Science and Social Science” messaging

**Files/lines**
- `generation_service.py:955-956` — error text *“Only CBSE Science and CBSE Social Science are configured in q_instructions right now.”* (false — six subjects are configured).
- `generation_router.py:96-100` — `should_use_new_engine` docstring still says *“subject == Science AND class == 10”*.
- `generation_router.py:146-150` — the not‑eligible reason log only checks `["science","social science"]` and `1..10`, so Math/English/Hindi/Telugu produce misleading logs.

**Fix (applied)** — Corrected the error string to reference the actual supported set, and
rewrote the docstring and reason log to use `_NEW_ENGINE_ELIGIBILITY` so the message is
accurate for all six subjects.

## 4. 🟢 Science expected‑count — VERIFIED CORRECT (no off‑by‑one)

**File/line** — `generation_router.py:1937-1947` (`_expected_counts["science"] = 39`).

**Finding** — The Science Class‑10 exact blueprint (`_exact_class10_blueprint_entries`
fallback, `generation_router.py:1821-1896`) expands to **39** slots summing to **80** marks
(Biology 16q/30m, Chemistry 13q/25m, Physics 10q/25m). The `39` is **correct**; there is no
silent off‑by‑one. Added a regression test asserting the built Science plan length equals
`_expected_counts["science"]` and totals 80.

## 5. 🟡 Hindi अनुच्छेद hint contradicts the “exactly 3 hint points” rule

**File/line** — `generation_router.py:1438-1443` (Q12 hint) said *“3 topic options each with
**3‑4** संकेत‑बिन्दु”* then listed **four** guiding points (भूमिका/विस्तार‑1/विस्तार‑2/निष्कर्ष).

**Fix (applied)** — Tightened to **exactly 3** संकेत‑बिन्दु per topic, and `validate_composition`
rejects any अनुच्छेद topic that does not present 3 hint points (hard retry).

## 6. 🟡 Internal‑choice “OR” not localised to the paper's script

**File/line** — `generation_service.py:205-218` (`_printable_question_content`) always inserts
the literal `OR`, even for Hindi/Telugu papers.

**Fix (applied)** — The OR separator is now `अथवा` for Hindi and `లేదా` for Telugu (`OR`
otherwise), driven by `slot.subject`. (The frontend renders the server‑composed `content`, so
this is the single correct place to localise it; no hardcoded OR string exists in the frontend.)

## 7. 🟡 Script integrity was advisory only — no hard retry

**Files/lines** — Devanagari/Telugu enforcement existed only as prompt text
(`generation_router.py:514, 534, 768-791`); nothing validated the **output**, so Roman‑script
output streamed straight to the editor.

**Fix (applied)** — `services/language_validation.py` adds a hard script guard
(`validate_script`) for Hindi (Devanagari range U+0900–U+097F) and Telugu (U+0C00–U+0C7F),
wired as a **hard retry** in `_generate_slot` (up to 3 attempts for language slots), then a
clear warning event instead of a malformed question.

## 8. 🟡 No output schema validation before SSE (HANDOFF issue #11)

**Files/lines** — `_coerce_question` (`generation_service.py:250`) enforces presence of
options/OR/VI but never validated grammar/composition adequacy.

**Fix (applied)** — Added `validate_language_question(slot, question)` (grammar coverage,
composition scenario/word‑limit/stimulus checks, script) run as a gate before the `question`
SSE event. CONTENT/Science/Social/Math are unaffected (validation only runs for the language
non‑CONTENT modes).

## 9. 🟢 Subject normalisation / eligibility edge cases — OK

Aliases (`maths`, `hindi b`, `telugu telangana`, `sst`, …) resolve correctly
(`normalize_subject`, verified by `test_new_subjects.TestSubjectAliases`). Non‑Class‑10 requests
for the four new subjects return `is_eligible_for_new_engine == False` and fall back to the
legacy engine without crashing.

## 10. Dead / compat / pre‑existing‑failure inventory

- `route_and_execute_new_engine` + `AcademicGenerationFacade` + the `*OrchestratorV2`/`*Plugin`
  classes are **not** on the live streaming path (compat shim + debug `TestScienceEngineView`
  only). Left intact; flagged here so future readers don't assume they drive generation.
- After mode tagging, the `GRAMMAR`/`LETTER`/`READING_COMP` branches inside `_build_content_instruction`
  (the renamed CONTENT-mode body) are now unreachable — those qtypes only ever appear in
  GRAMMAR/COMPOSITION/PASSAGE slots, which are routed before CONTENT. Left in place deliberately as
  harmless defensive fallbacks (removing them would be a no-op risk with no upside); not contradictory
  at runtime since CONTENT slots never carry those qtypes.
- **Pre‑existing test failures (not caused by this work):**
  - `test_hybrid_routing.test_should_use_new_engine_ineligible` asserted `CBSE+Math+10 → legacy`,
    which became false when Mathematics gained a new‑engine blueprint (commit 925387a). **Fixed**
    the fixture to use a genuinely ineligible case (unsupported subject) — justified change.
  - `test_architecture` “Facade blueprint validation compiles and executes successfully” fails
    on `main` independently of this work (facade path, non‑language). **Left as‑is**, out of scope.

## Marks integrity (verified, tests added)

| Subject | Per‑section marks | Total |
|---|---|---|
| English 184 | A 20 / B 20 / C 40 | 80 |
| Hindi 085 | क 14 / ख 16 / ग 28 / घ 22 | 80 |
| Telugu 089 | ఎ 10 / బి 11 / సి 29 / డి 30 | 80 |
| Mathematics 041 | A 20 / B 10 / C 18 / D 20 / E 12 | 80 |
| Science | Bio 30 / Chem 25 / Phys 25 | 80 |

---

## Residual risks

- Validation runs on **free text** (no structured sub‑parts), so the grammar/composition gates
  are heuristic. They are tuned conservative — they reject only clear violations (Roman‑script in
  a Telugu/Hindi slot, missing word‑limit token, too few detectable grammar tasks, a single‑option
  analytical stimulus) to avoid false‑reject retry storms. Subtle pedagogical errors inside
  otherwise well‑formed text are not caught.
- Telugu Chandas gaṇa correctness is enforced primarily by injecting the correct metre→gaṇa table
  into the prompt; the post‑hoc check only fails on an explicit metre+gaṇa mismatch it can parse.
- The structured `sub_parts`/`correct_option` model from the brief was intentionally **not**
  introduced (would require an editor rewrite). If that schema is later desired, it is a separate,
  larger workstream touching `_single_question_schema`, `_coerce_question`, the SSE contract, and
  the TipTap editor.
