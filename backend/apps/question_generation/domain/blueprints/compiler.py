"""
Question Generation Domain - Blueprint Compiler
"""

import uuid
from typing import Dict, List, Optional

from ..constants import CBSE_EXAM_DURATION_MINUTES
from ..datatypes import CompiledPaperBlueprint, ExamBlueprint, InstitutionPolicy, SectionBlueprint
from ..enums import AcademicClass, BloomsLevel, EducationBoard, ExamType, QuestionTypeCode, StreamType
from ..interfaces import IBlueprintCompiler
from ..instructions.science.blueprint import ExamBlueprintRegistry
from ..instructions.science.curriculum import CurriculumGraphFactory, CurriculumWeightageRegistry, PrerequisitePacingOptimizer


class BlueprintCompiler(IBlueprintCompiler):
    """
    Deterministic blueprint compiler. Produces a resolved blueprint before any generation.
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
        institution_policy: Optional[InstitutionPolicy] = None,
    ) -> CompiledPaperBlueprint:
        base = self._blueprint_registry.get_blueprint(exam_type, academic_class)

        concept_ids = self._resolve_concepts(chapters)
        ordered_concepts = self._pacing.optimize_sequence(concept_ids)

        if count and count < len(ordered_concepts):
            ordered_concepts = self._sample_concepts(ordered_concepts, count)

        stream_dist = self._compute_stream_distribution(ordered_concepts)
        comp_dist = self._compute_competency_distribution(ordered_concepts)
        blooms_dist = self._compute_blooms_distribution(base, difficulty)
        diff_curve = self._generate_difficulty_curve(base.sections, difficulty)
        qtype_dist = self._compute_qtype_distribution(base.sections)
        chapter_dist = self._compute_chapter_distribution(ordered_concepts)

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
            institution_policy=institution_policy,
        )

    def _resolve_concepts(self, chapters: List[str]) -> List[str]:
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
        if len(ordered_concepts) <= count:
            return ordered_concepts

        scored_concepts = []
        for cid in ordered_concepts:
            profile = self._weights.get_weight_profile(cid)
            weight = profile.board_weightage if profile else 0.5
            scored_concepts.append((cid, weight))

        scored_concepts.sort(key=lambda x: x[1], reverse=True)
        selected_set = {cid for cid, _ in scored_concepts[:count]}
        return [cid for cid in ordered_concepts if cid in selected_set]

    def _compute_stream_distribution(self, concept_ids: List[str]) -> Dict[StreamType, float]:
        counts: Dict[StreamType, int] = {}
        for cid in concept_ids:
            node = self._graph.nodes.get(cid)
            if node:
                counts[node.stream] = counts.get(node.stream, 0) + 1
        total = sum(counts.values()) or 1
        return {s: c / total for s, c in counts.items()}

    def _compute_competency_distribution(self, concept_ids: List[str]) -> Dict[str, float]:
        comp_map: Dict[str, float] = {}
        for cid in concept_ids:
            profile = self._weights.get_weight_profile(cid)
            if profile.target_nep_competency_code:
                comp_map[profile.target_nep_competency_code] = profile.board_weightage
        return comp_map

    def _compute_blooms_distribution(self, base: ExamBlueprint, difficulty: str) -> Dict[BloomsLevel, float]:
        blooms = dict(base.bloom_distribution_target)

        if difficulty == "hard":
            blooms[BloomsLevel.ANALYZE] = blooms.get(BloomsLevel.ANALYZE, 0) + 0.05
            blooms[BloomsLevel.EVALUATE] = blooms.get(BloomsLevel.EVALUATE, 0) + 0.05
            blooms[BloomsLevel.REMEMBER] = max(blooms.get(BloomsLevel.REMEMBER, 0) - 0.10, 0)
        elif difficulty == "easy":
            blooms[BloomsLevel.REMEMBER] = blooms.get(BloomsLevel.REMEMBER, 0) + 0.10
            blooms[BloomsLevel.ANALYZE] = max(blooms.get(BloomsLevel.ANALYZE, 0) - 0.05, 0)
            blooms[BloomsLevel.EVALUATE] = max(blooms.get(BloomsLevel.EVALUATE, 0) - 0.05, 0)

        total = sum(blooms.values()) or 1
        return {k: v / total for k, v in blooms.items()}

    def _generate_difficulty_curve(self, sections: List[SectionBlueprint], difficulty: str) -> List[float]:
        n = len(sections)
        base_start = {"easy": 0.20, "medium": 0.30, "hard": 0.40}.get(difficulty, 0.30)
        base_end = {"easy": 0.60, "medium": 0.75, "hard": 0.90}.get(difficulty, 0.75)
        step = (base_end - base_start) / max(n - 1, 1)
        return [round(base_start + i * step, 3) for i in range(n)]

    def _compute_qtype_distribution(self, sections: List[SectionBlueprint]) -> Dict[QuestionTypeCode, int]:
        dist: Dict[QuestionTypeCode, int] = {}
        for sec in sections:
            dist[sec.question_type] = dist.get(sec.question_type, 0) + sec.question_count
        return dist

    def _compute_chapter_distribution(self, concept_ids: List[str]) -> Dict[str, float]:
        n = len(concept_ids) or 1
        return {cid: 1.0 / n for cid in concept_ids}
