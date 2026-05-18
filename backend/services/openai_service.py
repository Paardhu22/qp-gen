from typing import Optional

from django.conf import settings
from openai import OpenAI

from apps.accounts.models import User
from apps.generation.models import ApiUsage

_client: Optional[OpenAI] = None


def get_openai_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.OPENAI_API_KEY)
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
