import logging
import re
import threading
import time
from typing import Optional

from django.conf import settings
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
    RateLimitError,
)

from apps.accounts.models import User
from apps.generation.models import ApiUsage

_client: Optional[OpenAI] = None
logger = logging.getLogger("[OPENAI_SERVICE]")

# ── Vision-captioning throughput control ────────────────────────────────
#
# Caption calls are gated by a PROCESS-WIDE semaphore, not a per-chapter
# pool. HSAT ingestion runs chapters in parallel (HSAT_CHAPTER_CONCURRENCY)
# and each chapter used to spin its own 8-thread captioning pool, so the
# real vision concurrency was outer × inner = up to 24 simultaneous gpt-4o
# calls. At ~1,130 tokens per call that slams the 30,000 TPM ceiling within
# seconds and every retry re-collides — the observed wall of 429s. With a
# global cap of 3, in-flight demand is ~3,400 tokens, comfortably inside
# the budget no matter how many chapters ingest at once.
_caption_gate: Optional[threading.BoundedSemaphore] = None
_caption_gate_lock = threading.Lock()

#: Max attempts for one caption call. Combined with exact-wait 429 backoff
#: this absorbs a sustained TPM squeeze without giving up on the image.
_CAPTION_MAX_ATTEMPTS = 6

_RETRY_AFTER_RE = re.compile(r"try again in\s+(\d+(?:\.\d+)?)\s*(ms|s)", re.IGNORECASE)


def _caption_concurrency() -> int:
    return max(1, int(getattr(settings, "PDF_IMAGE_CAPTION_CONCURRENCY", 3)))


def _get_caption_gate() -> threading.BoundedSemaphore:
    global _caption_gate
    with _caption_gate_lock:
        if _caption_gate is None:
            _caption_gate = threading.BoundedSemaphore(_caption_concurrency())
        return _caption_gate


def _rate_limit_wait_seconds(error_message: str) -> float:
    """Sleep exactly as long as OpenAI asks, not a fixed/exponential guess.

    The 429 body carries 'Please try again in 2.3s' (or '...in 350ms').
    Honouring it (+100 ms of slack) drains the token bucket at precisely
    the right cadence instead of re-colliding or oversleeping.
    """
    match = _RETRY_AFTER_RE.search(error_message)
    if not match:
        return 2.0
    value = float(match.group(1))
    if match.group(2).lower() == "ms":
        value /= 1000.0
    return value + 0.1


def get_openai_client() -> OpenAI:
    global _client
    if _client is None:
        # max_retries=5 lets the SDK absorb transient 429 / 5xx hiccups
        # without bubbling failures up to the ingestion or generation
        # pipelines. Combined with detail="low" on vision calls, this
        # keeps captioning well inside Tier 1 TPM budgets.
        #
        # timeout is explicit because the SDK's default is 600s: a single
        # hung request would outlive gunicorn's worker timeout (the worker is
        # killed mid-stream and the client sees a truncated response) and,
        # with max_retries=5, could in principle occupy a worker for the best
        # part of an hour. A generation call that has produced nothing in
        # OPENAI_TIMEOUT_SECONDS is not going to recover; failing it lets the
        # batch record the failure and the pipeline carry on with the rest.
        _client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            max_retries=5,
            timeout=float(getattr(settings, "OPENAI_TIMEOUT_SECONDS", 120.0)),
        )
    return _client


def _record_usage(user: Optional[User], operation: str, model: str, usage: object | None) -> None:
    if not usage:
        return

    try:
        ApiUsage.objects.create(
            user=user,
            # `billing_organization`, not `organization`: the latter is
            # approval-gated, so a member whose join request had not been
            # approved yet had every call filed as "unassigned" — invisible on
            # the school's dashboard and outside its monthly limit. See
            # apps/accounts/models.User.
            organization=getattr(user, "billing_organization", None),
            operation=operation,
            model=model,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            total_tokens=getattr(usage, "total_tokens", 0) or 0,
        )
    except Exception as exc:
        logger.warning("Failed to record %s usage for %s: %s", operation, model, exc)


