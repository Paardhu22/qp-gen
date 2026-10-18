"""The maths contract: \\( … \\) inline, \\[ … \\] display, nodes in the document."""

import json

from django.test import SimpleTestCase

from services.generation.rules.typesetting import (
    MATH_PROMPT_RULES,
    node_text,
    normalize_math_text,
    repair_json_backslashes,
    restore_eaten_escapes,
    text_to_blocks,
)


def _inline(latex):
    return {"type": "inlineMath", "attrs": {"latex": latex}}


def _text(text):
    return {"type": "text", "text": text}


class NodeTextTests(SimpleTestCase):
    def test_inline_math_keeps_its_latex_inside_the_delimiters(self):
        para = {"type": "paragraph", "content": [_text("Solve "), _inline("x^2 - 4 = 0"), _text(" for x.")]}
        self.assertEqual(node_text(para), "Solve \\(x^2 - 4 = 0\\) for x.")

    def test_a_display_block_becomes_a_display_span(self):
        block = {"type": "mathBlock", "attrs": {"latex": "\\int_0^1 x\\,dx"}}
        self.assertEqual(node_text(block), "\\[\\int_0^1 x\\,dx\\]")

    def test_blocks_are_separated_but_inline_pieces_are_not(self):
        question = {
            "type": "questionBlock",
            "content": [
                {"type": "paragraph", "content": [_text("un"), _text("believable "), _inline("a")]},
                {"type": "mathBlock", "attrs": {"latex": "b"}},
            ],
        }
        self.assertEqual(node_text(question), "unbelievable \\(a\\) \\[b\\]")

    def test_an_empty_equation_adds_nothing(self):
        self.assertEqual(node_text(_inline("  ")), "")


class JsonRepairTests(SimpleTestCase):
    def test_a_single_backslash_before_a_paren_is_made_parseable(self):
        raw = '{"answer": "Value is \\(x^2\\) and \\sqrt{3}"}'
        with self.assertRaises(json.JSONDecodeError):
            json.loads(raw)
        self.assertEqual(
            json.loads(repair_json_backslashes(raw))["answer"],
            "Value is \\(x^2\\) and \\sqrt{3}",
        )

    def test_already_escaped_pairs_are_left_alone(self):
        raw = '{"answer": "\\\\(x\\\\) and a \\"quote\\" and \\u00e9"}'
        self.assertEqual(repair_json_backslashes(raw), raw)
        self.assertEqual(json.loads(raw)["answer"], '\\(x\\) and a "quote" and é')

    def test_a_mix_of_doubled_and_single_backslashes(self):
        raw = '{"answer": "\\\\(a\\\\) then \\(b\\)"}'
        self.assertEqual(json.loads(repair_json_backslashes(raw))["answer"], "\\(a\\) then \\(b\\)")

    def test_u_without_four_hex_digits_is_not_an_escape(self):
        raw = '{"answer": "\\underline{x}"}'
        self.assertEqual(json.loads(repair_json_backslashes(raw))["answer"], "\\underline{x}")


class EatenEscapeTests(SimpleTestCase):
    """A valid JSON reply that wrote ``\\frac`` comes back as form feed + "rac"."""

    def test_the_real_json_round_trip_corrupts_these_commands(self):
        # What actually happens when the model forgets to double the backslash:
        # the lone "\\(" forces a repair pass, and "\\frac" then parses as a
        # legal escape.
        parsed = json.loads(repair_json_backslashes('{"a": "\\(\\frac{1}{2} \\times \\theta \\beta\\)"}'))["a"]
        self.assertNotIn("\\frac", parsed)
        self.assertEqual(restore_eaten_escapes(parsed), "\\(\\frac{1}{2} \\times \\theta \\beta\\)")

    def test_neq_nu_and_rho_inside_maths(self):
        parsed = json.loads(repair_json_backslashes('{"a": "\\(a \\neq b, \\nu, \\rho\\)"}'))["a"]
        self.assertEqual(restore_eaten_escapes(parsed), "\\(a \\neq b, \\nu, \\rho\\)")

    def test_bare_commands_outside_delimiters_are_restored_too(self):
        parsed = json.loads('{"a": "so \\frac{1}{2} and \\theta"}')["a"]
        self.assertEqual(restore_eaten_escapes(parsed), "so \\frac{1}{2} and \\theta")

    def test_real_line_breaks_in_prose_survive(self):
        text = "1. First point\nunits are in cm\n2. Second point"
        self.assertEqual(restore_eaten_escapes(text), text)


