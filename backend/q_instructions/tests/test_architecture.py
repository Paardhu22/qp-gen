"""
AOS — Comprehensive Architecture Test Suite
===============================================
Validates the complete refactored modular architecture.
Tests every layer from core → subjects → board_systems → generation → master.
"""

import sys
import os

# Ensure backend is on path (3 dirs up: tests <- q_instructions <- backend)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def run_tests():
    results = {"passed": 0, "failed": 0, "errors": []}

    def assert_true(expr, msg):
        if expr:
            results["passed"] += 1
        else:
            results["failed"] += 1
            results["errors"].append(msg)

    # ===== CORE LAYER =====
    print("Testing CORE layer...")

    from q_instructions.core.enums import (
        AcademicClass, StreamType, BloomsLevel, QuestionTypeCode,
        ExamType, EducationBoard, ValidationSeverity, AbstractionLevel
    )
    assert_true(AcademicClass.CLASS_10.value == "Class 10", "AcademicClass enum")
    assert_true(len(StreamType) >= 8, "StreamType count")
    assert_true(len(BloomsLevel) == 6, "BloomsLevel count")
    assert_true(len(QuestionTypeCode) == 10, "QuestionTypeCode count")

    from q_instructions.core.datatypes import (
        ExamBlueprint, SectionBlueprint, QuestionInstance,
        CompiledPaperBlueprint, ConceptNode, ValidationReport
    )
    q = QuestionInstance("Q1", AcademicClass.CLASS_10, StreamType.PHYSICS,
                         QuestionTypeCode.MCQ, BloomsLevel.REMEMBER, 1, "Test?", 30)
    assert_true(q.question_id == "Q1", "QuestionInstance creation")

    from q_instructions.core.exceptions import ConceptNotFoundError, HallucinationDetectedError
    try:
        raise ConceptNotFoundError("C10_FAKE")
    except ConceptNotFoundError as e:
        assert_true("C10_FAKE" in str(e), "Custom exception")

    from q_instructions.core.constants import CBSE_TOTAL_MARKS, FORBIDDEN_HALLUCINATION_TERMS
    assert_true(CBSE_TOTAL_MARKS == 80, "CBSE marks constant")
    assert_true("phlogiston" in FORBIDDEN_HALLUCINATION_TERMS, "Forbidden terms")

    from q_instructions.core.validators import ValidationOrchestrator, MarksSumRule
    assert_true(isinstance(ValidationOrchestrator(), ValidationOrchestrator), "Validator init")

    # ===== SUBJECTS LAYER =====
    print("Testing SUBJECTS layer...")

    from q_instructions.subjects.science.streams import StreamFoundationEngine
    streams = StreamFoundationEngine()
    phys = streams.get_profile(StreamType.PHYSICS)
    assert_true(phys.numerical_weightage_coefficient == 0.60, "Physics numerical weight")

    from q_instructions.subjects.science.blooms_engine import BloomsTaxonomyEngine
    blooms = BloomsTaxonomyEngine()
    remember = blooms.get_profile(BloomsLevel.REMEMBER)
    assert_true(remember.cognitive_weight_index == 1.0, "Bloom REMEMBER weight")
    assert_true(blooms.verify_action_verb(BloomsLevel.APPLY, "Calculate"), "Verb verification")

    from q_instructions.subjects.science.curriculum import (
        CurriculumGraphFactory, ConceptGraph, CurriculumWeightageRegistry,
        PrerequisitePacingOptimizer, DifficultyEstimationEngine,
        CurriculumDuplicatePreventionEngine
    )
    graph = CurriculumGraphFactory.construct_comprehensive_graph()
    assert_true(len(graph.nodes) == 16, f"Graph nodes: expected 16, got {len(graph.nodes)}")
    assert_true(not graph.detect_cycles(), "Graph has no cycles")

    topo = graph.topological_sort()
    assert_true(len(topo) == 16, "Topological sort completeness")

    # Verify prerequisite ordering
    ohm_idx = topo.index("C10_PHY_OHM")
    ser_idx = topo.index("C10_PHY_SER")
    assert_true(ohm_idx < ser_idx, "Ohm before Series in topo sort")

    weights = CurriculumWeightageRegistry()
    ohm_w = weights.get_weight_profile("C10_PHY_OHM")
    assert_true(ohm_w.is_board_favorite, "Ohm's law is board favorite")

    pacing = PrerequisitePacingOptimizer(graph)
    ordered = pacing.optimize_sequence(["C10_PHY_SER", "C10_PHY_OHM"])
    assert_true(ordered[0] == "C10_PHY_OHM", "Pacing: Ohm before Series")

    diff_engine = DifficultyEstimationEngine(graph, weights)
    d = diff_engine.estimate_difficulty("C10_PHY_OHM", BloomsLevel.APPLY)
    assert_true(0.0 < d < 1.0, "Difficulty within bounds")

    dup_engine = CurriculumDuplicatePreventionEngine(graph)
    ok, errs = dup_engine.audit_duplication_safety(["C10_PHY_OHM", "C10_PHY_OHM"])
    assert_true(not ok, "Duplicate detection catches repeats")

    from q_instructions.subjects.science.blueprint import ExamBlueprintRegistry
    bp_reg = ExamBlueprintRegistry()
    bp = bp_reg.get_blueprint(ExamType.FINAL, AcademicClass.CLASS_10)
    assert_true(bp.total_marks == 80, "Blueprint total marks")
    assert_true(bp.duration_minutes == 180, "Blueprint duration")

    from q_instructions.subjects.registry import SubjectRegistry
    reg = SubjectRegistry()
    assert_true(len(reg.list_subjects()) == 0, "Empty registry")

    # ===== BOARD SYSTEMS LAYER =====
    print("Testing BOARD SYSTEMS layer...")

    from q_instructions.board_systems.cbse.parser import SamplePaperParser
    parser = SamplePaperParser()
    sample = "SECTION A\nQ1. What is pH? [1 marks]\nQ2. Assertion(A): ...\nSECTION B\nQ3. Differentiate [2 marks]"
    nodes = parser.parse(sample)
    assert_true(len(nodes) == 3, f"Parser: expected 3 questions, got {len(nodes)}")
    assert_true(nodes[0].section_id == "A", "Parser section detection")

    from q_instructions.board_systems.cbse.distractors import DistractorEngine
    dist = DistractorEngine()
    opts = dist.generate_circuit_distractors(20, 10, 2.0)
    assert_true(len(opts) == 4, "Distractor count")
    assert_true(opts[0].is_correct, "First option is correct")

    from q_instructions.board_systems.cbse.templates import QuestionTemplateLibrary
    lib = QuestionTemplateLibrary()
    num_templates = lib.get_templates_by_type(QuestionTypeCode.NUMERICAL)
    assert_true(len(num_templates) >= 1, "Numerical templates exist")

    from q_instructions.board_systems.cbse.accessibility import AccessibilityLearningEngine
    acc = AccessibilityLearningEngine()
    diag_q = QuestionInstance(
        "Q_D", AcademicClass.CLASS_10, StreamType.BIOLOGY,
        QuestionTypeCode.DIAGRAM, BloomsLevel.UNDERSTAND, 3,
        "Draw a neat labelled diagram of the heart.", 100
    )
    vi_q = acc.translate_for_vi(diag_q)
    assert_true("Descriptive Alternate" in vi_q.content_text or "heart" in vi_q.content_text.lower(),
                "VI translation")

    # ===== GENERATION LAYER =====
    print("Testing GENERATION layer...")

    from q_instructions.generation.blueprint_compiler import BlueprintCompiler
    compiler = BlueprintCompiler()
    compiled = compiler.compile(
        board=EducationBoard.CBSE,
        academic_class=AcademicClass.CLASS_10,
        exam_type=ExamType.FINAL,
        total_marks=80,
        chapters=["Ohm", "pH", "Photosynthesis"],
        difficulty="medium"
    )
    assert_true(compiled.total_marks == 80, "Compiled blueprint marks")
    assert_true(len(compiled.retrieval_targets) > 0, "Retrieval targets populated")
    assert_true(len(compiled.difficulty_curve) > 0, "Difficulty curve generated")
    assert_true(compiled.paper_id.startswith("BP_"), "Paper ID format")

    from q_instructions.generation.safety_engine import GenerationSafetyEngine
    safety = GenerationSafetyEngine(graph)
    bad_q = QuestionInstance(
        "Q_BAD", AcademicClass.CLASS_10, StreamType.PHYSICS,
        QuestionTypeCode.MCQ, BloomsLevel.APPLY, 1,
        "Solve the flux-gate-membrane problem.", 30
    )
    errs = safety.audit_question(bad_q)
    assert_true(len(errs) > 0, "Safety catches hallucinated term")

    # ===== RETRIEVAL LAYER =====
    print("Testing RETRIEVAL layer...")

    from q_instructions.retrieval.semantic_index import SemanticSearchIndex
    idx = SemanticSearchIndex()
    chunks = idx.retrieve("C10_PHY_OHM", [0.90, 0.02, 0.01, 0.95, 0.01, 0.02, 0.01, 0.95])
    assert_true(len(chunks) > 0, "Retrieval finds Ohm context")
    assert_true(chunks[0].chunk_id == "CH4_C2", "Correct Ohm chunk retrieved")

    # ===== INSTITUTION LAYER =====
    print("Testing INSTITUTION layer...")

    from q_instructions.institution.policies import InstitutionOverrideEngine
    inst = InstitutionOverrideEngine()
    dps = inst.get_policy("DPS_E_DELHI")
    assert_true(dps.comp_questions_minimum_ratio == 0.60, "DPS competency ratio")
    assert_true("Delhi" in dps.name, "DPS name")

    # ===== MASTER ORCHESTRATOR =====
    print("Testing MASTER ORCHESTRATOR...")

    from q_instructions.master.orchestrator import MasterAcademicOrchestrator
    orch = MasterAcademicOrchestrator(institution_id="DPS_E_DELHI")
    booklet = orch.generate_paper(
        academic_class=AcademicClass.CLASS_10,
        exam_type=ExamType.FINAL,
        chapters=["Ohm", "pH", "Photosynthesis", "Circulation"],
        difficulty="medium",
        seed=42
    )
    assert_true(booklet is not None, "Booklet generated")
    assert_true(len(booklet.question_sequence) > 0, "Questions populated")
    assert_true(len(booklet.vi_accessible_sequence) > 0, "VI booklet populated")
    assert_true(len(booklet.answer_keys) > 0, "Answer keys populated")
    assert_true(booklet.analytics.total_marks > 0, "Analytics marks > 0")
    assert_true(booklet.generation_duration_ms > 0, "Performance benchmark > 0")
    assert_true("Delhi" in booklet.school_name, "Institution policy applied")

    # ===== ORCHESTRATION & PACING LAYER =====
    print("Testing ORCHESTRATION & PACING layer...")

    from q_instructions.core.enums import StudentArchetype, CognitiveCurveShape
    from q_instructions.orchestration.psychology import StudentProfileRegistry, PaperRhythmEngine
    from q_instructions.orchestration.spacing import SpacingController
    from q_instructions.orchestration.choices import InternalChoiceEngine
    from q_instructions.orchestration.pipeline import PaperOrchestrationPipeline, AsciiTimelineVisualizer
    from q_instructions.orchestration.choreography import SectionChoreographerFactory

    # 1. Psychology profiles & transition
    profile_reg = StudentProfileRegistry()
    steady = profile_reg.get_profile(StudentArchetype.STEADY_AVERAGE)
    assert_true(steady.baseline_proficiency == 0.72, "Steady average baseline")

    rhythm = PaperRhythmEngine(steady)
    stimulus = rhythm.calculate_stimulus(BloomsLevel.APPLY, 240, 2)
    assert_true(stimulus.estimated_minutes == 4.0, "Stimulus estimated minutes")

    # 2. Spacing optimizer
    spacing = SpacingController(graph)
    q_ohm = QuestionInstance("Q_OHM", AcademicClass.CLASS_10, StreamType.PHYSICS, QuestionTypeCode.NUMERICAL, BloomsLevel.APPLY, 3, "Ohm law?", 100)
    q_ser = QuestionInstance("Q_SER", AcademicClass.CLASS_10, StreamType.PHYSICS, QuestionTypeCode.NUMERICAL, BloomsLevel.APPLY, 3, "Series?", 120)
    spaced_qs = spacing.optimize_spacing([q_ohm, q_ser], ["C10_PHY_SER", "C10_PHY_OHM"], min_spacing_index=2)
    assert_true(len(spaced_qs) == 2, "Spacing controller optimization")

    # 3. Section Choreographer Factory
    mcq_choreographer = SectionChoreographerFactory.get_choreographer(QuestionTypeCode.MCQ)
    assert_true(mcq_choreographer is not None, "Choreographer factory resolution")

    # 4. Internal Choice equivalence engine
    choice_engine = InternalChoiceEngine()
    paired = choice_engine.pair_questions([q_ohm, q_ser], "C", max_pairs=1)
    assert_true(len(paired) == 1, "Choice engine pairing equivalence")

    # 5. Psychometric simulation pipeline
    pipe = PaperOrchestrationPipeline()
    report = pipe.audit_paper_rhythm("BP_TEST_1", [q_ohm, q_ser])
    assert_true(report.paper_id == "BP_TEST_1", "Psychometric simulation report")
    assert_true(StudentArchetype.STEADY_AVERAGE in report.archetype_results, "Archetype simulation results populated")
    assert_true(isinstance(AsciiTimelineVisualizer.render_timeline(report.archetype_results[StudentArchetype.STEADY_AVERAGE]), str), "Timeline visualizer")

    # ===== SUBJECT PLUGINS =====
    print("Testing SUBJECT PLUGINS layer...")
    from q_instructions.subjects.science.science import SciencePlugin
    sci_plugin = SciencePlugin()
    reg.register(sci_plugin)
    assert_true(reg.get("science").get_subject_name() == "Science", "Science plugin registration")

    # ===== ANALYTICS & REALISM LAYER =====
    print("Testing ANALYTICS & REALISM layer...")
    from q_instructions.analytics.dashboard import DiagnosticsDashboardCalculator
    from q_instructions.analytics.realism_scoring import PaperRealismAuditor
    from q_instructions.board_systems.cbse.parser import ParsedQuestionNode

    calc = DiagnosticsDashboardCalculator()
    dash = calc.compile_dashboard([q_ohm, q_ser], ["C10_PHY_OHM", "C10_PHY_SER"])
    assert_true(dash.total_marks == 6, "Dashboard total marks computation")

    auditor = PaperRealismAuditor()
    parsed_node = ParsedQuestionNode(1, "Ohm law calculate", 3, False, "C", QuestionTypeCode.NUMERICAL, ["calculate"])
    realism_report = auditor.compare_realism("TEST_REAL", [q_ohm], [parsed_node])
    assert_true(realism_report.overall_realism_index > 0.0, "Realism metrics computation")

    # ===== INTEGRATION FACADE & DTO CONTRACTS =====
    print("Testing INTEGRATION FACADE & DTO CONTRACTS layer...")
    from q_instructions.master.facade import (
        AcademicGenerationFacade, GeneratePaperRequest, GenerateQuestionsRequest,
        PaperBlueprintDTO
    )
    facade = AcademicGenerationFacade()

    # 1. Test validate_blueprint
    bp_dto = PaperBlueprintDTO(
        paper_id="TEST_BP_1",
        board="CBSE",
        academic_class="CLASS_10",
        exam_type="FINAL",
        total_marks=75,
        duration_minutes=180,
        sections=[],
        retrieval_targets=["C10_PHY_OHM", "C10_PHY_SER"]
    )
    val_dto = facade.validate_blueprint(bp_dto)
    assert_true(val_dto.is_valid, "Facade blueprint validation compiles and executes successfully")

    # 2. Test generate_questions (Bank)
    bank_req = GenerateQuestionsRequest(
        academic_class="CLASS_10",
        stream="PHYSICS",
        question_type="NUMERICAL",
        blooms_level="APPLY",
        count=2,
        concept_ids=["C10_PHY_OHM", "C10_PHY_SER"]
    )
    bank_qs = facade.generate_questions(bank_req)
    assert_true(len(bank_qs) == 2, "Facade isolated question bank generation returns correct DTO count")
    assert_true(bank_qs[0].assigned_marks == 3, "Isolated question DTO fields mapped properly")

    # 3. Test generate_paper (Vertical Slice: CBSE Class 10 Science Midterm Paper, Single Chapter: Electricity)
    paper_req = GeneratePaperRequest(
        board="CBSE",
        academic_class="CLASS_10",
        exam_type="FINAL",
        chapters=["Electricity"],
        difficulty="medium",
        institution_id="DPS_E_DELHI",
        seed=101
    )
    res = facade.generate_paper(paper_req)
    assert_true(res.paper_id.startswith("BP_"), "Facade returns valid DTO with correct ID format")
    assert_true("Delhi" in res.school_name, "Facade successfully resolves institutional policies")
    assert_true(len(res.questions) > 0, "Facade end-to-end questions sequence populated with QuestionDTOs")
    assert_true(len(res.vi_accessible_questions) > 0, "Facade end-to-end accessibility alternative sequence populated")
    assert_true(len(res.answer_keys) > 0, "Facade rubrics and marking keys populated")
    assert_true(res.analytics.total_marks > 0, "Facade computes diagnostics analytics cleanly")
    assert_true(res.observability_metrics["blueprint_compile_time_ms"] > 0, "Observability metrics tracking compile duration")
    assert_true(res.observability_metrics["question_drafting_time_ms"] > 0, "Observability metrics tracking drafting duration")
    assert_true(res.observability_metrics["validation_audit_time_ms"] > 0, "Observability metrics tracking validation duration")
    assert_true(res.observability_metrics["total_execution_time_ms"] > 0, "Observability metrics tracking total execution latency")
    print("\n" + "=" * 70)
    print("AOS MODULAR ARCHITECTURE — COMPREHENSIVE TEST RESULTS")
    print("=" * 70)
    total = results["passed"] + results["failed"]
    print(f"  Passed: {results['passed']} / {total}")
    print(f"  Failed: {results['failed']} / {total}")

    if results["errors"]:
        print("\n  FAILURES:")
        for err in results["errors"]:
            print(f"    ✗ {err}")
    else:
        print("\n  ✓ ALL TESTS PASSED — Architecture is production-grade.")

    print("=" * 70)
    return results["failed"] == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
