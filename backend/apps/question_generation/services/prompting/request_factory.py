from typing import Optional

from django.conf import settings

from ...domain.context import GenerationContext
from ...infrastructure.providers.base import LLMMessage, LLMRequest
from ...domain.prompts.spec import PromptDocument


class LLMRequestFactory:
    def build(self, prompt: PromptDocument, user_prompt: str, model: Optional[str] = None) -> LLMRequest:
        return LLMRequest(
            model=model or settings.OPENAI_MODEL,
            messages=[
                LLMMessage(role="system", content=prompt.render()),
                LLMMessage(role="user", content=user_prompt),
            ],
            response_format={"type": "json_object"},
            stream=True,
            stream_options={"include_usage": True},
        )
