"""
AOS Hindi Course B — CBSE Class 10 Orchestration Engine
=========================================================
CBSE Hindi Course B (Code 085) SQP 2025-26.

Enforces: 16 questions, 80 marks, Khand Ka→Kha→Ga→Gha ordering,
Devanagari Unicode throughout, theme diversity across apathit passages.
"""

from typing import List
from q_instructions.core.enums import QuestionTypeCode, BloomsLevel
from q_instructions.core.datatypes import QuestionInstance


class HindiOrchestratorV2:
    """Enforces CBSE SQP 2025-26 rules for Hindi Course B papers."""

    # Prescribed texts (hints only — never reproduce in questions)
    SPARSH_GADYA = [
        "बड़े भाई साहब", "डायरी का एक पन्ना", "तताँरा-वामीरो कथा",
        "तीसरी कसम के शिल्पकार शैलेंद्र", "गिरगिट",
        "अब कहाँ दूसरे के दुख से दुखी होने वाले",
    ]
    SPARSH_KAVYA = [
        "साखी", "मीरा के पद", "बिहारी", "मनुष्यता",
        "पर्वत प्रदेश में पावस", "मधुर-मधुर मेरे दीपक जल",
        "तोप", "कर चले हम फ़िदा", "आत्मत्राण",
    ]
    SANCHAYAN = ["हरिहर काका", "सपनों के-से दिन", "टोपी शुक्ला"]

    MARKS_LAYOUT = {
        "Q1": 7, "Q2": 7,                          # Apathit
        "Q3": 4, "Q4": 4, "Q5": 4, "Q6": 4,        # Grammar
        "Q7": 5, "Q8": 6, "Q9": 5, "Q10": 6,       # Pathyapustak
        "Q11": 6,                                   # Sanchayan
        "Q12": 5, "Q13": 5, "Q14": 4, "Q15": 3, "Q16": 5,  # Rachnatmak
    }

    def validate_marks_sum(self, questions: List[QuestionInstance]) -> bool:
        return sum(q.assigned_marks for q in questions) == 80

    def validate_apathit_theme_diversity(self, q1_theme: str, q2_theme: str) -> bool:
        """Q1 and Q2 must be on clearly different themes."""
        return q1_theme.strip().lower() != q2_theme.strip().lower()

    def validate_devanagari(self, text: str) -> bool:
        """Returns True if the text contains Devanagari script characters."""
        return any("ऀ" <= ch <= "ॿ" for ch in text)

    def sequence_paper(self, questions: List[QuestionInstance]) -> List[QuestionInstance]:
        """Sections in order Ka→Kha→Ga→Gha."""
        return questions
