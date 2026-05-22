import random
from typing import List, Set

from ..board_systems.cbse.templates import QuestionTemplateLibrary
from ..datatypes import QuestionTemplate
from ..enums import BloomsLevel, QuestionTypeCode


class IntelligentTemplateSelector:
    def __init__(self, library: QuestionTemplateLibrary):
        self._library = library
        self._used_ids: Set[str] = set()

    def select(self, qtype: QuestionTypeCode, target_bloom: BloomsLevel | None = None) -> QuestionTemplate:
        templates = self._library.get_templates_by_type(qtype)
        if not templates:
            return self._library.get_all_templates()[0]

        scored: List[tuple[int, QuestionTemplate]] = []
        for t in templates:
            score = 0
            if t.template_id not in self._used_ids:
                score += 100
            if target_bloom and t.target_bloom == target_bloom:
                score += 50
            scored.append((score, t))

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score = scored[0][0]
        best_templates = [t for s, t in scored if s == best_score]
        selected = random.choice(best_templates)
        self._used_ids.add(selected.template_id)
        return selected
