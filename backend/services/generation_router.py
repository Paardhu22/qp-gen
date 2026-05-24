import logging
import re
import dataclasses
from collections import Counter
from typing import List, Dict, Any, Iterable, Optional, Tuple

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
    choice_required: bool = False
    requires_image: bool = False
    vi_required: bool = False
    instruction_hint: str = ""


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


def _type_label(question_type: str, marks: int) -> str:
    labels = {
        "MCQ": "MCQs",
        "ASSERTION_REASON": "Assertion-Reason",
        "SHORT_ANSWER": "VSAs" if marks == 2 else "Short Answers",
        "LONG_ANSWER": "Long Answers",
        "CASE_STUDY": "Case-Based",
        "DIAGRAM": "Diagram/Map",
    }
    return labels.get(question_type, question_type.replace("_", " ").title())


def summarize_question_plan(plan: List[QuestionGenerationSlot]) -> Dict[str, Any]:
    counts = Counter((slot.question_type, slot.marks) for slot in plan)
    ordered_keys: List[Tuple[str, int]] = []
    for slot in plan:
        key = (slot.question_type, slot.marks)
        if key not in ordered_keys:
            ordered_keys.append(key)
    exact_counts = [
        f"{count} {_type_label(question_type, marks)} ({marks}m)"
        for question_type, marks in ordered_keys
        for count in [counts[(question_type, marks)]]
    ]
    section_marks: Dict[str, int] = {}
    section_questions: Dict[str, int] = {}
    for slot in plan:
        section_marks[slot.section_title] = section_marks.get(slot.section_title, 0) + slot.marks
        section_questions[slot.section_title] = section_questions.get(slot.section_title, 0) + 1

    return {
        "total_questions": len(plan),
        "total_marks": sum(slot.marks for slot in plan),
        "or_choices": sum(1 for slot in plan if slot.choice_required),
        "image_questions": sum(1 for slot in plan if slot.requires_image),
        "vi_alternatives": sum(1 for slot in plan if slot.vi_required),
        "exact_counts": exact_counts,
        "section_marks": section_marks,
        "section_questions": section_questions,
    }


def build_plan_blueprint_instructions(
    *,
    plan: List[QuestionGenerationSlot],
    difficulty: str,
    class_num: int,
    subject: str,
) -> str:
    subject_label = "Social Science" if normalize_subject(subject) == "social science" else "Science"
    summary = summarize_question_plan(plan)
    lines = [
        "CBSE QUESTION PLAN (STRICT):",
        f"- Board: CBSE | Class: {class_num} | Subject: {subject_label}",
        f"- Difficulty target: {difficulty.upper()}",
        (
            f"- Generate EXACTLY {summary['total_questions']} question objects "
            f"for EXACTLY {summary['total_marks']} marks."
        ),
        f"- Exact counts: {'; '.join(summary['exact_counts'])}.",
        (
            f"- Internal OR choices required: {summary['or_choices']}. "
            "Each OR alternative MUST be nested in the parent question's `or_choice` field and MUST NOT be a separate question object. The backend prints OR visibly."
        ),
        f"- Image/map/diagram slots: {summary['image_questions']}. VI alternatives required: {summary['vi_alternatives']}.",
        "- Use only retrieved chunks and supplied images. No unsupported facts.",
    ]
    section_line = "; ".join(
        f"{title}: {summary['section_questions'][title]} questions, {summary['section_marks'][title]} marks"
        for title in summary["section_marks"]
    )
    if section_line:
        lines.append(f"- Locked sections: {section_line}.")
    return "\n".join(lines)


