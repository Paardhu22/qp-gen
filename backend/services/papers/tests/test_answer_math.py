"""Maths in answer scripts: the question's equations reach the model, the
model's equations reach the document as nodes — not as raw LaTeX text."""

import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from services.papers import answer_script as ans


def _inline(latex):
    return {"type": "inlineMath", "attrs": {"latex": latex}}


def _text(text):
    return {"type": "text", "text": text}


def _paper_with_question(blocks, **attrs):
    return {
        "type": "doc",
        "content": [
            {
                "type": "page",
                "content": [
                    {
                        "type": "questionBlock",
                        "attrs": {"marks": 3, "questionType": "SHORT_ANSWER", **attrs},
                        "content": blocks,
                    }
                ],
            }
        ],
    }


def _stub_client(*replies):
    """An OpenAI client stand-in that answers with each reply in turn."""
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        content = replies[min(len(calls) - 1, len(replies) - 1)]
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason="stop")],
            usage=None,
        )

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return client, calls


def _answer(reply_text, question=None, or_choice=None):
    client, calls = _stub_client(reply_text)
    q = question or {"content": "Solve \\(x^{2} = 9\\).", "marks": 3, "type": "SHORT_ANSWER", "typeCode": "", "options": [], "or_choice": or_choice}
    with override_settings(ANSWER_MODEL="gpt-4o"), patch.object(ans, "_record_usage"):
        _, result = ans._generate_single_answer_llm_only(client, 1, q, [], user=None)
    return result, calls


class QuestionExtractionTests(SimpleTestCase):
    def test_equations_in_the_question_reach_the_prompt_as_latex(self):
        doc = _paper_with_question(
            [
                {"type": "paragraph", "content": [_text("Find the roots of "), _inline("x^2 - 5x + 6 = 0"), _text(".")]},
                {"type": "mathBlock", "attrs": {"latex": "\\int_0^1 x\\,dx"}},
            ]
        )
        (q,) = ans._extract_questions_from_content(json.dumps(doc))
        self.assertEqual(
            q["content"],
            "Find the roots of \\(x^2 - 5x + 6 = 0\\). \\[\\int_0^1 x\\,dx\\]",
        )

    def test_maths_in_the_options_is_kept_too(self):
        doc = _paper_with_question(
            [
                {"type": "paragraph", "content": [_text("The value of "), _inline("\\sqrt{16}"), _text(" is")]},
                {
                    "type": "orderedList",
                    "content": [
                        {"type": "listItem", "content": [{"type": "paragraph", "content": [_inline("2")]}]},
                        {"type": "listItem", "content": [{"type": "paragraph", "content": [_inline("4")]}]},
                    ],
                },
            ],
            questionType="MCQ",
        )
        (q,) = ans._extract_questions_from_content(json.dumps(doc))
        self.assertEqual(q["options"], ["\\(2\\)", "\\(4\\)"])
        self.assertIn("\\(\\sqrt{16}\\)", q["content"])

    def test_a_question_without_maths_reads_as_before(self):
        doc = _paper_with_question([{"type": "paragraph", "content": [_text("Name the capital of France.")]}])
        (q,) = ans._extract_questions_from_content(json.dumps(doc))
        self.assertEqual(q["content"], "Name the capital of France.")


class PromptTests(SimpleTestCase):
    def test_the_system_prompt_states_the_maths_rules(self):
        self.assertIn("\\( ... \\)", ans.SYSTEM_PROMPT)
        self.assertIn("\\[ ... \\]", ans.SYSTEM_PROMPT)
        self.assertIn("every backslash inside a JSON string must be doubled", ans.SYSTEM_PROMPT)

    def test_the_model_is_shown_the_question_with_its_equations(self):
        result, calls = _answer(json.dumps({"answer": "x = 3", "or_answer": None}))
        sent = calls[0]["messages"]
        self.assertEqual(sent[0]["content"], ans.SYSTEM_PROMPT)
        self.assertIn("Solve \\(x^{2} = 9\\).", sent[1]["content"])


