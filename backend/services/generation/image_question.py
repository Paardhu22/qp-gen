"""Questions from a teacher's own image.

A teacher has a diagram, a graph, a map, a photo of apparatus — and wants a
question about *that picture*. They can leave the system to work out what it
shows, or tell it: what the image is, what the question should focus on, and
what to change about the picture before it is printed.

Three rules shape everything here:

**The teacher's words win.** The model reads the image and writes a
question, but the description (what the image represents) and the instructions
(what to ask, how) are given to it as authoritative. Where they clarify an
ambiguous picture they override the model's own reading; where they say nothing
the model decides, exactly as it does when no words are given at all.

**The original is never touched.** An edit (crop, highlight, box, arrow, label,
cover) is a list of instructions applied to a *copy*. The upload is stored as it
arrived, the edited copy beside it, and the question uses the copy only when
edits were asked for. Edits are deterministic drawing operations, not an image
model repainting the picture, so a figure's numbers and labels cannot be altered
by accident.

**Nothing leaves this module half-valid.** Uploads are checked by their bytes,
not their names; edit operations are clamped to the picture; the model's answer
goes through the same normaliser as every other generated question.

Coordinates in an edit are fractions of the ORIGINAL image's width and height,
from the top-left. Annotations are drawn on the full image and a crop, if there
is one, is applied last.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import struct
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from services.generation.pool.schema import PoolValidationError, normalize_pool_question
from services.generation.rules.content_filters import clean_question_text
from services.llm.openai_client import _record_usage, get_openai_client
from services.storage.media_urls import stable_media_url

logger = logging.getLogger("[IMAGE_QUESTION]")


class ImageQuestionError(Exception):
    """The request cannot be done as sent: a bad file, an empty instruction.

    The teacher can fix it. The message is fit for a toast.
    """


class ImageProviderError(ImageQuestionError):
    """The request was fine but the model or storage failed. Trying again may work."""


# ── Looking at the bytes ────────────────────────────────────────────────

#: Only formats whose signature we check below. SVG is deliberately absent: it
#: is markup that can carry script, and nothing here needs it.
ALLOWED_TYPES: Dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
}
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MIN_SIDE = 24
MAX_SIDE = 8000
#: Long enough for a paragraph of context, short enough that the field is not a
#: free text channel to the model.
MAX_TEXT_CHARS = 2000


@dataclass(frozen=True)
class ImageInfo:
    content_type: str
    extension: str
    width: int
    height: int
    size: int
    sha256: str


def sniff_type(raw: bytes) -> str:
    """The image type from the file's own first bytes, or ``""``.

    A filename or a browser-reported type is whatever the sender says it is.
    """
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if raw[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return ""


def _dimensions(raw: bytes, content_type: str) -> Tuple[int, int]:
    """Width and height read from the header; raises ``ValueError`` if unreadable."""
    try:
        if content_type == "image/png":
            if raw[12:16] != b"IHDR":
                raise ValueError("no IHDR chunk")
            return struct.unpack(">II", raw[16:24])
        if content_type == "image/gif":
            return struct.unpack("<HH", raw[6:10])
        if content_type == "image/webp":
            kind = raw[12:16]
            if kind == b"VP8X":
                return (1 + int.from_bytes(raw[24:27], "little"), 1 + int.from_bytes(raw[27:30], "little"))
            if kind == b"VP8L":
                bits = int.from_bytes(raw[21:25], "little")
                return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
            if kind == b"VP8 ":
                return (struct.unpack("<H", raw[26:28])[0] & 0x3FFF, struct.unpack("<H", raw[28:30])[0] & 0x3FFF)
            raise ValueError("unknown WebP chunk")
        if content_type == "image/jpeg":
            i = 2
            while i + 9 < len(raw):
                if raw[i] != 0xFF:
                    i += 1
                    continue
                marker = raw[i + 1]
                if marker == 0xFF:  # fill byte
                    i += 1
                    continue
                if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:  # no length
                    i += 2
                    continue
                length = struct.unpack(">H", raw[i + 2 : i + 4])[0]
                if marker in range(0xC0, 0xD0) and marker not in (0xC4, 0xC8, 0xCC):
                    height, width = struct.unpack(">HH", raw[i + 5 : i + 9])
                    return width, height
                i += 2 + length
            raise ValueError("no frame header")
    except (struct.error, IndexError) as exc:
        raise ValueError(str(exc)) from exc
    raise ValueError("unsupported type")


def inspect_image(raw: bytes) -> ImageInfo:
    """Validate an upload by its bytes. Raises `ImageQuestionError` with a reason."""
    if not raw:
        raise ImageQuestionError("That file is empty. Choose an image and try again.")
    if len(raw) > MAX_IMAGE_BYTES:
        raise ImageQuestionError(
            f"That image is {len(raw) / (1024 * 1024):.1f} MB. Images up to "
            f"{MAX_IMAGE_BYTES // (1024 * 1024)} MB are accepted — try a smaller or cropped copy."
        )
    content_type = sniff_type(raw)
    if not content_type:
        raise ImageQuestionError("That file is not a PNG, JPEG, WebP or GIF image.")
    try:
        width, height = _dimensions(raw, content_type)
    except ValueError:
        raise ImageQuestionError("That image file looks damaged and could not be read.") from None
    if min(width, height) < MIN_SIDE:
        raise ImageQuestionError(f"That image is too small to read ({width}×{height}). Use one at least {MIN_SIDE}px on each side.")
    if max(width, height) > MAX_SIDE:
        raise ImageQuestionError(f"That image is too large ({width}×{height}). Use one no larger than {MAX_SIDE}px on a side.")
    return ImageInfo(
        content_type=content_type,
        extension=ALLOWED_TYPES[content_type],
        width=width,
        height=height,
        size=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
    )


# ── Edits ───────────────────────────────────────────────────────────────

#: What can be done to a picture. Every one is a deterministic drawing step the
#: browser applies to a copy; none repaints content.
EDIT_OPS = ("crop", "highlight", "box", "arrow", "label", "cover")
MAX_EDITS = 30
MAX_LABEL_CHARS = 60
_DEFAULT_COLOURS = {"highlight": "#ffd400", "box": "#e11d48", "arrow": "#e11d48", "label": "#111827"}
_COLOUR = re.compile(r"^#[0-9a-fA-F]{6}$")
#: A box smaller than this (a fraction of the picture) is a stray click, not an edit.
_MIN_BOX = 0.005


def _unit(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return max(0.0, min(1.0, number))


def _box(raw: Dict[str, Any]) -> Optional[Tuple[float, float, float, float]]:
    x, y, w, h = (_unit(raw.get(k)) for k in ("x", "y", "w", "h"))
    if None in (x, y, w, h):
        return None
    w = min(w, 1.0 - x)
    h = min(h, 1.0 - y)
    if w < _MIN_BOX or h < _MIN_BOX:
        return None
    return round(x, 4), round(y, 4), round(w, 4), round(h, 4)


def sanitize_edits(raw: Any) -> List[Dict[str, Any]]:
    """The valid edits in ``raw``, clamped to the picture. Never raises.

    This is the one gate for edits, whoever wrote them — the teacher's own
    drawing or a model's suggestion — so an edit that survives it can be applied
    and described without further checks.
    """
    if not isinstance(raw, (list, tuple)):
        return []
    edits: List[Dict[str, Any]] = []
    for item in raw:
        if len(edits) >= MAX_EDITS:
            break
        if not isinstance(item, dict) or item.get("op") not in EDIT_OPS:
            continue
        op = item["op"]
        if op in ("crop", "highlight", "box", "cover"):
            box = _box(item)
            if box is None:
                continue
            edit: Dict[str, Any] = {"op": op, "x": box[0], "y": box[1], "w": box[2], "h": box[3]}
        elif op == "arrow":
            x1, y1, x2, y2 = (_unit(item.get(k)) for k in ("x1", "y1", "x2", "y2"))
            if None in (x1, y1, x2, y2) or (abs(x1 - x2) < _MIN_BOX and abs(y1 - y2) < _MIN_BOX):
                continue
            edit = {"op": op, "x1": round(x1, 4), "y1": round(y1, 4), "x2": round(x2, 4), "y2": round(y2, 4)}
        else:  # label
            x, y = _unit(item.get("x")), _unit(item.get("y"))
            text = " ".join(str(item.get("text") or "").split())[:MAX_LABEL_CHARS]
            if x is None or y is None or not text:
                continue
            edit = {"op": op, "x": round(x, 4), "y": round(y, 4), "text": text}
        if op in _DEFAULT_COLOURS:
            colour = str(item.get("color") or "")
            edit["color"] = colour if _COLOUR.match(colour) else _DEFAULT_COLOURS[op]
        edits.append(edit)
    # One crop: the last one wins, as it does in the editor.
    crops = [i for i, e in enumerate(edits) if e["op"] == "crop"]
    for i in crops[:-1]:
        edits[i] = None  # type: ignore[assignment]
    return [e for e in edits if e is not None]


def _where(x: float, y: float) -> str:
    vertical = "upper" if y < 0.34 else "lower" if y > 0.66 else "middle"
    horizontal = "left" if x < 0.34 else "right" if x > 0.66 else "centre"
    if vertical == "middle" and horizontal == "centre":
        return "the centre"
    return f"the {vertical}-{horizontal}" if vertical != "middle" else f"the middle-{horizontal}"


def describe_edits(edits: Sequence[Dict[str, Any]]) -> List[str]:
    """The edits as plain sentences, for the model.

    The model sees only the edited picture. These tell it what was done to it —
    in particular that a covered region was removed on purpose and must not be
    asked about, and which part is highlighted.
    """
    lines: List[str] = []
    for edit in edits:
        op = edit["op"]
        if op == "crop":
            lines.append("The picture was cropped to the part that matters; everything outside it was removed.")
        elif op == "highlight":
            lines.append(f"The part around {_where(edit['x'] + edit['w'] / 2, edit['y'] + edit['h'] / 2)} was highlighted to draw attention to it.")
        elif op == "box":
            lines.append(f"A box was drawn around the part at {_where(edit['x'] + edit['w'] / 2, edit['y'] + edit['h'] / 2)}.")
        elif op == "arrow":
            lines.append(f"An arrow points to {_where(edit['x2'], edit['y2'])}.")
        elif op == "label":
            lines.append(f"The text “{edit['text']}” was written on the picture near {_where(edit['x'], edit['y'])}.")
        elif op == "cover":
            lines.append(
                f"The part at {_where(edit['x'] + edit['w'] / 2, edit['y'] + edit['h'] / 2)} was covered "
                "(removed) on purpose: do not ask about what was there."
            )
    return lines


# ── Storage ─────────────────────────────────────────────────────────────

_STORAGE_PREFIX = "user_images"


def _store(user, raw: bytes, info: ImageInfo, kind: str) -> str:
    """Save ``raw`` under the user's folder, keyed by its hash, and return its
    stable ``/media/…`` URL (never a presigned one, which would expire).

    Identical bytes land on the same key, so re-uploading a picture costs no
    extra storage. ``kind`` separates the original from its edited copy in the
    key, so editing never overwrites what was uploaded.
    """
    owner = str(getattr(user, "id", "") or "anonymous")
    path = f"{_STORAGE_PREFIX}/{owner}/{info.sha256[:24]}-{kind}.{info.extension}"
    try:
        if not default_storage.exists(path):
            path = default_storage.save(path, ContentFile(raw))
    except Exception as exc:
        logger.error("Could not store an uploaded image: %s", exc, exc_info=True)
        raise ImageProviderError("The image could not be saved. Try again.") from exc
    return stable_media_url(path)


def store_images(
    user,
    *,
    image: bytes,
    original: Optional[bytes] = None,
    edits: Any = None,
) -> Dict[str, Any]:
    """Validate and store a picture and, when it was edited, the original beside it.

    ``image`` is what will be printed: the edited copy when ``original`` is given,
    otherwise the upload itself. The original is stored unchanged either way.
    """
    clean_edits = sanitize_edits(edits)
    info = inspect_image(image)
    if original is not None and original != image:
        original_info = inspect_image(original)
        original_url = _store(user, original, original_info, "original")
        url = _store(user, image, info, "edited")
        return {
            "url": url,
            "originalUrl": original_url,
            "edited": True,
            "edits": clean_edits,
            "width": info.width,
            "height": info.height,
        }
    url = _store(user, image, info, "original")
    return {
        "url": url,
        "originalUrl": url,
        "edited": False,
        "edits": [],
        "width": info.width,
        "height": info.height,
    }


# ── Asking the model ────────────────────────────────────────────────────

def _model() -> str:
    return (
        str(getattr(settings, "IMAGE_QUESTION_MODEL", "") or "").strip()
        or getattr(settings, "OPENAI_VISION_MODEL", "")
        or getattr(settings, "OPENAI_MODEL", "gpt-4.1-mini")
    )


def _data_url(raw: bytes, content_type: str) -> str:
    return f"data:{content_type};base64,{base64.b64encode(raw).decode('ascii')}"


#: Question shapes a picture can sensibly carry, as the teacher picks them.
QUESTION_TYPES: Tuple[Tuple[str, str], ...] = (
    ("", "Let the AI choose"),
    ("MCQ", "Multiple choice"),
    ("VERY_SHORT_ANSWER", "Very short answer"),
    ("SHORT_ANSWER", "Short answer"),
    ("LONG_ANSWER", "Long answer"),
    ("NUMERICAL", "Numerical"),
    ("CASE_STUDY", "Case-based"),
    ("ASSERTION_REASON", "Assertion–reason"),
)
_TYPE_CODES = {code for code, _ in QUESTION_TYPES if code}

SYSTEM_PROMPT = (
    "You are a senior CBSE examiner writing ONE question for a printed question paper, "
    "based on an image the teacher has supplied.\n\n"
    "The image is printed with the question, so the question may refer to it "
    "(\"In the figure shown…\", \"the graph above\"). It must still be answerable by a "
    "student who can see the image and knows the Class syllabus.\n\n"
    "How to use what you are given:\n"
    "1. The teacher's DESCRIPTION says what the image represents. Treat it as true. "
    "Where it clarifies something the picture leaves ambiguous, follow the description "
    "over your own reading.\n"
    "2. The teacher's INSTRUCTIONS say what the question should focus on and how it "
    "should be asked. Follow them. They take priority over your own choice of focus, "
    "type and style whenever they say something about it; where they are silent you decide.\n"
    "3. If there is no description or instruction, work out what the image shows and "
    "write the best single question about it.\n"
    "4. Read values, labels and text off the image exactly as printed; never invent a "
    "number, label or fact that is neither visible nor stated by the teacher. If the "
    "picture is too unclear to ask about safely, say so in `understanding.concerns` and "
    "ask about only what is certain.\n"
    "5. If the picture was edited (cropped, highlighted, labelled, covered), you are "
    "shown the edited version and told what was done. Refer to a highlighted or boxed "
    "part as such, and never ask about a part that was covered.\n"
    "6. Stay inside the class's syllabus for the subject. Match the requested question "
    "type, marks and difficulty when they are given.\n"
    "7. Write maths in LaTeX: inline \\( … \\) and standalone equations in \\[ … \\]; "
    "never $…$. Because your reply is JSON, every backslash inside a JSON string must be "
    "doubled.\n\n"
    "Return ONLY a JSON object:\n"
    "{\n"
    '  "understanding": {"summary": "<one or two sentences: what the image shows>",\n'
    '                    "kind": "diagram|graph|chart|map|table|photo|text|other",\n'
    '                    "elements": ["<key parts you identified>"],\n'
    '                    "concerns": ["<anything unclear or unsafe to ask about>"]},\n'
    '  "alt_text": "<a short description of the image for a screen reader>",\n'
    '  "question": {"type": "<MCQ|VERY_SHORT_ANSWER|SHORT_ANSWER|LONG_ANSWER|NUMERICAL|CASE_STUDY|ASSERTION_REASON>",\n'
    '               "question": "<the question text>",\n'
    '               "options": ["<A>", "<B>", "<C>", "<D>"],\n'
    '               "answer": "<what a marking scheme accepts>",\n'
    '               "explanation": "<why>",\n'
    '               "marks": <integer>,\n'
    '               "topic": "<specific topic>",\n'
    '               "blooms": "REMEMBER|UNDERSTAND|APPLY|ANALYZE|EVALUATE|CREATE",\n'
    '               "difficulty": "easy|medium|hard"}\n'
    "}\n"
    "Omit `options` (or send []) unless the question is multiple choice."
)


def build_generation_messages(
    *,
    image: bytes,
    content_type: str,
    description: str,
    instructions: str,
    edits: Sequence[Dict[str, Any]],
    subject: str,
    class_num: int,
    question_type: str,
    marks: Optional[int],
    difficulty: str,
) -> List[Dict[str, Any]]:
    """The model request for one image question. Pure, so it can be inspected."""
    lines = [f"Subject: {subject or 'not stated'} | Class: {class_num}"]
    lines.append(
        f"Question type: {question_type}" if question_type else "Question type: your choice — whatever suits the image best."
    )
    lines.append(f"Marks: {marks}" if marks else "Marks: your choice, in proportion to the work involved.")
    lines.append(f"Difficulty: {difficulty}" if difficulty in ("easy", "medium", "hard") else "Difficulty: moderate.")
    lines.append("")
    lines.append(f"TEACHER'S DESCRIPTION of the image: {description}" if description else "TEACHER'S DESCRIPTION: none given — work out what the image shows.")
    lines.append(f"TEACHER'S INSTRUCTIONS for the question: {instructions}" if instructions else "TEACHER'S INSTRUCTIONS: none given — choose a sensible focus.")
    if edits:
        lines.append("")
        lines.append("WHAT WAS DONE TO THE PICTURE (you are shown the edited version):")
        lines.extend(f"- {sentence}" for sentence in describe_edits(edits))
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "\n".join(lines)},
                {"type": "image_url", "image_url": {"url": _data_url(image, content_type), "detail": "high"}},
            ],
        },
    ]


def _complete_json(messages: List[Dict[str, Any]], *, user, operation: str) -> Dict[str, Any]:
    """One JSON-mode vision call. Raises `ImageQuestionError` for anything the
    teacher should be told about."""
    model = _model()
    kwargs: Dict[str, Any] = dict(
        model=model,
        messages=messages,
        response_format={"type": "json_object"},
        max_completion_tokens=3000,
    )
    # `reasoning_effort` is only accepted by gpt-5 / o-series models.
    if model.startswith(("gpt-5", "o1", "o3")):
        kwargs["reasoning_effort"] = "low"
    try:
        completion = get_openai_client().chat.completions.create(**kwargs)
        _record_usage(user, operation, model, completion.usage)
        raw = (completion.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.error("%s failed: %s", operation, exc, exc_info=True)
        raise ImageProviderError(
            "The image could not be read right now. Try again in a moment."
        ) from exc
    parsed = _parse_json(raw)
    if parsed is None:
        logger.warning("%s returned no usable JSON: %.200r", operation, raw)
        raise ImageProviderError("The AI's answer could not be understood. Try again.")
    return parsed


_LONE_BACKSLASH = re.compile(r'\\(["\\/bfnrt]|u[0-9a-fA-F]{4})|\\')


def _parse_json(raw: str) -> Optional[Dict[str, Any]]:
    """The reply as an object. Tolerates a code fence and the commonest LaTeX
    slip — one backslash where JSON needs two."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    body = text[start : end + 1]
    for candidate in (body, _LONE_BACKSLASH.sub(lambda m: m.group(0) if m.group(1) else "\\\\", body)):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _clip(text: Any) -> str:
    return " ".join(str(text or "").split())[:MAX_TEXT_CHARS]