def build_general_instructions(plan: List[QuestionGenerationSlot], subject: str, class_num: int) -> List[str]:
    subject_norm = normalize_subject(subject)
    if class_num in [9, 10] and subject_norm == "science":
        return [
            f"This question paper consists of {len(plan)} questions in 3 sections. Section A is Biology, Section B is Chemistry, Section C is Physics.",
            "All questions are compulsory. However, an internal choice is provided in some questions. Attempt only one alternative wherever OR is given.",
            "The paper follows the CBSE Science stream-wise pattern and carries 80 marks.",
            "Questions with visual, diagram, table, circuit, optics, or lab-setup dependency include a Visually Impaired alternative where required.",
        ]
    if class_num in [9, 10] and subject_norm == "social science":
        return [
            f"There are {len(plan)} questions in the Question Paper. All questions are compulsory.",
            "The question paper has four Sections: A-History, B-Geography, C-Political Science, and D-Economics.",
            "Each Section is of 20 Marks.",
            "Very Short Answer Type Questions (VSA): 2 marks each. Max 40 words.",
            "Short Answer Type Questions (SA): 3 marks each. Max 60 words.",
            "Long Answer Type Questions (LA): 5 marks each. Max 120 words.",
            "Case-Based Questions (CBQ): 4 marks each, 3 sub-questions. Max 100 words.",
            "Map questions: Section A-History (2 marks), Section B-Geography (3 marks).",
            "No overall choice. Internal choice is provided in some questions.",
            "Separate VI questions are provided for visual/map/cartoon questions.",
        ]
    if subject_norm == "social science" and 6 <= class_num <= 8:
        return [
            "All questions are compulsory.",
            "Section A contains MCQs, Section B contains VSA questions, Section C contains SA questions, Section D contains LA questions, and Section E contains CBQs where applicable.",
            "Internal choice is provided only in Section C and Section D where specified.",
        ]
    return ["All questions are compulsory.", "Questions are generated from the uploaded source material only."]


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
    plan: Optional[List[QuestionGenerationSlot]] = None,
) -> str:
    """
    Returns strict pedagogical prompt for the LLM based on Grade Tiers.
    """
    if plan is not None:
        return build_plan_blueprint_instructions(
            plan=plan,
            difficulty=difficulty,
            class_num=class_num,
            subject=subject,
        )

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
        return 39
    if class_num == 10 and subject_norm == "social science":
        return 38
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
        return "Questions"

    if subject_norm == "social science":
        titles = {
            "HISTORY": "Section A - History",
            "GEOGRAPHY": "Section B - Geography",
            "CIVICS": "Section C - Political Science",
            "ECONOMICS": "Section D - Economics",
        }
        return titles.get(stream_name, f"Section: {stream_name.title()}")

    titles = {
        "BIOLOGY": "Section A - Biology",
        "CHEMISTRY": "Section B - Chemistry",
        "PHYSICS": "Section C - Physics",
    }
    return titles.get(stream_name, f"Section: {stream_name.title()}")


def _section_title_for_question_type(subject_norm: str, class_num: int, qtype_name: str, marks: int) -> str:
    if subject_norm == "social science" and 6 <= class_num <= 8:
        if qtype_name in {"MCQ", "ASSERTION_REASON"}:
            return "Section A - MCQ"
        if marks == 2:
            return "Section B - Very Short Answer"
        if marks == 3:
            return "Section C - Short Answer"
        if marks == 5:
            return "Section D - Long Answer"
        if qtype_name == "CASE_STUDY" or marks == 4:
            return "Section E - Case-Based Questions"
    return "Questions"


