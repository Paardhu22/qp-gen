"""
AOS Science — CBSE Science Paper Orchestration Engine v2
============================================================
Architectural reference: CBSE Science SQP 2025-26 (Code 086, Class X)

Phase 1 — Stream-based Orchestration (Bio -> Chem -> Phys)
Phase 2 — Stream Behavior Intelligence
Phase 3 — Marks-Tier Internal Progression
Phase 4 — OR Choice Engine
Phase 5 — Question Type Taxonomy
Phase 6 — Visually Impaired (VI) Support
Phase 7 — Dynamic Question Count Support
Phase 8 — Retrieval-First Architecture
Phase 9 — Realism Validation
"""

import math
from typing import List, Dict, Tuple
from q_instructions.core.enums import StreamType, QuestionTypeCode, BloomsLevel
from q_instructions.core.datatypes import QuestionInstance

class ScienceOrchestratorV2:
    """Enforces CBSE SQP 2025-26 rules for Science papers."""

    STREAM_PROPORTIONS = {
        StreamType.BIOLOGY: 0.385,   # ~15/39 questions, ~30/80 marks
        StreamType.CHEMISTRY: 0.308, # ~12/39 questions, ~25/80 marks
        StreamType.PHYSICS: 0.307    # ~12/39 questions, ~25/80 marks
    }

    def allocate_streams(self, total_questions: int) -> Dict[StreamType, int]:
        """Dynamically allocate questions proportionally."""
        if total_questions == 0:
            return {StreamType.BIOLOGY: 0, StreamType.CHEMISTRY: 0, StreamType.PHYSICS: 0}

        bio = round(total_questions * self.STREAM_PROPORTIONS[StreamType.BIOLOGY])
        chem = round(total_questions * self.STREAM_PROPORTIONS[StreamType.CHEMISTRY])
        phys = total_questions - bio - chem # Remaining to phys to ensure exact sum

        return {
            StreamType.BIOLOGY: bio,
            StreamType.CHEMISTRY: chem,
            StreamType.PHYSICS: phys
        }

    def build_tier_progression(self, count: int) -> List[Tuple[QuestionTypeCode, int]]:
        """
        Builds marks ladder (1 -> 2 -> 3 -> 4 -> 5) based on allocated count for a stream.
        """
        progression = []
        if count == 0:
            return progression
        
        # Approximate distributions per stream based on SQP scaling
        # Example scaling logic for small to large sets
        if count <= 2:
            progression = [(QuestionTypeCode.MCQ, 1), (QuestionTypeCode.SHORT_ANSWER, 2)]
        elif count <= 4:
            progression = [
                (QuestionTypeCode.MCQ, 1),
                (QuestionTypeCode.ASSERTION_REASON, 1),
                (QuestionTypeCode.SHORT_ANSWER, 2),
                (QuestionTypeCode.SHORT_ANSWER, 3)
            ]
        else:
            # Distribute roughly: 40% 1-mark, 15% 2-mark, 20% 3-mark, 15% 4-mark, 10% 5-mark
            num_1m = math.ceil(count * 0.40)
            num_2m = math.ceil(count * 0.15)
            num_3m = math.ceil(count * 0.20)
            num_4m = max(1, math.floor(count * 0.15)) if count >= 7 else 0
            num_5m = max(1, math.floor(count * 0.10)) if count >= 10 else 0
            
            # Adjust to exact count
            while num_1m + num_2m + num_3m + num_4m + num_5m > count:
                if num_1m > 1: num_1m -= 1
                elif num_3m > 1: num_3m -= 1
                else: break
                
            while num_1m + num_2m + num_3m + num_4m + num_5m < count:
                num_1m += 1

            for _ in range(num_1m - 1): progression.append((QuestionTypeCode.MCQ, 1))
            if num_1m > 0: progression.append((QuestionTypeCode.ASSERTION_REASON, 1)) # Always at end of 1-marks
            
            for _ in range(num_2m): progression.append((QuestionTypeCode.SHORT_ANSWER, 2))
            for _ in range(num_3m): progression.append((QuestionTypeCode.SHORT_ANSWER, 3))
            for _ in range(num_4m): progression.append((QuestionTypeCode.CASE_STUDY, 4))
            for _ in range(num_5m): progression.append((QuestionTypeCode.LONG_ANSWER, 5))

        return progression[:count]

    def applies_or_choice(self, qtype: QuestionTypeCode, marks: int) -> bool:
        """OR choices only in >= 2 marks. 5 marks always have OR."""
        if marks < 2 or qtype in [QuestionTypeCode.MCQ, QuestionTypeCode.ASSERTION_REASON]:
            return False
        if marks == 5 or qtype == QuestionTypeCode.LONG_ANSWER:
            return True
        # Probabilistic OR choice for 2, 3, 4 marks (simulating real distribution)
        return True # For simplification, RAG engine decides.

    def sequence_paper(self, bio_qs: List[QuestionInstance], chem_qs: List[QuestionInstance], phys_qs: List[QuestionInstance]) -> List[QuestionInstance]:
        """Ensure order is Biology -> Chemistry -> Physics"""
        return bio_qs + chem_qs + phys_qs

    def validate_realism(self, questions: List[QuestionInstance]) -> bool:
        """Phase 9 Validation."""
        if not questions: return True
        
        # 1. Stream order
        streams = [q.stream for q in questions if q.stream in (StreamType.BIOLOGY, StreamType.CHEMISTRY, StreamType.PHYSICS)]
        expected = sorted(streams, key=lambda s: {StreamType.BIOLOGY: 0, StreamType.CHEMISTRY: 1, StreamType.PHYSICS: 2}.get(s, 99))
        if streams != expected: return False
        
        # 2. Progression
        # Check monotonic progression within streams
        for stream in [StreamType.BIOLOGY, StreamType.CHEMISTRY, StreamType.PHYSICS]:
            stream_qs = [q for q in questions if q.stream == stream]
            marks = [q.assigned_marks for q in stream_qs]
            if marks != sorted(marks): return False
            
        return True
