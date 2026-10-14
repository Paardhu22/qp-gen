"""What a figure IS, decided before anything draws it.

A chart is not a picture of a chart. It is a small set of numbers plus a
statement of how to plot them, and the only reason the old path produced
unusable pie charts is that this layer did not exist: the question text went
straight to an image model, which had to invent the values it was drawing.

Everything here is deliberately dumb data. `extract.py` fills it from a model
call, the dialog lets a teacher correct it, and `charts.py` turns it into
pixels — and none of those three can be reasoned about unless the thing passing
between them has one definition. Validation is strict and happens once, here,
on the way in: a renderer that has to defend itself against a missing `value`
is a renderer nobody can read.

## Exam safety lives in the data, not in a plea

`show_values` and the absence of any title/caption field are the whole of it.
The old prompt spent 40 lines asking an image model not to reveal the answer
(`question_image._EXAM_CONSTRAINTS`) and had no way to insist. Here, a pie
chart asking "what percentage travel by bus" is rendered from a spec whose
`show_values` is False, and the renderer has no code path that prints a
percentage. That is not a request; it is an absence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: Bumped whenever a renderer's output changes for the same spec. Part of the
#: cache key, so improving a chart invalidates every stored SVG that used the
#: old code — see `figures.storage_path`.
RENDERER_VERSION = 1

KIND_CHART = "chart"
KIND_MAP = "map"
KIND_ILLUSTRATION = "illustration"

CHART_PIE = "pie"
CHART_BAR = "bar"
CHART_HISTOGRAM = "histogram"
CHART_LINE = "line"
CHART_NUMBER_LINE = "number_line"
CHART_COORDINATE_GRID = "coordinate_grid"

#: Every chart this module can draw. An `extract` result naming anything else
#: is treated as "not a chart" and falls through to the image model, which is
#: the safe direction: a wrong illustration is a picture nobody uses, a wrong
#: chart is a question nobody can answer.
CHART_KINDS: Tuple[str, ...] = (
    CHART_PIE,
    CHART_BAR,
    CHART_HISTOGRAM,
    CHART_LINE,
    CHART_NUMBER_LINE,
    CHART_COORDINATE_GRID,
)

# Bounds. These are not arbitrary — they are what fits legibly in the 340px
# half-width slot the editor drops a figure into (`float-image.tsx:77`). A
# 30-wedge pie is not a chart, it is a colour wheel, and a teacher who wants
# one is better served by the failure than by an unreadable render.
MAX_SERIES = 12
MAX_BINS = 20
MAX_POINTS = 30
MAX_LABEL_CHARS = 40


class SpecError(ValueError):
    """The spec cannot be drawn. Message is for a log, not for a teacher."""


@dataclass(frozen=True)
class Datum:
    """One labelled value. Also carries number-line marks, where `value` is a
    position on the axis rather than a magnitude."""

    label: str
    value: float


@dataclass(frozen=True)
class Bin:
    """One histogram class interval, e.g. 10–20 with frequency 7.

    Boundaries are explicit rather than parsed out of a label like "10-20":
    the en-dash/hyphen/"to" variations a model produces are exactly the kind
    of string handling that fails silently on the one paper nobody checked.
    """

    lower: float
    upper: float
    value: float


@dataclass(frozen=True)
class Point:
    """One plotted coordinate. `label` is usually "A" or "P(2, 3)"."""

    x: float
    y: float
    label: str = ""


@dataclass(frozen=True)
class ChartSpec:
    """A complete, validated drawing instruction.

    One dataclass rather than a class per chart: the fields genuinely overlap
    (every chart has axis labels, most have a series), and six near-identical
    dataclasses would put the differences in the type system where nobody
    reads them instead of in `validate`, where the error messages are.
    """

    chart: str
    series: Tuple[Datum, ...] = ()
    bins: Tuple[Bin, ...] = ()
    points: Tuple[Point, ...] = ()
    x_label: str = ""
    y_label: str = ""
    #: Force the value axis to end here. None lets the tick chooser decide,
    #: which is right unless the question names a scale ("using a scale of
    #: 1 cm = 10 students").
    y_max: Optional[float] = None
    #: Print the number above each bar / inside each wedge. False by default:
    #: see the module docstring. The extractor sets it True only when the
    #: question hands the reader those numbers anyway.
    show_values: bool = False
    #: Number line and coordinate grid: the visible extent.
    axis_min: Optional[float] = None
    axis_max: Optional[float] = None
    axis_step: Optional[float] = None

    def cache_fingerprint(self) -> str:
        """Everything that changes the pixels, in a stable order."""
        parts: List[str] = [f"v{RENDERER_VERSION}", self.chart]
        parts += [f"s:{d.label}={_fmt(d.value)}" for d in self.series]
        parts += [f"b:{_fmt(b.lower)}-{_fmt(b.upper)}={_fmt(b.value)}" for b in self.bins]
        parts += [f"p:{_fmt(p.x)},{_fmt(p.y)},{p.label}" for p in self.points]
        parts += [
            f"x:{self.x_label}",
            f"y:{self.y_label}",
            f"ymax:{_fmt(self.y_max) if self.y_max is not None else '-'}",
            f"vals:{int(self.show_values)}",
            f"amin:{_fmt(self.axis_min) if self.axis_min is not None else '-'}",
            f"amax:{_fmt(self.axis_max) if self.axis_max is not None else '-'}",
            f"astep:{_fmt(self.axis_step) if self.axis_step is not None else '-'}",
        ]
        return "\n".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        """The wire shape. This is what the dialog edits and posts back, so it
        has to round-trip through `parse_chart_spec` unchanged."""
        out: Dict[str, Any] = {
            "kind": KIND_CHART,
            "chart": self.chart,
            "xLabel": self.x_label,
            "yLabel": self.y_label,
            "showValues": self.show_values,
        }
        if self.series:
            out["series"] = [{"label": d.label, "value": d.value} for d in self.series]
        if self.bins:
            out["bins"] = [
                {"lower": b.lower, "upper": b.upper, "value": b.value} for b in self.bins
            ]
        if self.points:
            out["points"] = [
                {"x": p.x, "y": p.y, "label": p.label} for p in self.points
            ]
        if self.y_max is not None:
            out["yMax"] = self.y_max
        if self.axis_min is not None:
            out["axisMin"] = self.axis_min
        if self.axis_max is not None:
            out["axisMax"] = self.axis_max
        if self.axis_step is not None:
            out["axisStep"] = self.axis_step
        return out


def _fmt(value: Optional[float]) -> str:
    """Render a number the way the cache key and the axis labels both want it:
    no trailing ".0" on whole numbers, so 45 and 45.0 are one cache entry and
    one tick label."""
    if value is None:
        return "-"
    if float(value).is_integer():
        return str(int(value))
    return f"{float(value):g}"


def _number(raw: Any, where: str) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise SpecError(f"{where}: {raw!r} is not a number")
    if math.isnan(value) or math.isinf(value):
        raise SpecError(f"{where}: {raw!r} is not finite")
    return value


def _label(raw: Any, where: str, *, required: bool = True) -> str:
    text = " ".join(str(raw or "").split())
    if not text and required:
        raise SpecError(f"{where}: label is empty")
    if len(text) > MAX_LABEL_CHARS:
        # Truncated rather than refused: an over-long category name is a
        # cosmetic problem, and refusing the whole chart over one would send a
        # perfectly good pie chart to the image model instead.
        text = text[: MAX_LABEL_CHARS - 1].rstrip() + "…"
    return text


def _accepts(raw: Dict[str, Any], *names: str) -> Any:
    """First present key of several spellings.

    The extractor is prompted in camelCase (it is the wire shape) but models
    drift to snake_case constantly, and a spec rejected over `show_values` vs
    `showValues` costs a teacher an image-model render for no reason.
    """
    for name in names:
        if name in raw and raw[name] is not None:
            return raw[name]
    return None


def parse_chart_spec(raw: Any) -> ChartSpec:
    """Validate a spec dict — from the model, or from the teacher's edits.

    Raises `SpecError` on anything it will not draw. Callers treat that as
    "this is not a chart" and fall back; nothing here should ever reach a
    teacher as a message, because "bins[2]: upper <= lower" is not actionable
    by the person who typed a question about rainfall.
    """
    if not isinstance(raw, dict):
        raise SpecError("spec is not an object")

    chart = str(_accepts(raw, "chart", "chartType", "chart_type") or "").strip().lower()
    if chart not in CHART_KINDS:
        raise SpecError(f"unknown chart type {chart!r}")

    series = _parse_series(_accepts(raw, "series", "data", "items"))
    bins = _parse_bins(_accepts(raw, "bins", "intervals", "classes"))
    points = _parse_points(_accepts(raw, "points", "coordinates"))

    spec = ChartSpec(
        chart=chart,
        series=series,
        bins=bins,
        points=points,
        x_label=_label(_accepts(raw, "xLabel", "x_label"), "xLabel", required=False),
        y_label=_label(_accepts(raw, "yLabel", "y_label"), "yLabel", required=False),
        y_max=_optional_number(_accepts(raw, "yMax", "y_max"), "yMax"),
        show_values=bool(_accepts(raw, "showValues", "show_values") or False),
        axis_min=_optional_number(_accepts(raw, "axisMin", "axis_min"), "axisMin"),
        axis_max=_optional_number(_accepts(raw, "axisMax", "axis_max"), "axisMax"),
        axis_step=_optional_number(_accepts(raw, "axisStep", "axis_step"), "axisStep"),
    )
    _validate_for_chart(spec)
    return spec


def _optional_number(raw: Any, where: str) -> Optional[float]:
    if raw is None or raw == "":
        return None
    return _number(raw, where)


def _parse_series(raw: Any) -> Tuple[Datum, ...]:
    if not raw:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise SpecError("series is not a list")
    if len(raw) > MAX_SERIES:
        raise SpecError(f"series has {len(raw)} entries; max {MAX_SERIES}")
    out: List[Datum] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise SpecError(f"series[{index}] is not an object")
        out.append(
            Datum(
                label=_label(
                    _accepts(entry, "label", "name", "category"), f"series[{index}]"
                ),
                value=_number(
                    _accepts(entry, "value", "frequency", "count", "y"),
                    f"series[{index}].value",
                ),
            )
        )
    return tuple(out)


def _parse_bins(raw: Any) -> Tuple[Bin, ...]:
    if not raw:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise SpecError("bins is not a list")
    if len(raw) > MAX_BINS:
        raise SpecError(f"bins has {len(raw)} entries; max {MAX_BINS}")
    out: List[Bin] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise SpecError(f"bins[{index}] is not an object")
        lower = _number(_accepts(entry, "lower", "from", "start"), f"bins[{index}].lower")
        upper = _number(_accepts(entry, "upper", "to", "end"), f"bins[{index}].upper")
        if upper <= lower:
            raise SpecError(f"bins[{index}]: upper {upper} is not above lower {lower}")
        out.append(
            Bin(
                lower=lower,
                upper=upper,
                value=_number(
                    _accepts(entry, "value", "frequency", "count"),
                    f"bins[{index}].value",
                ),
            )
        )
    ordered = sorted(out, key=lambda b: b.lower)
    # Contiguity is what makes a histogram a histogram. Overlapping classes
    # mean the extractor misread the table, and drawing them anyway produces
    # bars that silently sit on top of one another.
    for previous, current in zip(ordered, ordered[1:]):
        if current.lower < previous.upper:
            raise SpecError(
                f"bins overlap: {previous.lower}-{previous.upper} and "
                f"{current.lower}-{current.upper}"
            )
    return tuple(ordered)


def _parse_points(raw: Any) -> Tuple[Point, ...]:
    if not raw:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise SpecError("points is not a list")
    if len(raw) > MAX_POINTS:
        raise SpecError(f"points has {len(raw)} entries; max {MAX_POINTS}")
    out: List[Point] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise SpecError(f"points[{index}] is not an object")
        out.append(
            Point(
                x=_number(_accepts(entry, "x"), f"points[{index}].x"),
                y=_number(_accepts(entry, "y"), f"points[{index}].y"),
                label=_label(
                    _accepts(entry, "label", "name"), f"points[{index}]", required=False
                ),
            )
        )
    return tuple(out)


def _validate_for_chart(spec: ChartSpec) -> None:
    """Per-chart requirements, after the shared shape checks passed."""
    chart = spec.chart

    if chart in (CHART_PIE, CHART_BAR, CHART_LINE, CHART_NUMBER_LINE):
        if len(spec.series) < 2:
            raise SpecError(f"{chart} needs at least 2 series entries")

    if chart in (CHART_PIE, CHART_BAR):
        for datum in spec.series:
            if datum.value < 0:
                raise SpecError(
                    f"{chart}: {datum.label} is negative ({datum.value})"
                )

    if chart == CHART_PIE:
        total = sum(d.value for d in spec.series)
        if total <= 0:
            raise SpecError("pie: every value is zero")

    if chart == CHART_HISTOGRAM:
        if len(spec.bins) < 2:
            raise SpecError("histogram needs at least 2 bins")
        for entry in spec.bins:
            if entry.value < 0:
                raise SpecError(f"histogram: negative frequency {entry.value}")

    if chart == CHART_COORDINATE_GRID:
        if len(spec.points) < 1:
            raise SpecError("coordinate_grid needs at least 1 point")

    if chart == CHART_NUMBER_LINE:
        if spec.axis_min is not None and spec.axis_max is not None:
            if spec.axis_max <= spec.axis_min:
                raise SpecError("number_line: axisMax is not above axisMin")
