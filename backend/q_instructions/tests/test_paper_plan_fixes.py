"""
Tests for the PaperPlan + figure-pipeline + type-fidelity work
that fixes the three biggest correctness regressions in qp-gen:

1. Generated paper did not match the user's free-text instructions.
   - Bogus "SECTION S" leaked because the section regex matched
     "sections" → ("section", "s").
   - Meta-clauses like "i want 3 sections" synthesised a slot from a
     stray digit.
   - Custom-mode Exact Count was ignored when it disagreed with the
     parsed per-section breakdown.
   - `board` mode silently overwrote the teacher's explicit section
     breakdown with the fixed CBSE blueprint.
   - Concurrent LLM completion could render sections in random order
     (Section C before Section A).
2. "Question visual" image placeholders for figures that did not exist.
3. Type fidelity: SHORT/LONG slots accepting MCQ-style options
   (and MCQ slots accepting bare text) was caught silently.

Tests are deterministic and do not touch the LLM. They exercise the
plan resolution, parser, label-derivation and figure validators only.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
from dotenv import load_dotenv
load_dotenv(
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        ".env",
    )
)
django.setup()

from services.generation_router import (  # noqa: E402
    _is_explicit_section_breakdown,
    _parse_instructions_for_slots,
    build_question_plan,
    build_realized_general_instructions,
    paper_plan_section_order,
)
from services.generation_service import (  # noqa: E402
    _coerce_question,
    _content_references_missing_figure,
    _figure_to_data_url,
    _strip_figure_references,
)


# ---------------------------------------------------------------------------
# ISSUE 1 — instruction parsing precedence
# ---------------------------------------------------------------------------
class ParserCorrectnessTests(unittest.TestCase):
    """The free-text parser is the source of truth for custom-mode
    plans. Every regression below was visible in production."""

    LIVE_USER_INPUT = (
        "i have uploaded 2 pdf's i want 3 sections\n"
        "section A : 10 mcq's\n"
        "section B : 5 short\n"
        "section C : 5 long"
    )

    def test_section_regex_does_not_eat_plurals(self):
        """`sections` must NOT match as ("section", "s") → "Section S"."""
        templates = _parse_instructions_for_slots("i want 3 sections of mcqs")
        titles = [t["section_title"] for t in templates]
        self.assertNotIn("Section S", titles)

    def test_meta_clause_drops_when_no_question_cue(self):
        """`i have uploaded 2 pdf's i want 3 sections` has no qtype
        keyword and no `questions?` marker → must produce no slot."""
        templates = _parse_instructions_for_slots(
            "i have uploaded 2 pdf's i want 3 sections"
        )
        self.assertEqual(templates, [])

    def test_live_failing_input_parses_cleanly(self):
        """The exact input that produced the broken paper in production
        must now yield three sections A/B/C with the right counts and
        types — and no phantom Section S."""
        templates = _parse_instructions_for_slots(self.LIVE_USER_INPUT)
        self.assertEqual(len(templates), 3, templates)
        self.assertEqual(
            [t["section_title"] for t in templates],
            ["Section A", "Section B", "Section C"],
        )
        # MCQ / SHORT_ANSWER / LONG_ANSWER, in order
        names = [t["qtype"].name for t in templates]
        self.assertEqual(names, ["MCQ", "SHORT_ANSWER", "LONG_ANSWER"])
        counts = [t["count"] for t in templates]
        self.assertEqual(counts, [10, 5, 5])

    def test_existing_explicit_format_still_parses(self):
        """`Section A: 5 questions of 1 mark each` has no qtype keyword
        but DOES have the `questions` marker → must still parse (legacy
        test_hybrid_routing.test_custom_section_names_and_newline_parsing)."""
        templates = _parse_instructions_for_slots(
            "Section A: 5 questions of 1 mark each\n"
            "Section B: 2 questions of 5 marks each"
        )
        self.assertEqual(len(templates), 2)
        self.assertEqual(templates[0]["count"], 5)
        self.assertEqual(templates[0]["marks"], 1)
        self.assertEqual(templates[1]["count"], 2)
        self.assertEqual(templates[1]["marks"], 5)


# ---------------------------------------------------------------------------
# ISSUE 1 — full PaperPlan resolution (general + board precedence)
# ---------------------------------------------------------------------------
class PaperPlanResolutionTests(unittest.TestCase):
    LIVE_USER_INPUT = ParserCorrectnessTests.LIVE_USER_INPUT

    def test_custom_mode_live_input_produces_20_slots_named_a_b_c(self):
        """`custom` + Exact Count = 20 + the live failing input → must
        materialize exactly 20 slots split A(10)/B(5)/C(5), section
        names verbatim, types correct, none of them sitting in 'SECTION S'."""
        plan = build_question_plan(
            topic="",
            difficulty="hard",
            count=20,
            class_num=10,
            subject="Science",
            instructions=self.LIVE_USER_INPUT,
            count_variation="custom",
        )
        self.assertEqual(len(plan), 20)

        section_a = [s for s in plan if s.section_title == "Section A"]
        section_b = [s for s in plan if s.section_title == "Section B"]
        section_c = [s for s in plan if s.section_title == "Section C"]
        self.assertEqual(len(section_a), 10)
        self.assertEqual(len(section_b), 5)
        self.assertEqual(len(section_c), 5)

        self.assertTrue(all(s.question_type == "MCQ" for s in section_a))
        self.assertTrue(all(s.question_type == "SHORT_ANSWER" for s in section_b))
        self.assertTrue(all(s.question_type == "LONG_ANSWER" for s in section_c))

        self.assertNotIn("Section S", {s.section_title for s in plan})

    def test_plan_section_order_preserves_user_input(self):
        plan = build_question_plan(
            topic="",
            difficulty="hard",
            count=20,
            class_num=10,
            subject="Science",
            instructions=self.LIVE_USER_INPUT,
            count_variation="custom",
        )
        self.assertEqual(
            paper_plan_section_order(plan),
            ["Section A", "Section B", "Section C"],
        )

    def test_board_mode_empty_instructions_keeps_full_blueprint(self):
        """Board mode + empty instructions → the existing 39-question
        Class 10 Science blueprint must come through byte-identical."""
        plan = build_question_plan(
            topic="",
            difficulty="medium",
            count=-1,
            class_num=10,
            subject="Science",
            instructions="",
            count_variation="cbse",
        )
        # 39 questions for class-10 Science blueprint (per
        # `_expected_counts` in _build_exact_cbse_class10_plan).
        self.assertEqual(len(plan), 39)

    def test_board_mode_with_custom_section_breakdown_overrides_blueprint(self):
        """Board mode + EXPLICIT per-section instructions → user wins.
        The blueprint must not silently overwrite the teacher's structure."""
        plan = build_question_plan(
            topic="",
            difficulty="medium",
            count=-1,  # board defaults
            class_num=10,
            subject="Science",
            instructions=(
                "section A : 6 mcqs\n"
                "section B : 4 short answers\n"
                "section C : 2 long answers"
            ),
            count_variation="cbse",
        )
        self.assertEqual(len(plan), 12)
        self.assertEqual(
            paper_plan_section_order(plan),
            ["Section A", "Section B", "Section C"],
        )

    def test_board_mode_with_loose_instructions_keeps_blueprint(self):
        """Loose instructions like 'make it harder' must NOT be misread
        as a section override; the blueprint must stay in charge."""
        plan = build_question_plan(
            topic="",
            difficulty="medium",
            count=-1,
            class_num=10,
            subject="Science",
            instructions="please make it slightly harder",
            count_variation="cbse",
        )
        self.assertEqual(len(plan), 39)

    def test_is_explicit_section_breakdown_helper(self):
        # Empty / single-section → not explicit
        self.assertFalse(_is_explicit_section_breakdown([]))
        self.assertFalse(
            _is_explicit_section_breakdown(
                [{"section_title": "Section A", "qtype": None, "marks": 1, "count": 5}]
            )
        )
        # Multiple, all named → explicit
        self.assertTrue(
            _is_explicit_section_breakdown(
                [
                    {"section_title": "Section A", "qtype": None, "marks": 1, "count": 5},
                    {"section_title": "Section B", "qtype": None, "marks": 2, "count": 5},
                ]
            )
        )
        # Multiple, some unnamed → not explicit
        self.assertFalse(
            _is_explicit_section_breakdown(
                [
                    {"section_title": "Section A", "qtype": None, "marks": 1, "count": 5},
                    {"section_title": None, "qtype": None, "marks": 2, "count": 5},
                ]
            )
        )


