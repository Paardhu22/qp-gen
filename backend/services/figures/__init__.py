"""Deterministic figures for exam questions.

Public surface is two calls, in the order the dialog makes them:

* `extract_figure_spec(question_text=…)` — what figure does this question want,
  and with what numbers? Fast, cheap, and always answers.
* `render_chart(spec=…)` — draw it. No model, no network, no randomness; the
  same spec produces the same bytes forever.

Splitting them is the point. The old flow was one slow billable call that
returned a picture a teacher could only accept or discard; between these two
sits the moment a teacher can see the numbers that were read out of their
question and fix them before anything is drawn. A deterministic renderer fed
the wrong data is still wrong, and the teacher is the only one who can catch
that.

`charts.py` and `spec.py` know nothing about Django or storage; this module is
where a drawing becomes a stored file with a stable URL.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from services.media_urls import stable_media_url

from . import charts
from .extract import MAX_QUESTION_CHARS, extract_figure_spec
from .spec import (
    CHART_KINDS,
    KIND_CHART,
    KIND_ILLUSTRATION,
    KIND_MAP,
    ChartSpec,
    SpecError,
    parse_chart_spec,
)

logger = logging.getLogger("[FIGURES]")

__all__ = [
    "CHART_KINDS",
    "KIND_CHART",
    "KIND_ILLUSTRATION",
    "KIND_MAP",
    "MAX_QUESTION_CHARS",
    "SpecError",
    "extract_figure_spec",
    "parse_chart_spec",
    "render_chart",
    "storage_path",
]

#: Alongside `question_images/`, not inside it: these are a different kind of
#: object with a different cache key and a different extension, and one prefix
#: holding both would make either one impossible to clear alone.
_STORAGE_PREFIX = "question_figures"


def storage_path(spec: ChartSpec) -> str:
    """Cache key covering everything that determines the pixels.

    That includes `RENDERER_VERSION`, which the fingerprint carries: hashing
    only the data would let a stored SVG outlive the code that drew it, so
    improving a renderer would change nothing for any chart already rendered.
    Superseded files are orphaned rather than deleted — storage is cheap, and
    an unreachable object is not a regression.
    """
    digest = hashlib.sha256(
        spec.cache_fingerprint().encode("utf-8")
    ).hexdigest()[:32]
    return f"{_STORAGE_PREFIX}/{digest}.svg"


def render_chart(*, spec: Any) -> Dict[str, Any]:
    """Draw a chart and store it. Returns ``{"imageUrl", "kind", "cached"}``.

    `spec` is the wire dict — from the extractor, or from the teacher's edits
    in the dialog, which is why it is re-validated here rather than trusted.
    Raises `SpecError` if it will not draw.
    """
    parsed = spec if isinstance(spec, ChartSpec) else parse_chart_spec(spec)
    path = storage_path(parsed)

    try:
        if default_storage.exists(path):
            return {
                "imageUrl": stable_media_url(path),
                "kind": KIND_CHART,
                "cached": True,
            }
    except Exception as exc:
        # A backend that cannot answer exists() is no reason to refuse —
        # rendering again is cheap here, unlike the image path.
        logger.debug("Could not check the figure cache for %s: %s", path, exc)

    markup = charts.render(parsed)

    try:
        stored_path = default_storage.save(
            path, ContentFile(markup.encode("utf-8"))
        )
    except Exception as exc:
        logger.error("Could not store the rendered figure: %s", exc, exc_info=True)
        raise SpecError(f"could not store the figure: {exc}") from exc

    return {
        "imageUrl": stable_media_url(stored_path),
        "kind": KIND_CHART,
        "cached": False,
    }
