"""Draw one figure for one question, when a teacher asks for it.

This is not the image stage that used to sit between Model 1 and Model 2. That
one guessed which questions wanted pictures and drew them speculatively during
every generation; it was ~85% of a paper's cost and produced figures nobody had
asked for. It was removed.

What replaced it inverts the control. Nothing is drawn during generation. A
teacher reads the finished paper, decides *this* question would be clearer with
a figure, picks a style, and pays for exactly that one image. Cost tracks
intent, and the teacher sees the question before deciding — which is the only
moment anyone can actually judge whether a picture helps.

## Style is the teacher's choice, not a house rule

The old stage hard-coded a single textbook-line-art look because it was drawing
science diagrams unattended. Here the teacher says what they want, and the three
styles are genuinely different jobs:

* ``line_art`` — a labelled textbook figure. Ray diagrams, circuits, anatomy.
* ``realistic`` — a photographic depiction. Apparatus, specimens, real objects.
* ``cartoon`` — a friendly illustration. Primary classes, word problems.

What does NOT change with style are the exam constraints: no title, no caption,
no figure number, no watermark, and any label must be legible. Those are what
make an image usable on a printed paper, and a teacher choosing "cartoon" has
not asked for a captioned meme.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import threading
from typing import Any, Dict, Optional, Tuple

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from services.media_urls import stable_media_url
from services.openai_service import get_openai_client

logger = logging.getLogger("[QUESTION_IMAGE]")

#: Where generated figures live. Keyed by a hash of everything that determines
#: the pixels, so the same request is never billed twice — across questions,
#: papers or users.
_STORAGE_PREFIX = "question_images"

STYLE_LINE_ART = "line_art"
STYLE_REALISTIC = "realistic"
STYLE_CARTOON = "cartoon"

#: Offered to the teacher in the style picker. Order is the order shown.
STYLE_CHOICES: Tuple[Dict[str, str], ...] = (
    {
        "value": STYLE_LINE_ART,
        "label": "Line art",
        "description": "Clean black-and-white textbook figure with labels.",
    },
    {
        "value": STYLE_REALISTIC,
        "label": "Realistic",
        "description": "Photographic depiction of the real object or apparatus.",
    },
    {
        "value": STYLE_CARTOON,
        "label": "Cartoon",
        "description": "Friendly illustration, good for younger classes.",
    },
)

# ── What every figure must obey, whatever style it is drawn in ─────────────
#
# These are the failure modes image models reliably hit on exam figures: they
# add decorative titles and captions, they stamp watermarks, and their label
# text degrades into letter-shaped noise. A figure whose labels cannot be read
# is not a cheaper figure — it is an unanswerable question.
_EXAM_CONSTRAINTS = (
    "This image will be printed inside a school examination paper.\n"
    "Draw ONLY the subject described. Add no title, no caption, no figure "
    "number, no watermark, no border, no legend, and no label that was not "
    "asked for.\n"
    "Any text in the image must be crisp, horizontal, upright English in a "
    "plain face, large enough to read at half size.\n"
    "Do not depict any real, named or identifiable person.\n"
    "Leave a small even margin around the subject.\n"
)

_STYLE_DIRECTIONS: Dict[str, str] = {
    STYLE_LINE_ART: (
        "Draw this as a flat two-dimensional line drawing in the style of an "
        "Indian school science textbook: uniform black strokes on a pure white "
        "background, no colour fills, no shading, no gradients, no drop "
        "shadows, no 3D perspective, no photorealism, no background scenery.\n"
        "Place each label clear of the line it names and join it with a thin "
        "leader line where needed.\n"
    ),
    STYLE_REALISTIC: (
        "Render this as a clear, well-lit photographic image on a plain "
        "uncluttered background. Natural colours and proportions, sharp focus "
        "on the subject, no artistic filters, no motion blur, no dramatic "
        "lighting, nothing in the frame that is not part of the subject.\n"
    ),
    STYLE_CARTOON: (
        "Draw this as a simple, friendly cartoon illustration with bold clean "
        "outlines and flat cheerful colours, in the style of a primary school "
        "textbook. Keep shapes simple and readable; no speech bubbles, no "
        "comic panels, no exaggerated expressions that obscure the subject.\n"
    ),
}


def normalize_style(raw: Any) -> str:
    """Coerce a client value to a known style, defaulting to line art.

    Line art is the default because it is the only style that is *always*
    appropriate on an exam paper — a wrong-but-clear diagram is fixable, a
    photorealistic render of a misunderstood prompt is not.
    """
    value = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    return value if value in _STYLE_DIRECTIONS else STYLE_LINE_ART


def _image_model() -> str:
    return str(getattr(settings, "OPENAI_IMAGE_MODEL", "gpt-image-1"))


def _image_size() -> str:
    return str(getattr(settings, "OPENAI_IMAGE_SIZE", "1024x1024"))


def _image_quality() -> str:
    return str(getattr(settings, "OPENAI_IMAGE_QUALITY", "high")).strip().lower()


# Serialises image requests process-wide. One at a time by default: image
# generation is slow and expensive, and a burst of parallel requests from one
# impatient teacher is the fastest way to hit the org's rate limit.
_gate_lock = threading.Lock()
_gate: Optional[threading.BoundedSemaphore] = None


def _image_gate() -> threading.BoundedSemaphore:
    global _gate
    with _gate_lock:
        if _gate is None:
            _gate = threading.BoundedSemaphore(
                max(1, int(getattr(settings, "OPENAI_IMAGE_CONCURRENCY", 1)))
            )
        return _gate


def build_prompt(question_text: str, style: str) -> str:
    """Turn a question into a drawing instruction.

    Deliberately NOT a model call. The question already describes what it is
    about, and paying a text model to restate it before paying an image model
    to draw it doubles the latency of an interactive action to save nothing —
    image models read this kind of description directly.

    The question text is framed as *subject matter*, never as an instruction,
    so "Draw a labelled diagram of the human eye" produces the eye rather than
    an image of the sentence.
    """
    subject = " ".join(str(question_text or "").split())
    # Long case studies carry a stimulus paragraph the figure does not need,
    # and an over-long prompt drifts. The opening sentences carry the subject.
    if len(subject) > 600:
        subject = subject[:600].rsplit(" ", 1)[0] + "…"

    return (
        f"{_STYLE_DIRECTIONS[style]}"
        f"{_EXAM_CONSTRAINTS}"
        "\nThe subject to depict, taken from an exam question. Depict what the "
        "question is ABOUT; do not draw the text of the question itself, and "
        "do not answer it:\n"
        f"{subject}"
    )


def _storage_path(prompt: str) -> str:
    """Cache key covering everything that determines the pixels.

    Hashing the prompt alone would let a stored PNG outlive the settings that
    drew it — raising the quality tier would change nothing, because every
    request still hit its old render. Old files are orphaned rather than
    deleted; storage is cheap and an unreachable object is not a regression.
    """
    fingerprint = "\n".join(
        [prompt.strip(), _image_model(), _image_size(), _image_quality()]
    )
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:32]
    return f"{_STORAGE_PREFIX}/{digest}.png"


def _decode_response(response: Any) -> Tuple[Optional[bytes], Optional[str]]:
    data = getattr(response, "data", None) or []
    if not data:
        return None, "the image model returned no data"

    b64 = getattr(data[0], "b64_json", None)
    if b64:
        try:
            return base64.b64decode(b64), None
        except Exception as exc:
            return None, f"could not decode the generated image: {exc}"

    # Some deployments return a URL instead of inline bytes.
    url = getattr(data[0], "url", None)
    if not url:
        return None, "the image model returned neither image data nor a URL"
    try:
        import urllib.request

        with urllib.request.urlopen(url, timeout=30) as handle:
            return handle.read(), None
    except Exception as exc:
        return None, f"could not fetch the generated image: {exc}"


class QuestionImageError(RuntimeError):
    """Generation failed in a way worth telling the teacher about."""


def generate_question_image(
    *, question_text: str, style: Any = STYLE_LINE_ART, user=None
) -> Dict[str, Any]:
    """Draw one figure for one question.

    Returns ``{"imageUrl", "style", "cached"}``. Raises `QuestionImageError`
    with a message fit for a toast — this is an interactive action, so a
    failure has a teacher waiting on it and must say something useful rather
    than fail silently the way a background stage could.
    """
    text = " ".join(str(question_text or "").split())
    if not text:
        raise QuestionImageError(
            "This question has no text to draw from. Add the question first."
        )

    resolved_style = normalize_style(style)
    prompt = build_prompt(text, resolved_style)
    path = _storage_path(prompt)

    # An identical request — same question, same style, same settings — reuses
    # the stored PNG. Teachers regenerate the same paper often.
    try:
        if default_storage.exists(path):
            return {
                "imageUrl": stable_media_url(path),
                "style": resolved_style,
                "cached": True,
            }
    except Exception as exc:
        # A backend that cannot answer exists() is not a reason to refuse —
        # fall through and draw it again.
        logger.debug("Could not check the image cache for %s: %s", path, exc)

    generate_kwargs: Dict[str, Any] = {
        "model": _image_model(),
        "prompt": prompt,
        "size": _image_size(),
        "n": 1,
    }
    # gpt-image-1 takes low|medium|high. dall-e uses standard|hd, so passing
    # ours would be a BadRequestError on any other model.
    if _image_model().startswith("gpt-image"):
        generate_kwargs["quality"] = _image_quality()

    try:
        client = get_openai_client()
        with _image_gate():
            response = client.images.generate(**generate_kwargs)
    except Exception as exc:
        logger.error("Image generation failed: %s", exc, exc_info=True)
        raise QuestionImageError(
            "The image could not be generated. Try again, or pick a different "
            "style."
        ) from exc

    raw, error = _decode_response(response)
    if error or not raw:
        logger.error("Image generation returned nothing usable: %s", error)
        raise QuestionImageError(
            "The image came back empty. Try again, or pick a different style."
        )

    try:
        stored_path = default_storage.save(path, ContentFile(raw))
    except Exception as exc:
        logger.error("Could not store the generated image: %s", exc, exc_info=True)
        raise QuestionImageError(
            "The image was drawn but could not be saved. Try again."
        ) from exc

    # Only the stable /media/<key> URL is returned. A presigned URL would be
    # long expired by the time the teacher reopens the paper.
    return {
        "imageUrl": stable_media_url(stored_path),
        "style": resolved_style,
        "cached": False,
    }
