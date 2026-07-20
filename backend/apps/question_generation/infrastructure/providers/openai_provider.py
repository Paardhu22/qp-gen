import logging
import re
from typing import Any, Dict, Iterable, Optional

from django.conf import settings
from openai import OpenAI

from .base import LLMMessage, LLMProvider, LLMRequest, LLMResponse
from services.openai_service import _record_usage

logger = logging.getLogger("[OPENAI_PROVIDER]")

#: Reasoning-family models reject `max_tokens` and require
#: `max_completion_tokens` (that limit also covers hidden reasoning tokens).
#: Everything else — gpt-4.1*, gpt-4o* — takes `max_tokens`.
_REASONING_MODEL_RE = re.compile(r"^(gpt-5|o1|o3|o4)", re.IGNORECASE)


def _token_limit_kwarg(model: str, max_output_tokens: Optional[int]) -> Dict[str, Any]:
    if not max_output_tokens or max_output_tokens <= 0:
        return {}
    if _REASONING_MODEL_RE.match(model or ""):
        return {"max_completion_tokens": max_output_tokens}
    return {"max_tokens": max_output_tokens}


class OpenAIProvider(LLMProvider):
    def __init__(self) -> None:
        self._client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def _base_kwargs(self, request: LLMRequest) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {
            "model": request.model,
            "messages": [
                {"role": m.role, "content": m.content} for m in request.messages
            ],
        }
        # The SDK distinguishes "omitted" from "explicitly null" — sending
        # response_format=None is not the same as leaving it out.
        if request.response_format:
            kwargs["response_format"] = request.response_format
        kwargs.update(_token_limit_kwarg(request.model, request.max_output_tokens))
        return kwargs

    def chat(self, request: LLMRequest) -> LLMResponse:
        completion = self._client.chat.completions.create(**self._base_kwargs(request))
        _record_usage(request.user, request.operation, request.model, completion.usage)
        content = completion.choices[0].message.content or ""
        return LLMResponse(content=content, usage=completion.usage)

    def stream_chat(self, request: LLMRequest) -> Iterable[str]:
        kwargs = self._base_kwargs(request)
        kwargs["stream"] = True
        kwargs["stream_options"] = request.stream_options or {"include_usage": True}

        stream = self._client.chat.completions.create(**kwargs)

        usage = None
        finish_reason = None
        for chunk in stream:
            # The usage-bearing chunk arrives last and carries no choices.
            if getattr(chunk, "usage", None):
                usage = chunk.usage
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            if getattr(choice, "finish_reason", None):
                finish_reason = choice.finish_reason
            delta = choice.delta.content or ""
            if delta:
                yield delta

        # Recorded once the stream drains. Streamed calls previously logged no
        # ApiUsage at all, which made the bulk of the spend invisible.
        _record_usage(request.user, request.operation, request.model, usage)

        if finish_reason == "length":
            logger.warning(
                "Response hit the completion cap (model=%s, max_output_tokens=%s, "
                "operation=%s). Output is truncated — raise the batch budget.",
                request.model, request.max_output_tokens, request.operation,
            )
