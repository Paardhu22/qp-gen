from typing import Optional

from django.conf import settings
from openai import OpenAI

from apps.accounts.models import User
from apps.generation.models import ApiUsage

_client: Optional[OpenAI] = None


def get_openai_client() -> OpenAI:
    global _client
    if _client is None:
        # max_retries=5 lets the SDK absorb transient 429 / 5xx hiccups
        # without bubbling failures up to the ingestion or generation
        # pipelines. Combined with detail="low" on vision calls, this
        # keeps captioning well inside Tier 1 TPM budgets.
        _client = OpenAI(api_key=settings.OPENAI_API_KEY, max_retries=5)
    return _client


def _record_usage(user: Optional[User], operation: str, model: str, usage: object | None) -> None:
    if not usage:
        return

    ApiUsage.objects.create(
        user=user,
        operation=operation,
        model=model,
        prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        total_tokens=getattr(usage, "total_tokens", 0) or 0,
    )


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

    completion = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt},
        ],
    )

    content = completion.choices[0].message.content
    _record_usage(user, "answer_key", settings.OPENAI_MODEL, completion.usage)
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

    Uses ``OPENAI_VISION_MODEL`` (default ``gpt-4o-mini``), NOT the heavier
    ``OPENAI_MODEL`` reasoning model — captioning a textbook visual for
    retrieval only needs the multimodal head, not chain-of-thought. The
    profile in scratch/profile_ingestion.py shows a ~7× per-call latency
    cut from this switch.
    """
    client = get_openai_client()
    context = page_context.strip()
    if len(context) > 1200:
        context = context[:1200]

    model = getattr(settings, "OPENAI_VISION_MODEL", settings.OPENAI_MODEL)
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "Caption textbook visuals for retrieval. Describe only visible academic content, "
                    "labels, entities, map regions, axes, and the likely CBSE concept. Be concise."
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
                            # TPM rate limits within the first 8 concurrent
                            # captioning calls). Retrieval-grade captioning
                            # needs only the gist of the figure, so the
                            # low-detail vision branch is the right fit.
                            "detail": "low",
                        },
                    },
                ],
            },
        ],
    )

    _record_usage(user, "image_caption", model, completion.usage)
    return (completion.choices[0].message.content or "").strip()