def _slot_instruction(slot: QuestionGenerationSlot) -> str:
    qtype = slot.question_type
    lines = [
        f"Generate exactly ONE {slot.marks}-mark {qtype} question.",
        f"Subject: {slot.subject} | Class: {slot.class_num} | Stream/Track: {slot.stream}.",
        f"Difficulty target: {slot.difficulty}.",
        "Use only the retrieved textbook chunks. Do not introduce unsupported facts.",
        f"The JSON field 'marks' MUST be {slot.marks}.",
        f"The JSON field 'type' MUST be {slot.legacy_type}.",
        "Return exactly one top-level `question` object.",
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

    if slot.instruction_hint:
        lines.append(slot.instruction_hint)

    if slot.choice_required:
        lines.append(
            "Add exactly one internal choice in `question.or_choice`. Do NOT output the OR alternative as another question. Do NOT duplicate OR in content."
        )
    else:
        lines.append("Set `question.or_choice` to null.")

    if slot.vi_required:
        lines.append(
            "Add a same-marks Visually Impaired alternative in `question.vi_alternative`. Do NOT hide it in metadata."
        )
    else:
        lines.append("Set `question.vi_alternative` to null unless the slot explicitly requires it.")

    if slot.requires_image:
        lines.append(
            "This is an image/map/diagram slot. Use the supplied image payload and copy its `image_url` into `question.image_url`."
        )
    else:
        lines.append("Set `question.image_url` to an empty string unless the slot explicitly uses a retrieved image.")

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
    choice_required: bool = False,
    requires_image: bool = False,
    vi_required: bool = False,
    instruction_hint: str = "",
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
        "diagram map figure visual image" if requires_image else "",
        "visually impaired alternative VI" if vi_required else "",
        "internal choice OR alternative" if choice_required else "",
        instruction_hint[:160].strip(),
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
        choice_required=choice_required,
        requires_image=requires_image,
        vi_required=vi_required,
        instruction_hint=instruction_hint,
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


def _choose_stream_by_marks(
    targets: Dict[str, int],
    assigned_marks: Dict[str, int],
    marks: int,
    fixed_stream: Optional[str] = None,
) -> str:
    if fixed_stream:
        assigned_marks[fixed_stream] = assigned_marks.get(fixed_stream, 0) + marks
        return fixed_stream

    stream = min(
        targets,
        key=lambda item: (
            assigned_marks.get(item, 0) / max(targets[item], 1),
            assigned_marks.get(item, 0),
        ),
    )
    assigned_marks[stream] = assigned_marks.get(stream, 0) + marks
    return stream


def _exact_class10_blueprint_entries(subject_norm: str) -> List[Dict[str, Any]]:
    if subject_norm == "social science":
        return [
            {"section": "Section A - History", "stream": "HISTORY", "qtype": "MCQ", "marks": 1, "count": 1, "hint": "History Q1 must be a match-the-following MCQ with Column I and Column II."},
            {"section": "Section A - History", "stream": "HISTORY", "qtype": "MCQ", "marks": 1, "count": 1, "requires_image": True, "vi_required": True, "hint": "History Q2 must be a picture/image identification MCQ with a VI alternative."},
            {"section": "Section A - History", "stream": "HISTORY", "qtype": "MCQ", "marks": 1, "count": 1, "hint": "History Q3 must be a standard four-option MCQ."},
            {"section": "Section A - History", "stream": "HISTORY", "qtype": "MCQ", "marks": 1, "count": 1, "hint": "History Q4 must be quotation/source-based."},
            {"section": "Section A - History", "stream": "HISTORY", "qtype": "SHORT_ANSWER", "marks": 2, "count": 1, "choice_required": True},
            {"section": "Section A - History", "stream": "HISTORY", "qtype": "SHORT_ANSWER", "marks": 3, "count": 1, "choice_required": True},
            {"section": "Section A - History", "stream": "HISTORY", "qtype": "LONG_ANSWER", "marks": 5, "count": 1, "choice_required": True},
            {"section": "Section A - History", "stream": "HISTORY", "qtype": "CASE_STUDY", "marks": 4, "count": 1, "hint": "CBQ must have exactly three sub-questions totalling 4 marks: 1+1+2."},
            {"section": "Section A - History", "stream": "HISTORY", "qtype": "DIAGRAM", "marks": 2, "count": 1, "requires_image": True, "vi_required": True, "hint": "History map work: identify or locate two historical places on an India outline map."},
            {"section": "Section B - Geography", "stream": "GEOGRAPHY", "qtype": "MCQ", "marks": 1, "count": 1, "hint": "Geography Q10 must be a standard MCQ."},
            {"section": "Section B - Geography", "stream": "GEOGRAPHY", "qtype": "MCQ", "marks": 1, "count": 1, "hint": "Geography Q11 must be a diagram/table empty-box fill MCQ."},
            {"section": "Section B - Geography", "stream": "GEOGRAPHY", "qtype": "MCQ", "marks": 1, "count": 1, "hint": "Geography Q12 must be news article or data-based."},
            {"section": "Section B - Geography", "stream": "GEOGRAPHY", "qtype": "MCQ", "marks": 1, "count": 1, "hint": "Geography Q13 must be statement classification."},
            {"section": "Section B - Geography", "stream": "GEOGRAPHY", "qtype": "MCQ", "marks": 1, "count": 1, "hint": "Geography Q14 must be standard factual."},
            {"section": "Section B - Geography", "stream": "GEOGRAPHY", "qtype": "MCQ", "marks": 1, "count": 1, "hint": "Geography Q15 must be policy/scheme evaluation."},
            {"section": "Section B - Geography", "stream": "GEOGRAPHY", "qtype": "SHORT_ANSWER", "marks": 2, "count": 1, "hint": "Geography has no 3-mark SA in exact mode."},
            {"section": "Section B - Geography", "stream": "GEOGRAPHY", "qtype": "LONG_ANSWER", "marks": 5, "count": 1, "choice_required": True},
            {"section": "Section B - Geography", "stream": "GEOGRAPHY", "qtype": "CASE_STUDY", "marks": 4, "count": 1, "hint": "CBQ must have exactly three sub-questions totalling 4 marks: 1+2+1."},
            {"section": "Section B - Geography", "stream": "GEOGRAPHY", "qtype": "DIAGRAM", "marks": 3, "count": 1, "choice_required": True, "requires_image": True, "vi_required": True, "hint": "Geography map work: Part I 1 mark with internal OR; Part II 2 marks locating two features."},
            {"section": "Section C - Political Science", "stream": "CIVICS", "qtype": "MCQ", "marks": 1, "count": 1, "hint": "Civics Q20 must be multi-statement type."},
            {"section": "Section C - Political Science", "stream": "CIVICS", "qtype": "MCQ", "marks": 1, "count": 1, "requires_image": True, "vi_required": True, "hint": "Civics Q21 must be cartoon-based with a VI alternative."},
            {"section": "Section C - Political Science", "stream": "CIVICS", "qtype": "MCQ", "marks": 1, "count": 1, "hint": "Civics Q22 must be case scenario or constitutional reasoning."},
            {"section": "Section C - Political Science", "stream": "CIVICS", "qtype": "ASSERTION_REASON", "marks": 1, "count": 1, "hint": "Assertion-Reason appears only in Civics for Social Science."},
            {"section": "Section C - Political Science", "stream": "CIVICS", "qtype": "SHORT_ANSWER", "marks": 2, "count": 2, "hint": "Civics has exactly two VSA questions and no OR at 2 marks."},
            {"section": "Section C - Political Science", "stream": "CIVICS", "qtype": "SHORT_ANSWER", "marks": 3, "count": 1, "hint": "Civics SA has no OR."},
            {"section": "Section C - Political Science", "stream": "CIVICS", "qtype": "LONG_ANSWER", "marks": 5, "count": 1, "choice_required": True},
            {"section": "Section C - Political Science", "stream": "CIVICS", "qtype": "CASE_STUDY", "marks": 4, "count": 1, "hint": "CBQ must have exactly three sub-questions totalling 4 marks: 1+1+2."},
            {"section": "Section D - Economics", "stream": "ECONOMICS", "qtype": "MCQ", "marks": 1, "count": 6, "hint": "Economics MCQs must vary across factual, inference, example, justification, and match-column forms."},
            {"section": "Section D - Economics", "stream": "ECONOMICS", "qtype": "SHORT_ANSWER", "marks": 3, "count": 3, "hint": "Economics has exactly three 3-mark SA questions, no VSA, no CBQ, no map."},
            {
                "section": "Section D - Economics",
                "stream": "ECONOMICS",
                "qtype": "LONG_ANSWER",
                "marks": 5,
                "count": 1,
                "choice_required": True,
            },
        ]

    return [
        {"section": "Section A - Biology", "stream": "BIOLOGY", "qtype": "MCQ", "marks": 1, "count": 7, "hint": "Standard Biology MCQs come before Assertion-Reason."},
        {"section": "Section A - Biology", "stream": "BIOLOGY", "qtype": "ASSERTION_REASON", "marks": 1, "count": 2},
        {
            "section": "Section A - Biology",
            "stream": "BIOLOGY",
            "qtype": "SHORT_ANSWER",
            "marks": 2,
            "count": 3,
            "choice_first": 1,
        },
        {
            "section": "Section A - Biology",
            "stream": "BIOLOGY",
            "qtype": "SHORT_ANSWER",
            "marks": 3,
            "count": 2,
        },
        {
            "section": "Section A - Biology",
            "stream": "BIOLOGY",
            "qtype": "CASE_STUDY",
            "marks": 4,
            "count": 1,
            "choice_required": True,
            "vi_required": True,
            "hint": "Biology competency/case-based question with exactly three sub-questions totalling 4 marks and a partial OR.",
        },
        {
            "section": "Section A - Biology",
            "stream": "BIOLOGY",
            "qtype": "LONG_ANSWER",
            "marks": 5,
            "count": 1,
            "choice_required": True,
        },
        {"section": "Section B - Chemistry", "stream": "CHEMISTRY", "qtype": "MCQ", "marks": 1, "count": 7, "hint": "Standard Chemistry MCQs come before Assertion-Reason."},
        {"section": "Section B - Chemistry", "stream": "CHEMISTRY", "qtype": "ASSERTION_REASON", "marks": 1, "count": 1},
        {"section": "Section B - Chemistry", "stream": "CHEMISTRY", "qtype": "SHORT_ANSWER", "marks": 2, "count": 1},
        {"section": "Section B - Chemistry", "stream": "CHEMISTRY", "qtype": "SHORT_ANSWER", "marks": 3, "count": 2, "choice_first": 1},
        {
            "section": "Section B - Chemistry",
            "stream": "CHEMISTRY",
            "qtype": "CASE_STUDY",
            "marks": 4,
            "count": 1,
            "vi_required": True,
            "hint": "Chemistry case-based question must include a VI alternative if a lab setup, table, structure, or diagram is referenced.",
        },
        {"section": "Section B - Chemistry", "stream": "CHEMISTRY", "qtype": "LONG_ANSWER", "marks": 5, "count": 1, "choice_required": True},
        {"section": "Section C - Physics", "stream": "PHYSICS", "qtype": "MCQ", "marks": 1, "count": 2, "hint": "Standard Physics MCQs come before Assertion-Reason."},
        {"section": "Section C - Physics", "stream": "PHYSICS", "qtype": "ASSERTION_REASON", "marks": 1, "count": 1},
        {"section": "Section C - Physics", "stream": "PHYSICS", "qtype": "SHORT_ANSWER", "marks": 2, "count": 1, "choice_required": True},
        {"section": "Section C - Physics", "stream": "PHYSICS", "qtype": "SHORT_ANSWER", "marks": 2, "count": 1, "vi_required": True, "hint": "This Physics 2-mark question must include a VI alternative."},
        {"section": "Section C - Physics", "stream": "PHYSICS", "qtype": "SHORT_ANSWER", "marks": 3, "count": 1, "hint": "This Physics question must be a numerical calculation using values not used elsewhere."},
        {"section": "Section C - Physics", "stream": "PHYSICS", "qtype": "SHORT_ANSWER", "marks": 3, "count": 2, "vi_required": True, "hint": "Physics optics/circuit/data interpretation questions must include VI alternatives when visual-dependent."},
        {
            "section": "Section C - Physics",
            "stream": "PHYSICS",
            "qtype": "CASE_STUDY",
            "marks": 4,
            "count": 1,
            "choice_required": True,
            "vi_required": True,
            "hint": "Physics competency/case-based question must have exactly three sub-questions totalling 4 marks, partial OR, and VI alternative.",
        },
        {
            "section": "Section C - Physics",
            "stream": "PHYSICS",
            "qtype": "LONG_ANSWER",
            "marks": 5,
            "count": 1,
            "choice_required": True,
            "vi_required": True,
        },
    ]


def _build_exact_cbse_class10_plan(
    *,
    topic: str,
    difficulty: str,
    subject_norm: str,
    subject_label: str,
    instructions: str,
) -> List[QuestionGenerationSlot]:
    slots: List[QuestionGenerationSlot] = []

    for entry in _exact_class10_blueprint_entries(subject_norm):
        choice_first = int(entry.get("choice_first") or 0)

        for local_index in range(int(entry["count"])):
            qtype_name = str(entry["qtype"])
            marks = int(entry["marks"])
            slots.append(
                _make_slot(
                    index=len(slots) + 1,
                    section_title=str(entry["section"]),
                    subject=subject_label,
                    stream=str(entry["stream"]),
                    qtype_name=qtype_name,
                    marks=marks,
                    difficulty=difficulty,
                    class_num=10,
                    topic=topic,
                    instructions=instructions,
                    choice_required=bool(entry.get("choice_required")) or local_index < choice_first,
                    requires_image=bool(entry.get("requires_image")) or qtype_name == "DIAGRAM",
                    vi_required=bool(entry.get("vi_required")),
                    instruction_hint=str(entry.get("hint") or ""),
                )
            )

    total_marks = sum(slot.marks for slot in slots)
    if total_marks != 80:
        raise ValueError(f"Internal CBSE Class 10 blueprint error: expected 80 marks, got {total_marks}.")
    expected_count = 38 if subject_norm == "social science" else 39
    if len(slots) != expected_count:
        raise ValueError(f"Internal CBSE Class 10 blueprint error: expected {expected_count} questions, got {len(slots)}.")
    return slots


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

    subject_label = "Social Science" if subject_norm == "social science" else "Science"

    if class_num == 10 and (not count or count <= 0):
        return _build_exact_cbse_class10_plan(
            topic=topic,
            difficulty=difficulty,
            subject_norm=subject_norm,
            subject_label=subject_label,
            instructions=instructions,
        )

    total_questions = count if count and count > 0 else default_cbse_question_count(subject_norm, class_num)
    total_questions = max(1, min(total_questions, 50))
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
                    section_title=_section_title_for_question_type(subject_norm, class_num, qtype.name, marks),
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