class ReplyHandlingTests(SimpleTestCase):
    def test_a_correctly_escaped_reply_keeps_its_latex(self):
        reply = json.dumps({"answer": "1. \\(x^{2} = 9\\)\n2. \\(x = \\pm 3\\)", "or_answer": None})
        result, _ = _answer(reply)
        self.assertEqual(result["answer"], "1. \\(x^{2} = 9\\)\n2. \\(x = \\pm 3\\)")

    def test_single_backslashes_in_the_reply_are_repaired(self):
        # Invalid JSON as the model wrote it: a lone "\(" is not a legal escape.
        reply = '{"answer": "Hence \\(\\frac{1}{2}\\) and \\(\\theta = 30^\\circ\\)", "or_answer": null}'
        with self.assertRaises(json.JSONDecodeError):
            json.loads(reply)
        result, _ = _answer(reply)
        self.assertEqual(result["answer"], "Hence \\(\\frac{1}{2}\\) and \\(\\theta = 30^\\circ\\)")

    def test_commands_json_would_silently_corrupt_come_back_intact(self):
        # "\frac", "\beta", "\neq" are all LEGAL JSON escapes (form feed, backspace,
        # newline), so this reply parses cleanly and the maths is garbage unless
        # it is restored.
        reply = '{"answer": "x \\neq y and \\beta and \\frac{1}{2}", "or_answer": null}'
        naive = json.loads(reply)["answer"]
        self.assertNotIn("\\", naive, "the premise: nothing survives a naive parse")
        result, _ = _answer(reply)
        self.assertEqual(
            result["answer"], "x \\(\\neq\\) y and \\(\\beta\\) and \\(\\frac{1}{2}\\)"
        )

    def test_dollar_delimiters_become_the_contract(self):
        reply = json.dumps({"answer": "So $x = 3$, and $$y = x^2$$", "or_answer": None})
        result, _ = _answer(reply)
        self.assertEqual(result["answer"], "So \\(x = 3\\), and \\[y = x^2\\]")

    def test_bare_latex_is_wrapped(self):
        reply = json.dumps({"answer": "Area = \\pi r^2 cm", "or_answer": None})
        result, _ = _answer(reply)
        self.assertEqual(result["answer"], "Area = \\(\\pi\\) \\(r^2\\) cm")

    def test_the_or_answer_gets_the_same_treatment(self):
        reply = '{"answer": "A: \\(a\\)", "or_answer": "B: $b^2$"}'
        result, _ = _answer(
            reply,
            question={"content": "Q \\(a\\)", "marks": 3, "type": "SHORT_ANSWER", "typeCode": "", "options": [], "or_choice": "alt"},
        )
        self.assertEqual(result["answer"], "A: \\(a\\)")
        self.assertEqual(result["or_answer"], "B: \\(b^2\\)")

    def test_a_truncated_reply_still_salvages_the_latex(self):
        # Not valid JSON at all (cut off) — the field-level salvage runs.
        reply = '{"answer": "Use \\(x^{2}\\) here", "or_answ'
        result, _ = _answer(reply)
        self.assertEqual(result["answer"], "Use \\(x^{2}\\) here")

    def test_failure_placeholders_are_untouched(self):
        result, _ = _answer("")
        self.assertEqual(result["answer"], "[Answer generation failed]")


