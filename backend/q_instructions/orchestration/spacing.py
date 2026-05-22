"""
AOS Orchestration — Spacing & Concept Overlap Engine
======================================================
Ensures proper cognitive spacing between related concepts and prevents
conceptual clustering or repetitive question types in sequential placement.
"""

from typing import List, Dict

from q_instructions.core.datatypes import QuestionInstance
from q_instructions.subjects.science.curriculum import ConceptGraph


class ConceptOverlapAnalyzer:
    """Analyzes overlap indexes between multiple concepts based on graph distances."""

    def __init__(self, graph: ConceptGraph) -> None:
        self.graph = graph

    def calculate_overlap(self, concept_a: str, concept_b: str) -> float:
        """
        Returns a normalized overlap score between 0.0 (no overlap) and 1.0 (identical/tight).
        Uses BFS distance in the concept graph to estimate proximity.
        """
        if concept_a == concept_b:
            return 1.0

        dist = self.graph.bfs_distance(concept_a, concept_b)
        # Check reverse path if directed graph
        if dist == -1:
            dist = self.graph.bfs_distance(concept_b, concept_a)

        if dist == -1:
            return 0.0

        # Closer distance means higher overlap: dist=1 -> 0.8, dist=2 -> 0.5, dist>=3 -> 0.1
        return max(1.0 - (dist * 0.3), 0.0)


class SpacingController:
    """Controls topological spacing of questions to prevent cognitive cluster fatigue."""

    def __init__(self, graph: ConceptGraph) -> None:
        self.analyzer = ConceptOverlapAnalyzer(graph)

    def optimize_spacing(
        self, questions: List[QuestionInstance], concept_ids: List[str], min_spacing_index: int = 3
    ) -> List[QuestionInstance]:
        """
        Rearranges questions to maximize semantic spacing between highly related concepts.
        Ensures related topics do not appear consecutively.
        """
        if len(questions) <= 2:
            return questions

        n = len(questions)
        result: List[QuestionInstance] = []
        remaining = list(zip(questions, concept_ids))

        # Start with the first question
        curr_q, curr_c = remaining.pop(0)
        result.append(curr_q)

        while remaining:
            best_idx = 0
            min_overlap = 1.0

            # Scan remaining questions to find the one with minimum overlap to recent placements
            for idx, (next_q, next_c) in enumerate(remaining):
                max_recent_overlap = 0.0

                # Check against last few placed questions (bounded by min_spacing_index)
                lookback = min(len(result), min_spacing_index)
                for placed_q in result[-lookback:]:
                    # Map placed question back to its concept ID
                    placed_idx = questions.index(placed_q)
                    placed_c = concept_ids[placed_idx]

                    overlap = self.analyzer.calculate_overlap(next_c, placed_c)
                    if overlap > max_recent_overlap:
                        max_recent_overlap = overlap

                if max_recent_overlap < min_overlap:
                    min_overlap = max_recent_overlap
                    best_idx = idx

            next_q, next_c = remaining.pop(best_idx)
            result.append(next_q)

        return result