def generate_answer_key(paper_content_html: str, user: Optional[User] = None) -> str:
    client = get_openai_client()

    prompt = (
        "You are an expert educator. Here is the HTML content of a question paper:\n\n"
        f"{paper_content_html}\n\n"
        "Please extract all the questions from this paper and generate a comprehensive answer key for it. "
        "Format your response as well-structured HTML (using <h1>, <h2>, <p>, <ul>, <li>, <strong>, etc.) "
        "that can be directly inserted into a rich text editor. "
        "Start with <h1 style=\"text-align: center\">Answer Key</h1>. "
        "Do not include markdown code block wrappers in your output, just return the raw HTML string."
    )

    # Read directly, not `getattr(..., settings.OPENAI_MODEL)`. Every stage
    # model is unconditionally defined in settings, so that fallback could
    # never fire -- but it is the exact inheritance the settings comment
    # forbids, written into the code that comment is about. An attribute that
    # should always exist is better read as one: if it ever goes missing, an
    # AttributeError names the problem instead of a 30k-TPM model quietly
    # taking over.
    answer_model = settings.ANSWER_MODEL
    completion = client.chat.completions.create(
        model=answer_model,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt},
        ],
    )

    content = completion.choices[0].message.content
    _record_usage(user, "answer_key", answer_model, completion.usage)
    return content or ""


def caption_image_for_embedding(
    image_data_url: str,
    page_context: str = "",
    user: Optional[User] = None,
) -> str:
    """
    Produce a concise hidden caption used only for vector retrieval.

    The stored chunk embeds this caption while the public question payload keeps
    the original image_url in metadata for later multimodal generation.

    Uses ``OPENAI_VISION_MODEL`` (default ``gpt-4o``), NOT the heavier
    ``OPENAI_MODEL`` reasoning model — captioning a textbook visual for
    retrieval only needs the multimodal head, not chain-of-thought. The
    profile in scratch/profile_ingestion.py shows a ~7× per-call latency
    cut from this switch.
    """
    # max_retries=0: this loop owns retry timing. The SDK's generic
    # exponential backoff neither parses the 'try again in Xs' hint nor
    # coordinates with the global gate, so its retries re-collided with
    # the other in-flight captions.
    client = get_openai_client().with_options(max_retries=0)
    context = page_context.strip()
    if len(context) > 1200:
        context = context[:1200]

    model = getattr(settings, "OPENAI_VISION_MODEL", settings.OPENAI_MODEL)
    messages = [
        {
            "role": "system",
            "content": (
                "Caption textbook visuals for retrieval. Describe only visible academic content, "
                "labels, entities, map regions, axes, and the likely CBSE concept. Be concise. "
                "Describe what the diagram shows in one or two FULL SENTENCES of prose. "
                "Never reply with just label names, single letters, or symbols "
                "(e.g. 'A', 'ΔB', '∠ABC') — that is residue, not a caption."
            ),
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Create a hidden retrieval caption for this textbook image. "
                        f"Nearby page text: {context or 'None'}"
                    ),
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image_data_url,
                        # `detail: "low"` bills a flat 85 tokens per
                        # image instead of tiling the source at full
                        # resolution (a 2480×3508 PDF page costs
                        # ~9,000 tokens at default detail, which slams
                        # TPM rate limits within the first few concurrent
                        # captioning calls). Retrieval-grade captioning
                        # needs only the gist of the figure, so the
                        # low-detail vision branch is the right fit.
                        "detail": "low",
                    },
                },
            ],
        },
    ]

    gate = _get_caption_gate()
    last_exc: Optional[Exception] = None
    for attempt in range(1, _CAPTION_MAX_ATTEMPTS + 1):
        # Hold a gate slot only while a request is actually in flight —
        # sleeping inside the gate would let one rate-limited call starve
        # the other caption workers.
        with gate:
            try:
                completion = client.chat.completions.create(
                    model=model, messages=messages
                )
                _record_usage(user, "image_caption", model, completion.usage)
                return (completion.choices[0].message.content or "").strip()
            except RateLimitError as exc:
                last_exc = exc
                wait = _rate_limit_wait_seconds(str(exc))
            except (APIConnectionError, APITimeoutError) as exc:
                last_exc = exc
                wait = min(1.0 * (2 ** (attempt - 1)), 8.0)
            except APIStatusError as exc:
                if exc.status_code < 500:
                    raise
                last_exc = exc
                wait = min(1.0 * (2 ** (attempt - 1)), 8.0)
        if attempt >= _CAPTION_MAX_ATTEMPTS:
            break
        logger.info(
            "Caption retry %s/%s in %.2fs after %s",
            attempt,
            _CAPTION_MAX_ATTEMPTS,
            wait,
            type(last_exc).__name__,
        )
        time.sleep(wait)

    assert last_exc is not None
    raise last_exc
