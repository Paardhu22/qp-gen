"""Tables in answer scripts: a question's table reaches the model with its rows
and columns intact, and a table in the model's working lands as a real table."""

import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from services.generation.rules.typesetting import (
    node_text,
    normalize_math_text,
    text_to_blocks,
)
from services.papers import answer_script as ans


def _text(t):
    return {"type": "text", "text": t}


def _inline(latex):
    return {"type": "inlineMath", "attrs": {"latex": latex}}


def _cell(kind, *content):
    return {"type": kind, "content": [{"type": "paragraph", "content": list(content)}]}


def _row(kind, *cells):
    return {"type": "tableRow", "content": [_cell(kind, *c) for c in cells]}


def _stats_table():
    return {
        "type": "table",
        "content": [
            _row("tableHeader", [_text("Class interval")], [_text("Frequency")]),
            _row("tableCell", [_text("0–10")], [_text("5")]),
            _row("tableCell", [_text("10–20")], [_text("8")]),
        ],
    }


def _paper_with_table():
    return {
        "type": "doc",
        "content": [
            {
                "type": "page",
                "content": [
                    {
                        "type": "questionBlock",
                        "attrs": {"marks": 3, "questionType": "SHORT_ANSWER"},
                        "content": [
                            {"type": "paragraph", "content": [_text("Find the mean of the following data.")]},
                            _stats_table(),
                        ],
                    }
                ],
            }
        ],
    }


def _types(nodes):
    return [n["type"] for n in nodes]


class ReadingATableTests(SimpleTestCase):
    def test_a_table_node_reads_as_pipe_rows_under_a_header(self):
        self.assertEqual(
            node_text(_stats_table()).strip(),
            "| Class interval | Frequency |\n| --- | --- |\n| 0–10 | 5 |\n| 10–20 | 8 |",
        )

    def test_a_table_without_header_cells_has_no_separator(self):
        table = {
            "type": "table",
            "content": [
                _row("tableCell", [_text("Frequency")], [_text("5")], [_text("8")]),
                _row("tableCell", [_text("Marks")], [_text("10")], [_text("20")]),
            ],
        }
        self.assertEqual(node_text(table).strip(), "| Frequency | 5 | 8 |\n| Marks | 10 | 20 |")

    def test_maths_in_a_cell_keeps_its_delimiters_and_its_bars(self):
        table = {
            "type": "table",
            "content": [
                _row("tableHeader", [_text("x")], [_text("|x|")]),
                _row("tableCell", [_inline("-3")], [_inline("|-3|")]),
            ],
        }
        rows = node_text(table).strip().splitlines()
        self.assertEqual(rows[2], "| \\(-3\\) | \\(|-3|\\) |")

    def test_the_question_keeps_its_rows_on_separate_lines(self):
        (q,) = ans._extract_questions_from_content(json.dumps(_paper_with_table()))
        self.assertEqual(
            q["content"],
            "Find the mean of the following data.\n"
            "| Class interval | Frequency |\n| --- | --- |\n| 0–10 | 5 |\n| 10–20 | 8 |",
        )

    def test_a_question_without_a_table_reads_as_before(self):
        doc = {
            "type": "doc",
            "content": [
                {"type": "page", "content": [
                    {"type": "questionBlock", "attrs": {"marks": 1},
                     "content": [{"type": "paragraph", "content": [_text("Name   the  capital.")]}]}
                ]}
            ],
        }
        (q,) = ans._extract_questions_from_content(json.dumps(doc))
        self.assertEqual(q["content"], "Name the capital.")