def _text_field(value: Any) -> str:
    """A free-text field, trimmed but with its line breaks kept."""
    return "\n".join(line.rstrip() for line in str(value or "").strip().splitlines())[:MAX_TEXT_CHARS]


def generate_image_question(
    *,
    user,
    image: bytes,
    original: Optional[bytes] = None,
    edits: Any = None,
    description: str = "",
    instructions: str = "",
    subject: str = "",
    class_num: int = 10,
    question_type: str = "",
    marks: Optional[int] = None,
    difficulty: str = "",
) -> Dict[str, Any]:
    """Write one question from a picture, with the teacher's words as context.

    Returns ``{"question", "understanding", "image", "usedDescription",
    "usedInstructions"}``. The ``question`` is shaped like every other generated
    question the editor inserts, with ``image_url`` set so it carries the picture.
    """
    info = inspect_image(image)  # validated first: no model call on a bad file
    clean_edits = sanitize_edits(edits)
    description = _text_field(description)
    instructions = _text_field(instructions)
    question_type = question_type if question_type in _TYPE_CODES else ""
    marks = marks if isinstance(marks, int) and 1 <= marks <= 20 else None
    difficulty = difficulty if difficulty in ("easy", "medium", "hard") else ""

    messages = build_generation_messages(
        image=image,
        content_type=info.content_type,
        description=description,
        instructions=instructions,
        edits=clean_edits,
        subject=subject,
        class_num=class_num,
        question_type=question_type,
        marks=marks,
        difficulty=difficulty,
    )
    parsed = _complete_json(messages, user=user, operation="image_question")

    raw_question = parsed.get("question")
    if not isinstance(raw_question, dict):
        raise ImageProviderError("The AI did not write a question for that image. Try again, or add a description.")
    if marks:
        raw_question = {**raw_question, "marks": marks}
    if question_type:
        raw_question = {**raw_question, "type": question_type}
    try:
        question = normalize_pool_question(
            raw_question,
            subject=subject or "General",
            chapter="Image question",
            default_difficulty=difficulty or "medium",
            source_type="image",
        )
    except PoolValidationError as exc:
        logger.warning("Image question failed validation: %s", exc)
        raise ImageProviderError(
            "The question the AI wrote was incomplete. Try again, or give it more to go on."
        ) from exc

    stored = store_images(user, image=image, original=original, edits=clean_edits)
    understanding = parsed.get("understanding") if isinstance(parsed.get("understanding"), dict) else {}
    alt = _clip(parsed.get("alt_text")) or _clip(understanding.get("summary"))[:200]

    content = clean_question_text(question.question)
    return {
        "question": {
            "content": content,
            "type": question.type,
            "options": list(question.options or []),
            "answer": question.answer,
            "explanation": question.explanation,
            "marks": question.marks,
            "image_url": stored["url"],
            "image_alt": alt,
            "metadata": {
                "difficulty": question.difficulty,
                "blooms": question.blooms,
                "inferredTopic": question.topic,
                "sourceType": "image",
                "imageQuestion": True,
                "originalImageUrl": stored["originalUrl"],
            },
        },
        "understanding": {
            "summary": _clip(understanding.get("summary")),
            "kind": _clip(understanding.get("kind"))[:30],
            "elements": [_clip(e)[:120] for e in (understanding.get("elements") or [])[:12] if _clip(e)],
            "concerns": [_clip(c)[:200] for c in (understanding.get("concerns") or [])[:6] if _clip(c)],
        },
        "image": {**stored, "alt": alt},
        "usedDescription": bool(description),
        "usedInstructions": bool(instructions),
    }


