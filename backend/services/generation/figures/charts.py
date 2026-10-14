"""Six chart renderers. Each turns a validated `ChartSpec` into an SVG string.

Every number a chart draws comes from the spec and nothing else. There is no
model in this file, no randomness, and no I/O — the same spec renders the same
bytes on every machine forever, which is what makes the cache key in
`figures.__init__` safe and what makes the tests assertions rather than
eyeballing.

## Layout is computed, not guessed

Margins are derived from the text that has to fit in them (`svg.text_width`),
because the alternative — a fixed 40px gutter — clips a y-axis labelled in
thousands and wastes half the plot on one labelled 0-5. The plot area is
whatever is left. That is the whole layout system.

## What is deliberately absent

No titles, no captions, no figure numbers, no source lines. A figure sits
inside a question that already says what it is, and a chart captioned
"Fig. 3: Modes of transport" on a printed paper is answering half the question
it was drawn to ask.
"""

from __future__ import annotations

import math
from typing import Callable, List, Sequence, Tuple

from .spec import (
    CHART_BAR,
    CHART_COORDINATE_GRID,
    CHART_HISTOGRAM,
    CHART_LINE,
    CHART_NUMBER_LINE,
    CHART_PIE,
    ChartSpec,
    SpecError,
)
from .svg import (
    BAR_FILL,
    FONT_AXIS_TITLE,
    FONT_LABEL,
    FONT_TICK,
    GRID_INK,
    INK,
    PAPER,
    STROKE_AXIS,
    STROKE_GRID,
    STROKE_SHAPE,
    Canvas,
    fill_for,
    fmt,
    nice_ticks,
    text_width,
    tick_values,
)

#: The drawing is authored at this size and scaled by the editor (340px in the
#: half-width slot, 660px full). Authoring larger than the smallest display
#: size keeps text from being the thing that decides the layout.
WIDTH = 520.0
HEIGHT = 380.0

PAD_TOP = 20.0
PAD_RIGHT = 24.0
PAD_LEFT = 12.0
PAD_BOTTOM = 12.0

#: Past this, rotate the category labels instead of letting them collide.
ROTATE_DEGREES = -35.0
MAX_BOTTOM_MARGIN = 132.0


def render(spec: ChartSpec) -> str:
    """Draw `spec`. The only entry point; `chart` has already been validated."""
    renderer = {
        CHART_PIE: _render_pie,
        CHART_BAR: _render_bar,
        CHART_HISTOGRAM: _render_histogram,
        CHART_LINE: _render_line,
        CHART_NUMBER_LINE: _render_number_line,
        CHART_COORDINATE_GRID: _render_coordinate_grid,
    }.get(spec.chart)
    if renderer is None:  # pragma: no cover - parse_chart_spec rejects these
        raise SpecError(f"no renderer for {spec.chart!r}")
    return renderer(spec)


# ── Shared cartesian frame ────────────────────────────────────────────────


class _Frame:
    """The plot rectangle and the two functions that map data into it."""

    def __init__(
        self,
        canvas: Canvas,
        left: float,
        top: float,
        right: float,
        bottom: float,
        y_start: float,
        y_end: float,
    ) -> None:
        self.canvas = canvas
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom
        self.y_start = y_start
        self.y_end = y_end

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top

    def y(self, value: float) -> float:
        span = self.y_end - self.y_start
        if span <= 0:
            return self.bottom
        return self.bottom - (value - self.y_start) / span * self.height


def _value_axis_bounds(
    values: Sequence[float], y_max: float | None, *, from_zero: bool
) -> Tuple[float, float, float]:
    """Round bounds and a round step for the value axis.

    `from_zero` is the CBSE convention for bars and histograms: a bar chart
    whose axis starts at 40 exaggerates every difference on it, which is a
    misleading figure rather than a compact one.
    """
    if not values:
        return (0.0, 1.0, 1.0)
    low = min(0.0, min(values)) if from_zero else min(values)
    high = max(values)
    if y_max is not None and y_max > high:
        high = y_max
    start, end, step = nice_ticks(low, high)
    if y_max is not None:
        # An explicit ceiling from the question ("scale: 1 cm = 10 students")
        # wins over the tick chooser, but the step still has to divide it
        # evenly or the top gridline lands off the frame.
        end = max(y_max, start + step)
    return (start, end, step)


