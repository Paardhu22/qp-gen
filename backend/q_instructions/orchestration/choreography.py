"""
AOS Orchestration — Section Choreography Engine
===================================================
Orchestrates chronological question ordering, difficulty escalation,
and competency placement within individual sections of an exam paper.
"""

from typing import List

from q_instructions.core.enums import QuestionTypeCode
from q_instructions.core.datatypes import QuestionInstance
from q_instructions.core.interfaces import ISectionChoreographer


class SectionAChoreographer(ISectionChoreographer):
    """Choreographs Section A: Warmup MCQs. Ascending difficulty."""

    def arrange_section(self, questions: List[QuestionInstance]) -> List[QuestionInstance]:
        # Order by ascending marks (should be 1 anyway) and then expected length
        return sorted(questions, key=lambda q: (q.assigned_marks, q.expected_word_count))


class SectionBChoreographer(ISectionChoreographer):
    """Choreographs Section B: Assertion & Reason questions."""

    def arrange_section(self, questions: List[QuestionInstance]) -> List[QuestionInstance]:
        # Assertions usually cluster together, order by word count
        return sorted(questions, key=lambda q: q.expected_word_count)


class SectionCChoreographer(ISectionChoreographer):
    """Choreographs Section C: Short Answer. Warmup → spike → relief."""

    def arrange_section(self, questions: List[QuestionInstance]) -> List[QuestionInstance]:
        if len(questions) <= 2:
            return questions
        # Place longest/hardest in middle, easiest at start/end
        sorted_qs = sorted(questions, key=lambda q: q.expected_word_count)
        result = [sorted_qs[0]]
        # Interleave the rest
        for idx, q in enumerate(sorted_qs[1:]):
            if idx % 2 == 0:
                result.append(q)
            else:
                result.insert(0, q)
        return result


class SectionDChoreographer(ISectionChoreographer):
    """Choreographs Section D: Numerical / Analytical questions."""

    def arrange_section(self, questions: List[QuestionInstance]) -> List[QuestionInstance]:
        # Numerical tasks are structured systematically
        return sorted(questions, key=lambda q: q.assigned_marks)


class SectionEChoreographer(ISectionChoreographer):
    """Choreographs Section E: Case Study / Passages. Paced cognitive relief."""

    def arrange_section(self, questions: List[QuestionInstance]) -> List[QuestionInstance]:
        # Put shorter passages first to ease reading load
        return sorted(questions, key=lambda q: q.expected_word_count)


class SectionChoreographerFactory:
    """Instantiates the correct choreographer for a given section type."""

    @staticmethod
    def get_choreographer(qtype: QuestionTypeCode) -> ISectionChoreographer:
        """Returns the appropriate section choreographer."""
        if qtype == QuestionTypeCode.MCQ:
            return SectionAChoreographer()
        elif qtype == QuestionTypeCode.ASSERTION_REASON:
            return SectionBChoreographer()
        elif qtype == QuestionTypeCode.CASE_STUDY:
            return SectionEChoreographer()
        elif qtype == QuestionTypeCode.NUMERICAL:
            return SectionDChoreographer()
        # Default choreographer for Short/Long answers
        return SectionCChoreographer()
