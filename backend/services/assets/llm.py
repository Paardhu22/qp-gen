"""One JSON call, retried, shared by every asset generator.

Deliberately much simpler than `pool.model1`: an asset call carries no chapter,
so the prompts are small, the responses are short, and there is no need for
streaming, prefix-cache-friendly message ordering, or a process-wide request
gate. What is shared with Model 1 is the response parser, so a fenced or
wrapper-object reply is salvaged the same way in both places.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

from django.conf import settings

from apps.question_generation.infrastructure.providers.base import (
    LLMMessage,
    LLMRequest,
)
from apps.question_generation.infrastructure.providers.openai_provider import (
    OpenAIProvider,
)
from services.pool.streaming import parse_question_payload

logger = logging.getLogger("[ASSETS]")

#: Attempts per call. Assets are few and each one owns a whole section of the
#: paper, so a retry is far cheaper than a missing Reading section.
MAX_ATTEMPTS = 3


class AssetLLMError(RuntimeError):
    """The model could not be made to return usable JSON."""


def resolve_model(explicit: Optional[str] = None) -> str:
    if explicit:
        return explicit
    return getattr(settings, "ASSET_MODEL", "") or getattr(
        settings, "POOL_MODEL", getattr(settings, "OPENAI_MODEL", "gpt-4.1-mini")
    )


def request_objects(
    *,
    system: str,
    instruction: str,
    max_output_tokens: int,
    operation: str,
    model: Optional[str] = None,
    user: Any = None,
    provider: Optional[OpenAIProvider] = None,
    wrapper_key: str = "items",
) -> List[Dict[str, Any]]:
    """Ask for a JSON array and return the objects in it.

    `wrapper_key` names the array inside the returned object — the JSON-object
    response format cannot return a bare array, so every generator asks for
    `{"<wrapper_key>": [...]}` and the parser unwraps it.
    """
    provider = provider or OpenAIProvider()
    resolved = resolve_model(model)
    request = LLMRequest(
        model=resolved,
        messages=[
            LLMMessage(role="system", content=system),
            LLMMessage(role="user", content=instruction),
        ],
        response_format={"type": "json_object"},
        max_output_tokens=max_output_tokens,
        user=user,
        operation=operation,
    )

    last_error = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = provider.chat(request)
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "%s attempt %d/%d failed: %s", operation, attempt, MAX_ATTEMPTS, last_error
            )
            if attempt < MAX_ATTEMPTS:
                time.sleep(min(2 ** (attempt - 1), 8))
            continue

        objects = _unwrap(response.content, wrapper_key)
        if objects:
            return objects

        last_error = "no usable objects in the response"
        logger.warning(
            "%s attempt %d/%d returned nothing parseable.",
            operation, attempt, MAX_ATTEMPTS,
        )

    raise AssetLLMError(f"{operation}: {last_error or 'no response'}")


def _unwrap(content: str, wrapper_key: str) -> List[Dict[str, Any]]:
    """Pull the array out of the response, whatever shape it arrived in."""
    text = (content or "").strip()
    if not text:
        return []

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return parse_question_payload(text)

    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]

    if isinstance(parsed, dict):
        for key in (wrapper_key, "items", "assets", "questions", "tasks", "data"):
            value = parsed.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        # A single un-wrapped asset is a legitimate response to a request for
        # one, so treat the whole object as the sole item.
        return [parsed]

    return []
