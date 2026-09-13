"""Chart questions: Model 1 writes the data, the deterministic renderer draws it.

The figure a chart question prints is never a URL a model produced — that
would be an invented image. It is drawn from the numbers the model wrote, by
`services.figures`, and a question whose numbers will not draw is dropped
rather than printed pointing at a chart that is not there.
"""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

_RENDERED = {"imageUrl": "/media/question_figures/abc.svg", "kind": "chart", "cached": False}

_BAR = {
    "chart": "bar",
    "series": [
        {"label": "School A", "value": 45},
        {"label": "School B", "value": 70},
        {"label": "School C", "value": 30},
    ],
    "xLabel": "School",
    "yLabel": "Trees planted",
    "showValues": False,
}


def _graph_read(**overrides):
    raw = {
        "type": "SHORT_ANSWER",
        "marks": 2,
        "question": "Study the bar graph. How many more trees did School B plant than School C?",
        "answer": "40",
        "figure": _BAR,
    }
    raw.update(overrides)
    return raw


def _normalise(raws, quota):
    from services.pool.model1 import _normalise_batch
    from services.pool.recipes import Batch

    return _normalise_batch(
        raws,
        batch=Batch("chart", [quota]),
        subject="Mathematics",
        chapter_name="Data Handling",
        pool_id="pool",
        difficulty="medium",
    )


class ChartInstructionTests(SimpleTestCase):
    def test_a_chart_type_is_told_to_send_its_data(self):
        from services.pool.model1 import _batch_instruction
        from services.pool.recipes import Batch, TypeQuota

        text = _batch_instruction(Batch("b", [TypeQuota("SHORT_ANSWER", 2, 2, type_code="GRAPH_READ")]))
        self.assertIn("`figure`", text)
        self.assertIn("overrides rule 7", text)
        self.assertIn('"showValues" to false', text)

    def test_a_chart_case_study_points_its_stimulus_at_the_figure(self):
        from services.pool.model1 import _batch_instruction
        from services.pool.recipes import Batch, TypeQuota

        text = _batch_instruction(
            Batch("b", [TypeQuota("CASE_STUDY", 4, 1, type_code="DATA_INTERPRETATION")])
        )
        self.assertIn("the chart's data in `figure`", text)


@mock.patch("services.pool.model1.render_chart", return_value=_RENDERED)
class ChartRenderingTests(SimpleTestCase):
    def _quota(self, type_code="GRAPH_READ", shape="SHORT_ANSWER", marks=2):
        from services.pool.recipes import TypeQuota

        return TypeQuota(shape, marks, 1, type_code=type_code)

    def test_the_figure_is_drawn_from_the_model_data(self, render):
        questions, invalid = _normalise([_graph_read()], self._quota())
        self.assertEqual(invalid, 0)
        self.assertEqual(questions[0].image, "/media/question_figures/abc.svg")
        drawn = render.call_args.kwargs["spec"]
        self.assertEqual([datum.value for datum in drawn.series], [45, 70, 30])
        self.assertFalse(drawn.show_values)

    def test_a_url_from_the_model_is_never_used(self, render):
        questions, _ = _normalise(
            [_graph_read(image="https://example.com/invented.png")], self._quota()
        )
        self.assertEqual(questions[0].image, "/media/question_figures/abc.svg")

    def test_data_that_will_not_draw_drops_the_question(self, render):
        broken = {**_BAR, "series": [{"label": "School A", "value": 45}]}
        questions, invalid = _normalise([_graph_read(figure=broken)], self._quota())
        self.assertEqual((questions, invalid), ([], 1))
        render.assert_not_called()

    def test_a_chart_question_without_data_is_dropped(self, render):
        questions, invalid = _normalise([_graph_read(figure=None)], self._quota())
        self.assertEqual((questions, invalid), ([], 1))

    def test_other_types_ignore_a_figure(self, render):
        questions, invalid = _normalise(
            [_graph_read(type="SHORT_ANSWER")], self._quota(type_code="")
        )
        self.assertEqual(invalid, 0)
        self.assertIsNone(questions[0].image)
        render.assert_not_called()

    def test_a_chart_case_study_needs_no_printed_stimulus(self, render):
        raw = {
            "type": "CASE_STUDY",
            "marks": 4,
            "question": "Study the bar graph and answer the questions.",
            "figure": _BAR,
            "parts": [
                {"question": "Which school planted the most trees?", "marks": 1, "answer": "School B"},
                {"question": "How many more did School B plant than School C?", "marks": 1, "answer": "40"},
                {"question": "Find the average number of trees planted.", "marks": 2, "answer": "48.3"},
            ],
        }
        questions, invalid = _normalise(
            [raw], self._quota(type_code="DATA_INTERPRETATION", shape="CASE_STUDY", marks=4)
        )
        self.assertEqual(invalid, 0)
        self.assertEqual(questions[0].image, "/media/question_figures/abc.svg")
        self.assertEqual(len(questions[0].metadata["composite"]["subQuestions"]), 3)
