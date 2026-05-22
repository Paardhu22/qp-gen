from typing import Dict

from ..exceptions import SubjectNotRegisteredError
from .base import SubjectBundle
from .science.subject import ScienceInstructionSet


class SubjectRegistry:
    def __init__(self) -> None:
        self._registry: Dict[str, SubjectBundle] = {}
        self._initialize_defaults()

    def _initialize_defaults(self) -> None:
        science = ScienceInstructionSet()
        self.register(science.subject_name(), science.bundle())

    def register(self, subject_name: str, bundle: SubjectBundle) -> None:
        self._registry[subject_name.lower()] = bundle

    def get(self, subject_name: str) -> SubjectBundle:
        key = subject_name.lower()
        if key not in self._registry:
            raise SubjectNotRegisteredError(subject_name)
        return self._registry[key]
