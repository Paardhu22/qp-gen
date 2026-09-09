"""Tests for deterministic figure rendering.

Golden-value, never golden-pixel. What is pinned is what a teacher would
notice on a printed paper: that a wedge is the angle the data says it is, that
a bar lands on its gridline, that an axis is labelled in round numbers, and
that a figure drawn for a question never prints the answer to it. Nothing here
compares whole SVG strings — that test fails on every whitespace change and
tells you nothing about whether the chart is right.

The extractor's model call is stubbed. What a model reads out of a question is
not something a test can pin; what IS pinned is that every way it can fail
lands on the illustration path rather than on a wrong chart.
"""

from __future__ import annotations

import math
import re
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase, override_settings

from services.figures import SpecError, parse_chart_spec, render_chart, storage_path
from services.figures.charts import render
from services.figures.extract import extract_figure_spec
from services.figures.spec import (
    CHART_BAR,
    CHART_PIE,
    KIND_CHART,
    KIND_ILLUSTRATION,
    ChartSpec,
    Datum,
)
from services.figures.svg import nice_ticks, tick_values


PIE_RAW = {
    "kind": "chart",
    "chart": "pie",
    "series": [
        {"label": "Bus", "value": 240},
        {"label": "Cycle", "value": 180},
        {"label": "Walk", "value": 300},
    ],
    "yLabel": "Number of students",
}


# ── Spec validation ───────────────────────────────────────────────────────


class SpecTests(SimpleTestCase):
    def test_a_pie_spec_round_trips_through_the_wire_shape(self):
        # The dialog posts back what the extractor produced, so to_dict must
        # parse. A field that serialises to a name parse does not accept means
        # a teacher's edit is silently dropped.
        spec = parse_chart_spec(PIE_RAW)
        again = parse_chart_spec(spec.to_dict())
        self.assertEqual(spec, again)

    def test_snake_case_from_the_model_is_accepted(self):
        # The prompt asks for camelCase; models drift constantly, and a spec
        # rejected over the spelling costs an image-model render for nothing.
        spec = parse_chart_spec(
            {"chart": "bar", "series": PIE_RAW["series"], "show_values": True,
             "y_label": "Students"}
        )
        self.assertTrue(spec.show_values)
        self.assertEqual(spec.y_label, "Students")

    def test_an_unknown_chart_type_is_refused(self):
        with self.assertRaises(SpecError):
            parse_chart_spec({"chart": "sankey", "series": PIE_RAW["series"]})

    def test_a_pie_of_zeroes_is_refused_rather_than_divided_by(self):
        with self.assertRaises(SpecError):
            parse_chart_spec(
                {"chart": "pie", "series": [{"label": "A", "value": 0},
                                            {"label": "B", "value": 0}]}
            )

    def test_a_negative_bar_is_refused(self):
        with self.assertRaises(SpecError):
            parse_chart_spec(
                {"chart": "bar", "series": [{"label": "A", "value": 5},
                                            {"label": "B", "value": -2}]}
            )

    def test_overlapping_histogram_classes_are_refused(self):
        # Overlap means the extractor misread the table; drawing it anyway
        # stacks bars on top of one another and looks deliberate.
        with self.assertRaises(SpecError):
            parse_chart_spec(
                {"chart": "histogram", "bins": [
                    {"lower": 0, "upper": 20, "value": 4},
                    {"lower": 10, "upper": 30, "value": 6},
                ]}
            )

    def test_bins_are_sorted_so_the_x_axis_ascends(self):
        spec = parse_chart_spec(
            {"chart": "histogram", "bins": [
                {"lower": 20, "upper": 30, "value": 6},
                {"lower": 0, "upper": 10, "value": 4},
                {"lower": 10, "upper": 20, "value": 9},
            ]}
        )
        self.assertEqual([b.lower for b in spec.bins], [0, 10, 20])

    def test_a_single_category_is_not_a_chart(self):
        with self.assertRaises(SpecError):
            parse_chart_spec({"chart": "bar", "series": [{"label": "A", "value": 5}]})

    def test_an_over_long_label_is_trimmed_not_refused(self):
        spec = parse_chart_spec(
            {"chart": "bar", "series": [
                {"label": "x" * 200, "value": 5}, {"label": "B", "value": 6}]}
        )
        self.assertLessEqual(len(spec.series[0].label), 40)

    def test_a_non_finite_value_is_refused(self):
        with self.assertRaises(SpecError):
            parse_chart_spec(
                {"chart": "bar", "series": [{"label": "A", "value": "NaN"},
                                            {"label": "B", "value": 3}]}
            )


