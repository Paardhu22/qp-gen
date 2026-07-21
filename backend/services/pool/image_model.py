"""The image-question stage.

Runs between Model 1 and Model 2 and adds image-bearing questions to the pool.

Three strategies, selected by ``IMAGE_QUESTION_STRATEGY``:

``generate`` (default)
    A text model proposes diagram specs from the chapter, then ``gpt-image-1``
    draws each one and the question is written against the drawing.

``reuse``
    Questions are written about the figures already extracted from the
    uploaded chapter (captioned at ingest time). No image generation, so the
    figure is guaranteed to be the real textbook figure.

``hybrid``
    Reuse the chapter's own figures first; only synthesise when a slot has no
    real figure available.

Why the knob exists: synthesising diagrams costs roughly 20× a text question
and an AI-drawn circuit or ray diagram can be confidently wrong in ways a
student will notice. Every synthesised question is therefore tagged
``source_type="synthetic_image"`` so the review tray can flag it for a teacher
before it reaches a real exam, and switching strategy is an env var rather
than a refactor.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from apps.question_generation.infrastructure.providers.base import (
    LLMMessage,
    LLMRequest,
)
from apps.question_generation.infrastructure.providers.openai_provider import (
    OpenAIProvider,
)
from services.chapter_markdown import ChapterMarkdown, Figure
from services.media_urls import stable_media_url
from services.openai_service import get_openai_client
from services.pool.schema import (
    PoolQuestion,
    PoolValidationError,
    normalize_pool_question,
)
from services.pool.streaming import parse_question_payload

logger = logging.getLogger("[IMAGE_MODEL]")

STRATEGY_GENERATE = "generate"
STRATEGY_REUSE = "reuse"
STRATEGY_HYBRID = "hybrid"
_VALID_STRATEGIES = {STRATEGY_GENERATE, STRATEGY_REUSE, STRATEGY_HYBRID}

#: Where synthesised diagrams live. Keyed by prompt hash, so the same diagram
#: is never billed twice — across pools, chapters, or users.
_DIAGRAM_PREFIX = "generated_diagrams"

#: gpt-image-1 calls are slow (10-20s). Run a few in parallel, but not so many
#: that a single generation saturates the image rate limit.
_IMAGE_CONCURRENCY = 3


@dataclass
class ImageQuestionResult:
    questions: List[PoolQuestion] = field(default_factory=list)
    generated_count: int = 0
    reused_count: int = 0
    cache_hits: int = 0
    failures: List[str] = field(default_factory=list)
    estimated_cost_usd: float = 0.0

    @property
    def total(self) -> int:
        return len(self.questions)


def resolve_strategy() -> str:
    raw = str(getattr(settings, "IMAGE_QUESTION_STRATEGY", STRATEGY_GENERATE)).strip().lower()
    if raw not in _VALID_STRATEGIES:
        logger.warning(
            "Unknown IMAGE_QUESTION_STRATEGY %r; falling back to %r.",
            raw, STRATEGY_GENERATE,
        )
        return STRATEGY_GENERATE
    return raw


def _image_cap() -> int:
    return max(0, int(getattr(settings, "IMAGE_QUESTIONS_PER_POOL", 8)))


def _image_model() -> str:
    return str(getattr(settings, "OPENAI_IMAGE_MODEL", "gpt-image-1"))


def _image_size() -> str:
    return str(getattr(settings, "OPENAI_IMAGE_SIZE", "1024x1024"))


def _image_quality() -> str:
    """Cheapest suitable quality tier (settings.OPENAI_IMAGE_QUALITY, default 'low')."""
    return str(getattr(settings, "OPENAI_IMAGE_QUALITY", "low")).strip().lower()


# ── Stage 1: propose specs ──────────────────────────────────────────────


_SPEC_SYSTEM_PROMPT = (
    "You are a senior CBSE examiner designing DIAGRAM-BASED questions.\n\n"
    "For each question you must specify both the diagram to be drawn and the "
    "question asked about it.\n\n"
    "Rules for `diagram_prompt` — this text is sent verbatim to an image "
    "generator, so it must be self-contained and unambiguous:\n"
    "  • Describe a clean, black-and-white, textbook-style scientific diagram "
    "on a plain white background.\n"
    "  • Name every component and every label that must appear.\n"
    "  • State spatial relationships explicitly (what is left of what, what "
    "connects to what, direction of arrows).\n"
    "  • Never ask for photorealism, shading, colour gradients, or decoration.\n"
    "  • Never request text that the question itself must supply as the answer "
    "— if the question asks a student to identify part X, do not label X.\n\n"
    "Rules for the question:\n"
    "  • It must be answerable from the diagram you described, using only "
    "concepts present in the chapter.\n"
    "  • Refer to the figure as 'the given figure'.\n"
    "  • `answer` is what a marking scheme accepts; `explanation` is why.\n\n"
    "Every figure-based question MUST also carry `vi_alternative`: a "
    "self-contained, text-only version of the same question for visually "
    "impaired students, testing the same concept for the same marks without "
    "referring to any figure. CBSE requires this on picture and map questions.\n\n"
    "Return ONLY a JSON array. Each element:\n"
    "{\n"
    '  "topic": "<concept within the chapter>",\n'
    '  "diagram_prompt": "<what the image generator should draw>",\n'
    '  "type": "DIAGRAM",\n'
    '  "blooms": "REMEMBER|UNDERSTAND|APPLY|ANALYZE|EVALUATE|CREATE",\n'
    '  "difficulty": "easy|medium|hard",\n'
    '  "marks": <integer>,\n'
    '  "question": "<the question text>",\n'
    '  "options": ["<A>", "<B>", "<C>", "<D>"],\n'
    '  "answer": "<expected answer>",\n'
    '  "explanation": "<why>",\n'
    '  "vi_alternative": "<text-only version of the same question>"\n'
    "}\n"
    "Use `options` only when the question is multiple-choice; otherwise send []."
)


_REUSE_SYSTEM_PROMPT = (
    "You are a senior CBSE examiner writing questions about figures that "
    "already appear in a textbook chapter.\n\n"
    "You are given a numbered list of figures with their captions. Write one "
    "question per figure you choose, and set `figure_number` to that figure's "
    "number so the question can be attached to the right image.\n\n"
    "Rules:\n"
    "  • The question must be answerable from what the caption describes. Do "
    "not invent details the caption does not mention.\n"
    "  • Refer to the figure as 'the given figure'.\n"
    "  • Skip any figure whose caption is too vague to build a fair question "
    "on — a bad question is worse than one fewer question.\n"
    "  • `answer` is what a marking scheme accepts; `explanation` is why.\n"
    "  • Every question MUST carry `vi_alternative`: a self-contained, "
    "text-only version testing the same concept for the same marks, with no "
    "reference to any figure. CBSE requires this on picture and map "
    "questions.\n\n"
    "Return ONLY a JSON array. Each element:\n"
    "{\n"
    '  "figure_number": <integer>,\n'
    '  "topic": "<concept>",\n'
    '  "type": "DIAGRAM",\n'
    '  "blooms": "REMEMBER|UNDERSTAND|APPLY|ANALYZE|EVALUATE|CREATE",\n'
    '  "difficulty": "easy|medium|hard",\n'
    '  "marks": <integer>,\n'
    '  "question": "<the question text>",\n'
    '  "options": [],\n'
    '  "answer": "<expected answer>",\n'
    '  "explanation": "<why>",\n'
    '  "vi_alternative": "<text-only version of the same question>"\n'
    "}"
)


def _propose_specs(
    *,
    chapter: ChapterMarkdown,
    subject: str,
    class_num: int,
    difficulty: str,
    count: int,
    provider: OpenAIProvider,
    model: str,
    user=None,
) -> List[Dict[str, Any]]:
    """Ask the text model for `count` diagram specs."""
    instruction = (
        f"Design exactly {count} diagram-based questions for a Class {class_num} "
        f"{subject} paper at '{difficulty}' difficulty. Spread them across "
        "different concepts in the chapter — do not draw variations of the same "
        "diagram."
    )
    request = LLMRequest(
        model=model,
        messages=[
            LLMMessage(role="system", content=_SPEC_SYSTEM_PROMPT),
            LLMMessage(
                role="user",
                content=f"# CHAPTER SOURCE MATERIAL\n\n{chapter.markdown}",
            ),
            LLMMessage(role="user", content=instruction),
        ],
        max_output_tokens=max(2000, count * 400),
        user=user,
        operation="pool_image_specs",
    )

    buffer: List[str] = []
    for delta in provider.stream_chat(request):
        buffer.append(delta)
    return parse_question_payload("".join(buffer))


def _propose_reuse_questions(
    *,
    figures: Sequence[Figure],
    subject: str,
    class_num: int,
    difficulty: str,
    count: int,
    provider: OpenAIProvider,
    model: str,
    user=None,
) -> List[Dict[str, Any]]:
    """Author questions about figures already present in the chapter.

    Works from the captions produced at ingest time rather than re-sending the
    images to a vision model: the captions were themselves written by a vision
    model against the real figure, so a second vision pass would pay twice for
    the same information.
    """
    listing = "\n".join(
        f"{index}. {figure.caption or '(no caption available)'}"
        for index, figure in enumerate(figures, start=1)
    )
    instruction = (
        f"Write up to {count} questions for a Class {class_num} {subject} paper "
        f"at '{difficulty}' difficulty, using these figures:\n\n{listing}"
    )
    request = LLMRequest(
        model=model,
        messages=[
            LLMMessage(role="system", content=_REUSE_SYSTEM_PROMPT),
            LLMMessage(role="user", content=instruction),
        ],
        max_output_tokens=max(2000, count * 350),
        user=user,
        operation="pool_image_reuse",
    )

    buffer: List[str] = []
    for delta in provider.stream_chat(request):
        buffer.append(delta)
    return parse_question_payload("".join(buffer))


# ── Stage 2: draw ───────────────────────────────────────────────────────


def _diagram_storage_path(prompt: str) -> str:
    digest = hashlib.sha256(prompt.strip().encode("utf-8")).hexdigest()[:32]
    return f"{_DIAGRAM_PREFIX}/{digest}.png"


def _generate_diagram(prompt: str, *, user=None) -> tuple[Optional[str], bool, Optional[str]]:
    """Draw one diagram. Returns (stable_url, was_cache_hit, error).

    Cached by prompt hash: an identical diagram_prompt reuses the stored PNG
    instead of paying for a second render. Chapters get regenerated often, and
    the spec model is fairly stable in how it words a given diagram, so this
    hits more than it might appear.
    """
    path = _diagram_storage_path(prompt)

    try:
        if default_storage.exists(path):
            return stable_media_url(path), True, None
    except Exception as exc:
        # A storage backend that cannot answer exists() is not a reason to
        # abandon the question — fall through and regenerate.
        logger.debug("Could not check diagram cache for %s: %s", path, exc)

    try:
        client = get_openai_client()
        generate_kwargs: Dict[str, Any] = {
            "model": _image_model(),
            "prompt": prompt,
            "size": _image_size(),
            "n": 1,
        }
        # gpt-image-1 exposes a low|medium|high quality tier; "low" is the
        # cheapest and stays legible for schematic diagrams. dall-e models use a
        # different vocabulary (standard|hd), so only pass quality for
        # gpt-image-1 to avoid a BadRequestError on other image models.
        if _image_model().startswith("gpt-image"):
            generate_kwargs["quality"] = _image_quality()
        response = client.images.generate(**generate_kwargs)
    except Exception as exc:
        return None, False, f"{type(exc).__name__}: {exc}"

    data = getattr(response, "data", None) or []
    if not data:
        return None, False, "image model returned no data"

    b64 = getattr(data[0], "b64_json", None)
    if not b64:
        # Some deployments return a URL instead of inline bytes.
        url = getattr(data[0], "url", None)
        if not url:
            return None, False, "image model returned neither b64_json nor url"
        try:
            import urllib.request

            with urllib.request.urlopen(url, timeout=30) as handle:
                raw = handle.read()
        except Exception as exc:
            return None, False, f"could not fetch generated image: {exc}"
    else:
        try:
            raw = base64.b64decode(b64)
        except Exception as exc:
            return None, False, f"could not decode generated image: {exc}"

    if not raw:
        return None, False, "generated image was empty"

    try:
        stored_path = default_storage.save(path, ContentFile(raw))
    except Exception as exc:
        return None, False, f"could not store generated image: {exc}"

    # Persist only the stable /media/<key> URL. A presigned URL saved here
    # would be long expired by the time a teacher opens the paper.
    return stable_media_url(stored_path), False, None


# ── Orchestration ───────────────────────────────────────────────────────


def _build_question(
    raw: Dict[str, Any],
    *,
    subject: str,
    chapter_name: str,
    pool_id: str,
    difficulty: str,
    image_url: Optional[str],
    source_type: str,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> Optional[PoolQuestion]:
    payload = dict(raw)
    payload["type"] = payload.get("type") or "DIAGRAM"
    payload["image"] = image_url
    try:
        question = normalize_pool_question(
            payload,
            subject=subject,
            chapter=chapter_name,
            pool_id=pool_id,
            default_difficulty=difficulty,
            source_type=source_type,
        )
    except PoolValidationError as exc:
        logger.debug("Dropped an image question: %s", exc)
        return None

    question.metadata.update(extra_metadata or {})
    return question


def _run_generate(
    *,
    chapter: ChapterMarkdown,
    subject: str,
    chapter_name: str,
    class_num: int,
    difficulty: str,
    pool_id: str,
    count: int,
    provider: OpenAIProvider,
    model: str,
    user,
    result: ImageQuestionResult,
    on_question: Optional[Callable[[PoolQuestion], None]],
) -> None:
    try:
        specs = _propose_specs(
            chapter=chapter, subject=subject, class_num=class_num,
            difficulty=difficulty, count=count, provider=provider,
            model=model, user=user,
        )
    except Exception as exc:
        result.failures.append(f"spec generation failed: {exc}")
        return

    specs = [s for s in specs if str(s.get("diagram_prompt") or "").strip()][:count]
    if not specs:
        result.failures.append("no usable diagram specs were proposed")
        return

    def _draw(spec: Dict[str, Any]):
        prompt = str(spec["diagram_prompt"]).strip()
        url, cached, error = _generate_diagram(prompt, user=user)
        return spec, url, cached, error

    with ThreadPoolExecutor(max_workers=_IMAGE_CONCURRENCY) as executor:
        futures = [executor.submit(_draw, spec) for spec in specs]
        for future in as_completed(futures):
            try:
                spec, url, cached, error = future.result()
            except Exception as exc:
                result.failures.append(f"diagram worker crashed: {exc}")
                continue

            if error or not url:
                result.failures.append(f"diagram failed: {error}")
                continue

            question = _build_question(
                spec,
                subject=subject,
                chapter_name=chapter_name,
                pool_id=pool_id,
                difficulty=difficulty,
                image_url=url,
                source_type="synthetic_image",
                extra_metadata={
                    "imagePrompt": str(spec.get("diagram_prompt") or ""),
                    "imageModel": _image_model(),
                    "syntheticImage": True,
                    # Surfaced in the review tray: a teacher must eyeball an
                    # AI-drawn diagram before it goes on a real paper.
                    "requiresReview": True,
                },
            )
            if not question:
                continue

            if cached:
                result.cache_hits += 1
            else:
                result.generated_count += 1
                result.estimated_cost_usd += float(
                    getattr(settings, "IMAGE_COST_USD_PER_IMAGE", 0.04)
                )

            result.questions.append(question)
            if on_question:
                on_question(question)


def _run_reuse(
    *,
    chapter: ChapterMarkdown,
    subject: str,
    chapter_name: str,
    class_num: int,
    difficulty: str,
    pool_id: str,
    count: int,
    provider: OpenAIProvider,
    model: str,
    user,
    result: ImageQuestionResult,
    on_question: Optional[Callable[[PoolQuestion], None]],
) -> int:
    """Author questions about the chapter's own figures. Returns how many were made."""
    usable = [f for f in chapter.figures if f.url and (f.caption or "").strip()]
    if not usable:
        return 0

    try:
        raw_questions = _propose_reuse_questions(
            figures=usable, subject=subject, class_num=class_num,
            difficulty=difficulty, count=count, provider=provider,
            model=model, user=user,
        )
    except Exception as exc:
        result.failures.append(f"reuse authoring failed: {exc}")
        return 0

    made = 0
    for raw in raw_questions:
        if made >= count:
            break
        try:
            index = int(raw.get("figure_number") or 0)
        except (TypeError, ValueError):
            continue
        if not 1 <= index <= len(usable):
            continue

        figure = usable[index - 1]
        question = _build_question(
            raw,
            subject=subject,
            chapter_name=chapter_name,
            pool_id=pool_id,
            difficulty=difficulty,
            image_url=figure.url,
            source_type="chapter_figure",
            extra_metadata={
                "figurePage": figure.page,
                "figureCaption": figure.caption,
                "sourcePdf": figure.source_pdf,
                "syntheticImage": False,
            },
        )
        if not question:
            continue

        result.questions.append(question)
        result.reused_count += 1
        made += 1
        if on_question:
            on_question(question)

    return made


