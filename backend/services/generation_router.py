import logging
import re
import dataclasses
from typing import List, Dict, Any, Iterable

from django.conf import settings

from q_instructions.master.facade import AcademicGenerationFacade, GeneratePaperRequest

logger = logging.getLogger("[GEN_ROUTER]")
logger.setLevel(logging.INFO)

def should_use_new_engine(payload: dict) -> bool:
    """
    Determines if the payload is eligible for the new academic science engine.
    Eligibility rule:
    board == "CBSE" AND subject == "Science" AND class == 10
    """
    logger.info(f"[GEN_ROUTER] RAW PAYLOAD:\n{payload}")
    
    if not settings.QG_NEW_ENGINE_ENABLED:
        logger.info("[ROUTE_DECISION] Feature flag disabled for new engine")
        return False

    if not payload:
        logger.info("[ROUTE_DECISION] Missing payload entirely")
        return False
        
    board = payload.get("board", "")
    subject = payload.get("subject", "")
    # Support class, class_level, gradeClass, grade_class
    class_val = payload.get("class", payload.get("class_level", payload.get("gradeClass", payload.get("grade_class", ""))))
    
    if not board:
        logger.info("[ROUTE_DECISION] Missing 'board' in payload")
        return False
    if not subject:
        logger.info("[ROUTE_DECISION] Missing 'subject' in payload")
        return False
    if not class_val:
        logger.info("[ROUTE_DECISION] Missing 'class'/'gradeClass' in payload")
        return False
        
    board_norm = str(board).strip().upper()
    subject_norm = str(subject).strip().lower()
    
    # Class cleanup - extract digits and match 10 (tolerant to Class 10, 10th, 10, etc.)
    class_str = str(class_val).strip().lower()
    digits = "".join(filter(str.isdigit, class_str))
    class_num = int(digits) if digits else None
    
    logger.info(f"[GEN_ROUTER] NORMALIZED VALUES:\nboard={board_norm}\nsubject={subject_norm}\nclass={class_num}")
    
    is_eligible = (board_norm == "CBSE" and subject_norm == "science" and class_num == 10)
    
    logger.info(f"[GEN_ROUTER] ELIGIBILITY RESULT: {is_eligible}")
    
    if is_eligible:
        logger.info(f"[ROUTE_DECISION] Using NEW engine for {board_norm} Class {class_num} {subject.strip()}")
    else:
        reason = "Mismatch: "
        if board_norm != "CBSE": reason += f"board({board_norm}!=CBSE) "
        if subject_norm != "science": reason += f"subject({subject_norm}!=science) "
        if class_num != 10: reason += f"class({class_num}!=10)"
        logger.info(f"[ROUTE_DECISION] Falling back to LEGACY engine. Reason: {reason}")
        
    return is_eligible


def extract_mcq_options(content_text: str) -> tuple:
    """
    Extracts MCQ options from standard template text if formatted like:
    (a) Option A
    (b) Option B
    (c) Option C
    (d) Option D
    Returns the clean main question text and the list of extracted options.
    """
    pattern = re.compile(r'\(([a-d])\)\s*(.*?)(?=\s*\([a-d]\)|$)')
    matches = pattern.findall(content_text)
    if len(matches) == 4:
        main_question = re.split(r'\s*\([a-d]\)', content_text)[0].strip()
        options = [m[1].strip() for m in matches]
        return main_question, options
    return content_text, []


def adapt_response_to_legacy(new_response) -> dict:
    """
    Adapts a GeneratedPaperResponse from the new engine to the legacy JSON format.
    """
    from apps.question_generation.adapters.legacy_response import adapt_questions_to_legacy

    return adapt_questions_to_legacy(new_response)


def build_blueprint_instructions(
    topic: str,
    difficulty: str,
    count: int,
) -> str:
    """
    Uses the AcademicGenerationFacade to compile a detailed curriculum blueprint,
    returning a strict pedagogical prompt for the LLM.
    """
    logger.info("[NEW_ENGINE] Compiling academic blueprint for LLM guidance...")
    
    chapters_list = [t.strip() for t in topic.split(",")] if "," in topic else [topic]
    
    # Map incoming request fields into the new engine request schema
    try:
        from apps.question_generation.domain.blueprints.compiler import BlueprintCompiler
        from apps.question_generation.domain.enums import EducationBoard, AcademicClass, ExamType

        compiler = BlueprintCompiler()
        blueprint = compiler.compile(
            board=EducationBoard.CBSE,
            academic_class=AcademicClass.CLASS_10,
            exam_type=ExamType.FINAL,
            total_marks=80,
            chapters=chapters_list,
            difficulty=difficulty,
            count=count,
            institution_policy=None,
        )
        
        rules = [
            "ACADEMIC BLUEPRINT INSTRUCTIONS (MANDATORY):",
            f"- Board: {blueprint.board.name} | Class: {blueprint.academic_class.name} | Exam: {blueprint.exam_type.name}",
            f"- Overall Difficulty Target: {difficulty.upper()}",
            f"- You MUST generate exactly {count} questions in total.",
            "- Your questions MUST strictly use the provided PDF context.",
            "- Distribute questions across MCQ, ASSERTION_REASON, SHORT, LONG, and CASE_STUDY types logically.",
        ]
        
        if blueprint.blooms_distribution:
            rules.append("\nCOGNITIVE COMPLEXITY (Bloom's Taxonomy) TARGETS:")
            for k, v in blueprint.blooms_distribution.items():
                rules.append(f"  * {k.name}: {int(v * 100)}%")
                
        return "\n".join(rules)
    except Exception as e:
        logger.error(f"[NEW_ENGINE] Failed to compile blueprint instructions: {e}")
        return ""