# ── Suggesting edits from words ─────────────────────────────────────────

EDIT_PLAN_PROMPT = (
    "You prepare edits to an image that will be printed in an exam paper. You are given "
    "the image and the teacher's request in words. Turn the request into a list of "
    "drawing operations — nothing else.\n\n"
    "Operations (coordinates are fractions of the image's width and height, 0 to 1, "
    "measured from the TOP-LEFT corner):\n"
    '  {"op":"crop","x":,"y":,"w":,"h":}       keep only this rectangle\n'
    '  {"op":"highlight","x":,"y":,"w":,"h":}  a translucent marker over a region\n'
    '  {"op":"box","x":,"y":,"w":,"h":}        an outline around a region\n'
    '  {"op":"arrow","x1":,"y1":,"x2":,"y2":}  an arrow from (x1,y1) to (x2,y2)\n'
    '  {"op":"label","x":,"y":,"text":"..."}   text placed at (x,y)\n'
    '  {"op":"cover","x":,"y":,"w":,"h":}      a white rectangle that removes a region\n\n'
    "Rules:\n"
    "- Do exactly what the teacher asks and nothing more. Never remove, move or alter "
    "anything they did not mention.\n"
    "- Make each box tight around the thing it names. If you cannot find a thing "
    "confidently, do not guess a position: list it under `unsupported` instead.\n"
    "- You cannot redraw, recolour, resize objects, change numbers or add new drawn "
    "objects. Anything that needs that goes under `unsupported`.\n"
    "- Use at most one crop.\n\n"
    'Return ONLY JSON: {"edits": [...], "notes": ["<one short line saying what each edit does>"], '
    '"unsupported": ["<requested changes these operations cannot do>"]}'
)


def plan_image_edits(*, user, image: bytes, instruction: str, description: str = "") -> Dict[str, Any]:
    """Turn a request in words into drawing operations the teacher can review.

    Never applied automatically: the browser shows the proposal over the picture
    and the teacher adjusts or discards it. Positions a model gives are
    approximate, which is exactly why they are a proposal.
    """
    info = inspect_image(image)
    instruction = _text_field(instruction)
    if not instruction:
        raise ImageQuestionError("Say what you want changed, for example “crop to the circuit and highlight R2”.")
    text = f"TEACHER'S REQUEST: {instruction}"
    if _text_field(description):
        text += f"\nWHAT THE IMAGE IS (from the teacher): {_text_field(description)}"
    messages = [
        {"role": "system", "content": EDIT_PLAN_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": _data_url(image, info.content_type), "detail": "high"}},
            ],
        },
    ]
    parsed = _complete_json(messages, user=user, operation="image_edit_plan")
    edits = sanitize_edits(parsed.get("edits"))
    return {
        "edits": edits,
        "notes": [_clip(n)[:160] for n in (parsed.get("notes") or [])[:12] if _clip(n)],
        "unsupported": [_clip(u)[:200] for u in (parsed.get("unsupported") or [])[:8] if _clip(u)],
    }
