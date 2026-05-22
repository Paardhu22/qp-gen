from typing import Iterable

from django.conf import settings
from openai import OpenAI

from .base import LLMMessage, LLMProvider, LLMRequest, LLMResponse
from services.openai_service import _record_usage


class OpenAIProvider(LLMProvider):
    def __init__(self) -> None:
        self._client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def chat(self, request: LLMRequest) -> LLMResponse:
        completion = self._client.chat.completions.create(
            model=request.model,
            messages=[{"role": m.role, "content": m.content} for m in request.messages],
            response_format=request.response_format,
        )
        _record_usage(None, "question_generation", request.model, completion.usage)
        content = completion.choices[0].message.content or ""
        return LLMResponse(content=content, usage=completion.usage)

    def stream_chat(self, request: LLMRequest) -> Iterable[str]:
        stream = self._client.chat.completions.create(
            model=request.model,
            messages=[{"role": m.role, "content": m.content} for m in request.messages],
            response_format=request.response_format,
            stream=True,
            stream_options=request.stream_options or {"include_usage": True},
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content or ""
            if delta:
                yield delta
