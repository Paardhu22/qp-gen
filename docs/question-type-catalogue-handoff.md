# Question Type Catalogue — Status (2026-09-14)

## TL;DR

- **What:** the spec *"Question Type Catalogue — AOS (Draft 1)"*. It replaces the flat `type` string with ~160 named types built on separate axes.
- **Where:** branch `feat/question-type-catalogue`. All nine plan steps are implemented and committed, but the branch **is not merged**.
- **Tests:**
  - Backend: **1090 tests pass**, up from 953 at the start.
  - Frontend: `tsc`, `eslint` and the 32 block-mapping checks pass.
- **Not done yet:** a live end-to-end run. It needs Postgres, both servers and OpenAI credits; see [End-to-end checks](#end-to-end-checks).
- **Read next:**
  - [`backend/services/question_types/README.md`](../backend/services/question_types/README.md) for how the package works
  - [`docs/question-type-catalogue-plan.md`](./question-type-catalogue-plan.md) for the design

---

## Commits

| Step | Commit | What it holds |
|---|---|---|
| 1 | `06c95b6` | Catalogue package, derived vocabularies, integrity tests |
| 2 | `b312f40` | Migration 0016 from a frozen snapshot, `export_question_types`, the generated frontend module |
| 3 | `1f0f41d` | The exact type carried end to end: pool, slots, wire, bank, editor. HOTS and COMPETENCY become attributes. |
| 4 | `d3bd8f4` | Model 1 briefs for non-default types, option rules, the ±12 type preference, original-lane routing |
| 5 | `c59c5ed` | Structured sub-parts, choice pools, table stimuli; the DOCX export prints whole questions |
| 6 | `935a791` | Chart stimuli drawn by `services/figures` |
| 7 | `579b140`, `fc2a83d` | Menu by class (backend); searchable picker, slot attributes menu, swap dialog, class-fit note (frontend) |
| 8 | `579b140`, `fc2a83d`, `9cf3510` | Class starter templates, class-banded Bloom/difficulty targets, HOTS/competency preference |
| 9 | the commit adding this file | Designer, General Instructions parser and answer keys read the catalogue; package README |

`d0f28c2` separately removes the unused Lottie files.

---

## What changed for a teacher

- **Builder picker.** Slots are chosen from the catalogue.
  - The picker shows a short Suggested list for the class and subject; search and browse reach every type.
  - Types that need a printed picture are listed but disabled.
- **Slot attributes.** HOTS and real-world framing sit behind one small menu on each slot. A dot flags a type usually set to other classes.
- **Recommended for Class N.** This section appears in the template picker for Classes 1–9: 15 starter papers, 1–2 of them per class and subject.
- **Swap dialog.** It uses the same picker, and keeps the paper total in view.
- **Case studies, passages and data questions.** They come with structured parts, tables and drawn charts.
- **"Describe It Yourself" and General Instructions.** A type named in the brief is kept: "odd one out", "word bank", "letter writing". It is no longer flattened to MCQ or dropped.
- **Marking schemes.** True/false, fill-in-the-blank, matching, multi-correct, grammar and writing questions get their proper answer format.

## What did not change

- **Board papers.** Every CBSE card produces the same slots, and its Model 1 prompts are byte-identical.
- **Old data.** Saved templates, bank rows, editor documents and `slotMeta` with old codes still read, through aliases.
- **Class 9–10 assembly.** It uses exactly the old Bloom/difficulty shares.
- **The saved marking-scheme document.** It stores the same `questionType` labels as before. Only the prompt's format changed.

## Deviations from the plan

- **GRAPH_PLOT and GRAPHICAL_SOLUTION print no figure.** The chart renderer cannot draw an empty coordinate grid, so their stimulus is a data table, or nothing.
- **`presetFallbacks` is not shown in the UI.** It counts slots filled with a same-shape type because the pool lacked the exact one. It is sent on the `done` event, but nothing displays it yet.
- **`generation_router._parse_instructions_for_slots` still maps onto the legacy `q_instructions` enum.** Retiring `q_instructions` was out of scope.
- **The designer's schema now lists the catalogue types by name.** That adds about 1k tokens to each design call.

---

## End-to-end checks

These need local Postgres on :5433, the backend and the frontend, and they spend OpenAI credits.

1. The CBSE Class 10 Science card gives the same 38 slots and 80 marks as before.
2. A Class 7 Builder paper fills every slot and renders correctly. It should contain:
   - odd-one-out
   - a word-bank fill-up
   - a structured case study
   - a data-interpretation chart
   - notice writing
3. Swapping a question to "Correct statement" works.
4. Sets B and C still generate.
5. Building from the bank keeps each question's exact type.
6. The PDF and DOCX exports show every paragraph, table and chart.
7. The Class 2 starter template generates.
8. The Builder feels right with live data, at desktop and at phone width (~400px).
   - Already checked without a backend: the template grid, slot rows, picker, attributes menu and swap dialog were screenshotted headlessly with real catalogue data, at 1280px and 400px, in light and dark.
   - That pass fixed a blank band in the picker, template cards overflowing on phones and a crowded swap dialog.
   - What still needs a live run is the same UI fed by the backend.

---

## Where things live

| Concern | File |
|---|---|
| Catalogue and lookups | `backend/services/question_types/` |
| Builder menu, by subject and class | `backend/services/templates.py::question_types_for` |
| Class starters | `backend/services/starter_templates.py`, listed by `services/template_catalog.py` |
| Model 1 briefs and structure contract | `backend/services/pool/model1.py` |
| Model 2 type/class/attribute scoring | `backend/services/pool/model2.py::_score_question` |
| Structured questions | `backend/services/pool/structure.py` |
| Designer and General Instructions parser | `backend/services/paper_design.py`, `backend/services/pool/gim.py` |
| Answer formats | `backend/services/answer_script_service.py::_answer_format` |
| Picker | `frontend/components/question-type-picker.tsx` |
| Slot rows | `frontend/components/blueprint/slot-editor.tsx` |
| Generated type data | `frontend/lib/question-types.generated.ts`. Don't edit it by hand. |

## Commands

```bash
# Backend: Django TestCase; settings switch to in-memory SQLite automatically
cd backend && source venv/bin/activate
python manage.py test                                  # full suite
python manage.py test services.question_types          # the catalogue
python manage.py export_question_types --check         # frontend module in sync?

# Frontend
cd frontend
./node_modules/.bin/tsc --noEmit
./node_modules/.bin/eslint <files>
node scripts/test-question-nodes.mjs
```
