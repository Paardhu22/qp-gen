import logging
import re
import dataclasses
from typing import List, Dict, Any, Iterable

from django.conf import settings

from q_instructions.master.facade import AcademicGenerationFacade, GeneratePaperRequest

logger = logging.getLogger("[GEN_ROUTER]")
logger.setLevel(logging.INFO)


SUPPORTED_SUBJECTS = {"science", "social science"}


@dataclasses.dataclass(frozen=True)
class QuestionGenerationSlot:
    """A deterministic, pre-LLM contract for exactly one generated question."""

    index: int
    section_title: str
    subject: str
    stream: str
    question_type: str
    legacy_type: str
    marks: int
    difficulty: str
    class_num: int
    exact_instruction: str
    retrieval_query: str


def normalize_subject(subject: str) -> str:
    subject_norm = str(subject or "").strip().lower()
    if subject_norm in SUPPORTED_SUBJECTS:
        return subject_norm
    if subject_norm.replace("_", " ") in SUPPORTED_SUBJECTS:
        return subject_norm.replace("_", " ")
    return subject_norm


def extract_class_number(class_value: object, default: int = 10) -> int:
    class_str = str(class_value or "").strip().lower()
    digits = "".join(filter(str.isdigit, class_str))
    return int(digits) if digits else default

def should_use_new_engine(payload: dict) -> bool:
    """
    Determines if the payload is eligible for the new academic science engine.
    Eligibility rule:
    board == "CBSE" AND subject == "Science" AND class == 10
    """
    logger.info(f"[GEN_ROUTER] RAW PAYLOAD:\n{payload}")
    
    if not settings.QG_NEW_ENGINE_ENABLED:
        logger.info("[ROUTE_DECISION] QG_NEW_ENGINE_ENABLED is false; q_instructions routing remains enforced.")

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
    subject_norm = normalize_subject(subject)
    
    # Class cleanup - extract digits and match 10 (tolerant to Class 10, 10th, 10, etc.)
    class_str = str(class_val).strip().lower()
    digits = "".join(filter(str.isdigit, class_str))
    class_num = int(digits) if digits else None
    
    logger.info(f"[GEN_ROUTER] NORMALIZED VALUES:\nboard={board_norm}\nsubject={subject_norm}\nclass={class_num}")
    
    is_eligible = (board_norm == "CBSE" and subject_norm in ["science", "social science"] and class_num is not None and 1 <= class_num <= 10)
    
    logger.info(f"[GEN_ROUTER] ELIGIBILITY RESULT: {is_eligible}")
    
    if is_eligible:
        logger.info(f"[ROUTE_DECISION] Using NEW engine for {board_norm} Class {class_num} {subject.strip()}")
    else:
        reason = "Mismatch: "
        if board_norm != "CBSE": reason += f"board({board_norm}!=CBSE) "
        if subject_norm not in ["science", "social science"]: reason += f"subject({subject_norm} not valid) "
        if class_num is None or not (1 <= class_num <= 10): reason += f"class({class_num} not in 1-10)"
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


