"""SVG primitives shared by every chart, and the tick algorithm matplotlib
would have given us for free.

Output is vector on purpose. A figure printed on an A4 paper is scaled by the
editor (340px in the half-width slot, 660px full) and again by the PDF
exporter, and a raster at any single resolution is wrong at one of those. It
also survives both export paths untouched: `export-docx.ts` rasterizes an SVG
at 2x for Word, `export-pdf.ts` inlines it as a data URL for html2canvas.

## Everything is black on white

Not a style preference — a constraint. These figures are photocopied onto
answer booklets in schools, so colour is spent only where it carries meaning
(distinguishing pie wedges), and then as a greyscale ramp that survives a
photocopier rather than hues that all come out the same grey.
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

# ── The look ──────────────────────────────────────────────────────────────
#
# One place, because a chart whose axis is 1px and whose bars are 1.4px reads
# as a mistake even when nobody can say why.

FONT_STACK = "Arial, Helvetica, sans-serif"
INK = "#000000"
PAPER = "#ffffff"

STROKE_AXIS = 1.4
STROKE_SHAPE = 1.2
STROKE_GRID = 0.6
GRID_INK = "#c8c8c8"

FONT_TICK = 11.0
FONT_LABEL = 12.0
FONT_AXIS_TITLE = 12.5

#: One fill for every bar in a single-series bar chart or histogram. Shading
#: the bars differently would imply the shade encodes something; it does not —
#: the category is already on the axis under each bar. Mid-light so the value
#: label above a tall bar stays readable and the outline still reads.
BAR_FILL = "#cfcfcf"

#: Greyscale ramp for PIE WEDGES ONLY, light to dark. A pie is the one chart
#: here whose parts are not separated by position, so the fill is doing real
#: work: it is what ties a wedge to its legend entry. Chosen so adjacent
#: entries stay distinguishable after a photocopy — a linear ramp does not,
#: because toner crushes the dark end.
FILL_RAMP: Tuple[str, ...] = (
    "#ffffff",
    "#d0d0d0",
    "#9a9a9a",
    "#666666",
    "#e8e8e8",
    "#b5b5b5",
    "#7f7f7f",
    "#4d4d4d",
    "#dcdcdc",
    "#a8a8a8",
    "#8c8c8c",
    "#5a5a5a",
)


def fill_for(index: int) -> str:
    return FILL_RAMP[index % len(FILL_RAMP)]


def escape(text: str) -> str:
    """XML-escape. Question text reaches labels, and an unescaped ampersand in
    "Bread & Butter" produces an SVG the browser refuses to parse — which in
    the DOCX path is a silently dropped figure, not an error."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def fmt(value: float) -> str:
    """Coordinate formatting: two decimals, no trailing zeros, no '-0'.

    Keeps the markup readable and the file small, and — because it is also
    used for tick labels — stops 0.30000000000000004 reaching a printed axis.
    """
    rounded = round(float(value), 2)
    if rounded == 0:
        rounded = 0.0
    if float(rounded).is_integer():
        return str(int(rounded))
    return f"{rounded:g}"


def text_width(text: str, size: float) -> float:
    """Rough advance width in px for the font stack above.

    An estimate, not a measurement: the server has no font metrics and pulling
    in a font library to place an axis label would be a heavy dependency for a
    number that only has to be right enough to reserve margin. 0.55em is the
    average for Arial across mixed-case text; digits are narrower, so numeric
    tick labels come out slightly over-reserved, which is the safe direction.
    """
    return 0.55 * size * len(str(text))


# ── Tick selection ────────────────────────────────────────────────────────


def nice_ticks(
    low: float, high: float, target: int = 6
) -> Tuple[float, float, float]:
    """Extend [low, high] to round bounds and pick a round step.

    The 1/2/5x10^n rule: a step of 20 or 25 is a scale a student can read off
    graph paper, a step of 17.3 is not. Returns (start, end, step) where start
    <= low, end >= high, and every multiple of step in between is a tick.

    CBSE convention is that a bar/histogram axis starts at zero, so callers
    pass low=0 for those rather than this function assuming it — a temperature
    line graph legitimately starts below zero.
    """
    if not math.isfinite(low) or not math.isfinite(high):
        raise ValueError("nice_ticks needs finite bounds")
    if high < low:
        low, high = high, low
    if high == low:
        # A flat series still needs an axis. One unit of headroom is enough to
        # place the single value somewhere other than on the frame.
        high = low + 1.0

    span = high - low
    raw_step = span / max(1, target)
    magnitude = 10.0 ** math.floor(math.log10(raw_step))
    normalized = raw_step / magnitude

    if normalized <= 1.0:
        step = 1.0 * magnitude
    elif normalized <= 2.0:
        step = 2.0 * magnitude
    elif normalized <= 5.0:
        step = 5.0 * magnitude
    else:
        step = 10.0 * magnitude

    start = math.floor(low / step) * step
    end = math.ceil(high / step) * step
    # Floating point: floor(0.3/0.1)*0.1 can land a hair below 0.3 and add a
    # phantom tick. Snapping to the step grid removes the noise.
    return (round(start, 10), round(end, 10), round(step, 10))


