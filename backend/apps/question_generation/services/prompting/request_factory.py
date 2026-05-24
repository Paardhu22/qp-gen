from typing import Any, List, Optional

from django.conf import settings

from ...domain.context import GenerationContext
from ...infrastructure.providers.base import LLMMessage, LLMRequest
from ...domain.prompts.spec import PromptDocument


class LLMRequestFactory:
    def build(
        self,
        prompt: PromptDocument,
        user_prompt: str,
        model: Optional[str] = None,
        image_urls: Optional[List[str]] = None,
    ) -> LLMRequest:
        user_content: Any = user_prompt
        if image_urls:
            user_content = [{"type": "text", "text": user_prompt}]
            user_content.extend(
                {"type": "image_url", "image_url": {"url": image_url}}
                for image_url in image_urls
            )

        return LLMRequest(
            model=model or settings.OPENAI_MODEL,
            messages=[
                LLMMessage(role="system", content=prompt.render()),
                LLMMessage(role="user", content=user_content),
            ],
            response_format={"type": "json_object"},
            stream=True,
            stream_options={"include_usage": True},
        )