def build_social_science_blueprint_instructions(difficulty: str, count: int, class_num: int) -> str:
    rules = [
        "ACADEMIC BLUEPRINT INSTRUCTIONS (MANDATORY):",
        f"- Board: CBSE | Class: {class_num} | Subject: Social Science",
        f"- Overall Difficulty Target: {difficulty.upper()}",
    ]
    if count > 0:
        rules.append(f"- You MUST generate exactly {count} questions in total.")
    else:
        rules.append("- You MUST follow the EXACT CBSE question count and pattern for this class.")
        
    rules.append("- Your questions MUST strictly use the provided PDF context. No hallucinations.")

    if class_num in [1, 2]:
        rules.extend([
            "GRADE ROUTING TIER: 1A (Social Awareness, EVS)",
            "- Output format: ONE unified paper. NO SECTIONS. NO stream split.",
            "- Bloom's Level: L1 ONLY (Identify, name, recognize).",
            "- ALLOWED TYPES: Match the following, Fill in the blank, True/False, Circle the correct picture, One-word/one-line answer.",
            "- PROHIBITED: NO 4-option MCQs. NO Assertion-Reason. NO map questions. NO 'explain' or 'why' questions.",
            "- Marks per question: Strictly 1 mark.",
            "- Language: Simple everyday words."
        ])
    elif class_num in [3, 4, 5]:
        rules.extend([
            "GRADE ROUTING TIER: 1B (Social Studies, Primary Upper)",
            "- Output format: ONE unified paper. NO SECTIONS. NO formal track split.",
            "- Bloom's Level: L1-L2 ONLY.",
            "- ALLOWED TYPES: MCQ (4 options, simple), Fill in the blank, True/False, Match the following, Short Answer (1-2 sentences), Draw/label a map.",
            "- PROHIBITED: NO Assertion-Reason. NO Case-based. NO skill-based map identification (only fill/draw). NO 3, 4, or 5-mark questions.",
            "- Max question marks: 2."
        ])
    elif class_num in [6, 7, 8]:
        rules.extend([
            f"GRADE ROUTING TIER: 2/3 (General Social Science) - Class {class_num}",
            "- Output format: ONE unified paper. Sections are defined by MARKS TIER, not by subject.",
            "- Section A: MCQ (1m). Section B: VSA (2m). Section C: Short Answer (3m). Section D: Long Answer (5m). Section E: Case-Based (4m).",
            "- Subject Coverage: History (~25-30%), Geography (~25-30%), Political Science (~20-25%), Economics (~15-25% if applicable).",
            "- OR CHOICES: Allowed ONLY in Section C (3m) and Section D (5m).",
            "- Map questions are embedded, no separate section.",
        ])
        if class_num == 8:
            rules.extend([
                "- ALLOWED MCQ TYPES: Standard factual, statement-based, match columns, assertion-reason (starts at class 8).",
                "- Bloom's Level: L1-L4."
            ])
        else:
            rules.extend([
                "- ALLOWED MCQ TYPES: Standard factual, statement-based, match columns. NO Assertion-Reason. NO Cartoon-based.",
                f"- Bloom's Level: {'L1-L2' if class_num == 6 else 'L1-L3'}."
            ])
    else:
        rules.extend([
            "GRADE ROUTING TIER: 4 (Four-Track Social Science) - Class 9-10",
            "- Output format: STRICTLY split into four tracks: Section A (History), Section B (Geography), Section C (Political Science), Section D (Economics).",
            "- Total marks per section: Exactly 20 marks each.",
            "- Word limits: VSA=40 words, SA=60 words, LA=120 words, CBQ=100 words per sub-question. Must include these limits in instructions.",
            "- SECTION A (History): OR choices at 2m, 3m, AND 5m. Includes 2m Map question (with VI alternative text). Has CBQ.",
            "- SECTION B (Geography): NO 3-mark SA question. Includes 3m Map question (with VI alternative). OR only at 5m and Map Part I. Has CBQ.",
            "- SECTION C (Civics): Exclusive home of Assertion-Reason and Cartoon-based MCQs (with VI alternative). NO Map question. TWO 2m VSA questions. OR only at 5m. Has CBQ.",
            "- SECTION D (Economics): NO 2-mark VSA question. NO CBQ. NO Map question. THREE 3-mark SA questions. OR only at 5m.",
            "- CBQ rules: Always exactly 3 sub-questions totaling 4 marks (e.g. 1+1+2). No OR within CBQ."
        ])
        
    return "\n".join(rules)


