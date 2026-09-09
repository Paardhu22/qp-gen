"""Read a question and say what figure it wants — and, for a chart, with what
numbers.

This is the call the old path did not make. `question_image.build_prompt` was
explicit about not making it ("paying a text model to restate it before paying
an image model to draw it doubles the latency to save nothing"), and for a
photograph of a beaker that reasoning holds. For a pie chart it does not: the
image model was never told the wedge values, so it invented them, and no
amount of prompt tuning fixes a model that is guessing at data.

It runs unconditionally rather than behind a keyword gate. A gate would have
to recognise a chart question from its wording, and the questions that break
today are exactly the ones that describe their data without ever saying the
words "bar graph" — a prefilter would send those straight back to the image
model, which is the bug.

Cost is the reason that is affordable: one small structured call against a
30-second image render it usually replaces outright.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from django.conf import settings

from services.openai_service import get_openai_client
# Private by name, shared by intent: this is the one helper that files an
# ApiUsage row against the caller's billing organisation, and a new billable
# call that skipped it would be invisible to the monthly limit — the exact
# hole the image path still has.
from services.openai_service import _record_usage

from .spec import KIND_CHART, KIND_ILLUSTRATION, KIND_MAP, SpecError, parse_chart_spec

logger = logging.getLogger("[FIGURE_SPEC]")

#: Long enough for a case study with a data table, short enough that the
#: extractor cannot be used as a general-purpose text channel to the model.
MAX_QUESTION_CHARS = 2000

_SYSTEM = (
    "You read one exam question from an Indian school question paper and "
    "decide what figure, if any, it needs. You reply with JSON only."
)

_INSTRUCTION = """\
Classify the question into exactly one `kind`:

* "chart" — the question is about data that must be PLOTTED: a pie chart, bar
  graph, histogram, frequency polygon, ogive/cumulative frequency curve, a
  number line, or points on a coordinate grid. Choose this whenever the
  question supplies or implies the numbers.
* "map" — the question needs a geographic map (locating places, states,
  rivers, resources on an outline map).
* "illustration" — anything else that needs a picture: apparatus, a biological
  structure, a ray diagram, a circuit, a scene from a word problem. Also use
  this for a pure geometry construction (triangle, circle, tangent), which is
  drawn rather than plotted.

For "chart", also emit these fields:

  chart       one of: pie, bar, histogram, line, number_line, coordinate_grid
              (use "line" for a frequency polygon or an ogive)
  series      [{"label": "Bus", "value": 240}, ...]
              — for pie, bar, line; for number_line, `value` is the POSITION on
              the line and `label` is what to print above it (e.g. "3/4")
  bins        [{"lower": 10, "upper": 20, "value": 7}, ...] — histogram only
  points      [{"x": 2, "y": 3, "label": "A"}, ...] — coordinate_grid only
  xLabel      what the horizontal axis counts (e.g. "Mode of transport")
  yLabel      what the vertical axis counts (e.g. "Number of students")
  yMax        a scale ceiling ONLY if the question names one; otherwise omit
  showValues  true only if the question itself already gives the reader those
              numbers. If the question ASKS the student to read, compute or
              compare the values, this MUST be false.
  axisMin, axisMax, axisStep — number_line and coordinate_grid extent, if the
              question names one

Rules:

1. Take every number from the question. Never invent, round, complete or
   "correct" a value. If the question does not supply enough numbers to plot,
   return kind "illustration" instead — a plotted guess is worse than no chart.
2. The figure must never reveal the answer. If the question asks "how many
   students travel by bus", `showValues` is false.
3. Labels are short category names, not sentences. No titles, no captions.
4. Reply with a single JSON object and nothing else.

Question:
"""


def _spec_model() -> str:
    # Read as an attribute, not getattr-with-default: every stage model is
    # unconditionally defined in settings, and a silent fallback is the exact
    # inheritance the settings comment forbids.
    return settings.FIGURE_SPEC_MODEL


def extract_figure_spec(*, question_text: str, user=None) -> Dict[str, Any]:
    """Return ``{"kind": ..., "spec": {...} | None}``.

    Never raises for an unusable answer. Every failure — a model error, junk
    JSON, a spec that will not validate — resolves to `illustration`, which is
    the path that was already there. The worst case of this function is that
    the product behaves exactly as it did before it existed.
    """
    text = " ".join(str(question_text or "").split())[:MAX_QUESTION_CHARS]
    if not text:
        return {"kind": KIND_ILLUSTRATION, "spec": None}

    try:
        client = get_openai_client()
        completion = client.chat.completions.create(
            model=_spec_model(),
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": f"{_INSTRUCTION}{text}"},
            ],
            # Reading numbers off a table is not a creative act, and a
            # non-zero temperature here means the same question extracts
            # different data on two runs.
            temperature=0,
            response_format={"type": "json_object"},
        )
        _record_usage(user, "figure_spec", _spec_model(), completion.usage)
        raw = completion.choices[0].message.content or "{}"
    except Exception as exc:
        logger.warning("Figure spec extraction failed: %s", exc)
        return {"kind": KIND_ILLUSTRATION, "spec": None}

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Figure spec was not JSON: %s", raw[:200])
        return {"kind": KIND_ILLUSTRATION, "spec": None}

    kind = str(payload.get("kind") or "").strip().lower()

    if kind == KIND_MAP:
        # Maps are classified but not yet drawn — the base geometry decision is
        # open. Falling through to illustration keeps today's behaviour for
        # them rather than shipping a half-map.
        logger.info("Question classified as a map; no map renderer yet")
        return {"kind": KIND_ILLUSTRATION, "spec": None}

    if kind != KIND_CHART:
        return {"kind": KIND_ILLUSTRATION, "spec": None}

    try:
        spec = parse_chart_spec(payload)
    except SpecError as exc:
        logger.info("Rejected an extracted chart spec (%s); using the image model", exc)
        return {"kind": KIND_ILLUSTRATION, "spec": None}

    return {"kind": KIND_CHART, "spec": spec.to_dict()}
