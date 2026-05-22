from dataclasses import dataclass
from typing import Protocol

from ..interfaces import ISubjectPlugin


class SubjectInstructionSet(Protocol):
    def subject_name(self) -> str:
        ...

    def plugin(self) -> ISubjectPlugin:
        ...


@dataclass(frozen=True)
class SubjectBundle:
    name: str
    plugin: ISubjectPlugin
