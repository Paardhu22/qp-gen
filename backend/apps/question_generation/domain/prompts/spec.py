from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class PromptVersion:
    version_id: str
    description: str


@dataclass(frozen=True)
class PromptSection:
    title: str
    content: str


@dataclass(frozen=True)
class PromptDocument:
    version: PromptVersion
    sections: List[PromptSection] = field(default_factory=list)

    def render(self) -> str:
        parts: List[str] = []
        for section in self.sections:
            header = f"{section.title.strip()}"
            content = section.content.strip()
            parts.append(f"{header}\n{content}")
        return "\n\n".join(parts)
