"""
AOS Subjects — Subject Plugin Registry
=========================================
Manages registration and lookup of subject plugins.
Depends only on core.interfaces.
"""

from typing import Dict

from q_instructions.core.interfaces import ISubjectPlugin
from q_instructions.core.exceptions import SubjectNotRegisteredError


class SubjectRegistry:
    """Central registry for all subject plugins (Science, Math, Social, etc.)."""

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
