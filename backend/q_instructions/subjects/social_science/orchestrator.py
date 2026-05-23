"""
AOS Social Science — CBSE Social Science Paper Orchestration Engine v2
============================================================
Architectural reference: CBSE Social Science SQP 2025-26 (Code 087, Class X)

Phase 1 — Four-Track Stream Orchestration (History -> Geo -> Civics -> Econ)
Phase 2 — Question Type Constraints (Assertion-Reason only in Civics, No CBQ in Econ)
Phase 3 — Section Specific Marks Sparing (No 3m in Geo, No 2m in Econ)
Phase 4 — Assymetric OR Choice Engine (History gets 2m/3m/5m, others 5m only)
Phase 5 — Visually Impaired (VI) Support for Maps and Cartoons
"""

import math
from typing import List, Dict, Tuple
from q_instructions.core.enums import StreamType, QuestionTypeCode, BloomsLevel
from q_instructions.core.datatypes import QuestionInstance

class SocialScienceOrchestratorV2:
    """Enforces CBSE SQP 2025-26 rules for Social Science papers."""

    STREAM_PROPORTIONS = {
        StreamType.HISTORY: 0.25,      # 20/80 marks
        StreamType.GEOGRAPHY: 0.25,    # 20/80 marks
        StreamType.CIVICS: 0.25,       # 20/80 marks
        StreamType.ECONOMICS: 0.25     # 20/80 marks
    }

    def allocate_streams(self, total_questions: int) -> Dict[StreamType, int]:
        """Dynamically allocate questions symmetrically for 4 tracks."""
        if total_questions == 0:
            return {
                StreamType.HISTORY: 0,
                StreamType.GEOGRAPHY: 0,
                StreamType.CIVICS: 0,
                StreamType.ECONOMICS: 0
            }

        base = total_questions // 4
        remainder = total_questions % 4
        
        alloc = {
            StreamType.HISTORY: base,
            StreamType.GEOGRAPHY: base,
            StreamType.CIVICS: base,
            StreamType.ECONOMICS: base
        }
        
        # Distribute remainder
        for i, stream in enumerate([StreamType.HISTORY, StreamType.GEOGRAPHY, StreamType.ECONOMICS, StreamType.CIVICS]):
            if i < remainder:
                alloc[stream] += 1
                
        return alloc

    def build_tier_progression(self, count: int, stream: StreamType) -> List[Tuple[QuestionTypeCode, int]]:
        """
        Builds marks ladder specific to the Social Science subject sub-stream constraints.
        - Geography has NO 3-mark questions.
        - Economics has NO 2-mark VSA and NO Case-Based questions.
        - Civics has Assertion-Reason.
        """
        progression = []
        if count == 0:
            return progression
        
        num_1m = math.ceil(count * 0.40)
        num_2m = math.ceil(count * 0.15)
        num_3m = math.ceil(count * 0.15)
        num_4m = math.floor(count * 0.15)
        num_5m = math.floor(count * 0.15)
        
        # Apply strict SQP 2025-26 Sub-Stream Rules
        if stream == StreamType.GEOGRAPHY:
            num_2m += num_3m // 2
            num_1m += num_3m - (num_3m // 2)
            num_3m = 0  # No 3-mark SA
            
        if stream == StreamType.ECONOMICS:
            num_3m += num_2m // 2
            num_1m += num_2m - (num_2m // 2)
            num_2m = 0  # No 2-mark VSA
            
            num_5m += num_4m // 2
            num_3m += num_4m - (num_4m // 2)
            num_4m = 0  # No CBQ
            
        if stream == StreamType.CIVICS:
            # Civics gets two 2-mark VSA typically
            if num_2m < 2 and count >= 5:
                num_2m = 2
                num_1m = max(1, num_1m - 1)

        # Distribute into ladder
        for _ in range(num_1m - 1): progression.append((QuestionTypeCode.MCQ, 1))
        
        # Assertion-Reason only belongs to Civics
        if num_1m > 0: 
            if stream == StreamType.CIVICS:
                progression.append((QuestionTypeCode.ASSERTION_REASON, 1))
            else:
                progression.append((QuestionTypeCode.MCQ, 1))
        
        for _ in range(num_2m): progression.append((QuestionTypeCode.SHORT_ANSWER, 2))
        for _ in range(num_3m): progression.append((QuestionTypeCode.SHORT_ANSWER, 3))
        for _ in range(num_4m): progression.append((QuestionTypeCode.CASE_STUDY, 4))
        for _ in range(num_5m): progression.append((QuestionTypeCode.LONG_ANSWER, 5))

        return progression[:count]

    def applies_or_choice(self, qtype: QuestionTypeCode, marks: int, stream: StreamType) -> bool:
        """
        Asymmetric OR choice placement based on SQP constraints.
        - History: OR appears at 2m, 3m, and 5m.
        - Geo/Civics/Econ: OR appears ONLY at 5m.
        """
        if marks == 5 or qtype == QuestionTypeCode.LONG_ANSWER:
            return True
            
        if stream == StreamType.HISTORY and marks in [2, 3]:
            return True
            
        return False

    def sequence_paper(self, hist_qs: List[QuestionInstance], geo_qs: List[QuestionInstance], civ_qs: List[QuestionInstance], econ_qs: List[QuestionInstance]) -> List[QuestionInstance]:
        """Ensure strict four-track order: History -> Geography -> Civics -> Economics"""
        return hist_qs + geo_qs + civ_qs + econ_qs

    def validate_realism(self, questions: List[QuestionInstance]) -> bool:
        """Validate against SQP rules."""
        if not questions: return True
        
        # 1. Check for illegal 3-mark in Geo
        for q in questions:
            if q.stream == StreamType.GEOGRAPHY and q.assigned_marks == 3:
                return False
                
        # 2. Check for illegal 2-mark or CBQ in Econ
        for q in questions:
            if q.stream == StreamType.ECONOMICS and (q.assigned_marks == 2 or q.question_type == QuestionTypeCode.CASE_STUDY):
                return False
                
        # 3. Check Assertion-Reason bleed
        for q in questions:
            if q.question_type == QuestionTypeCode.ASSERTION_REASON and q.stream != StreamType.CIVICS:
                return False

        return True
