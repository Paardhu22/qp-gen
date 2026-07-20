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
# The type-fidelity and inline-SVG figure tests that lived here exercised
# the per-slot engine's _coerce_question and _figure_to_data_url. Both went
# away with that engine: the pool enforces question type by MATCHING a
# question to a slot (services/pool/schema.py::slot_accepts, covered in
# services/pool/test_model2.py) rather than by overriding a returned type,
# and figures are stored image URLs rather than model-drawn SVG markup.

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

    def test_request_completion_does_not_send_unsupported_temperature(self):
        """Regression: the per-Q LLM call must not pass `temperature=0`.

        gpt-5 family models reject any non-default temperature with
        BadRequestError ('unsupported_value'). When that exception was
        swallowed by the per-Q try/except, every question came back as
        "[Answer generation failed]" and the marks badge showed 0.

        This test captures the kwargs the service would pass to OpenAI
        without actually hitting the network. If a future change reverts
        `temperature=0` (or any value other than 1), the assertion fails.
        """
        from unittest.mock import MagicMock, patch
        from services import answer_script_service as svc

        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message.content = '{"answer": "ok", "or_answer": null}'
            response.usage = MagicMock(
                prompt_tokens=1, completion_tokens=1, total_tokens=2
            )
            return response

        fake_client = MagicMock()
        fake_client.chat.completions.create.side_effect = fake_create

        with patch.object(svc, "_record_usage"):
            svc._generate_single_answer_llm_only(
                client=fake_client,
                question_number=1,
                question={
                    "content": "What is X?",
                    "marks": 3,
                    "type": "SHORT_ANSWER",
                    "options": [],
                    "or_choice": None,
                },
                source_chunks=[],
                user=None,
            )

        self.assertNotIn(
            "temperature", captured,
            msg="answer_script_service must not pass `temperature` to OpenAI "
                "(gpt-5 only accepts default=1; sending any value causes a "
                "BadRequestError that blanket-fails every question).",
        )

    def test_build_answer_script_emits_question_blocks(self):
        """Regression: marks badge counts `questionBlock` nodes; the answer
        script must emit them so the badge isn't perma-zero."""
        from services.answer_script_service import _build_answer_script_content

        class _StubProject:
            name = "Class 10 — Science"

        class _StubPaper:
            project = _StubProject()

        answers = [
            {
                "question_number": 1, "marks": 2,
                "answer": "Photosynthesis is …",
                "question_type": "SHORT_ANSWER",
                "or_choice_text": None, "or_answer": None,
            },
            {
                "question_number": 2, "marks": 5,
                "answer": "Newton's laws state …",
                "question_type": "LONG_ANSWER",
                "or_choice_text": "Explain inertia",
                "or_answer": "Inertia is …",
            },
        ]

        blocks = _build_answer_script_content(_StubPaper(), answers)
        # Top-level wrapper is a page node containing the doc body.
        self.assertEqual(blocks[0]["type"], "page")
        body = blocks[0]["content"]
        q_blocks = [b for b in body if b.get("type") == "questionBlock"]
        self.assertEqual(len(q_blocks), 2)
        self.assertEqual(q_blocks[0]["attrs"]["marks"], 2)
        self.assertEqual(q_blocks[0]["attrs"]["number"], 1)
        self.assertEqual(q_blocks[1]["attrs"]["marks"], 5)
        # OR-answer expands into extra paragraphs inside the same questionBlock
        self.assertGreaterEqual(len(q_blocks[1]["content"]), 3)

    def test_per_q_budget_is_sufficient_for_reasoning_models(self):
        """Regression: gpt-5 family models eat `max_completion_tokens` with
        internal reasoning. Round-2 cause of "[Answer to be filled by
        teacher]" was a 1000-token budget being entirely consumed by
        reasoning, producing empty content (finish_reason=length).

        Assert the service requests at least 4000 tokens on the first
        attempt and passes `reasoning_effort` to throttle reasoning-token
        spend.
        """
        from unittest.mock import MagicMock, patch
        from services import answer_script_service as svc

        captured: list[dict] = []

        def fake_create(**kwargs):
            captured.append(kwargs)
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message.content = (
                '{"answer": "1. Real answer text.", "or_answer": null}'
            )
            response.choices[0].finish_reason = "stop"
            response.usage = MagicMock(
                prompt_tokens=10, completion_tokens=20, total_tokens=30
            )
            return response

        fake_client = MagicMock()
        fake_client.chat.completions.create.side_effect = fake_create

        with patch.object(svc, "_record_usage"):
            svc._generate_single_answer_llm_only(
                client=fake_client,
                question_number=1,
                question={
                    "content": "Long-answer Q.",
                    "marks": 5,
                    "type": "LONG_ANSWER",
                    "options": [],
                    "or_choice": None,
                },
                source_chunks=[],
                user=None,
            )

        self.assertGreaterEqual(
            captured[0].get("max_completion_tokens", 0), 4000,
            msg="Per-Q first attempt must allocate ≥4000 completion tokens "
                "so gpt-5 reasoning + visible JSON both fit. The previous "
                "1000-token budget caused 5-mark answers to come back empty.",
        )
        # reasoning_effort must be passed to gpt-5 family
        from django.conf import settings as dj_settings
        if (dj_settings.OPENAI_MODEL or "").startswith(("gpt-5", "o1", "o3")):
            self.assertIn(
                "reasoning_effort", captured[0],
                msg="gpt-5 family answer-script call must throttle reasoning "
                    "with reasoning_effort='low' (or similar).",
            )

    def test_truncated_first_attempt_triggers_higher_budget_retry(self):
        """Regression: if the first call comes back with finish_reason='length'
        or empty content, the service must retry with a larger budget — not
        emit "[Answer to be filled by teacher]".
        """
        from unittest.mock import MagicMock, patch
        from services import answer_script_service as svc

        calls: list[dict] = []

        def fake_create(**kwargs):
            calls.append(kwargs)
            response = MagicMock()
            response.choices = [MagicMock()]
            if len(calls) == 1:
                # First attempt — model exhausts the reasoning budget,
                # returns nothing visible. This is the production bug.
                response.choices[0].message.content = ""
                response.choices[0].finish_reason = "length"
            else:
                # Second attempt with a larger budget — real answer.
                response.choices[0].message.content = (
                    '{"answer": "1. Real recovered answer.", "or_answer": null}'
                )
                response.choices[0].finish_reason = "stop"
            response.usage = MagicMock(
                prompt_tokens=10, completion_tokens=20, total_tokens=30
            )
            return response

        fake_client = MagicMock()
        fake_client.chat.completions.create.side_effect = fake_create

        with patch.object(svc, "_record_usage"):
            _, result = svc._generate_single_answer_llm_only(
                client=fake_client,
                question_number=29,
                question={
                    "content": "Long-answer Q.",
                    "marks": 5,
                    "type": "LONG_ANSWER",
                    "options": [],
                    "or_choice": None,
                },
                source_chunks=[],
                user=None,
            )

        self.assertGreaterEqual(len(calls), 2, "must retry on length-truncation")
        self.assertGreater(
            calls[1]["max_completion_tokens"], calls[0]["max_completion_tokens"],
            msg="Retry must use a STRICTLY larger budget — same budget would "
                "hit the same length limit and silently fail again.",
        )
        self.assertEqual(result["answer"], "1. Real recovered answer.")
        self.assertNotIn("teacher", result["answer"].lower())
        self.assertNotIn("failed", result["answer"].lower())

    def test_thirty_question_paper_has_no_placeholder_answers(self):
        """Regression: a 30-question paper (matching the production
        symptom: Q29-Q38 all teacher-placeholder while Q28 worked) must
        round-trip with REAL answers for every question once the LLM
        returns content.

        The test mocks the OpenAI client to always return a non-trivial
        answer, then drives the full per-Q parallel pipeline and asserts
        none of the 30 resulting answer payloads carry the
        "[Answer to be filled by teacher]" placeholder.
        """
        from unittest.mock import MagicMock, patch
        from services import answer_script_service as svc

        def fake_create(**kwargs):
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message.content = (
                '{"answer": "Real numbered answer.", "or_answer": null}'
            )
            response.choices[0].finish_reason = "stop"
            response.usage = MagicMock(
                prompt_tokens=5, completion_tokens=5, total_tokens=10
            )
            return response

        fake_client = MagicMock()
        fake_client.chat.completions.create.side_effect = fake_create

        answers = []
        with patch.object(svc, "_record_usage"):
            for i in range(1, 31):
                _, ans = svc._generate_single_answer_llm_only(
                    client=fake_client,
                    question_number=i,
                    question={
                        "content": f"Question {i} stem.",
                        "marks": 5 if i % 2 == 0 else 2,
                        "type": "LONG_ANSWER" if i % 2 == 0 else "SHORT_ANSWER",
                        "options": [],
                        "or_choice": None,
                    },
                    source_chunks=[],
                    user=None,
                )
                answers.append(ans)

        self.assertEqual(len(answers), 30)
        for ans in answers:
            self.assertNotIn(
                "teacher", (ans["answer"] or "").lower(),
                msg=f"Q{ans['question_number']} fell back to the teacher "
                    "placeholder — the answer-script generator must emit "
                    "either a real answer or an explicit "
                    "[Answer generation failed] tag.",
            )
            self.assertTrue(
                ans["answer"], f"Q{ans['question_number']} answer is empty",
            )


if __name__ == "__main__":
    unittest.main()
