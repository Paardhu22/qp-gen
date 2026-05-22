"""
AOS Orchestration — Internal Choice & Equivalence Engine
===========================================================
Implements cognitive equivalence rules for internal choices (OR questions).
Ensures paired options have identical difficulty, cognitive load, and marks.
"""

from typing import List

from q_instructions.core.enums import QuestionTypeCode, BloomsLevel
from q_instructions.core.datatypes import QuestionInstance, InternalChoiceOption
from q_instructions.core.interfaces import IChoiceEquivalenceRule


class MarksEquivalenceRule(IChoiceEquivalenceRule):
    """Enforces that paired choice questions have identical marks."""

    def is_equivalent(self, q1: QuestionInstance, q2: QuestionInstance) -> bool:
        return q1.assigned_marks == q2.assigned_marks


class StreamEquivalenceRule(IChoiceEquivalenceRule):
    """Enforces that paired questions are from the same subject stream."""

    def is_equivalent(self, q1: QuestionInstance, q2: QuestionInstance) -> bool:
        return q1.stream == q2.stream


class BloomsEquivalenceRule(IChoiceEquivalenceRule):
    """Enforces identical Bloom's cognitive taxonomy level for choices."""

    def is_equivalent(self, q1: QuestionInstance, q2: QuestionInstance) -> bool:
        return q1.blooms_level == q2.blooms_level


class DiagrammaticEquivalenceRule(IChoiceEquivalenceRule):
    """Enforces matching diagram requirements (both require drawing, or neither do)."""

    def is_equivalent(self, q1: QuestionInstance, q2: QuestionInstance) -> bool:
        q1_diag = q1.question_type == QuestionTypeCode.DIAGRAM or "draw" in q1.content_text.lower()
        q2_diag = q2.question_type == QuestionTypeCode.DIAGRAM or "draw" in q2.content_text.lower()
        return q1_diag == q2_diag


class ChoiceEquivalenceValidator:
    """Validator compiling all choice equivalence checks."""

    def __init__(self) -> None:
        self._rules: List[IChoiceEquivalenceRule] = [
            MarksEquivalenceRule(),
            StreamEquivalenceRule(),
            BloomsEquivalenceRule(),
            DiagrammaticEquivalenceRule()
        ]

    def validate_choice(self, q1: QuestionInstance, q2: QuestionInstance) -> bool:
        """Runs all equivalence checks on paired option questions."""
        return all(rule.is_equivalent(q1, q2) for rule in self._rules)


class InternalChoiceEngine:
    """Pairs questions and generates valid internal choices for the paper."""

    def __init__(self) -> None:
        self.validator = ChoiceEquivalenceValidator()

    def pair_questions(
        self, available: List[QuestionInstance], section_id: str, max_pairs: int = 2
    ) -> List[InternalChoiceOption]:
        """Pairs compatible questions from available set into internal choices."""
        pairs: List[InternalChoiceOption] = []
        used = set()

        for i, q1 in enumerate(available):
            if q1.question_id in used:
                continue

            for j, q2 in enumerate(available[i+1:], start=i+1):
                if q2.question_id in used:
                    continue

                if self.validator.validate_choice(q1, q2):
                    pairs.append(InternalChoiceOption(q1, q2, section_id))
                    used.add(q1.question_id)
                    used.add(q2.question_id)
                    break

            if len(pairs) >= max_pairs:
                break

        return pairs