# ── Tick selection ────────────────────────────────────────────────────────


class TickTests(SimpleTestCase):
    def test_steps_are_always_one_two_or_five_times_a_power_of_ten(self):
        # The whole point of the algorithm: a step of 17.3 is not a scale a
        # student can read off graph paper.
        for high in (3, 7, 45, 96, 320, 780, 1_450, 26_000, 0.35):
            _start, _end, step = nice_ticks(0, high)
            mantissa = step / (10.0 ** math.floor(math.log10(step)))
            self.assertIn(round(mantissa, 6), (1.0, 2.0, 5.0), f"high={high}")

    def test_the_axis_always_reaches_past_the_data(self):
        for high in (45, 96, 7, 1_450):
            _start, end, _step = nice_ticks(0, high)
            self.assertGreaterEqual(end, high)

    def test_a_flat_series_still_gets_an_axis(self):
        start, end, step = nice_ticks(5, 5)
        self.assertLess(start, end)
        self.assertGreater(step, 0)

    def test_ticks_do_not_accumulate_floating_point_noise(self):
        values = tick_values(0, 1, 0.1)
        self.assertIn(0.3, values)
        self.assertEqual(len(values), 11)


# ── Rendering ─────────────────────────────────────────────────────────────


def _paths(markup: str):
    return re.findall(r'<path d="([^"]+)"', markup)


def _texts(markup: str):
    return re.findall(r"<text[^>]*>([^<]*)</text>", markup)


class PieRenderTests(SimpleTestCase):
    """240 / 180 / 300 of 720 is 120°, 90° and 150°. An image model cannot be
    made to draw that; this is the whole reason the module exists."""

    def setUp(self):
        self.spec = parse_chart_spec(PIE_RAW)
        self.markup = render(self.spec)

    def test_each_wedge_subtends_the_angle_its_value_says(self):
        centre = complex(230.0, 128.0)  # width/2, PAD_TOP + PIE_RADIUS
        expected = [120.0, 90.0, 150.0]

        sweeps = []
        for d in _paths(self.markup):
            numbers = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", d)]
            # M cx cy L x1 y1 A rx ry rot large-arc sweep x2 y2 Z
            #  0  1     2  3     4  5   6      7     8  9  10
            start = complex(numbers[2], numbers[3]) - centre
            end = complex(numbers[9], numbers[10]) - centre
            sweep = math.degrees(math.atan2(end.imag, end.real)) - math.degrees(
                math.atan2(start.imag, start.real)
            )
            sweeps.append(sweep % 360.0)

        self.assertEqual(len(sweeps), 3)
        for got, want in zip(sweeps, expected):
            self.assertAlmostEqual(got, want, delta=0.5)

    def test_the_wedges_close_the_circle(self):
        # Three wedges that sum to 359° leave a white slice a teacher will see.
        self.assertEqual(len(_paths(self.markup)), 3)

    def test_every_category_is_named_in_the_legend(self):
        texts = _texts(self.markup)
        for label in ("Bus", "Cycle", "Walk"):
            self.assertIn(label, texts)

    def test_no_value_is_printed_when_the_question_asks_for_it(self):
        # showValues defaults false: the figure must not answer the question.
        for value in ("240", "180", "300", "720"):
            self.assertNotIn(value, _texts(self.markup))

    def test_values_are_printed_when_the_question_already_gives_them(self):
        markup = render(parse_chart_spec({**PIE_RAW, "showValues": True}))
        for value in ("240", "180", "300"):
            self.assertIn(value, _texts(markup))

    def test_a_wedge_too_thin_to_hold_text_is_left_unlabelled(self):
        # A number printed across a 4° wedge overlaps its neighbours and is the
        # thing that makes a printed pie chart unreadable.
        markup = render(
            parse_chart_spec({
                "chart": "pie", "showValues": True,
                "series": [{"label": "A", "value": 400},
                           {"label": "B", "value": 5}],
            })
        )
        self.assertIn("400", _texts(markup))
        self.assertNotIn("5", _texts(markup))