def build_blueprint_instructions(
    topic: str,
    difficulty: str,
    count: int,
    class_num: int = 10,
    subject: str = "science",
) -> str:
    """
    Returns strict pedagogical prompt for the LLM based on Grade Tiers.
    """
    subject_norm = str(subject).strip().lower()
    if subject_norm == "social science":
        return build_social_science_blueprint_instructions(difficulty, count, class_num)

    logger.info(f"[NEW_ENGINE] Compiling academic blueprint for Class {class_num}...")
    
    rules = [
        "ACADEMIC BLUEPRINT INSTRUCTIONS (MANDATORY):",
        f"- Board: CBSE | Class: {class_num} | Subject: {'EVS' if class_num <= 5 else 'Science'}",
        f"- Overall Difficulty Target: {difficulty.upper()}",
    ]
    if count > 0:
        rules.append(f"- You MUST generate exactly {count} questions in total.")
    else:
        rules.append("- You MUST follow the EXACT CBSE question count and pattern for this class.")
        
    rules.append("- Your questions MUST strictly use the provided PDF context. No hallucinations.")

    # Tier 1A: Classes 1-2
    if class_num in [1, 2]:
        rules.extend([
            "GRADE ROUTING TIER: 1A (EVS, Primary Lower)",
            "- Output format: ONE unified paper. NO SECTIONS. NO stream split.",
            "- Bloom's Level: L1 ONLY (Recall, Identify, Name).",
            "- ALLOWED TYPES: Match the following, Fill in the blank, True/False, Circle the correct answer, Draw and color, One-word answer.",
            "- PROHIBITED: NO 4-option MCQs. NO Assertion-Reason. NO Case-based. NO Numericals. NO written sentences. NO OR choices.",
            "- Marks per question: Strictly 1 mark (Draw and color can be 1-2 marks)."
        ])
    # Tier 1B: Classes 3-5
    elif class_num in [3, 4, 5]:
        rules.extend([
            "GRADE ROUTING TIER: 1B (EVS, Primary Upper)",
            "- Output format: ONE unified paper. NO SECTIONS. NO stream split.",
            "- Bloom's Level: L1-L2 ONLY.",
            "- ALLOWED TYPES: Simple 4-option MCQ, Fill in the blank, True/False, Short Answer (1-2 sentences), Draw and label (3-5 parts), Match the following.",
            "- PROHIBITED: NO Assertion-Reason. NO OR choices. NO Case-based. NO Numericals. NO 3 or 4 mark questions.",
            "- Language: Everyday language. Do not ask for paragraphs."
        ])
    # Tier 2: Classes 6-7
    elif class_num in [6, 7]:
        rules.extend([
            "GRADE ROUTING TIER: 2 (General Science)",
            "- Output format: ONE unified paper. NO SECTIONS. NO stream split.",
            "- Bloom's Level: L1-L3.",
            "- ALLOWED TYPES: MCQ (1m), VSA (1m), Short Answer I (2m), Short Answer II (3m), Long Answer (4-5m), Diagram-based (2-3m).",
            "- PROHIBITED: NO Assertion-Reason. NO Case-based. NO VI alternatives.",
            "- OR CHOICES: Allowed ONLY in Long Answer (4-5m).",
            "- MARKS LADDER: Questions MUST follow strict internal progression: 1m MCQs -> 1m VSA -> 2m SA -> 3m SA -> 4/5m LA."
        ])
    # Tier 3: Class 8
    elif class_num == 8:
        rules.extend([
            "GRADE ROUTING TIER: 3 (Transitional Science)",
            "- Output format: ONE unified paper. NO SECTIONS.",
            "- Bloom's Level: L1-L4.",
            "- ALLOWED TYPES: MCQ (1m), Assertion-Reason (1m), VSA (1-2m), Short Answer (3m), Long Answer (4-5m), Simple case-based (3-4m), Diagram-based (2-3m).",
            "- OR CHOICES: Allowed ONLY in Long Answer (4-5m).",
            "- MARKS LADDER: 1m MCQs -> 1m Assertion-Reason -> 2m VSA -> 3m SA -> 4/5m LA."
        ])
    # Tier 4: Classes 9-10
    else:
        rules.extend([
            "GRADE ROUTING TIER: 4 (Stream Science)",
            "- Output format: STRICTLY split into Section A (Biology), Section B (Chemistry), Section C (Physics).",
            "- Proportions: Biology MUST carry ~38% of questions/marks. Chemistry and Physics share the remainder equally.",
            "- Bloom's Level: L1-L6.",
            "- MARKS LADDER: Inside EACH section, marks MUST progress: 1m -> 2m -> 3m -> 4m -> 5m.",
            "- OR CHOICES: Applied to questions of 2 marks and above. 5-mark questions ALWAYS have an OR choice. NEVER in 1-mark questions.",
            "- SPECIAL RULES: Diagram questions MUST have a Visually Impaired (VI) text alternative. Physics must be numerical-dominant. Competency-based questions appear in 3-4 mark tier.",
            "Distribute questions across MCQ, ASSERTION_REASON, SHORT, LONG, and CASE_STUDY logically."
        ])
        
    return "\n".join(rules)


def default_cbse_question_count(subject: str, class_num: int) -> int:
    subject_norm = normalize_subject(subject)
    if class_num == 10 and subject_norm == "science":
        return 38
    if class_num == 10 and subject_norm == "social science":
        return 37
    if class_num >= 8:
        return 20
    if class_num >= 6:
        return 15
    return 10


def _legacy_question_type(qtype_name: str) -> str:
    if qtype_name == "MCQ":
        return "MCQ"
    if qtype_name == "ASSERTION_REASON":
        return "ASSERTION_REASON"
    if qtype_name == "CASE_STUDY":
        return "CASE_STUDY"
    if qtype_name == "LONG_ANSWER":
        return "LONG"
    if qtype_name == "DIAGRAM":
        return "DIAGRAM"
    return "SHORT"


