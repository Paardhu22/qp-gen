"""Tables in model output: one pipe-row convention, bent into shape here."""

from django.test import SimpleTestCase

from services.generation.pool.model1 import _system_prompt
from services.generation.rules.content_filters import clean_question_text
from services.generation.rules.tables import (
    ANSWER_TABLE_RULES,
    QUESTION_TABLE_RULES,
    escape_cell,
    normalize_tables,
    parse_run,
    split_cells,
)
from services.question_types import get as get_type

CANONICAL = (
    "| Class interval | Frequency |\n"
    "| --- | --- |\n"
    "| 0–10 | 5 |\n"
    "| 10–20 | 8 |"
)


class SplitCellsTests(SimpleTestCase):
    def test_edge_pipes_are_not_cells(self):
        self.assertEqual(split_cells("| a | b |"), ["a", "b"])
        self.assertEqual(split_cells("a | b"), ["a", "b"])

    def test_a_pipe_inside_maths_belongs_to_the_cell(self):
        self.assertEqual(split_cells("| \\( |x| \\) | 3 |"), ["\\( |x| \\)", "3"])
        self.assertEqual(split_cells("| \\[ \\begin{array}{c|c} \\end{array} \\] | 3 |")[1], "3")

    def test_an_escaped_pipe_belongs_to_the_cell(self):
        self.assertEqual(split_cells("| A \\| B | 3 |"), ["A \\| B", "3"])

    def test_an_unclosed_math_span_cannot_swallow_the_row(self):
        self.assertEqual(split_cells("| \\( x | 3 | 4 |"), ["\\( x", "3", "4"])

    def test_escape_cell_protects_bare_pipes_but_not_maths(self):
        self.assertEqual(escape_cell("A | B"), "A \\| B")
        self.assertEqual(escape_cell("\\( |x| \\) | y"), "\\( |x| \\) \\| y")
        self.assertEqual(escape_cell("already \\| escaped"), "already \\| escaped")


class NormalizeTablesTests(SimpleTestCase):
    def test_a_canonical_table_is_untouched(self):
        self.assertEqual(normalize_tables(CANONICAL), CANONICAL)

    def test_text_around_a_table_is_untouched(self):
        text = f"Find the mean.\n{CANONICAL}\nShow your working."
        self.assertEqual(normalize_tables(text), text)

    def test_rows_without_the_outer_pipes_are_repaired(self):
        raw = "Class interval | Frequency\n--- | ---\n0–10 | 5\n10–20 | 8"
        self.assertEqual(normalize_tables(raw), CANONICAL)

    def test_a_missing_separator_is_added_when_the_first_row_is_a_header(self):
        raw = "| Class interval | Frequency |\n| 0–10 | 5 |\n| 10–20 | 8 |"
        self.assertEqual(normalize_tables(raw), CANONICAL)

    def test_a_row_wise_table_is_not_given_a_header(self):
        raw = "| Class interval | 0–10 | 10–20 |\n| Frequency | 5 | 8 |"
        self.assertEqual(normalize_tables(raw), raw)

    def test_a_fenced_table_loses_its_fence(self):
        raw = "```markdown\n" + CANONICAL + "\n```"
        self.assertEqual(normalize_tables(raw), CANONICAL)

    def test_ragged_rows_are_padded(self):
        raw = "| a | b | c |\n| --- | --- | --- |\n| 1 | 2 |"
        self.assertEqual(
            normalize_tables(raw), "| a | b | c |\n| --- | --- | --- |\n| 1 | 2 |  |"
        )

    def test_blank_lines_between_rows_do_not_split_a_table(self):
        raw = "| a | b |\n\n| --- | --- |\n\n| 1 | 2 |"
        self.assertEqual(normalize_tables(raw), "| a | b |\n| --- | --- |\n| 1 | 2 |")

    def test_stray_bold_and_line_breaks_in_cells_go(self):
        raw = "| **Class** | **Freq<br>uency** |\n| --- | --- |\n| 0–10 | 5 |"
        self.assertEqual(
            normalize_tables(raw), "| Class | Freq uency |\n| --- | --- |\n| 0–10 | 5 |"
        )

    def test_display_maths_in_a_cell_becomes_inline(self):
        raw = "| x | f(x) |\n| --- | --- |\n| 1 | \\[ x^2 \\] |"
        self.assertEqual(normalize_tables(raw).splitlines()[-1], "| 1 | \\( x^2 \\) |")

    def test_prose_with_a_bar_is_not_a_table(self):
        text = "Use a | b to mean either."
        self.assertEqual(normalize_tables(text), text)

    def test_two_shell_pipelines_are_not_a_table(self):
        text = "cat notes.txt | grep exam\nls | wc -l"
        self.assertEqual(normalize_tables(text), text)

    def test_a_single_barred_line_is_not_a_table(self):
        self.assertEqual(normalize_tables("| only | one |"), "| only | one |")

    def test_nothing_to_do_returns_the_same_text(self):
        self.assertEqual(normalize_tables("plain text"), "plain text")
        self.assertEqual(normalize_tables(""), "")

    def test_parse_run_reports_the_header(self):
        table = parse_run(CANONICAL.splitlines())
        self.assertTrue(table.header)
        self.assertEqual(table.rows[0], ["Class interval", "Frequency"])
        self.assertEqual(len(table.rows), 3)


class ScrubTests(SimpleTestCase):
    def test_a_generated_question_has_its_table_repaired_and_its_maths_wrapped(self):
        raw = (
            "Find the mean of the data.\n"
            "Marks | Students\n--- | ---\n0–10 | x^2\n10–20 | 8"
        )
        out = clean_question_text(raw)
        self.assertIn("| Marks | Students |\n| --- | --- |", out)
        self.assertIn("| 0–10 | \\(x^2\\) |", out)


class PromptTests(SimpleTestCase):
    def test_the_question_writer_is_told_to_print_data_as_a_table(self):
        prompt = _system_prompt("Mathematics", 10, "medium")
        self.assertIn("11. Tables:", prompt)
        self.assertIn("frequency distribution", prompt)
        self.assertIn("| --- | --- |", prompt)
        self.assertIn(QUESTION_TABLE_RULES.strip(), prompt)

    def test_the_rule_comes_before_the_output_format(self):
        prompt = _system_prompt("Mathematics", 10, "medium")
        self.assertLess(prompt.index("11. Tables:"), prompt.index("Return ONLY a JSON array"))

    def test_the_answer_writer_has_its_own_table_rule(self):
        self.assertIn("cumulative frequencies", ANSWER_TABLE_RULES)
        self.assertIn("| --- |", ANSWER_TABLE_RULES)

    def test_the_statistics_type_teaches_a_column_table_with_headings(self):
        spec = get_type("STATISTICS_COMPUTE")
        table = parse_run(spec.example.splitlines()[1:])
        self.assertTrue(table.header)
        self.assertEqual(table.rows[0], ["Class interval", "Frequency"])

    def test_the_statistics_sample_answer_matches_its_own_data(self):
        # classes 5, 15, 25, 35 with frequencies 5, 8, 12, 5.
        mean = (5 * 5 + 8 * 15 + 12 * 25 + 5 * 35) / 30
        self.assertIn(f"{mean:.2f}", get_type("STATISTICS_COMPUTE").answer)
