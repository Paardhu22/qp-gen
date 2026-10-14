from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


@dataclass(frozen=True)
class LLMMessage:
    role: str
    content: Any


@dataclass(frozen=True)
class LLMRequest:
    model: str
    messages: List[LLMMessage]
    response_format: Optional[Dict[str, str]] = None
    stream: bool = False
    stream_options: Optional[Dict[str, object]] = None
    #: Completion-length cap. Previously the pipeline computed per-slot
    #: budgets (see _slot_output_budget) but had nowhere to put them, so every
    #: call silently ran at the provider default — which is exactly how a
    #: 4-mark case study came out truncated mid-sentence. The provider
    #: translates this to `max_tokens` or `max_completion_tokens` depending on
    #: the model family.
    max_output_tokens: Optional[int] = None
    #: Attribution for ApiUsage rows. Without it every call is logged against
    #: a null user and per-user cost is unknowable.
    user: Optional[Any] = None
    #: Labels the ApiUsage row so pool generation, image authoring and paper
    #: assembly can be costed separately.
    operation: str = "question_generation"


@dataclass(frozen=True)
class LLMResponse:
    content: str
    usage: Optional[object] = None


class LLMProvider(ABC):
    @abstractmethod
    def chat(self, request: LLMRequest) -> LLMResponse:
        ...

    @abstractmethod
    def stream_chat(self, request: LLMRequest) -> Iterable[str]:
        ...