def _section_title_for_stream(subject_norm: str, stream_name: str, class_num: int) -> str:
    if class_num < 9:
        return "Section A: Questions"

    if subject_norm == "social science":
        titles = {
            "HISTORY": "Section A: History",
            "GEOGRAPHY": "Section B: Geography",
            "CIVICS": "Section C: Political Science",
            "ECONOMICS": "Section D: Economics",
        }
        return titles.get(stream_name, f"Section: {stream_name.title()}")

    titles = {
        "BIOLOGY": "Section A: Biology",
        "CHEMISTRY": "Section B: Chemistry",
        "PHYSICS": "Section C: Physics",
    }
    return titles.get(stream_name, f"Section: {stream_name.title()}")


def _slot_instruction(slot: QuestionGenerationSlot) -> str:
    qtype = slot.question_type
    lines = [
        f"Generate exactly ONE {slot.marks}-mark {qtype} question.",
        f"Subject: {slot.subject} | Class: {slot.class_num} | Stream/Track: {slot.stream}.",
        f"Difficulty target: {slot.difficulty}.",
        "Use only the retrieved textbook chunks. Do not introduce unsupported facts.",
        f"The JSON field 'marks' MUST be {slot.marks}.",
        f"The JSON field 'type' MUST be {slot.legacy_type}.",
    ]

    if qtype == "MCQ":
        lines.append("Provide exactly four plausible options and one correct answer.")
    elif qtype == "ASSERTION_REASON":
        lines.append(
            "Format content as 'Assertion (A): ...\\nReason (R): ...' and provide the four standard assertion-reason options."
        )
    elif qtype == "CASE_STUDY":
        lines.append("Create a short source-backed passage followed by exactly three sub-questions.")
    elif qtype == "LONG_ANSWER":
        lines.append("Require structured reasoning appropriate for a long-answer response.")

    return "\n".join(lines)


def _make_slot(
    *,
    index: int,
    section_title: str,
    subject: str,
    stream: str,
    qtype_name: str,
    marks: int,
    difficulty: str,
    class_num: int,
    topic: str,
    instructions: str,
) -> QuestionGenerationSlot:
    legacy_type = _legacy_question_type(qtype_name)
    query_parts = [
        topic.strip(),
        subject,
        f"class {class_num}",
        stream.replace("_", " "),
        qtype_name.replace("_", " "),
        f"{marks} mark",
        difficulty,
        instructions[:240].strip(),
    ]
    retrieval_query = " ".join(part for part in query_parts if part)
    draft = QuestionGenerationSlot(
        index=index,
        section_title=section_title,
        subject=subject,
        stream=stream,
        question_type=qtype_name,
        legacy_type=legacy_type,
        marks=marks,
        difficulty=difficulty,
        class_num=class_num,
        exact_instruction="",
        retrieval_query=retrieval_query,
    )
    return dataclasses.replace(draft, exact_instruction=_slot_instruction(draft))


