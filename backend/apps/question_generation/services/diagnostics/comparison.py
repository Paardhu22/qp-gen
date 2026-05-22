from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class ComparisonReport:
    total_questions_delta: int
    total_marks_delta: int
    question_type_counts: Dict[str, int]


def compare_papers(old_questions: List[dict], new_questions: List[dict]) -> ComparisonReport:
    old_count = len(old_questions)
    new_count = len(new_questions)

    old_marks = sum(q.get("marks", 0) for q in old_questions)
    new_marks = sum(q.get("marks", 0) for q in new_questions)

    type_counts: Dict[str, int] = {}
    for q in old_questions:
        qtype = q.get("type")
        type_counts[qtype] = type_counts.get(qtype, 0) + 1
    for q in new_questions:
        qtype = q.get("type")
        type_counts[qtype] = type_counts.get(qtype, 0) - 1

    return ComparisonReport(
        total_questions_delta=new_count - old_count,
        total_marks_delta=new_marks - old_marks,
        question_type_counts=type_counts,
    )
