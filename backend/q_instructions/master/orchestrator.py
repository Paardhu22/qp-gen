"""
AOS Master — Academic Orchestrator
======================================
Thin coordination layer that wires all engines together.
This module does NOT contain business logic — it delegates to
specialized engines following the single-responsibility principle.

Generation Pipeline:
  1. Blueprint Compilation (deterministic)
  2. Retrieval Orchestration (context assembly)
  3. Safety Audit (pre-generation checks)
  4. Question Drafting (template-based)
  5. Accessibility Translation (VI booklet)
  6. Answer Key Synthesis (rubric compilation)
  7. Analytics Computation (dashboard)
"""

import time
import sys
import random
from typing import List, Optional

from q_instructions.core.enums import (
    EducationBoard, AcademicClass, ExamType, QuestionTypeCode, BloomsLevel, StreamType
)
from q_instructions.core.datatypes import (
    CompiledPaperBlueprint, AssembledPaperBooklet, QuestionInstance,
    InstitutionPolicy, AnswerKeyRubric, RubricCriteria,
    PaperAnalyticsDashboard
)

from q_instructions.generation.blueprint_compiler import BlueprintCompiler
from q_instructions.generation.safety_engine import GenerationSafetyEngine
from q_instructions.retrieval.semantic_index import SemanticSearchIndex
from q_instructions.board_systems.cbse.templates import QuestionTemplateLibrary
from q_instructions.board_systems.cbse.accessibility import AccessibilityLearningEngine
from q_instructions.institution.policies import InstitutionOverrideEngine
from q_instructions.subjects.science.curriculum import (
    CurriculumGraphFactory, CurriculumWeightageRegistry,
    DifficultyEstimationEngine
)