def tick_values(start: float, end: float, step: float) -> List[float]:
    if step <= 0:
        return [start]
    out: List[float] = []
    count = int(round((end - start) / step))
    for index in range(count + 1):
        out.append(round(start + index * step, 10))
    return out


# ── Canvas ────────────────────────────────────────────────────────────────


class Canvas:
    """An ordered list of SVG elements plus the box they live in.

    Deliberately not a scene graph. Charts here are drawn back-to-front in one
    pass — grid, then shapes, then labels — and a tree would add structure
    nothing traverses.
    """

    def __init__(self, width: float, height: float) -> None:
        self.width = float(width)
        self.height = float(height)
        self._parts: List[str] = []

    # Each helper takes user-space coordinates and writes one element. Every
    # shape sets an explicit fill: an SVG shape with no fill attribute is
    # black, which turns an unfilled bar outline into a solid black block in
    # exactly the renderers that do not set it.

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        stroke: str = INK,
        width: float = STROKE_SHAPE,
        dash: Optional[str] = None,
    ) -> None:
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        self._parts.append(
            f'<line x1="{fmt(x1)}" y1="{fmt(y1)}" x2="{fmt(x2)}" y2="{fmt(y2)}"'
            f' stroke="{stroke}" stroke-width="{fmt(width)}"{dash_attr} />'
        )

    def rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        fill: str = PAPER,
        stroke: str = INK,
        stroke_width: float = STROKE_SHAPE,
    ) -> None:
        self._parts.append(
            f'<rect x="{fmt(x)}" y="{fmt(y)}" width="{fmt(width)}"'
            f' height="{fmt(height)}" fill="{fill}" stroke="{stroke}"'
            f' stroke-width="{fmt(stroke_width)}" />'
        )

    def circle(
        self,
        cx: float,
        cy: float,
        r: float,
        *,
        fill: str = INK,
        stroke: str = INK,
        stroke_width: float = STROKE_SHAPE,
    ) -> None:
        self._parts.append(
            f'<circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="{fmt(r)}" fill="{fill}"'
            f' stroke="{stroke}" stroke-width="{fmt(stroke_width)}" />'
        )

    def path(
        self,
        d: str,
        *,
        fill: str = "none",
        stroke: str = INK,
        stroke_width: float = STROKE_SHAPE,
    ) -> None:
        self._parts.append(
            f'<path d="{d}" fill="{fill}" stroke="{stroke}"'
            f' stroke-width="{fmt(stroke_width)}" stroke-linejoin="round" />'
        )

    def polyline(
        self,
        points: Sequence[Tuple[float, float]],
        *,
        stroke: str = INK,
        stroke_width: float = STROKE_SHAPE,
        dash: Optional[str] = None,
    ) -> None:
        coords = " ".join(f"{fmt(x)},{fmt(y)}" for x, y in points)
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        self._parts.append(
            f'<polyline points="{coords}" fill="none" stroke="{stroke}"'
            f' stroke-width="{fmt(stroke_width)}" stroke-linejoin="round"'
            f' stroke-linecap="round"{dash_attr} />'
        )

    def text(
        self,
        x: float,
        y: float,
        content: str,
        *,
        size: float = FONT_LABEL,
        anchor: str = "middle",
        weight: str = "normal",
        fill: str = INK,
        rotate: Optional[float] = None,
    ) -> None:
        if content is None or str(content) == "":
            return
        transform = (
            f' transform="rotate({fmt(rotate)} {fmt(x)} {fmt(y)})"'
            if rotate
            else ""
        )
        weight_attr = f' font-weight="{weight}"' if weight != "normal" else ""
        self._parts.append(
            f'<text x="{fmt(x)}" y="{fmt(y)}" font-family="{FONT_STACK}"'
            f' font-size="{fmt(size)}" text-anchor="{anchor}" fill="{fill}"'
            f'{weight_attr}{transform}>{escape(content)}</text>'
        )

    def render(self) -> str:
        """Serialize.

        `width`/`height` are set as well as `viewBox` because an SVG loaded
        through an `<img>` — which is what both export paths do — falls back to
        300x150 without an intrinsic size, and every figure would come out
        distorted in Word.
        """
        body = "".join(self._parts)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{fmt(self.width)}"'
            f' height="{fmt(self.height)}"'
            f' viewBox="0 0 {fmt(self.width)} {fmt(self.height)}">'
            f'<rect x="0" y="0" width="{fmt(self.width)}"'
            f' height="{fmt(self.height)}" fill="{PAPER}" />'
            f"{body}</svg>"
        )