def _build_primary_progression(total_questions: int, class_num: int, subject_norm: str):
    from q_instructions.core.enums import QuestionTypeCode

    progression = []
    if class_num <= 2:
        progression = [(QuestionTypeCode.SHORT_ANSWER, 1)] * total_questions
    elif class_num <= 5:
        for i in range(total_questions):
            if i % 3 == 0:
                progression.append((QuestionTypeCode.MCQ, 1))
            else:
                progression.append((QuestionTypeCode.SHORT_ANSWER, 1 if i % 2 else 2))
    elif class_num <= 7:
        for i in range(total_questions):
            if i < max(3, total_questions // 3):
                progression.append((QuestionTypeCode.MCQ, 1))
            elif i < max(6, total_questions // 2):
                progression.append((QuestionTypeCode.SHORT_ANSWER, 2))
            else:
                progression.append((QuestionTypeCode.SHORT_ANSWER, 3))
    else:
        for i in range(total_questions):
            if i < max(4, total_questions // 3):
                progression.append((QuestionTypeCode.MCQ, 1))
            elif subject_norm == "science" and i == max(4, total_questions // 3):
                progression.append((QuestionTypeCode.ASSERTION_REASON, 1))
            elif i >= total_questions - 2:
                progression.append((QuestionTypeCode.LONG_ANSWER, 5))
            elif i >= total_questions - 5:
                progression.append((QuestionTypeCode.CASE_STUDY, 4))
            else:
                progression.append((QuestionTypeCode.SHORT_ANSWER, 3))

    return progression[:total_questions]


def build_question_plan(
    topic: str,
    difficulty: str,
    count: int,
    class_num: int = 10,
    subject: str = "Science",
    instructions: str = "",
) -> List[QuestionGenerationSlot]:
    """
    Materializes q_instructions into one LLM contract per question.

    This is intentionally deterministic. The LLM may write wording, but it does
    not decide counts, marks, sections, or subject-specific routing.
    """
    subject_norm = normalize_subject(subject)
    if subject_norm not in SUPPORTED_SUBJECTS:
        raise ValueError("Only Science and Social Science are configured in q_instructions.")

    total_questions = count if count and count > 0 else default_cbse_question_count(subject_norm, class_num)
    total_questions = max(1, min(total_questions, 50))
    subject_label = "Social Science" if subject_norm == "social science" else "Science"
    slots: List[QuestionGenerationSlot] = []

    if subject_norm == "science" and class_num >= 9:
        from q_instructions.core.enums import StreamType
        from q_instructions.subjects.science.orchestrator import ScienceOrchestratorV2

        orchestrator = ScienceOrchestratorV2()
        allocations = orchestrator.allocate_streams(total_questions)
        stream_order = [StreamType.BIOLOGY, StreamType.CHEMISTRY, StreamType.PHYSICS]
        if total_questions < len(stream_order):
            allocations = {stream: 0 for stream in stream_order}
            for stream in stream_order[:total_questions]:
                allocations[stream] = 1
        for stream in stream_order:
            progression = orchestrator.build_tier_progression(allocations.get(stream, 0))
            for qtype, marks in progression:
                section_title = _section_title_for_stream(subject_norm, stream.name, class_num)
                slots.append(
                    _make_slot(
                        index=len(slots) + 1,
                        section_title=section_title,
                        subject=subject_label,
                        stream=stream.name,
                        qtype_name=qtype.name,
                        marks=marks,
                        difficulty=difficulty,
                        class_num=class_num,
                        topic=topic,
                        instructions=instructions,
                    )
                )
    elif subject_norm == "social science" and class_num >= 9:
        from q_instructions.core.enums import StreamType
        from q_instructions.subjects.social_science.orchestrator import SocialScienceOrchestratorV2

        orchestrator = SocialScienceOrchestratorV2()
        allocations = orchestrator.allocate_streams(total_questions)
        stream_order = [StreamType.HISTORY, StreamType.GEOGRAPHY, StreamType.CIVICS, StreamType.ECONOMICS]
        for stream in stream_order:
            progression = orchestrator.build_tier_progression(allocations.get(stream, 0), stream)
            for qtype, marks in progression:
                section_title = _section_title_for_stream(subject_norm, stream.name, class_num)
                slots.append(
                    _make_slot(
                        index=len(slots) + 1,
                        section_title=section_title,
                        subject=subject_label,
                        stream=stream.name,
                        qtype_name=qtype.name,
                        marks=marks,
                        difficulty=difficulty,
                        class_num=class_num,
                        topic=topic,
                        instructions=instructions,
                    )
                )
    else:
        progression = _build_primary_progression(total_questions, class_num, subject_norm)
        for qtype, marks in progression:
            slots.append(
                _make_slot(
                    index=len(slots) + 1,
                    section_title="Section A: Questions",
                    subject=subject_label,
                    stream="INTEGRATED",
                    qtype_name=qtype.name,
                    marks=marks,
                    difficulty=difficulty,
                    class_num=class_num,
                    topic=topic,
                    instructions=instructions,
                )
            )

    return slots[:total_questions]


def route_and_execute_new_engine(
    topic: str,
    difficulty: str,
    count: int,
    class_num: int = 10,
    subject: str = "Science",
) -> dict:
    """
    Compatibility wrapper used by older integration tests and debug tooling.
    The streaming generation path now uses build_question_plan instead.
    """
    request = GeneratePaperRequest(
        board="CBSE",
        academic_class=f"CLASS_{class_num}",
        exam_type="FINAL",
        chapters=[topic] if topic else [],
        difficulty=difficulty,
        count=count if count and count > 0 else None,
        institution_id="CBSE_OFFICIAL",
        seed=42,
    )
    response = AcademicGenerationFacade().generate_paper(request)
    adapted = adapt_response_to_legacy(response)
    subject_label = "Social Science" if normalize_subject(subject) == "social science" else "Science"
    for section in adapted.get("sections", []):
        for question in section.get("questions", []):
            question.setdefault("metadata", {})["subject"] = subject_label
    return adapted
