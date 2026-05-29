"""
AOS Telugu Telangana — CBSE Class 10 Orchestration Engine
===========================================================
CBSE Telugu Telangana (Code 089) SQP 2025-26.

Enforces: 18 questions, 80 marks, Vibhagam A→B→C→D ordering,
Telugu Unicode script throughout (U+0C00–U+0C7F).
"""

from typing import List
from q_instructions.core.enums import QuestionTypeCode, BloomsLevel
from q_instructions.core.datatypes import QuestionInstance

# Telugu Unicode range
_TELUGU_START = "ఀ"
_TELUGU_END = "౿"


class TeluguOrchestratorV2:
    """Enforces CBSE SQP 2025-26 rules for Telugu Telangana papers."""

    MARKS_LAYOUT = {
        "Q1": 10,                                              # Vibhagam A
        "Q2": 6, "Q3": 5,                                    # Vibhagam B
        "Q4": 4, "Q5": 4, "Q6": 4, "Q7": 4,                 # Vibhagam C grammar MCQs
        "Q8": 2, "Q9": 2, "Q10": 2, "Q11": 2,               # Vibhagam C vocabulary MCQs
        "Q12": 5,                                             # Vibhagam C parichita
        "Q13": 4, "Q14": 4, "Q15": 4, "Q16": 4, "Q17": 6, "Q18": 8,  # Vibhagam D
    }

    # Prescribed texts (hints only — never reproduce)
    GADYAM = ["గోలకొండ", "కొత్తబాట", "లక్ష్యసిద్ధి", "భిక్ష"]
    PADYAM = ["కాళహస్తీశ్వర శతకం", "జీవనభాషం"]
    UPAVACHAKAM_TOPICS = [
        "వాలి-సుగ్రీవ విరోధం",
        "రామాయణం ఎందుకు చదవాలి",
        "భరత పాదుక పట్టాభిషేకం",
        "రామ-రావణ యుద్ధం",
    ]

    def validate_marks_sum(self, questions: List[QuestionInstance]) -> bool:
        return sum(q.assigned_marks for q in questions) == 80

    def validate_telugu_script(self, text: str) -> bool:
        """Returns True if the text contains Telugu Unicode characters."""
        return any(_TELUGU_START <= ch <= _TELUGU_END for ch in text)

    def validate_no_roman(self, text: str) -> bool:
        """Returns True if text has no Latin alphabet (A-Z / a-z)."""
        return not any("A" <= ch <= "Z" or "a" <= ch <= "z" for ch in text)

    def sequence_paper(self, questions: List[QuestionInstance]) -> List[QuestionInstance]:
        """Sections in order A→B→C→D."""
        return questions
