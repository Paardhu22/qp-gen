"""
AOS Subjects — Subject Plugin Registry
=========================================
Manages registration and lookup of subject plugins.
Depends only on core.interfaces.

New subjects registered here: Mathematics (041), English (184), Hindi (085), Telugu (089).
"""

from typing import Dict

from q_instructions.core.interfaces import ISubjectPlugin
from q_instructions.core.exceptions import SubjectNotRegisteredError


class SubjectRegistry:
    """Central registry for all subject plugins (Science, Math, Social, English, Hindi, Telugu)."""

    def __init__(self) -> None:
        self._plugins: Dict[str, ISubjectPlugin] = {}

    def register(self, plugin: ISubjectPlugin) -> None:
        """Registers a subject plugin by its canonical name."""
        self._plugins[plugin.get_subject_name().lower()] = plugin

    def get(self, subject_name: str) -> ISubjectPlugin:
        """Retrieves a registered subject plugin."""
        key = subject_name.lower()
        if key not in self._plugins:
            raise SubjectNotRegisteredError(subject_name)
        return self._plugins[key]

    def list_subjects(self) -> list:
        """Lists all registered subject names."""
        return list(self._plugins.keys())


def build_default_registry() -> SubjectRegistry:
    """
    Constructs a SubjectRegistry pre-loaded with all known subject plugins.
    Imports are deferred to avoid circular import chains and side effects on module load.
    """
    from q_instructions.subjects.science.science import SciencePlugin
    from q_instructions.subjects.mathematics.mathematics import MathematicsPlugin
    from q_instructions.subjects.english.english import EnglishPlugin
    from q_instructions.subjects.hindi.hindi import HindiPlugin
    from q_instructions.subjects.telugu.telugu import TeluguPlugin

    reg = SubjectRegistry()
    reg.register(SciencePlugin())
    reg.register(MathematicsPlugin())
    reg.register(EnglishPlugin())
    reg.register(HindiPlugin())
    reg.register(TeluguPlugin())
    return reg