# ---------------------------------------------------------------------------
# ISSUE 1 — label/marks fidelity from the PaperPlan
# ---------------------------------------------------------------------------
class RealizedHeaderFidelityTests(unittest.TestCase):
    def test_per_section_label_uses_count_x_marks_each(self):
        """For uniform sections, label uses 'N × M = T Marks' — never the
        'N Questions = T Marks' fallback that production was hitting."""
        realized = {
            "sections": [
                {
                    "title": "Section A",
                    "questions": [{"marks": 1} for _ in range(10)],
                },
                {
                    "title": "Section B",
                    "questions": [{"marks": 3} for _ in range(5)],
                },
                {
                    "title": "Section C",
                    "questions": [{"marks": 5} for _ in range(5)],
                },
            ]
        }
        lines = build_realized_general_instructions(realized, "Science", 10)
        joined = "\n".join(lines)
        self.assertIn("10 × 1 = 10 Marks", joined)
        self.assertIn("5 × 3 = 15 Marks", joined)
        self.assertIn("5 × 5 = 25 Marks", joined)
        # Should never reference the leaked blueprint 38-mark figure.
        self.assertNotIn("38 Marks", joined)


# ---------------------------------------------------------------------------
# ISSUE 1 — type fidelity (slot type wins over LLM payload)
# ---------------------------------------------------------------------------
class _Slot:
    """Minimal stand-in for QuestionGenerationSlot — _coerce_question only
    reads a handful of attributes."""

    def __init__(
        self,
        *,
        legacy_type="MCQ",
        question_type="MCQ",
        marks=1,
        section_title="Section A",
        subject="Science",
        stream="INTEGRATED",
        difficulty="medium",
        class_num=10,
        index=1,
        requires_image=False,
        choice_required=False,
        vi_required=False,
    ):
        self.legacy_type = legacy_type
        self.question_type = question_type
        self.marks = marks
        self.section_title = section_title
        self.subject = subject
        self.stream = stream
        self.difficulty = difficulty
        self.class_num = class_num
        self.index = index
        self.requires_image = requires_image
        self.choice_required = choice_required
        self.vi_required = vi_required