class NormalizeTests(SimpleTestCase):
    def test_dollar_delimiters_become_the_contract(self):
        self.assertEqual(normalize_math_text("Find $x^2$ now"), "Find \\(x^2\\) now")
        self.assertEqual(normalize_math_text("$$a + b$$"), "\\[a + b\\]")

    def test_currency_is_not_maths(self):
        text = "It costs $5 and then $10 more, about $15."
        self.assertEqual(normalize_math_text(text), text)

    def test_an_escaped_dollar_is_a_dollar(self):
        self.assertEqual(normalize_math_text("pay \\$5 now"), "pay $5 now")

    def test_existing_delimiters_are_untouched(self):
        text = "Hence \\( \\frac{a}{b} \\) and\n\\[ x = 1 \\]"
        self.assertEqual(normalize_math_text(text), text)

    def test_bare_latex_is_wrapped(self):
        self.assertEqual(normalize_math_text("the value \\frac{1}{2} here"), "the value \\(\\frac{1}{2}\\) here")
        self.assertEqual(normalize_math_text("so x^2 = 4."), "so \\(x^2\\) = 4.")

    def test_a_matrix_is_one_expression_not_pieces(self):
        out = normalize_math_text("Let A = \\begin{pmatrix} 1 & 2 \\\\ 3 & 4 \\end{pmatrix} then")
        self.assertEqual(
            out, "Let A = \\[\\begin{pmatrix} 1 & 2 \\\\ 3 & 4 \\end{pmatrix}\\] then"
        )

    def test_a_matrix_already_in_delimiters_is_not_wrapped_twice(self):
        text = "\\[\\begin{pmatrix} 1 & 2 \\end{pmatrix}\\]"
        self.assertEqual(normalize_math_text(text), text)

    def test_plain_prose_is_unchanged(self):
        text = "1. The clergy\n2. The nobility (Any 2 points to be considered)"
        self.assertEqual(normalize_math_text(text), text)

    def test_empty_values_pass_through(self):
        self.assertEqual(normalize_math_text(""), "")
        self.assertIsNone(normalize_math_text(None))


class TextToBlocksTests(SimpleTestCase):
    def test_inline_math_becomes_nodes_between_text(self):
        blocks = text_to_blocks("Substituting \\(x = 2\\), we get \\(y = 7\\).")
        self.assertEqual(len(blocks), 1)
        self.assertEqual(
            blocks[0]["content"],
            [
                _text("Substituting "),
                _inline("x = 2"),
                _text(", we get "),
                _inline("y = 7"),
                _text("."),
            ],
        )

    def test_display_math_is_a_block_between_paragraphs(self):
        blocks = text_to_blocks("Given:\n\\[ x^2 + 1 = 0 \\]\nHence no real roots.")
        self.assertEqual([b["type"] for b in blocks], ["paragraph", "mathBlock", "paragraph"])
        self.assertEqual(blocks[1]["attrs"], {"latex": "x^2 + 1 = 0", "displayMode": True})

    def test_each_line_is_its_own_paragraph(self):
        blocks = text_to_blocks("1. First\n2. Second\n\n3. Third")
        self.assertEqual(
            [b["content"][0]["text"] for b in blocks], ["1. First", "2. Second", "3. Third"]
        )

    def test_inline_math_that_spans_a_line_break_stays_whole(self):
        blocks = text_to_blocks("so \\(a +\nb\\) done")
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["content"][1], _inline("a + b"))

    def test_an_unclosed_delimiter_stays_as_text(self):
        blocks = text_to_blocks("broken \\( x + 1")
        self.assertEqual(blocks[0]["content"], [_text("broken \\( x + 1")])

    def test_an_empty_answer_still_yields_a_paragraph(self):
        self.assertEqual(text_to_blocks(""), [{"type": "paragraph"}])
        self.assertEqual(text_to_blocks(None), [{"type": "paragraph"}])


class PromptRulesTests(SimpleTestCase):
    def test_the_rules_name_both_delimiters_and_the_json_escape(self):
        self.assertIn("\\( ... \\)", MATH_PROMPT_RULES)
        self.assertIn("\\[ ... \\]", MATH_PROMPT_RULES)
        self.assertIn("\\\\frac{1}{2}", MATH_PROMPT_RULES)
        self.assertIn("Never write maths as $", MATH_PROMPT_RULES)