def _build_frame(
    canvas: Canvas,
    *,
    y_start: float,
    y_end: float,
    y_step: float,
    x_tick_labels: Sequence[str],
    x_title: str,
    y_title: str,
    width: float = WIDTH,
    height: float = HEIGHT,
    draw_x_ticks: bool = True,
) -> Tuple[_Frame, bool]:
    """Draw axes, gridlines and tick labels; return the frame and whether the
    category labels ended up rotated (callers place value labels differently
    when they did)."""
    tick_labels = [fmt(v) for v in tick_values(y_start, y_end, y_step)]
    y_tick_room = max((text_width(t, FONT_TICK) for t in tick_labels), default=0.0)

    left = PAD_LEFT + y_tick_room + 8.0 + (FONT_AXIS_TITLE + 8.0 if y_title else 0.0)
    right = width - PAD_RIGHT
    top = PAD_TOP

    slot = (right - left) / max(1, len(x_tick_labels))
    widest_x = max((text_width(t, FONT_TICK) for t in x_tick_labels), default=0.0)
    rotated = bool(x_tick_labels) and widest_x > slot * 0.95

    if rotated:
        label_room = min(widest_x * math.sin(math.radians(abs(ROTATE_DEGREES))), 84.0)
    else:
        label_room = FONT_TICK + 2.0

    bottom_margin = min(
        MAX_BOTTOM_MARGIN,
        PAD_BOTTOM + label_room + 10.0 + (FONT_AXIS_TITLE + 8.0 if x_title else 0.0),
    )
    bottom = height - bottom_margin

    frame = _Frame(canvas, left, top, right, bottom, y_start, y_end)

    # Gridlines first so every shape drawn later sits on top of them.
    for value in tick_values(y_start, y_end, y_step):
        y = frame.y(value)
        if value != y_start:
            canvas.line(left, y, right, y, stroke=GRID_INK, width=STROKE_GRID)
        canvas.text(
            left - 6.0, y + FONT_TICK * 0.35, fmt(value), size=FONT_TICK, anchor="end"
        )

    canvas.line(left, top, left, bottom, stroke=INK, width=STROKE_AXIS)
    canvas.line(left, bottom, right, bottom, stroke=INK, width=STROKE_AXIS)

    if draw_x_ticks:
        for index, label in enumerate(x_tick_labels):
            centre = left + slot * (index + 0.5)
            if rotated:
                canvas.text(
                    centre,
                    bottom + 14.0,
                    label,
                    size=FONT_TICK,
                    anchor="end",
                    rotate=ROTATE_DEGREES,
                )
            else:
                canvas.text(centre, bottom + FONT_TICK + 5.0, label, size=FONT_TICK)

    if x_title:
        canvas.text(
            (left + right) / 2.0,
            height - PAD_BOTTOM - 2.0,
            x_title,
            size=FONT_AXIS_TITLE,
            weight="bold",
        )
    if y_title:
        canvas.text(
            PAD_LEFT + FONT_AXIS_TITLE * 0.4,
            (top + bottom) / 2.0,
            y_title,
            size=FONT_AXIS_TITLE,
            weight="bold",
            rotate=-90.0,
        )

    return frame, rotated


# ── Pie ───────────────────────────────────────────────────────────────────

PIE_RADIUS = 108.0
LEGEND_ROW = 19.0