class TypeFidelityTests(unittest.TestCase):
    def test_short_slot_rejects_mcq_payload_on_first_attempt(self):
        slot = _Slot(legacy_type="SHORT", question_type="SHORT_ANSWER", marks=3)
        raw = {
            "question": {
                "content": "Explain Ohm's law in your own words.",
                "type": "MCQ",
                "options": ["a", "b", "c", "d"],
                "answer": "a",
                "marks": 3,
            }
        }
        with self.assertRaises(ValueError):
            _coerce_question(raw, slot, source_chunks=[], is_retry=False)

    def test_short_slot_strips_mcq_options_on_final_attempt(self):
        slot = _Slot(legacy_type="SHORT", question_type="SHORT_ANSWER", marks=3)
        raw = {
            "question": {
                "content": "Explain Ohm's law in your own words.",
                "type": "MCQ",
                "options": ["a", "b", "c", "d"],
                "answer": "V = IR",
                "marks": 3,
            }
        }
        result = _coerce_question(raw, slot, source_chunks=[], is_retry=True)
        self.assertEqual(result["options"], [])
        self.assertEqual(result["type"], "SHORT")


# ---------------------------------------------------------------------------
# ISSUE 2 — figure pipeline (real SVG or text-self-contained, never fake)
# ---------------------------------------------------------------------------
class FigurePipelineTests(unittest.TestCase):
    def test_content_references_missing_figure_detects_common_phrasings(self):
        for phrase in [
            "Observe the given figure and find x.",
            "As shown in the diagram, AB = 4 cm.",
            "Refer to the adjoining circuit.",
            "In the figure below, ABC is a right triangle.",
        ]:
            self.assertTrue(
                _content_references_missing_figure(phrase),
                f"should flag: {phrase!r}",
            )

    def test_self_contained_text_is_not_flagged(self):
        self.assertFalse(
            _content_references_missing_figure(
                "In right triangle ABC, right-angled at B, AB = 24 cm and BC = 7 cm. Find AC."
            )
        )

    def test_strip_figure_references_drops_only_offending_sentence(self):
        original = (
            "Observe the figure above. In right triangle ABC, "
            "right-angled at B, AB = 24 cm and BC = 7 cm. Find AC."
        )
        cleaned = _strip_figure_references(original)
        self.assertNotIn("Observe the figure", cleaned)
        self.assertIn("right triangle ABC", cleaned)

    def test_valid_inline_svg_becomes_data_url(self):
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
            '<rect x="10" y="10" width="80" height="80" fill="none" stroke="black"/>'
            "</svg>"
        )
        url = _figure_to_data_url({"type": "svg", "content": svg})
        self.assertTrue(url.startswith("data:image/svg+xml;base64,"))

    def test_svg_with_script_is_rejected(self):
        bad_svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            "<script>alert(1)</script>"
            "</svg>"
        )
        self.assertEqual(_figure_to_data_url({"type": "svg", "content": bad_svg}), "")

    def test_oversized_svg_is_rejected(self):
        big_svg = "<svg>" + ("x" * 20000) + "</svg>"
        self.assertEqual(_figure_to_data_url({"type": "svg", "content": big_svg}), "")

    def test_coerce_question_rejects_figure_reference_without_figure(self):
        slot = _Slot(legacy_type="LONG", question_type="LONG_ANSWER", marks=5)
        raw = {
            "question": {
                "content": "Observe the given figure and prove that triangle ABC is isosceles.",
                "type": "LONG",
                "answer": "Proof here.",
                "marks": 5,
            }
        }
        with self.assertRaises(ValueError):
            _coerce_question(raw, slot, source_chunks=[], is_retry=False)

    def test_coerce_question_accepts_figure_reference_with_inline_svg(self):
        slot = _Slot(legacy_type="LONG", question_type="LONG_ANSWER", marks=5)
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
            '<polygon points="10,90 90,90 50,10" fill="none" stroke="black"/>'
            "</svg>"
        )
        raw = {
            "question": {
                "content": "Observe the figure and find AC.",
                "type": "LONG",
                "answer": "AC = 25 cm.",
                "marks": 5,
                "figure": {"type": "svg", "content": svg},
            }
        }
        result = _coerce_question(raw, slot, source_chunks=[], is_retry=False)
        self.assertTrue(result["image_url"].startswith("data:image/svg+xml;base64,"))