class IndexedVariableTests(SimpleTestCase):
    """x1 in a model's answer must reach the document as maths, per subject."""

    def _answer_for(self, subject, answer):
        client, _ = _stub_client(json.dumps({"answer": answer, "or_answer": None}))
        q = {"content": "Find the distance.", "marks": 3, "type": "SHORT_ANSWER", "typeCode": "", "options": []}
        with override_settings(ANSWER_MODEL="gpt-4o"), patch.object(ans, "_record_usage"):
            _, result = ans._generate_single_answer_llm_only(client, 1, q, [], user=None, subject=subject)
        return result["answer"]

    def test_a_maths_answer_gets_subscripts(self):
        got = self._answer_for("Mathematics", "d = sqrt((x2 - x1)^2 + (y2 - y1)^2) where (x1, y1) is A.")
        self.assertIn("\\((x_{1}, y_{1})\\)", got)
        self.assertIn("\\(x_{2}\\)", got)

    def test_an_ict_answer_keeps_its_cell_references(self):
        text = "Enter =SUM(A1:A5) in cell B1."
        self.assertEqual(self._answer_for("ICT", text), text)

    def test_the_subscripted_answer_becomes_math_nodes(self):
        got = self._answer_for("Mathematics", "Hence x1 + x2 = 5.")
        doc = []
        ans._append_answers(doc, [{"question_number": 1, "marks": 2, "answer": got, "question_type": "SHORT_ANSWER"}])
        latex = [
            n["attrs"]["latex"]
            for n in doc[0]["content"][0]["content"]
            if n["type"] == "inlineMath"
        ]
        self.assertEqual(latex, ["x_{1}", "x_{2}"])

    def test_the_system_prompt_asks_for_latex_subscripts(self):
        self.assertIn("x_{1}", ans.SYSTEM_PROMPT)
        self.assertIn("Do not write x1", ans.SYSTEM_PROMPT)


class DocumentTests(SimpleTestCase):
    def _blocks(self, answers):
        doc = []
        ans._append_answers(doc, answers)
        return doc

    def test_inline_maths_becomes_nodes_inside_the_question_block(self):
        (block,) = self._blocks(
            [{"question_number": 1, "marks": 2, "answer": "Hence \\(x = 3\\).", "question_type": "SHORT_ANSWER"}]
        )
        self.assertEqual(block["type"], "questionBlock")
        self.assertEqual(
            block["content"][0],
            {
                "type": "paragraph",
                "content": [_text("Hence "), _inline("x = 3"), _text(".")],
            },
        )

    def test_display_maths_becomes_a_math_block(self):
        (block,) = self._blocks(
            [{"question_number": 1, "marks": 3, "answer": "Working:\n\\[ \\int_0^1 x\\,dx = \\frac{1}{2} \\]\nDone.", "question_type": "SHORT_ANSWER"}]
        )
        self.assertEqual(
            [n["type"] for n in block["content"]], ["paragraph", "mathBlock", "paragraph"]
        )
        self.assertEqual(
            block["content"][1]["attrs"]["latex"], "\\int_0^1 x\\,dx = \\frac{1}{2}"
        )

    def test_numbered_points_are_separate_paragraphs(self):
        (block,) = self._blocks(
            [{"question_number": 1, "marks": 3, "answer": "1. First\n2. Second\n3. Third", "question_type": "SHORT_ANSWER"}]
        )
        self.assertEqual(len(block["content"]), 3)

    def test_the_or_alternative_keeps_its_maths(self):
        (block,) = self._blocks(
            [
                {
                    "question_number": 4,
                    "marks": 5,
                    "answer": "A: \\(a\\)",
                    "or_choice_text": "alt",
                    "or_answer": "B: \\(b\\)",
                    "question_type": "LONG_ANSWER",
                }
            ]
        )
        kinds = [n["type"] for n in block["content"]]
        self.assertEqual(kinds, ["paragraph", "paragraph", "paragraph"])
        self.assertEqual(block["content"][1]["content"][0]["marks"], [{"type": "bold"}])
        self.assertIn(_inline("b"), block["content"][2]["content"])

    def test_no_raw_delimiters_survive_in_any_text_node(self):
        (block,) = self._blocks(
            [{"question_number": 1, "marks": 3, "answer": "Take \\(a\\) then \\[b\\] and \\(c\\)", "question_type": "SHORT_ANSWER"}]
        )

        def texts(node):
            if node.get("type") == "text":
                yield node["text"]
            for child in node.get("content") or []:
                yield from texts(child)

        joined = " ".join(texts(block))
        self.assertNotIn("\\(", joined)
        self.assertNotIn("\\[", joined)

    def test_a_failed_answer_is_still_a_plain_paragraph(self):
        (block,) = self._blocks(
            [{"question_number": 1, "marks": 1, "answer": "[Answer generation failed]", "question_type": "SHORT_ANSWER"}]
        )
        self.assertEqual(block["content"], [{"type": "paragraph", "content": [_text("[Answer generation failed]")]}])
