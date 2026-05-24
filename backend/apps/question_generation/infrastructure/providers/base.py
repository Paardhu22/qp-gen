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
