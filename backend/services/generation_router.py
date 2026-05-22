import logging
import re
import dataclasses
from typing import List, Dict, Any, Iterable

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
    # 1. Build a lookup for expected answers from answer_keys
    answer_lookup = {}
    for ak in new_response.answer_keys:
        answer_lookup[ak["question_id"]] = ak.get("expected_answer", "Explanatory points with scientific reasoning.")

    # 2. Convert standard questions to legacy structure
    legacy_questions = []
    for q in new_response.questions:
        q_id = q.question_id
        content = q.content_text
        q_type = q.question_type # e.g. "MCQ", "SHORT_ANSWER", "NUMERICAL", "DIAGRAM", "CASE_STUDY", "LONG_ANSWER"
        
        # Normalize question types to legacy: MCQ, SHORT, LONG, TF
        legacy_type = "SHORT"
        if q_type == "MCQ":
            legacy_type = "MCQ"
        elif q_type == "LONG_ANSWER":
            legacy_type = "LONG"
        elif q_type in ["SHORT_ANSWER", "NUMERICAL", "DIAGRAM", "CASE_STUDY"]:
            legacy_type = "SHORT"
            
        # Parse MCQ options if type is MCQ
        options = []
        if q_type == "MCQ":
            content, options = extract_mcq_options(content)
            
        answer = answer_lookup.get(q_id, "Explanatory points with scientific reasoning.")
        
        # Build metadata
        metadata = {
            "gradeClass": "10th Grade",
            "subject": "Science",
            "inferredTopic": q.stream, # E.g., Physics, Chemistry, Biology
            "inferredChapter": q.metadata.get("inferredChapter", "Electricity"),
            "sourcePdf": q.metadata.get("sourcePdf", ""),
            "difficulty": q.metadata.get("difficulty", "Medium")
        }
        
        legacy_questions.append({
            "content": content,
            "type": legacy_type,
            "options": options,
            "answer": answer,
            "marks": q.assigned_marks,
            "metadata": metadata
        })

    # Group legacy_questions by type into sections
    sections_map = {}
    for lq in legacy_questions:
        lq_type = lq["type"]
        if lq_type == "MCQ":
            sec_title = "Section A: Multiple Choice Questions (1 Mark)"
        elif lq_type == "LONG":
            sec_title = "Section C: Long Answer Questions (5 Marks)"
        else:
            sec_title = "Section B: Short Answer Questions"
            
        if sec_title not in sections_map:
            sections_map[sec_title] = []
        sections_map[sec_title].append(lq)
        
    sections = []
    for title, qs in sections_map.items():
        sections.append({
            "title": title,
            "questions": qs
        })
        
    return {"sections": sections}


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
    facade = AcademicGenerationFacade()
    
    chapters_list = [t.strip() for t in topic.split(",")] if "," in topic else [topic]
    
    # Map incoming request fields into the new engine request schema
    paper_req = GeneratePaperRequest(
        board="CBSE",
        academic_class="CLASS_10",
        exam_type="FINAL",
        chapters=chapters_list,
        difficulty=difficulty,
        count=count,
        institution_id="CBSE_OFFICIAL",
        seed=42
    )
    
    # Compile blueprint (we use the internal orchestrator's compiler here since facade.generate_paper drafts static templates)
    try:
        from q_instructions.core.enums import EducationBoard, AcademicClass, ExamType
        policy = facade._orchestrator._institutions.get_policy(paper_req.institution_id)
        blueprint = facade._orchestrator._compiler.compile(
            board=EducationBoard.CBSE,
            academic_class=AcademicClass.CLASS_10,
            exam_type=ExamType.FINAL,
            total_marks=80,
            chapters=chapters_list,
            difficulty=difficulty,
            count=count,
            institution_policy=policy
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
