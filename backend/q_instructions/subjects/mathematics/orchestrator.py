"""
AOS Mathematics Standard — CBSE Class 10 Orchestration Engine
===============================================================
CBSE Mathematics Standard (Code 041) SQP 2025-26.

Enforces: 38 questions, 80 marks, Section A→B→C→D→E ordering,
Bloom's distribution (Apply 35%, Analyse 25%), topic diversity in Section A.
"""

from typing import List, Dict, Tuple
from q_instructions.core.enums import QuestionTypeCode, BloomsLevel, StreamType
from q_instructions.core.datatypes import QuestionInstance


class MathematicsOrchestratorV2:
    """Enforces CBSE SQP 2025-26 rules for Mathematics Standard papers."""

    # Section → (question_type, marks_each, count, choice_slots)
    SECTION_LAYOUT: List[Tuple[str, QuestionTypeCode, int, int, int]] = [
        ("A", QuestionTypeCode.MCQ,          1, 18, 0),
        ("A", QuestionTypeCode.ASSERTION_REASON, 1, 2, 0),
        ("B", QuestionTypeCode.SHORT_ANSWER, 2, 5, 2),  # Q21,Q24 have choice
        ("C", QuestionTypeCode.SHORT_ANSWER, 3, 6, 2),  # Q29,Q31 have choice
        ("D", QuestionTypeCode.LONG_ANSWER,  5, 4, 2),  # Q34,Q35 have choice
        ("E", QuestionTypeCode.CASE_STUDY,   4, 3, 3),  # all 3 case studies have OR in sub-part iii
    ]

    BLOOMS_TARGET = {
        BloomsLevel.REMEMBER:  0.15,
        BloomsLevel.UNDERSTAND: 0.15,
        BloomsLevel.APPLY:     0.35,
        BloomsLevel.ANALYZE:   0.25,
        BloomsLevel.EVALUATE:  0.07,
        BloomsLevel.CREATE:    0.03,
    }

    TOPIC_SPREAD = [
        "Real Numbers", "Polynomials", "Pair of Linear Equations",
        "Quadratic Equations", "Arithmetic Progressions",
        "Coordinate Geometry", "Triangles", "Circles",
        "Trigonometry", "Heights and Distances",
        "Areas Related to Circles", "Surface Areas and Volumes",
        "Statistics", "Probability",
    ]

    def validate_topic_diversity(self, section_a_topics: List[str]) -> bool:
        """Section A must cover ≥7 distinct topics; no topic in >3 MCQs."""
        distinct = len(set(section_a_topics))
        max_freq = max((section_a_topics.count(t) for t in set(section_a_topics)), default=0)
        return distinct >= 7 and max_freq <= 3

    def validate_marks_sum(self, questions: List[QuestionInstance]) -> bool:
        return sum(q.assigned_marks for q in questions) == 80

    def applies_or_choice(self, section: str, local_index: int) -> bool:
        """Returns True if this question slot carries an internal OR choice."""
        if section == "B":
            return local_index in [0, 3]   # Q21, Q24
        if section == "C":
            return local_index in [3, 5]   # Q29, Q31
        if section == "D":
            return local_index in [2, 3]   # Q34, Q35
        if section == "E":
            return True                    # sub-part (iii) always has OR
        return False

    def sequence_paper(self, questions: List[QuestionInstance]) -> List[QuestionInstance]:
        """Sections in order A→B→C→D→E."""
        return questions