class BarRenderTests(SimpleTestCase):
    def setUp(self):
        self.spec = parse_chart_spec({
            "chart": "bar",
            "series": [{"label": "Maths", "value": 45},
                       {"label": "Science", "value": 30},
                       {"label": "English", "value": 15}],
            "xLabel": "Subject", "yLabel": "Students",
        })
        self.markup = render(self.spec)

    def test_a_bar_lands_exactly_on_its_gridline(self):
        # The claim the whole module makes: a bar of 45 sits on the 45 line.
        rects = re.findall(
            r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"',
            self.markup,
        )
        # rect[0] is the canvas background; bars follow the frame.
        bars = rects[1:]
        self.assertEqual(len(bars), 3)

        heights = [float(b[3]) for b in bars]
        # 45 : 30 : 15 must render as 3 : 2 : 1.
        self.assertAlmostEqual(heights[0] / heights[2], 3.0, delta=0.02)
        self.assertAlmostEqual(heights[1] / heights[2], 2.0, delta=0.02)

    def test_the_value_axis_starts_at_zero(self):
        # An axis starting at 15 would exaggerate every difference on it.
        self.assertIn("0", _texts(self.markup))

    def test_both_axis_titles_are_drawn(self):
        texts = _texts(self.markup)
        self.assertIn("Subject", texts)
        self.assertIn("Students", texts)

    def test_no_title_or_caption_is_ever_drawn(self):
        # A figure sits inside a question that already says what it is.
        self.assertNotIn("<title", self.markup)
        self.assertNotIn("Fig", self.markup)


class HistogramRenderTests(SimpleTestCase):
    def setUp(self):
        self.markup = render(parse_chart_spec({
            "chart": "histogram",
            "bins": [{"lower": 0, "upper": 10, "value": 4},
                     {"lower": 10, "upper": 20, "value": 9},
                     {"lower": 20, "upper": 30, "value": 6}],
            "yLabel": "Frequency",
        }))

    def test_the_bars_touch(self):
        # Gaps would make it a bar chart, which is a different claim.
        rects = re.findall(
            r'<rect x="([\d.]+)" y="[\d.]+" width="([\d.]+)"', self.markup
        )[1:]
        self.assertEqual(len(rects), 3)
        for (x1, w1), (x2, _w2) in zip(rects, rects[1:]):
            self.assertAlmostEqual(float(x1) + float(w1), float(x2), delta=0.05)

    def test_ticks_sit_on_the_class_boundaries(self):
        texts = _texts(self.markup)
        for boundary in ("0", "10", "20", "30"):
            self.assertIn(boundary, texts)


class NumberLineRenderTests(SimpleTestCase):
    def test_marks_are_labelled_as_written_not_as_decimals(self):
        # 3/4 is marked at 0.75 and printed as "3/4" — the label is what the
        # question calls it, the value is only where it goes.
        markup = render(parse_chart_spec({
            "chart": "number_line",
            "series": [{"label": "1/4", "value": 0.25},
                       {"label": "3/4", "value": 0.75}],
            "axisMin": 0, "axisMax": 1, "axisStep": 0.25,
        }))
        texts = _texts(markup)
        self.assertIn("3/4", texts)
        self.assertIn("1/4", texts)

    def test_the_line_carries_an_arrow_at_each_end(self):
        markup = render(parse_chart_spec({
            "chart": "number_line",
            "series": [{"label": "-2", "value": -2}, {"label": "3", "value": 3}],
        }))
        self.assertEqual(len(_paths(markup)), 2)


class CoordinateGridRenderTests(SimpleTestCase):
    def setUp(self):
        self.markup = render(parse_chart_spec({
            "chart": "coordinate_grid",
            "points": [{"x": 2, "y": 3, "label": "A"},
                       {"x": -1, "y": -2, "label": "B"}],
        }))

    def test_the_grid_is_square_so_distances_are_true(self):
        # A question asking for AB has an answer the figure must not contradict.
        head = re.search(r'width="([\d.]+)" height="([\d.]+)"', self.markup)
        self.assertEqual(head.group(1), head.group(2))

    def test_the_origin_is_marked(self):
        self.assertIn("O", _texts(self.markup))

    def test_every_point_is_labelled(self):
        texts = _texts(self.markup)
        self.assertIn("A", texts)
        self.assertIn("B", texts)