class WritingATableTests(SimpleTestCase):
    TABLE = (
        "| Class interval | Frequency | Cumulative frequency |\n"
        "| --- | --- | --- |\n"
        "| 0–10 | 5 | 5 |\n"
        "| 10–20 | 8 | 13 |"
    )

    def test_pipe_rows_become_a_table_node(self):
        (table,) = text_to_blocks(self.TABLE)
        self.assertEqual(table["type"], "table")
        self.assertEqual(len(table["content"]), 3)
        self.assertEqual([c["type"] for c in table["content"][0]["content"]], ["tableHeader"] * 3)
        self.assertEqual([c["type"] for c in table["content"][1]["content"]], ["tableCell"] * 3)

    def test_the_cell_text_is_in_a_paragraph_of_the_cell(self):
        (table,) = text_to_blocks(self.TABLE)
        first_body = table["content"][1]["content"][0]["content"][0]
        self.assertEqual(first_body["content"], [_text("0–10")])

    def test_headers_and_figures_are_centred(self):
        (table,) = text_to_blocks(self.TABLE)
        header_cell = table["content"][0]["content"][0]["content"][0]
        figure_cell = table["content"][1]["content"][1]["content"][0]
        self.assertEqual(header_cell["attrs"], {"textAlign": "center"})
        self.assertEqual(figure_cell["attrs"], {"textAlign": "center"})

    def test_a_cell_that_is_one_equation_is_centred_like_the_figures_around_it(self):
        text = "| Class | Midpoint |\n| --- | --- |\n| 0–10 | \\( \\frac{0+10}{2} \\) |"
        (table,) = text_to_blocks(text)
        cell = table["content"][1]["content"][1]["content"][0]
        self.assertEqual(cell["attrs"], {"textAlign": "center"})

    def test_words_with_an_equation_in_them_are_not_centred(self):
        text = "| Step | Working |\n| --- | --- |\n| Substitute the values into \\( x^2 \\) and simplify | done |"
        (table,) = text_to_blocks(text)
        cell = table["content"][1]["content"][0]["content"][0]
        self.assertNotIn("attrs", cell)

    def test_prose_around_a_table_stays_prose(self):
        blocks = text_to_blocks(f"Working:\n{self.TABLE}\nHence the median class is 10–20.")
        self.assertEqual(_types(blocks), ["paragraph", "table", "paragraph"])

    def test_maths_in_a_cell_becomes_an_equation_node(self):
        text = "| Class | Midpoint |\n| --- | --- |\n| 0–10 | \\( \\frac{0+10}{2} \\) |"
        (table,) = text_to_blocks(text)
        cell = table["content"][1]["content"][1]["content"][0]
        self.assertEqual(cell["content"], [_inline("\\frac{0+10}{2}")])

    def test_a_bar_inside_maths_does_not_split_the_cell(self):
        text = "| x | abs |\n| --- | --- |\n| \\( -3 \\) | \\( |-3| \\) |"
        (table,) = text_to_blocks(text)
        cells = table["content"][1]["content"]
        self.assertEqual(len(cells), 2)
        self.assertEqual(cells[1]["content"][0]["content"], [_inline("|-3|")])

    def test_an_escaped_bar_prints_as_a_bar(self):
        text = "| Set | n |\n| --- | --- |\n| A \\| B | 3 |"
        (table,) = text_to_blocks(text)
        self.assertEqual(table["content"][1]["content"][0]["content"][0]["content"], [_text("A | B")])

    def test_a_lone_barred_line_is_prose(self):
        blocks = text_to_blocks("Choose a | b today")
        self.assertEqual(_types(blocks), ["paragraph"])

    def test_empty_cells_are_empty_paragraphs(self):
        (table,) = text_to_blocks("| a | b |\n| --- | --- |\n| 1 |  |")
        self.assertEqual(table["content"][1]["content"][1]["content"], [{"type": "paragraph"}])

    def test_a_table_survives_math_normalisation_unchanged_in_shape(self):
        raw = "Class | Freq\n--- | ---\n0–10 | $x^2$\n10–20 | 8"
        (table,) = text_to_blocks(normalize_math_text(raw))
        self.assertEqual(len(table["content"]), 3)
        self.assertEqual(table["content"][0]["content"][0]["type"], "tableHeader")
        self.assertIn(_inline("x^2"), table["content"][1]["content"][1]["content"][0]["content"])


def _answer_with(reply_json, question):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=reply_json), finish_reason="stop")],
            usage=None,
        )

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    with override_settings(ANSWER_MODEL="gpt-4o"), patch.object(ans, "_record_usage"):
        _, result = ans._generate_single_answer_llm_only(client, 1, question, [], user=None)
    return result, calls


class EndToEndTests(SimpleTestCase):
    def _question(self):
        (q,) = ans._extract_questions_from_content(json.dumps(_paper_with_table()))
        return q

    def test_the_model_is_shown_the_table_and_told_how_to_write_one(self):
        _, calls = _answer_with(json.dumps({"answer": "ok", "or_answer": None}), self._question())
        system, user = (m["content"] for m in calls[0]["messages"])
        self.assertIn("| Class interval | Frequency |\n| --- | --- |", user)
        self.assertIn("Tables:", system)
        self.assertIn("Cumulative frequency", system)

    def test_a_worked_table_in_the_reply_lands_in_the_document_as_a_table(self):
        working = (
            "1. Class marks and \\(fx\\):\n"
            "| Class interval | f | x | fx |\n| --- | --- | --- | --- |\n"
            "| 0–10 | 5 | 5 | 25 |\n| 10–20 | 8 | 15 | 120 |\n"
            "2. Mean = \\( \\frac{145}{13} \\)"
        )
        result, _ = _answer_with(json.dumps({"answer": working, "or_answer": None}), self._question())
        doc = []
        ans._append_answers(doc, [result])
        (block,) = doc
        self.assertEqual(_types(block["content"]), ["paragraph", "table", "paragraph"])
        table = block["content"][1]
        self.assertEqual(len(table["content"]), 3)
        self.assertEqual(len(table["content"][0]["content"]), 4)
        self.assertEqual(table["content"][0]["content"][0]["type"], "tableHeader")

    def test_a_table_the_model_wrote_without_outer_pipes_is_still_a_table(self):
        working = "Class | f\n--- | ---\n0–10 | 5\n10–20 | 8"
        result, _ = _answer_with(json.dumps({"answer": working, "or_answer": None}), self._question())
        (block,) = _append(result)
        self.assertEqual(_types(block["content"]), ["table"])

    def test_the_or_alternative_can_carry_a_table_too(self):
        reply = json.dumps({"answer": "A", "or_answer": "| a | b |\n| --- | --- |\n| 1 | 2 |"})
        q = dict(self._question(), or_choice="alt")
        result, _ = _answer_with(reply, q)
        (block,) = _append(result)
        self.assertIn("table", _types(block["content"]))


def _append(result):
    doc = []
    ans._append_answers(doc, [result])
    return doc