def _render_pie(spec: ChartSpec) -> str:
    """Wedges clockwise from twelve o'clock, which is how every Indian
    textbook draws one, with a legend underneath.

    Category names go in the legend rather than inside the wedges: a small
    wedge cannot hold "Public transport", and a leader line to a label outside
    the circle is the thing that makes a printed pie chart unreadable at 340px.
    """
    total = sum(d.value for d in spec.series)
    width = 460.0
    widest_label = max(text_width(d.label, FONT_TICK) for d in spec.series)
    legend_columns = (
        2
        if len(spec.series) > 1
        and (17.0 + widest_label + 22.0) * 2 <= width - 2 * PAD_LEFT
        else 1
    )
    legend_rows = (len(spec.series) + legend_columns - 1) // legend_columns
    height = PAD_TOP + PIE_RADIUS * 2 + 24.0 + legend_rows * LEGEND_ROW + 14.0

    canvas = Canvas(width, height)
    cx = width / 2.0
    cy = PAD_TOP + PIE_RADIUS

    angle = -90.0  # twelve o'clock
    for index, datum in enumerate(spec.series):
        sweep = 360.0 * (datum.value / total) if total else 0.0
        end = angle + sweep

        if sweep >= 359.999:
            # A single-category pie is a circle; an arc path from a point back
            # to the same point draws nothing at all.
            canvas.circle(
                cx, cy, PIE_RADIUS, fill=fill_for(index), stroke=INK,
                stroke_width=STROKE_SHAPE,
            )
        else:
            x1 = cx + PIE_RADIUS * math.cos(math.radians(angle))
            y1 = cy + PIE_RADIUS * math.sin(math.radians(angle))
            x2 = cx + PIE_RADIUS * math.cos(math.radians(end))
            y2 = cy + PIE_RADIUS * math.sin(math.radians(end))
            large_arc = 1 if sweep > 180.0 else 0
            canvas.path(
                f"M {fmt(cx)} {fmt(cy)} L {fmt(x1)} {fmt(y1)} "
                f"A {fmt(PIE_RADIUS)} {fmt(PIE_RADIUS)} 0 {large_arc} 1 "
                f"{fmt(x2)} {fmt(y2)} Z",
                fill=fill_for(index),
                stroke=INK,
                stroke_width=STROKE_SHAPE,
            )

        # The value inside the wedge, only when the question hands the reader
        # those numbers anyway, and only when the wedge can hold the text.
        if spec.show_values and sweep >= 22.0:
            mid = math.radians(angle + sweep / 2.0)
            label_r = PIE_RADIUS * 0.62
            canvas.text(
                cx + label_r * math.cos(mid),
                cy + label_r * math.sin(mid) + FONT_LABEL * 0.35,
                fmt(datum.value),
                size=FONT_LABEL,
            )
        angle = end

    # The legend is sized to its longest label and centred, not stretched
    # across the canvas: two short categories split into fixed half-width
    # columns leave a gap wide enough to read as two separate legends.
    item_width = 17.0 + widest_label + 22.0
    columns = legend_columns
    block_left = max(PAD_LEFT, (width - item_width * columns) / 2.0)
    legend_top = PAD_TOP + PIE_RADIUS * 2 + 26.0

    for index, datum in enumerate(spec.series):
        x = block_left + (index % columns) * item_width
        y = legend_top + (index // columns) * LEGEND_ROW
        canvas.rect(x, y - 8.0, 11.0, 11.0, fill=fill_for(index), stroke=INK,
                    stroke_width=0.9)
        canvas.text(
            x + 17.0, y + 1.0, datum.label, size=FONT_TICK, anchor="start"
        )
    return canvas.render()


# ── Bar ───────────────────────────────────────────────────────────────────


def _render_bar(spec: ChartSpec) -> str:
    values = [d.value for d in spec.series]
    y_start, y_end, y_step = _value_axis_bounds(values, spec.y_max, from_zero=True)

    canvas = Canvas(WIDTH, HEIGHT)
    frame, rotated = _build_frame(
        canvas,
        y_start=y_start,
        y_end=y_end,
        y_step=y_step,
        x_tick_labels=[d.label for d in spec.series],
        x_title=spec.x_label,
        y_title=spec.y_label,
    )

    slot = frame.width / len(spec.series)
    bar_width = slot * 0.58
    for index, datum in enumerate(spec.series):
        centre = frame.left + slot * (index + 0.5)
        top = frame.y(datum.value)
        canvas.rect(
            centre - bar_width / 2.0,
            top,
            bar_width,
            frame.bottom - top,
            fill=BAR_FILL,
            stroke=INK,
        )
        if spec.show_values:
            canvas.text(centre, top - 5.0, fmt(datum.value), size=FONT_TICK)
    return canvas.render()


# ── Histogram ─────────────────────────────────────────────────────────────


def _render_histogram(spec: ChartSpec) -> str:
    """Contiguous bars on a continuous x axis.

    The difference from a bar chart is not cosmetic: a histogram's x axis is a
    number line, bars touch, and the tick marks sit on the class boundaries
    rather than under the bar centres. A bar chart drawn with gaps in place of
    a histogram is a different claim about the data.
    """
    values = [b.value for b in spec.bins]
    y_start, y_end, y_step = _value_axis_bounds(values, spec.y_max, from_zero=True)

    x_low = spec.bins[0].lower
    x_high = spec.bins[-1].upper

    canvas = Canvas(WIDTH, HEIGHT)
    boundaries = [b.lower for b in spec.bins] + [spec.bins[-1].upper]
    frame, _rotated = _build_frame(
        canvas,
        y_start=y_start,
        y_end=y_end,
        y_step=y_step,
        x_tick_labels=[fmt(b) for b in boundaries],
        x_title=spec.x_label,
        y_title=spec.y_label,
        draw_x_ticks=False,
    )

    def x_at(value: float) -> float:
        span = x_high - x_low
        if span <= 0:
            return frame.left
        return frame.left + (value - x_low) / span * frame.width

    for entry in spec.bins:
        left = x_at(entry.lower)
        right = x_at(entry.upper)
        top = frame.y(entry.value)
        canvas.rect(
            left, top, right - left, frame.bottom - top,
            fill=BAR_FILL, stroke=INK,
        )
        if spec.show_values:
            canvas.text((left + right) / 2.0, top - 5.0, fmt(entry.value),
                        size=FONT_TICK)

    for boundary in boundaries:
        x = x_at(boundary)
        canvas.line(x, frame.bottom, x, frame.bottom + 4.0, stroke=INK,
                    width=STROKE_AXIS)
        canvas.text(x, frame.bottom + FONT_TICK + 7.0, fmt(boundary),
                    size=FONT_TICK)
    return canvas.render()


# ── Line (and ogive) ──────────────────────────────────────────────────────


def _render_line(spec: ChartSpec) -> str:
    """Points joined in the order given, with a marker on each.

    This is also the ogive renderer: a cumulative frequency curve is a line
    graph whose x values are class boundaries and whose y values accumulate,
    and giving it its own renderer would duplicate this one to change nothing.
    """
    values = [d.value for d in spec.series]
    y_start, y_end, y_step = _value_axis_bounds(
        values, spec.y_max, from_zero=min(values) >= 0
    )

    canvas = Canvas(WIDTH, HEIGHT)
    frame, _rotated = _build_frame(
        canvas,
        y_start=y_start,
        y_end=y_end,
        y_step=y_step,
        x_tick_labels=[d.label for d in spec.series],
        x_title=spec.x_label,
        y_title=spec.y_label,
    )

    slot = frame.width / len(spec.series)
    coords: List[Tuple[float, float]] = [
        (frame.left + slot * (index + 0.5), frame.y(datum.value))
        for index, datum in enumerate(spec.series)
    ]
    canvas.polyline(coords, stroke=INK, stroke_width=1.6)
    for (x, y), datum in zip(coords, spec.series):
        canvas.circle(x, y, 3.2, fill=INK, stroke=INK, stroke_width=0.8)
        if spec.show_values:
            canvas.text(x, y - 9.0, fmt(datum.value), size=FONT_TICK)
    return canvas.render()


# ── Number line ───────────────────────────────────────────────────────────


def _render_number_line(spec: ChartSpec) -> str:
    """A ruled axis with the marked positions dotted on it.

    `series` here is positions, not magnitudes: `value` is where on the axis
    the mark sits and `label` is what to print above it, which is why a
    fraction question can mark 3/4 and print "3/4" rather than "0.75".
    """
    positions = [d.value for d in spec.series]
    low = spec.axis_min if spec.axis_min is not None else min(positions)
    high = spec.axis_max if spec.axis_max is not None else max(positions)
    if high <= low:
        high = low + 1.0
    # A mark sitting exactly on the end of the rule reads as running off it.
    pad = (high - low) * 0.12
    low -= pad
    high += pad

    if spec.axis_step and spec.axis_step > 0:
        start, end, step = (
            math.floor(low / spec.axis_step) * spec.axis_step,
            math.ceil(high / spec.axis_step) * spec.axis_step,
            spec.axis_step,
        )
    else:
        start, end, step = nice_ticks(low, high, target=8)

    width = WIDTH
    height = 140.0
    canvas = Canvas(width, height)

    left = PAD_LEFT + 26.0
    right = width - PAD_LEFT - 26.0
    axis_y = 86.0

    def x_at(value: float) -> float:
        span = end - start
        if span <= 0:
            return left
        return left + (value - start) / span * (right - left)

    canvas.line(left - 18.0, axis_y, right + 18.0, axis_y, stroke=INK,
                width=STROKE_AXIS)
    # Arrowheads: the line continues in both directions, which is the whole
    # point of a number line.
    for tip, direction in ((left - 18.0, -1.0), (right + 18.0, 1.0)):
        canvas.path(
            f"M {fmt(tip)} {fmt(axis_y)} L {fmt(tip - direction * 9.0)} "
            f"{fmt(axis_y - 4.5)} L {fmt(tip - direction * 9.0)} "
            f"{fmt(axis_y + 4.5)} Z",
            fill=INK,
            stroke=INK,
            stroke_width=0.8,
        )

    for value in tick_values(start, end, step):
        x = x_at(value)
        canvas.line(x, axis_y - 5.0, x, axis_y + 5.0, stroke=INK,
                    width=STROKE_SHAPE)
        canvas.text(x, axis_y + FONT_TICK + 10.0, fmt(value), size=FONT_TICK)

    for datum in spec.series:
        x = x_at(datum.value)
        canvas.circle(x, axis_y, 4.4, fill=INK, stroke=INK, stroke_width=0.8)
        canvas.text(x, axis_y - 14.0, datum.label, size=FONT_LABEL, weight="bold")

    if spec.x_label:
        canvas.text((left + right) / 2.0, height - 8.0, spec.x_label,
                    size=FONT_AXIS_TITLE, weight="bold")
    return canvas.render()


# ── Coordinate grid ───────────────────────────────────────────────────────


def _render_coordinate_grid(spec: ChartSpec) -> str:
    """Squared paper with the axes through the origin.

    Square on purpose: one unit on x must be one unit on y, or a question that
    asks for the distance between two plotted points has a figure that
    contradicts its own answer.
    """
    xs = [p.x for p in spec.points]
    ys = [p.y for p in spec.points]

    low = spec.axis_min if spec.axis_min is not None else min(xs + ys + [0.0])
    high = spec.axis_max if spec.axis_max is not None else max(xs + ys + [0.0])
    span = max(abs(low), abs(high), 1.0)
    limit = math.ceil(span + 1.0)
    step = 1.0 if limit <= 12 else math.ceil(limit / 10.0)

    size = 420.0
    canvas = Canvas(size, size)
    left, top = 26.0, 18.0
    right, bottom = size - 18.0, size - 26.0
    plot = min(right - left, bottom - top)
    right = left + plot
    bottom = top + plot

    def x_at(value: float) -> float:
        return left + (value + limit) / (2.0 * limit) * plot

    def y_at(value: float) -> float:
        return bottom - (value + limit) / (2.0 * limit) * plot

    value = -limit
    while value <= limit + 1e-9:
        canvas.line(x_at(value), top, x_at(value), bottom, stroke=GRID_INK,
                    width=STROKE_GRID)
        canvas.line(left, y_at(value), right, y_at(value), stroke=GRID_INK,
                    width=STROKE_GRID)
        value += step

    zero_x, zero_y = x_at(0.0), y_at(0.0)
    canvas.line(left, zero_y, right, zero_y, stroke=INK, width=STROKE_AXIS)
    canvas.line(zero_x, top, zero_x, bottom, stroke=INK, width=STROKE_AXIS)

    value = -limit
    while value <= limit + 1e-9:
        if abs(value) > 1e-9:
            canvas.text(x_at(value), zero_y + FONT_TICK + 5.0, fmt(value),
                        size=FONT_TICK)
            canvas.text(zero_x - 6.0, y_at(value) + FONT_TICK * 0.35, fmt(value),
                        size=FONT_TICK, anchor="end")
        value += step
    canvas.text(zero_x - 6.0, zero_y + FONT_TICK + 5.0, "O", size=FONT_TICK,
                anchor="end")

    canvas.text(right - 4.0, zero_y - 7.0, spec.x_label or "X", size=FONT_AXIS_TITLE,
                anchor="end", weight="bold")
    canvas.text(zero_x + 8.0, top + FONT_AXIS_TITLE, spec.y_label or "Y",
                size=FONT_AXIS_TITLE, anchor="start", weight="bold")

    for point in spec.points:
        px, py = x_at(point.x), y_at(point.y)
        canvas.circle(px, py, 3.6, fill=INK, stroke=INK, stroke_width=0.8)
        if point.label:
            canvas.text(px + 7.0, py - 7.0, point.label, size=FONT_LABEL,
                        anchor="start")
    return canvas.render()