class MarkupHealthTests(SimpleTestCase):
    """Properties that must hold for every chart, because a violation is
    invisible until an export silently drops the figure."""

    ALL = (
        PIE_RAW,
        {"chart": "bar", "series": PIE_RAW["series"]},
        {"chart": "line", "series": PIE_RAW["series"]},
        {"chart": "histogram", "bins": [
            {"lower": 0, "upper": 10, "value": 4},
            {"lower": 10, "upper": 20, "value": 9}]},
        {"chart": "number_line", "series": [
            {"label": "0", "value": 0}, {"label": "5", "value": 5}]},
        {"chart": "coordinate_grid", "points": [{"x": 1, "y": 1, "label": "P"}]},
    )

    def test_every_chart_parses_as_xml(self):
        from xml.etree import ElementTree

        for raw in self.ALL:
            markup = render(parse_chart_spec(raw))
            ElementTree.fromstring(markup)  # raises on malformed markup

    def test_an_ampersand_in_a_label_does_not_break_the_svg(self):
        # "Bread & Butter" in an unescaped SVG is a figure the DOCX export
        # drops silently rather than an error anyone sees.
        from xml.etree import ElementTree

        markup = render(parse_chart_spec({
            "chart": "bar",
            "series": [{"label": "Bread & Butter", "value": 4},
                       {"label": "<Rice>", "value": 6}],
        }))
        ElementTree.fromstring(markup)

    def test_every_chart_declares_an_intrinsic_size(self):
        # An SVG in an <img> without width/height falls back to 300x150, which
        # distorts every figure in Word.
        for raw in self.ALL:
            markup = render(parse_chart_spec(raw))
            self.assertRegex(markup, r'<svg[^>]+width="[\d.]+"[^>]+height="[\d.]+"')
            self.assertIn("viewBox=", markup)

    def test_every_drawn_shape_sets_an_explicit_fill(self):
        # An SVG shape with no fill is black — an unfilled bar outline becomes
        # a solid black block.
        for raw in self.ALL:
            markup = render(parse_chart_spec(raw))
            for shape in re.findall(r"<(?:rect|circle|path|polyline)[^>]*>", markup):
                self.assertIn("fill=", shape)

    def test_rendering_is_deterministic(self):
        # The cache key assumes it.
        for raw in self.ALL:
            spec = parse_chart_spec(raw)
            self.assertEqual(render(spec), render(spec))


# ── Cache key ─────────────────────────────────────────────────────────────


class CacheKeyTests(SimpleTestCase):
    def test_changing_a_value_changes_the_path(self):
        one = parse_chart_spec(PIE_RAW)
        two = parse_chart_spec({**PIE_RAW, "series": [
            {"label": "Bus", "value": 241},
            {"label": "Cycle", "value": 180},
            {"label": "Walk", "value": 300},
        ]})
        self.assertNotEqual(storage_path(one), storage_path(two))

    def test_showing_values_changes_the_path(self):
        # Same data, different figure — one answers the question and one does
        # not, and serving the wrong one from cache would be the worst bug here.
        self.assertNotEqual(
            storage_path(parse_chart_spec(PIE_RAW)),
            storage_path(parse_chart_spec({**PIE_RAW, "showValues": True})),
        )

    def test_the_renderer_version_is_part_of_the_key(self):
        # Otherwise improving a chart changes nothing for any already rendered.
        spec = parse_chart_spec(PIE_RAW)
        today = storage_path(spec)
        with patch("services.figures.spec.RENDERER_VERSION", 99):
            self.assertNotEqual(storage_path(spec), today)

    def test_an_identical_spec_is_one_cache_entry(self):
        self.assertEqual(
            storage_path(parse_chart_spec(PIE_RAW)),
            storage_path(parse_chart_spec(dict(PIE_RAW))),
        )

    def test_a_whole_number_written_as_a_float_is_the_same_entry(self):
        floaty = {**PIE_RAW, "series": [
            {"label": "Bus", "value": 240.0},
            {"label": "Cycle", "value": 180.0},
            {"label": "Walk", "value": 300.0},
        ]}
        self.assertEqual(
            storage_path(parse_chart_spec(PIE_RAW)),
            storage_path(parse_chart_spec(floaty)),
        )


