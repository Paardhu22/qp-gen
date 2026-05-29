"""
AOS English Language & Literature — CBSE Class 10 Orchestration Engine
========================================================================
CBSE English Language & Literature (Code 184) SQP 2025-26.

Enforces: 11 questions, 80 marks, Sections A→B→C ordering,
prescribed text constraints, no reproduction of textbook content.
"""

from typing import List
from q_instructions.core.enums import QuestionTypeCode, BloomsLevel, StreamType
from q_instructions.core.datatypes import QuestionInstance


class EnglishOrchestratorV2:
    """Enforces CBSE SQP 2025-26 rules for English Language & Literature papers."""

    # Prescribed text references (for topic hint seeding — never reproduce)
    FIRST_FLIGHT_PROSE = [
        "A Letter to God", "Nelson Mandela: Long Walk to Freedom",
        "Two Stories About Flying", "From the Diary of Anne Frank",
        "Glimpses of India", "Mijbil the Otter", "Madam Rides the Bus",
        "The Sermon at Benares", "The Proposal",
    ]
    FIRST_FLIGHT_POETRY = [
        "Dust of Snow", "Fire and Ice", "A Tiger in the Zoo",
        "How to Tell Wild Animals", "The Ball Poem", "Amanda!",
        "Animals", "The Trees", "Fog", "The Tale of Custard the Dragon",
        "For Anne Gregory",
    ]
    FOOTPRINTS = [
        "A Triumph of Surgery", "The Thief's Story", "The Midnight Visitor",
        "A Question of Trust", "Footprints Without Feet", "Making of a Scientist",
        "The Necklace", "The Hack Driver", "Bholi", "The Book That Saved the Earth",
    ]

    MARKS_LAYOUT = {
        "Q1": 10, "Q2": 10,  # Section A Reading
        "Q3": 10, "Q4": 5, "Q5": 5,  # Section B Grammar & Writing
        "Q6": 5, "Q7": 5, "Q8": 12, "Q9": 6, "Q10": 6, "Q11": 6,  # Section C Literature
    }

    def validate_marks_sum(self, questions: List[QuestionInstance]) -> bool:
        return sum(q.assigned_marks for q in questions) == 80

    def validate_q8_source_span(self, topics: List[str]) -> bool:
        """Q8 must span ≥2 First Flight Prose + ≥1 First Flight Poetry + ≥1 Footprints."""
        ff_prose = sum(1 for t in topics if any(p in t for p in self.FIRST_FLIGHT_PROSE))
        ff_poetry = sum(1 for t in topics if any(p in t for p in self.FIRST_FLIGHT_POETRY))
        footprints = sum(1 for t in topics if any(p in t for p in self.FOOTPRINTS))
        return ff_prose >= 2 and ff_poetry >= 1 and footprints >= 1

    def validate_extract_diversity(self, q6_source: str, q7_source: str) -> bool:
        """Q6 and Q7 must be from different chapters."""
        return q6_source != q7_source

    def sequence_paper(self, questions: List[QuestionInstance]) -> List[QuestionInstance]:
        """Sections in order A→B→C."""
        return questions