class MasterAcademicOrchestrator:
    """
    Central coordination layer.
    Delegates all domain logic to specialized engines.
    """

    def __init__(self, institution_id: str = "CBSE_OFFICIAL") -> None:
        self.institution_id = institution_id

        # Wire engines
        self._compiler = BlueprintCompiler()
        self._graph = CurriculumGraphFactory.construct_comprehensive_graph()
        self._weights = CurriculumWeightageRegistry()
        self._retrieval = SemanticSearchIndex()
        self._safety = GenerationSafetyEngine(self._graph)
        self._templates = QuestionTemplateLibrary()
        self._accessibility = AccessibilityLearningEngine()
        self._institutions = InstitutionOverrideEngine()
        self._diff_engine = DifficultyEstimationEngine(self._graph, self._weights)

    def generate_paper(
        self,
        academic_class: AcademicClass,
        exam_type: ExamType,
        chapters: List[str],
        difficulty: str = "medium",
        seed: int = 42
    ) -> AssembledPaperBooklet:
        """
        Full generation pipeline:
          1. Compile blueprint
          2. Draft questions from templates
          3. Validate safety
          4. Generate accessibility booklet
          5. Compile answer keys
          6. Compute analytics
        """
        start_time = time.time()
        random.seed(seed)

        # 1. Compile deterministic blueprint
        policy = self._institutions.get_policy(self.institution_id)
        blueprint = self._compiler.compile(
            board=EducationBoard.CBSE,
            academic_class=academic_class,
            exam_type=exam_type,
            total_marks=80,
            chapters=chapters,
            difficulty=difficulty,
            institution_policy=policy
        )

        # 2. Draft questions
        questions = self._draft_questions(blueprint, policy)

        # 3. Safety audit
        concept_ids = blueprint.retrieval_targets
        errors = self._safety.audit_paper(questions, concept_ids)
        # In production: log errors and attempt repair

        # 4. Accessibility split
        standard, vi_accessible = self._accessibility.generate_dual_booklet(questions)

        # 5. Answer keys
        answer_keys = self._compile_answer_keys(questions, concept_ids)

        # 6. Analytics
        analytics = self._compute_analytics(questions, concept_ids)

        elapsed = (time.time() - start_time) * 1000.0
        mem = sys.getsizeof(self) / 1024.0

        return AssembledPaperBooklet(
            paper_id=blueprint.paper_id,
            school_name=policy.name,
            board=EducationBoard.CBSE,
            general_instructions=[
                "All questions are compulsory.",
                f"This paper consists of {len(questions)} questions.",
                policy.custom_instruction_footer
            ],
            question_sequence=standard,
            vi_accessible_sequence=vi_accessible,
            answer_keys=answer_keys,
            analytics=analytics,
            generation_duration_ms=elapsed,
            memory_allocation_kb=mem
        )

    def _draft_questions(
        self, blueprint: CompiledPaperBlueprint, policy: InstitutionPolicy
    ) -> List[QuestionInstance]:
        """Drafts questions obeying V2 Rules: Bio->Chem->Phys and marks ladder."""
        from q_instructions.generation.template_selector import IntelligentTemplateSelector
        from q_instructions.generation.parameter_synthesizer import ParameterSynthesizer
        from q_instructions.subjects.science.orchestrator import ScienceOrchestratorV2

        template_selector = IntelligentTemplateSelector(self._templates)
        synthesizer = ParameterSynthesizer()
        orchestrator = ScienceOrchestratorV2()

        # 1. Group by streams
        stream_groups = {StreamType.BIOLOGY: [], StreamType.CHEMISTRY: [], StreamType.PHYSICS: []}
        for cid in blueprint.retrieval_targets:
            node = self._graph.nodes.get(cid)
            if node and node.stream in stream_groups:
                stream_groups[node.stream].append(cid)
            elif node:
                # Default unknown to physics
                stream_groups[StreamType.PHYSICS].append(cid)

        # 2. Sequence Biology -> Chemistry -> Physics
        questions: List[QuestionInstance] = []
        for stream in [StreamType.BIOLOGY, StreamType.CHEMISTRY, StreamType.PHYSICS]:
            cids = stream_groups[stream]
            progression = orchestrator.build_tier_progression(len(cids))
            
            for i, cid in enumerate(cids):
                node = self._graph.nodes.get(cid)
                if not node: continue
                
                # Use progression ladder to determine qtype and marks
                if i < len(progression):
                    base_qtype, marks = progression[i]
                else:
                    base_qtype, marks = QuestionTypeCode.SHORT_ANSWER, 3

                # Override with node-specific traits if logical
                qtype = self._resolve_qtype(node, base_qtype)
                
                # Enforce OR choices
                has_or_choice = orchestrator.applies_or_choice(qtype, marks)

                template = template_selector.select(qtype, None)
                context = self._retrieval.retrieve(cid, [0.1, 0.8, 0.05, 0.15, 0.85, 0.02, 0.02, 0.01])

                q_text = template.template_text
                q_text = q_text.replace("[Chemical compound]", node.concept_name)
                q_text = q_text.replace("[Product]", "gaseous oxides")
                q_text = q_text.replace("[Reaction type]", "Thermal Decomposition")
                if context:
                    q_text = q_text.replace("[Technical passage detailing resistivity]", f"Textbook: {context[0].text_content}")

                q_text = synthesizer.synthesize(q_text)
                if not synthesizer.validate_no_placeholders(q_text):
                    continue
                    
                if has_or_choice:
                    q_text += "\n\nOR\n\n[Alternative Question of same marks and topic]"

                questions.append(QuestionInstance(
                    question_id=f"Q_{cid}",
                    academic_class=blueprint.academic_class,
                    stream=node.stream,
                    question_type=qtype,
                    blooms_level=template.target_bloom,
                    assigned_marks=marks,
                    content_text=q_text,
                    expected_word_count=50 if qtype in [QuestionTypeCode.MCQ, QuestionTypeCode.ASSERTION_REASON] else 150
                ))

        # 3. Validate Realism
        if not orchestrator.validate_realism(questions):
            # In production this would trigger a rebuild, here we just log
            print("[WARNING] Realism validation failed: Paper may not reflect true CBSE SQP.")

        return questions

    def _resolve_qtype(self, node, base_qtype: QuestionTypeCode) -> QuestionTypeCode:
        """Resolves best question type ensuring tier compliance."""
        # Don't override MCQs
        if base_qtype in [QuestionTypeCode.MCQ, QuestionTypeCode.ASSERTION_REASON]:
            return base_qtype
            
        # For 3-5 marks, allow diagram/numerical/case study overrides
        if node.base_numerical_depth > 0.70 and base_qtype != QuestionTypeCode.LONG_ANSWER:
            return QuestionTypeCode.NUMERICAL
        if "circ" in node.concept_id.lower() or "nut" in node.concept_id.lower():
            return QuestionTypeCode.DIAGRAM
        if node.base_reasoning_steps >= 4:
            return QuestionTypeCode.CASE_STUDY
            
        return base_qtype

    def _compile_answer_keys(
        self, questions: List[QuestionInstance], concept_ids: List[str]
    ) -> List[AnswerKeyRubric]:
        """Compiles marking rubrics for all questions."""
        keys: List[AnswerKeyRubric] = []
        for idx, q in enumerate(questions):
            cid = concept_ids[idx] if idx < len(concept_ids) else ""
            profile = self._weights.get_weight_profile(cid)
            comp = profile.target_nep_competency_code

            if q.question_type == QuestionTypeCode.NUMERICAL:
                keys.append(AnswerKeyRubric(
                    question_id=q.question_id,
                    expected_answer="Step-by-step: Given → Formula → Substitution → Answer with units.",
                    rubrics=[
                        RubricCriteria("R1", "Given values with signs", 0.5, comp),
                        RubricCriteria("R2", "Formula statement", 0.5, comp),
                        RubricCriteria("R3", "Algebraic steps", 1.0, comp),
                        RubricCriteria("R4", "Final answer with units", 1.0, comp),
                    ],
                    evaluator_tip="Award partial credit for correct formula even with algebraic slips."
                ))
            else:
                keys.append(AnswerKeyRubric(
                    question_id=q.question_id,
                    expected_answer="Explanatory points with scientific reasoning.",
                    rubrics=[
                        RubricCriteria("R1", "Core scientific points", 1.0, comp),
                        RubricCriteria("R2", "Supporting explanations", 1.0, comp),
                        RubricCriteria("R3", "Equations/diagrams if applicable", 1.0, comp),
                    ],
                    evaluator_tip="Look for keywords matching Bloom's action verbs."
                ))
        return keys

    def _compute_analytics(
        self, questions: List[QuestionInstance], concept_ids: List[str]
    ) -> PaperAnalyticsDashboard:
        """Computes paper analytics dashboard."""
        total_marks = sum(q.assigned_marks for q in questions)
        total_qs = len(questions)

        if total_qs == 0:
            return PaperAnalyticsDashboard(0, 0, 0.0, "Empty", {}, {}, [])

        # Difficulty
        diffs = []
        for idx, q in enumerate(questions):
            cid = concept_ids[idx] if idx < len(concept_ids) else "C10_PHY_OHM"
            diffs.append(self._diff_engine.estimate_difficulty(cid, q.blooms_level))
        avg_diff = sum(diffs) / len(diffs)

        skew = "Balanced"
        if avg_diff > 0.65:
            skew = "Hard Paper Skew"
        elif avg_diff < 0.40:
            skew = "Easy Paper Skew"

        # Blooms distribution
        blooms_cnt = {}
        for q in questions:
            blooms_cnt[q.blooms_level] = blooms_cnt.get(q.blooms_level, 0) + 1

        # Stream distribution
        stream_cnt = {}
        for q in questions:
            stream_cnt[q.stream] = stream_cnt.get(q.stream, 0) + 1
        stream_dist = {s: c / total_qs for s, c in stream_cnt.items()}

        # NEP competencies
        nep = set()
        for cid in concept_ids:
            p = self._weights.get_weight_profile(cid)
            if p.target_nep_competency_code:
                nep.add(p.target_nep_competency_code)

        return PaperAnalyticsDashboard(
            total_marks=total_marks,
            total_questions=total_qs,
            average_difficulty=avg_diff,
            difficulty_skewness=skew,
            blooms_distribution=blooms_cnt,
            stream_distribution=stream_dist,
            nep_competency_coverage=list(nep)
        )