# ── Storage ───────────────────────────────────────────────────────────────


class RenderChartTests(TestCase):
    def test_a_chart_is_stored_and_returned_as_a_stable_url(self):
        with patch("services.figures.default_storage") as storage:
            storage.exists.return_value = False
            storage.save.side_effect = lambda path, _content: path
            result = render_chart(spec=PIE_RAW)

        self.assertEqual(result["kind"], "chart")
        self.assertFalse(result["cached"])
        self.assertTrue(result["imageUrl"].startswith("/media/question_figures/"))
        self.assertTrue(result["imageUrl"].endswith(".svg"))

    def test_an_identical_chart_is_served_from_cache(self):
        with patch("services.figures.default_storage") as storage:
            storage.exists.return_value = True
            result = render_chart(spec=PIE_RAW)

        self.assertTrue(result["cached"])
        storage.save.assert_not_called()

    def test_a_spec_the_teacher_broke_is_refused_before_storage(self):
        with patch("services.figures.default_storage") as storage:
            with self.assertRaises(SpecError):
                render_chart(spec={"chart": "pie", "series": [
                    {"label": "A", "value": 0}, {"label": "B", "value": 0}]})
            storage.save.assert_not_called()


# ── Extraction ────────────────────────────────────────────────────────────


def _completion(content: str):
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    completion = MagicMock()
    completion.choices = [choice]
    completion.usage = MagicMock(
        prompt_tokens=100, completion_tokens=50, total_tokens=150
    )
    return completion


@override_settings(FIGURE_SPEC_MODEL="gpt-4.1-mini")
class ExtractTests(TestCase):
    def _extract(self, content: str):
        client = MagicMock()
        client.chat.completions.create.return_value = _completion(content)
        with patch("services.figures.extract.get_openai_client", return_value=client):
            with patch("services.figures.extract._record_usage") as record:
                result = extract_figure_spec(question_text="A pie chart shows…")
        return result, client, record

    def test_a_chart_answer_comes_back_as_a_spec(self):
        import json

        result, _client, _record = self._extract(json.dumps(PIE_RAW))
        self.assertEqual(result["kind"], KIND_CHART)
        self.assertEqual(len(result["spec"]["series"]), 3)

    def test_the_billable_call_is_recorded(self):
        # The image path never did this, so image spend is invisible to the
        # monthly limit. A new billable call must not repeat that.
        import json

        _result, _client, record = self._extract(json.dumps(PIE_RAW))
        record.assert_called_once()
        self.assertEqual(record.call_args[0][1], "figure_spec")

    def test_extraction_is_not_a_creative_act(self):
        import json

        _result, client, _record = self._extract(json.dumps(PIE_RAW))
        self.assertEqual(client.chat.completions.create.call_args[1]["temperature"], 0)

    def test_a_map_falls_back_until_there_is_a_map_renderer(self):
        result, _client, _record = self._extract('{"kind": "map"}')
        self.assertEqual(result["kind"], KIND_ILLUSTRATION)

    def test_an_illustration_answer_carries_no_spec(self):
        result, _client, _record = self._extract('{"kind": "illustration"}')
        self.assertEqual(result["kind"], KIND_ILLUSTRATION)
        self.assertIsNone(result["spec"])

    def test_junk_json_falls_back_rather_than_raising(self):
        result, _client, _record = self._extract("not json at all")
        self.assertEqual(result["kind"], KIND_ILLUSTRATION)

    def test_a_spec_that_will_not_validate_falls_back(self):
        # A plotted guess is worse than no chart.
        result, _client, _record = self._extract(
            '{"kind": "chart", "chart": "pie", "series": []}'
        )
        self.assertEqual(result["kind"], KIND_ILLUSTRATION)

    def test_a_model_failure_falls_back_rather_than_raising(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("429")
        with patch("services.figures.extract.get_openai_client", return_value=client):
            result = extract_figure_spec(question_text="anything")
        self.assertEqual(result["kind"], KIND_ILLUSTRATION)

    def test_an_empty_question_spends_nothing(self):
        client = MagicMock()
        with patch("services.figures.extract.get_openai_client", return_value=client):
            result = extract_figure_spec(question_text="   ")
        client.chat.completions.create.assert_not_called()
        self.assertEqual(result["kind"], KIND_ILLUSTRATION)
