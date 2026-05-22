"""
AOS Generation — Deterministic Blueprint Compiler
====================================================
THE HEART OF THE PLATFORM.

Compiles a deterministic, fully-resolved exam blueprint
from high-level specifications BEFORE any generation occurs.
This blueprint becomes the SINGLE SOURCE OF TRUTH.
"""

import math
import uuid
from typing import List, Dict, Optional

from q_instructions.core.enums import (
    EducationBoard, AcademicClass, ExamType, StreamType,
    QuestionTypeCode, BloomsLevel
)
from q_instructions.core.datatypes import (
    CompiledPaperBlueprint, SectionBlueprint, ExamBlueprint,
    InstitutionPolicy
)
from q_instructions.core.interfaces import IBlueprintCompiler
from q_instructions.core.constants import CBSE_TOTAL_MARKS, CBSE_EXAM_DURATION_MINUTES

from q_instructions.subjects.science.blueprint import ExamBlueprintRegistry
from q_instructions.subjects.science.curriculum import (
    CurriculumGraphFactory, CurriculumWeightageRegistry,
    PrerequisitePacingOptimizer
)


class BlueprintCompiler(IBlueprintCompiler):
    """
    Compiles a deterministic paper blueprint from exam specifications.
    
    Pipeline:
      1. Load base exam blueprint (sections, marks structure)
      2. Resolve chapter → concept mapping
      3. Compute stream distribution from selected chapters
      4. Compute competency distribution from concept weights
      5. Compute Bloom's distribution from difficulty setting
      6. Generate difficulty curve across sections
      7. Compute question type distribution from sections
      8. Resolve retrieval targets (concept IDs needing context)
      9. Apply institution policy overrides
      10. Package into immutable CompiledPaperBlueprint
    """

    def __init__(self) -> None:
        self._blueprint_registry = ExamBlueprintRegistry()
        self._graph = CurriculumGraphFactory.construct_comprehensive_graph()
        self._weights = CurriculumWeightageRegistry()
        self._pacing = PrerequisitePacingOptimizer(self._graph)

    def compile(
        self,
        board: EducationBoard,
        academic_class: AcademicClass,
        exam_type: ExamType,
        total_marks: int,
        chapters: List[str],
        difficulty: str = "medium",
        count: Optional[int] = None,
        institution_policy: Optional[InstitutionPolicy] = None
    ) -> CompiledPaperBlueprint:
        """Compiles a fully resolved, deterministic paper blueprint."""

        # 1. Load base structure
        base = self._blueprint_registry.get_blueprint(exam_type, academic_class)

        # 2. Resolve chapter → concept mapping
        concept_ids = self._resolve_concepts(chapters)

        # 3. Order concepts topologically
        ordered_concepts = self._pacing.optimize_sequence(concept_ids)
        
        # Apply count limits intelligently
        if count and count < len(ordered_concepts):
            ordered_concepts = self._sample_concepts(ordered_concepts, count)

        # 4. Compute stream distribution
        stream_dist = self._compute_stream_distribution(ordered_concepts)

        # 5. Compute competency distribution
        comp_dist = self._compute_competency_distribution(ordered_concepts)

        # 6. Compute Bloom's distribution adjusted by difficulty
        blooms_dist = self._compute_blooms_distribution(base, difficulty)

        # 7. Generate difficulty curve
        diff_curve = self._generate_difficulty_curve(base.sections, difficulty)

        # 8. Compute question type distribution
        qtype_dist = self._compute_qtype_distribution(base.sections)

        # 9. Compute chapter distribution
        chapter_dist = self._compute_chapter_distribution(ordered_concepts)

        # 10. Package
        paper_id = f"BP_{board.name}_{academic_class.name}_{uuid.uuid4().hex[:8]}"

        return CompiledPaperBlueprint(
            paper_id=paper_id,
            board=board,
            academic_class=academic_class,
            exam_type=exam_type,
            total_marks=total_marks,
            duration_minutes=base.duration_minutes,
            sections=base.sections,
            stream_distribution=stream_dist,
            competency_distribution=comp_dist,
            blooms_distribution=blooms_dist,
            chapter_distribution=chapter_dist,
            difficulty_curve=diff_curve,
            question_type_distribution=qtype_dist,
            retrieval_targets=ordered_concepts,
            institution_policy=institution_policy
        )

    def _resolve_concepts(self, chapters: List[str]) -> List[str]:
        """Maps chapter hints to concept IDs in the graph."""
        all_ids = list(self._graph.nodes.keys())
        if not chapters:
            return all_ids

        matched: List[str] = []
        for chapter in chapters:
            ch_lower = chapter.lower()
            for cid, node in self._graph.nodes.items():
                if ch_lower in node.concept_name.lower() or ch_lower in cid.lower():
                    if cid not in matched:
                        matched.append(cid)

        return matched if matched else all_ids

    def _sample_concepts(self, ordered_concepts: List[str], count: int) -> List[str]:
        """Intelligently downsamples concepts based on board weightage."""
        import logging
        logger = logging.getLogger("AOS.BlueprintCompiler")
        
        if len(ordered_concepts) <= count:
            logger.info(f"[BLUEPRINT] Resolved concepts: {len(ordered_concepts)} | Requested count: {count} | Selected concepts: {len(ordered_concepts)}")
            return ordered_concepts
            
        scored_concepts = []
        for cid in ordered_concepts:
            profile = self._weights.get_weight_profile(cid)
            weight = profile.board_weightage if profile else 0.5
            scored_concepts.append((cid, weight))
            
        # Sort by weight descending
        scored_concepts.sort(key=lambda x: x[1], reverse=True)
        
        # Take the top `count`
        selected_set = {cid for cid, w in scored_concepts[:count]}
        
        # Restore original topological order
        final_selection = [cid for cid in ordered_concepts if cid in selected_set]
        
        logger.info(f"[BLUEPRINT] Resolved concepts: {len(ordered_concepts)} | Requested count: {count} | Selected concepts: {len(final_selection)}")
        return final_selection

    def _compute_stream_distribution(self, concept_ids: List[str]) -> Dict[StreamType, float]:
        """Computes stream allocation from concept set."""
        counts: Dict[StreamType, int] = {}
        for cid in concept_ids:
            node = self._graph.nodes.get(cid)
            if node:
                counts[node.stream] = counts.get(node.stream, 0) + 1
        total = sum(counts.values()) or 1
        return {s: c / total for s, c in counts.items()}

    def _compute_competency_distribution(self, concept_ids: List[str]) -> Dict[str, float]:
        """Computes NEP competency spread."""
        comp_map: Dict[str, float] = {}
        for cid in concept_ids:
            profile = self._weights.get_weight_profile(cid)
            if profile.target_nep_competency_code:
                comp_map[profile.target_nep_competency_code] = profile.board_weightage
        return comp_map

    def _compute_blooms_distribution(
        self, base: ExamBlueprint, difficulty: str
    ) -> Dict[BloomsLevel, float]:
        """Adjusts Bloom's targets based on difficulty setting."""
        blooms = dict(base.bloom_distribution_target)

        if difficulty == "hard":
            # Shift weight upward
            blooms[BloomsLevel.ANALYZE] = blooms.get(BloomsLevel.ANALYZE, 0) + 0.05
            blooms[BloomsLevel.EVALUATE] = blooms.get(BloomsLevel.EVALUATE, 0) + 0.05
            blooms[BloomsLevel.REMEMBER] = max(blooms.get(BloomsLevel.REMEMBER, 0) - 0.10, 0)
        elif difficulty == "easy":
            # Shift weight downward
            blooms[BloomsLevel.REMEMBER] = blooms.get(BloomsLevel.REMEMBER, 0) + 0.10
            blooms[BloomsLevel.ANALYZE] = max(blooms.get(BloomsLevel.ANALYZE, 0) - 0.05, 0)
            blooms[BloomsLevel.EVALUATE] = max(blooms.get(BloomsLevel.EVALUATE, 0) - 0.05, 0)

        # Normalize
        total = sum(blooms.values()) or 1
        return {k: v / total for k, v in blooms.items()}

    def _generate_difficulty_curve(
        self, sections: List[SectionBlueprint], difficulty: str
    ) -> List[float]:
        """Generates a monotonically increasing difficulty curve per section."""
        n = len(sections)
        base_start = {"easy": 0.20, "medium": 0.30, "hard": 0.40}.get(difficulty, 0.30)
        base_end = {"easy": 0.60, "medium": 0.75, "hard": 0.90}.get(difficulty, 0.75)
        step = (base_end - base_start) / max(n - 1, 1)
        return [round(base_start + i * step, 3) for i in range(n)]

    def _compute_qtype_distribution(
        self, sections: List[SectionBlueprint]
    ) -> Dict[QuestionTypeCode, int]:
        """Counts questions per type from the section layout."""
        dist: Dict[QuestionTypeCode, int] = {}
        for sec in sections:
            dist[sec.question_type] = dist.get(sec.question_type, 0) + sec.question_count
        return dist

    def _compute_chapter_distribution(self, concept_ids: List[str]) -> Dict[str, float]:
        """Computes even distribution weight across concepts."""
        n = len(concept_ids) or 1
        return {cid: 1.0 / n for cid in concept_ids}