def generate_image_questions(
    *,
    chapter: ChapterMarkdown,
    subject: str,
    chapter_name: str,
    class_num: int,
    pool_id: str,
    difficulty: str = "medium",
    count: Optional[int] = None,
    strategy: Optional[str] = None,
    model: Optional[str] = None,
    user=None,
    on_question: Optional[Callable[[PoolQuestion], None]] = None,
) -> ImageQuestionResult:
    """Produce image-bearing questions and add them to the pool.

    Never raises: an image stage that fails must not take the text pool down
    with it. Failures are collected on the result for the caller to surface.
    """
    result = ImageQuestionResult()

    target = _image_cap() if count is None else max(0, count)
    if target == 0:
        return result
    if chapter.is_empty:
        result.failures.append("chapter source material is empty")
        return result

    resolved_strategy = (strategy or resolve_strategy()).lower()
    resolved_model = model or getattr(settings, "POOL_MODEL", settings.OPENAI_MODEL)
    provider = OpenAIProvider()

    started = time.monotonic()
    logger.info(
        "Image stage starting: pool=%s strategy=%s target=%d figures_available=%d",
        pool_id, resolved_strategy, target, len(chapter.figures),
    )

    common = dict(
        chapter=chapter, subject=subject, chapter_name=chapter_name,
        class_num=class_num, difficulty=difficulty, pool_id=pool_id,
        provider=provider, model=resolved_model, user=user,
        result=result, on_question=on_question,
    )

    try:
        if resolved_strategy == STRATEGY_REUSE:
            _run_reuse(count=target, **common)
        elif resolved_strategy == STRATEGY_HYBRID:
            # Real figures first; synthesise only what the chapter cannot cover.
            reused = _run_reuse(count=target, **common)
            remaining = target - reused
            if remaining > 0:
                _run_generate(count=remaining, **common)
        else:
            _run_generate(count=target, **common)
    except Exception as exc:
        # Defensive: the stage is optional, so nothing here may propagate.
        logger.error("Image stage crashed: %s", exc, exc_info=True)
        result.failures.append(str(exc))

    logger.info(
        "Image stage finished: pool=%s produced=%d (generated=%d reused=%d "
        "cached=%d) est_cost=$%.2f failures=%d in %.1fs",
        pool_id, result.total, result.generated_count, result.reused_count,
        result.cache_hits, result.estimated_cost_usd, len(result.failures),
        time.monotonic() - started,
    )

    return result