class AnswerScriptServiceTests(unittest.TestCase):
    """Regression tests for the answer_script_service 500 bug (syntax error)."""

    def test_module_imports_cleanly(self):
        """The service must import without SyntaxError / IndentationError."""
        import importlib
        import services.answer_script_service as m
        # If we get here, no import-time error.
        self.assertTrue(callable(m.generate_answer_script))

    def test_parse_answer_payload_valid_json(self):
        from services.answer_script_service import _parse_answer_payload
        result = _parse_answer_payload('{"answer": "Paris", "or_answer": null}')
        self.assertEqual(result["answer"], "Paris")
        self.assertIsNone(result["or_answer"])

    def test_parse_answer_payload_sanitize(self):
        """Must fall back to sanitize-then-parse when the raw text is wrapped in prose."""
        from services.answer_script_service import _parse_answer_payload
        raw = 'Here is the answer:\n{"answer": "42", "or_answer": null}\nDone.'
        result = _parse_answer_payload(raw)
        self.assertIsNotNone(result)
        self.assertEqual(result["answer"], "42")

    def test_parse_answer_payload_invalid_returns_none(self):
        from services.answer_script_service import _parse_answer_payload
        self.assertIsNone(_parse_answer_payload("not json at all"))

    def test_fallback_answer_from_text_no_or(self):
        from services.answer_script_service import _fallback_answer_from_text
        ans, or_ans = _fallback_answer_from_text(
            '{"answer": "France", "or_answer": null}', None
        )
        self.assertEqual(ans, "France")
        self.assertIsNone(or_ans)

    def test_extract_questions_from_tiptap_json(self):
        """Parser must extract questionBlock nodes from TipTap JSON content."""
        import json
        from services.answer_script_service import _extract_questions_from_content

        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "page",
                    "attrs": {"pageId": "p1"},
                    "content": [
                        {
                            "type": "questionBlock",
                            "attrs": {"marks": 2, "questionType": "SHORT_ANSWER"},
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "What is osmosis?"}],
                                }
                            ],
                        },
                        {
                            "type": "questionBlock",
                            "attrs": {"marks": 1, "questionType": "MCQ"},
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Which gas is produced?"}],
                                },
                                {
                                    "type": "orderedList",
                                    "content": [
                                        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Oxygen"}]}]},
                                        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Nitrogen"}]}]},
                                    ],
                                },
                            ],
                        },
                    ],
                }
            ],
        }

        questions = _extract_questions_from_content(json.dumps(doc))
        self.assertEqual(len(questions), 2)
        self.assertIn("osmosis", questions[0]["content"])
        self.assertEqual(questions[0]["marks"], 2)
        self.assertEqual(len(questions[1]["options"]), 2)


if __name__ == "__main__":
    unittest.main()
