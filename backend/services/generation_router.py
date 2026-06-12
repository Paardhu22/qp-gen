import logging
import re
import dataclasses
from collections import Counter
from typing import List, Dict, Any, Iterable, Optional, Set, Tuple

from django.conf import settings

from q_instructions.master.facade import AcademicGenerationFacade, GeneratePaperRequest
from services.syllabus_scope import (
    excluded_topics_prose_block,
    excluded_topics_compact_line,
    social_science_bloom_bias_block,
    social_science_bloom_bias_line,
    maths_cognitive_band_block,
    maths_cognitive_band_line,
)

logger = logging.getLogger("[GEN_ROUTER]")
logger.setLevel(logging.INFO)


SUPPORTED_SUBJECTS = {
    "science", "social science",
    "mathematics", "english", "hindi", "telugu",
}

# Subject code → eligible class numbers (new engine only)
_NEW_ENGINE_ELIGIBILITY: Dict[str, list] = {
    "science":        list(range(1, 11)),
    "social science": list(range(1, 11)),
    "mathematics":    [10],
    "english":        [10],
    "hindi":          [10],
    "telugu":         [10],
}

# Subject aliases → canonical name
_SUBJECT_ALIASES: Dict[str, str] = {
    "maths":          "mathematics",
    "math":           "mathematics",
    "mathematics standard": "mathematics",
    "mathematics basic": "mathematics",
    "maths basic":    "mathematics",
    "math basic":     "mathematics",
    "mathematics (code 041)": "mathematics",
    "mathematics (code 241)": "mathematics",
    "041":            "mathematics",
    "241":            "mathematics",
    "sst":            "social science",
    "social studies": "social science",
    "hindi b":        "hindi",
    "hindi course b": "hindi",
    "english language": "english",
    "english literature": "english",
    "english language and literature": "english",
    "telugu telangana": "telugu",
}


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
    requires_figure: bool = False  # geometry/mensuration slots that MUST include an inline SVG diagram
    vi_required: bool = False
    instruction_hint: str = ""
    # CONTENT | PASSAGE | GRAMMAR | COMPOSITION (see q_instructions.core.enums.GenerationMode).
    # Defaults to CONTENT so Science / Social Science / Mathematics behaviour is unchanged.
    generation_mode: str = "CONTENT"


def normalize_subject(subject: str) -> str:
    subject_norm = str(subject or "").strip().lower()
    # Check alias map first
    if subject_norm in _SUBJECT_ALIASES:
        return _SUBJECT_ALIASES[subject_norm]
    if subject_norm in SUPPORTED_SUBJECTS:
        return subject_norm
    if subject_norm.replace("_", " ") in SUPPORTED_SUBJECTS:
        return subject_norm.replace("_", " ")
    # Partial alias matching (e.g. "hindi course b" vs "hindi b")
    for alias, canonical in _SUBJECT_ALIASES.items():
        if alias in subject_norm:
            return canonical
    return subject_norm


def resolve_maths_basic(subject_raw: str, payload: Optional[dict] = None) -> bool:
    """True when the request targets Mathematics **Basic** (Code 241).

    Standard (041) vs Basic (241) share the identical 38-question A–E
    skeleton — only the cognitive-band target prose differs. The tier is a
    selection-time flag, NOT a structural change, so it never touches the
    section plan. Detected from an explicit payload field (``mathLevel`` /
    ``math_level`` / ``mathsLevel``) or a "basic"/"241" marker in the subject
    string. Anything that is not Mathematics, or not explicitly Basic,
    resolves to Standard (False) — no breaking change to existing calls.
    """
    if normalize_subject(subject_raw) != "mathematics":
        return False
    payload = payload or {}
    level = str(
        payload.get("mathLevel")
        or payload.get("math_level")
        or payload.get("mathsLevel")
        or payload.get("maths_level")
        or ""
    ).strip().lower()
    if level in {"basic", "241"}:
        return True
    if level in {"standard", "041"}:
        return False
    raw = str(subject_raw or "").lower()
    return "basic" in raw or "241" in raw


def is_eligible_for_new_engine(subject_norm: str, class_num: int) -> bool:
    """Returns True if this subject+class combination has a new-engine blueprint."""
    if subject_norm not in _NEW_ENGINE_ELIGIBILITY:
        return False
    return class_num in _NEW_ENGINE_ELIGIBILITY[subject_norm]


def extract_class_number(class_value: object, default: int = 10) -> int:
    class_str = str(class_value or "").strip().lower()
    digits = "".join(filter(str.isdigit, class_str))
    return int(digits) if digits else default

def should_use_new_engine(payload: dict) -> bool:
    """
    Determines if the payload is eligible for the new q_instructions engine.
    Eligibility rule: board == "CBSE" AND the (subject, class) pair has a
    new-engine blueprint per _NEW_ENGINE_ELIGIBILITY (Science/Social 1-10;
    Mathematics/English/Hindi/Telugu class 10).
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
    
    is_eligible = (
        board_norm == "CBSE"
        and class_num is not None
        and is_eligible_for_new_engine(subject_norm, class_num)
    )
    
    logger.info(f"[GEN_ROUTER] ELIGIBILITY RESULT: {is_eligible}")
    
    if is_eligible:
        logger.info(f"[ROUTE_DECISION] Using NEW engine for {board_norm} Class {class_num} {subject.strip()}")
    else:
        reason = "Mismatch: "
        if board_norm != "CBSE":
            reason += f"board({board_norm}!=CBSE) "
        elif subject_norm not in _NEW_ENGINE_ELIGIBILITY:
            reason += f"subject({subject_norm} has no new-engine blueprint) "
        elif class_num is None or not is_eligible_for_new_engine(subject_norm, class_num):
            eligible = _NEW_ENGINE_ELIGIBILITY.get(subject_norm, [])
            reason += f"class({class_num} not in {eligible} for {subject_norm})"
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
        "READING_COMP": "Reading Comprehension",
        "GRAMMAR": "Grammar Tasks",
        "LETTER": "Writing Tasks",
        "NUMERICAL": "Numericals",
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


def build_slot_blueprint_instructions(
    slot: QuestionGenerationSlot,
    difficulty: str,
    class_num: int,
    subject: str,
    maths_basic: bool = False,
) -> str:
    """
    Directive 5: Truncated prompt to save TTFT.
    Only pass what is absolutely necessary for THIS specific slot.

    This is the prose that actually reaches the LLM per question (the
    paper-level builders feed history logging / the printed header). The
    off-syllabus, Bloom-bias, and Maths-tier guidance is therefore injected
    here too — kept to one compact line each so TTFT is unaffected.
    """
    _lmap = {"social science": "Social Science", "mathematics": "Mathematics", "english": "English", "hindi": "Hindi", "telugu": "Telugu"}
    subject_norm = normalize_subject(subject)
    subject_label = _lmap.get(subject_norm, "Science")
    lines = [
        "ACADEMIC BLUEPRINT INSTRUCTIONS (MANDATORY):",
        f"- Board: CBSE | Class: {class_num} | Subject: {subject_label}",
        f"- Difficulty target: {difficulty.upper()}",
        f"- Generate EXACTLY ONE question for {slot.marks} marks.",
        f"- Question Type: {slot.legacy_type}",
    ]

    # Off-syllabus exclusions (single source of truth: services.syllabus_scope).
    exclusion_line = excluded_topics_compact_line(subject_norm, class_num)
    if exclusion_line:
        lines.append(exclusion_line)

    # Social Science is ~50% HOTS — bias every slot toward analysis.
    if subject_norm == "social science":
        bias_line = social_science_bloom_bias_line(class_num)
        if bias_line:
            lines.append(bias_line)

    # Mathematics Standard (041) vs Basic (241) cognitive-tier selection.
    if subject_norm == "mathematics" and class_num == 10:
        lines.append(maths_cognitive_band_line(maths_basic))

    # Send word limits only if it's a descriptive question
    if slot.legacy_type in ["SHORT", "LONG", "CASE_STUDY"]:
        if slot.marks == 2:
            lines.append("- Word limit: Max 40 words.")
        elif slot.marks == 3:
            lines.append("- Word limit: Max 60 words.")
        elif slot.marks >= 5:
            lines.append("- Word limit: Max 120 words.")

    # Send CBQ specific rule
    if slot.legacy_type == "CASE_STUDY":
        lines.append("- CBQ rules: Always exactly 3 sub-questions totaling 4 marks (e.g. 1+1+2). No OR within CBQ.")

    return "\n".join(lines)


def build_plan_blueprint_instructions(
    *,
    plan: List[QuestionGenerationSlot],
    difficulty: str,
    class_num: int,
    subject: str,
    maths_basic: bool = False,
) -> str:
    _lmap2 = {"social science": "Social Science", "mathematics": "Mathematics", "english": "English", "hindi": "Hindi", "telugu": "Telugu"}
    subject_norm = normalize_subject(subject)
    subject_label = _lmap2.get(subject_norm, "Science")
    if subject_norm == "mathematics":
        subject_label = "Mathematics Basic (Code 241)" if maths_basic else "Mathematics Standard (Code 041)"
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
    is_custom = any(slot.stream == "INTEGRATED" for slot in plan)
    if is_custom:
        lines.extend([
            "LAYER 3 — COUNT VARIATION GATE: Custom Count Worksheet Mode",
            "- WORKSHEET MODE: ABANDON formal subject-track architecture (Hist/Geo/Civ/Econ or Bio/Chem/Phys).",
            "- Sections MUST be built dynamically based purely on QUESTION TYPES (e.g., Section A - Objective Questions, Section B - Short Answers).",
            "- Do NOT print subject-specific headers.",
            "- Scale question counts and types exactly as specified in the user's General Instructions.",
        ])
    section_line = "; ".join(
        f"{title}: {summary['section_questions'][title]} questions, {summary['section_marks'][title]} marks"
        for title in summary["section_marks"]
    )
    if section_line:
        lines.append(f"- Locked sections: {section_line}.")

    # Cognitive-band + off-syllabus guidance (history-log fidelity; the LLM
    # gets the same guidance per-slot via build_slot_blueprint_instructions).
    if not is_custom:
        if subject_norm == "mathematics" and class_num == 10:
            lines.append(maths_cognitive_band_line(maths_basic))
        if subject_norm == "social science":
            bias = social_science_bloom_bias_line(class_num)
            if bias:
                lines.append(bias)
        exclusion_line = excluded_topics_compact_line(subject_norm, class_num)
        if exclusion_line:
            lines.append(exclusion_line)
    return "\n".join(lines)


def build_general_instructions(plan: List[QuestionGenerationSlot], subject: str, class_num: int, instructions: str = "") -> List[str]:
    is_custom = any(slot.stream == "INTEGRATED" for slot in plan)
    if is_custom:
        if instructions:
            import re
            lines = [line.strip() for line in re.split(r'[\r\n]+', instructions) if line.strip()]
            if lines:
                return lines
        return [
            f"This question paper consists of {len(plan)} questions in dynamically structured sections.",
            "All questions are compulsory. Internal choice is provided in some questions.",
            "Attempt all questions based on the instructions provided in each section."
        ]
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
    if class_num == 10 and subject_norm == "mathematics":
        return [
            "This question paper contains 38 questions. All questions are compulsory.",
            "The question paper is divided into five sections: A, B, C, D, and E.",
            "Section A comprises 20 questions of 1 mark each (Q1–Q18 MCQs, Q19–Q20 Assertion-Reason).",
            "Section B comprises 5 questions of 2 marks each (Q21–Q25). Internal choice in Q21 and Q24.",
            "Section C comprises 6 questions of 3 marks each (Q26–Q31). Internal choice in Q29 and Q31.",
            "Section D comprises 4 questions of 5 marks each (Q32–Q35). Internal choice in Q34 and Q35.",
            "Section E comprises 3 case-based questions of 4 marks each (Q36–Q38), with sub-parts (i)1+(ii)1+(iii)2. Internal OR on sub-part (iii) only.",
            "Use of calculator is not permitted.",
        ]
    if class_num == 10 and subject_norm == "english":
        return [
            "This question paper contains 11 questions. All questions are compulsory.",
            "Marks are indicated against each question.",
            "Q1–Q2: Reading Comprehension (10 marks each). Q3: Grammar tasks (10 marks, do any 10 of 12). Q4–Q5: Writing tasks (5 marks each).",
            "Q6–Q7: Literature extracts — Prose and Poetry (5 marks each). Q8: Short answer questions from First Flight and Footprints (12 marks, do any 4 of 5). Q9: Footprints long answer (6 marks, do any 2 of 3). Q10–Q11: First Flight and Footprints long answers (6 marks each, internal choice).",
        ]
    if class_num == 10 and subject_norm == "hindi":
        return [
            "इस प्रश्नपत्र में 16 प्रश्न हैं। सभी प्रश्न अनिवार्य हैं।",
            "प्रत्येक प्रश्न के अंक उसके सामने दिए गए हैं।",
            "Q1–Q2: अपठित बोध (7-7 अंक)। Q3–Q6: व्याकरण (4-4 अंक, 5 में से 4 करें)।",
            "Q7–Q11: पाठ्यपुस्तक — स्पर्श/संचयन (विविध अंक)। Q12–Q16: लेखन कार्य (विविध अंक)।",
            "जहाँ आंतरिक विकल्प है, वहाँ कोई एक विकल्प चुनें।",
        ]
    if class_num == 10 and subject_norm == "telugu":
        return [
            "ఈ ప్రశ్నపత్రంలో 18 ప్రశ్నలు ఉన్నాయి. అన్నీ తప్పనిసరి.",
            "Q1: అపఠిత గద్యం + 5 బహుళైచ్ఛిక ప్రశ్నలు (10 మార్కులు). Q2–Q3: లేఖన రచన / ప్రక్రియ.",
            "Q4–Q11: వ్యాకరణ మరియు పదజాల బహుళైచ్ఛిక ప్రశ్నలు. Q12–Q18: పాఠ్యపుస్తక ప్రశ్నలు.",
            "సమాధానాలు తెలుగు లిపిలో మాత్రమే రాయాలి.",
        ]
    if subject_norm == "social science" and 6 <= class_num <= 8:
        return [
            "All questions are compulsory.",
            "Section A contains MCQs, Section B contains VSA questions, Section C contains SA questions, Section D contains LA questions, and Section E contains CBQs where applicable.",
            "Internal choice is provided only in Section C and Section D where specified.",
        ]
    return ["All questions are compulsory.", "Questions are generated from the uploaded source material only."]


# ---------------------------------------------------------------------------
# Realized-paper header derivation (ISSUE A2)
# ---------------------------------------------------------------------------
# Hardcoded blueprint headers (e.g. "This question paper contains 38 questions
# … Section A comprises 20 questions of 1 mark each") lied when the body was
# truncated to 12. The fix: derive the printed header from the questions
# actually generated (the "realized paper") so the header and body can never
# disagree. `build_general_instructions` still produces the planned header for
# the initial plan event, but the streamer overwrites `result["generalInstructions"]`
# at done-time using `build_realized_general_instructions`.

_MATHS_SECTION_DETAIL = {
    "Section A - MCQ":                  "MCQs and Assertion-Reason (1 mark each)",
    "Section B - Very Short Answer":    "Very Short Answer Questions",
    "Section C - Short Answer":         "Short Answer Questions",
    "Section D - Long Answer":          "Long Answer Questions",
    "Section E - Case-Based Questions": "Case-Based Questions",
}


def _realized_section_breakdown(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Walk the realized result and return a list of
    {title, count, marks_each (or None if mixed), total_marks} per section,
    preserving section order.
    """
    sections = result.get("sections") or []
    breakdown: List[Dict[str, Any]] = []
    for section in sections:
        questions = section.get("questions") or []
        if not questions:
            continue
        marks_seen: List[int] = []
        for q in questions:
            try:
                marks_seen.append(int(q.get("marks") or 0))
            except (TypeError, ValueError):
                marks_seen.append(0)
        unique_marks = sorted({m for m in marks_seen if m > 0})
        marks_each = unique_marks[0] if len(unique_marks) == 1 else None
        total_marks = sum(marks_seen)
        breakdown.append({
            "title": section.get("title") or "Section",
            "count": len(questions),
            "marks_each": marks_each,
            "total_marks": total_marks,
        })
    return breakdown


def _section_label_line(entry: Dict[str, Any], detail: str = "") -> str:
    title = entry["title"]
    count = entry["count"]
    total_marks = entry["total_marks"]
    marks_each = entry.get("marks_each")
    label = f"{title} comprises {count} question{'s' if count != 1 else ''}"
    if marks_each is not None:
        label += f" of {marks_each} mark{'s' if marks_each != 1 else ''} each ({count} × {marks_each} = {total_marks} Marks)"
    else:
        label += f" carrying a total of {total_marks} Marks"
    if detail:
        label += f" — {detail}"
    return label + "."


def build_realized_general_instructions(
    result: Dict[str, Any],
    subject: str,
    class_num: int,
    *,
    scope_policy: str = "strict",
    fallback_count: int = 0,
    requested_count: Optional[int] = None,
) -> List[str]:
    """Derive the general-instructions header from the realized paper so the
    printed header can never overstate the actual body. Preserves a couple of
    subject-specific style lines (e.g. "Use of calculator is not permitted").
    """
    breakdown = _realized_section_breakdown(result)
    total_questions = sum(item["count"] for item in breakdown)
    total_marks = sum(item["total_marks"] for item in breakdown)
    subject_norm = normalize_subject(subject)

    if total_questions == 0:
        return ["No questions could be generated."]

    lines: List[str] = []
    intro = f"This question paper contains {total_questions} question{'s' if total_questions != 1 else ''}"
    if total_marks:
        intro += f" carrying a total of {total_marks} marks"
    intro += ". All questions are compulsory."
    lines.append(intro)

    # Per-section breakdown with realized counts and marks
    detail_map: Dict[str, str] = {}
    if class_num == 10 and subject_norm == "mathematics":
        detail_map = dict(_MATHS_SECTION_DETAIL)

    if len(breakdown) > 1:
        sections_word = ", ".join(b["title"].split(" - ")[0] for b in breakdown)
        lines.append(f"The question paper is divided into the following sections: {sections_word}.")
        for entry in breakdown:
            lines.append(_section_label_line(entry, detail_map.get(entry["title"], "")))
    else:
        # Single-section paper
        lines.append(_section_label_line(breakdown[0], detail_map.get(breakdown[0]["title"], "")))

    # Subject-specific style lines that aren't count-derived
    if class_num == 10 and subject_norm == "mathematics":
        lines.append("Use of calculator is not permitted.")

    # Honest notices about coverage
    if scope_policy == "source_only" and requested_count and total_questions < requested_count:
        lines.append(
            f"Notice: only {total_questions} of {requested_count} blueprint questions could "
            "be generated from the uploaded sources. Upload more chapters or switch to "
            "full-blueprint mode for a complete paper."
        )
    elif fallback_count > 0:
        lines.append(
            f"Notice: {fallback_count} of {total_questions} questions were generated from the "
            "CBSE curriculum (the uploaded sources did not cover those topics)."
        )

    return lines


def build_social_science_blueprint_instructions(difficulty: str, count: int, class_num: int) -> str:
    rules = [
        "ACADEMIC BLUEPRINT INSTRUCTIONS (MANDATORY):",
        f"- Board: CBSE | Class: {class_num} | Subject: Social Science",
        f"- Overall Difficulty Target: {difficulty.upper()}",
    ]
    if count > 0:
        rules.extend([
            f"- You MUST generate exactly {count} questions in total.",
            "LAYER 3 — COUNT VARIATION GATE: Custom Count Worksheet Mode",
            "- WORKSHEET MODE: ABANDON formal subject-track architecture (Hist/Geo/Civ/Econ or Bio/Chem/Phys).",
            "- Sections MUST be built dynamically based purely on QUESTION TYPES (e.g., Section A - Objective Questions, Section B - Short Answers).",
            "- Do NOT print subject-specific headers.",
            "- Scale question counts and types exactly as specified in the user's General Instructions.",
        ])
        return "\n".join(rules)

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
        # Bloom-band bias (30/14/50 + map) and off-syllabus exclusions — Class 10
        # only. Single source of truth: services.syllabus_scope.
        rules.extend(social_science_bloom_bias_block(class_num))
        rules.extend(excluded_topics_prose_block("social science", class_num))

    return "\n".join(rules)


def _build_mathematics_blueprint_instructions(difficulty: str, count: int, maths_basic: bool = False) -> str:
    # Standard (041) vs Basic (241) share the identical A–E skeleton; only the
    # subject label and the cognitive-band target prose differ.
    subject_line = (
        "- Board: CBSE | Class: 10 | Subject: Mathematics Basic (Code 241)"
        if maths_basic
        else "- Board: CBSE | Class: 10 | Subject: Mathematics Standard (Code 041)"
    )
    rules = [
        "ACADEMIC BLUEPRINT INSTRUCTIONS (MANDATORY):",
        subject_line,
        f"- Overall Difficulty Target: {difficulty.upper()}",
    ]
    if count > 0:
        rules.extend([
            f"- You MUST generate exactly {count} questions.",
            "WORKSHEET MODE: Sections based on question type; no formal section split required.",
        ])
        rules.extend(maths_cognitive_band_block(maths_basic))
        return "\n".join(rules)
    rules.extend([
        "- Total: 38 questions, 80 marks, 3 hours.",
        "- Section A (Q1–Q20, 20×1m): Q1–Q18 are MCQs; Q19 AND Q20 MUST BE Assertion-Reason questions (always at the END of Section A, never elsewhere).",
        "- Section B (Q21–Q25, 5×2m): Internal choice in Q21 and Q24.",
        "- Section C (Q26–Q31, 6×3m): Internal choice in Q29 and Q31.",
        "- Section D (Q32–Q35, 4×5m): Internal choice in Q34 and Q35.",
        "- Section E (Q36–Q38, 3×4m): Sub-parts (i)1+(ii)1+(iii)2; internal OR on sub-part (iii) only.",
        "- Cover at least 7 distinct NCERT topics in Section A. No topic in more than 3 MCQs.",
        "- Unit weightage (must match exactly): Number Systems 6m, Algebra 20m, Coordinate Geometry 6m, Geometry 15m, Trigonometry 12m, Mensuration 10m, Statistics & Probability 11m.",
        "- PICTURE/DIAGRAM CAP: The ENTIRE paper may contain AT MOST 2 picture/diagram/figure questions (across all sections combined). Any further questions MUST be answerable from text alone.",
        "- LaTeX delimiters: write inline math as \\( ... \\) and display equations as \\[ ... \\]. Do NOT use $...$ or $$...$$.",
        "- All answers must be correct mathematically. Show working in long answers.",
        "- Use π = 22/7 unless the question specifically states π = 3.14.",
        "- Calculator not permitted.",
    ])
    # Cognitive-band target: Standard 54/24/22 vs Basic 75/15/10 (same skeleton).
    rules.extend(maths_cognitive_band_block(maths_basic))
    return "\n".join(rules)


def _build_english_blueprint_instructions(difficulty: str, count: int) -> str:
    rules = [
        "ACADEMIC BLUEPRINT INSTRUCTIONS (MANDATORY):",
        "- Board: CBSE | Class: 10 | Subject: English Language & Literature (Code 184)",
        f"- Overall Difficulty Target: {difficulty.upper()}",
    ]
    if count > 0:
        rules.extend([f"- You MUST generate exactly {count} questions.", "WORKSHEET MODE: Dynamic sections."])
        return "\n".join(rules)
    rules.extend([
        "- Total: 11 questions, 80 marks, 3 hours.",
        "- Q1–Q2 (10m each): Reading Comprehension passages — one factual, one discursive.",
        "- Q3 (10m): Grammar — 12 tasks, do any 10 (editing, gap-fill, reporting, transformation).",
        "- Q4 (5m): Formal letter (complaint/request/order) or notice. Q5 (5m): Analytical paragraph.",
        "- Q6 (5m): Extract from First Flight prose — 4-5 MCQs/very short answers.",
        "- Q7 (5m): Extract from First Flight poetry — 4-5 MCQs/very short answers.",
        "- Q8 (12m): Short answers — 5 questions from First Flight Prose, First Flight Poetry, and Footprints (do any 4, 3m each).",
        "- Q9 (6m): Footprints — 3 LA options, do any 2 (3m each).",
        "- Q10 (6m): First Flight LA — one question with internal OR.",
        "- Q11 (6m): Footprints LA — one question with internal OR.",
        "- Q8 must span at least 2 First Flight Prose chapters, 1 First Flight poem, and 1 Footprints story.",
    ])
    return "\n".join(rules)


def _build_hindi_blueprint_instructions(difficulty: str, count: int) -> str:
    rules = [
        "ACADEMIC BLUEPRINT INSTRUCTIONS (MANDATORY):",
        "- Board: CBSE | Class: 10 | Subject: Hindi Course B (Code 085)",
        f"- Overall Difficulty Target: {difficulty.upper()}",
        "- IMPORTANT: Every question, instruction, option, and heading MUST be in Devanagari Unicode (U+0900–U+097F). No Roman script.",
    ]
    if count > 0:
        rules.extend([f"- You MUST generate exactly {count} questions.", "WORKSHEET MODE: Dynamic sections."])
        return "\n".join(rules)
    rules.extend([
        "- Total: 16 questions, 80 marks, 3 hours.",
        "- Q1–Q2 (7m each): अपठित गद्यांश — दोनों प्रश्न अलग-अलग विषयों पर होने चाहिए।",
        "- Q3–Q6 (4m each): व्याकरण — पदबंध/वाक्य/समास/मुहावरे (5 में से 4 करें)।",
        "- Q7 (5m): गद्यांश MCQ (स्पर्श)। Q8 (6m): गद्य SA 4-do-3। Q9 (5m): काव्यांश MCQ। Q10 (6m): काव्य SA 4-do-3।",
        "- Q11 (6m): संचयन 3-do-2। Q12 (5m): अनुच्छेद। Q13 (5m): पत्र। Q14 (4m): सूचना। Q15 (3m): विज्ञापन। Q16 (5m): लघु-कथा/ईमेल।",
    ])
    return "\n".join(rules)


def _build_telugu_blueprint_instructions(difficulty: str, count: int) -> str:
    rules = [
        "ACADEMIC BLUEPRINT INSTRUCTIONS (MANDATORY):",
        "- Board: CBSE | Class: 10 | Subject: Telugu Telangana (Code 089)",
        f"- Overall Difficulty Target: {difficulty.upper()}",
        "- IMPORTANT: Every question, option, instruction, and section header MUST be in Telugu Unicode (U+0C00–U+0C7F). No Roman script at all.",
    ]
    if count > 0:
        rules.extend([f"- You MUST generate exactly {count} questions.", "WORKSHEET MODE: Dynamic sections."])
        return "\n".join(rules)
    rules.extend([
        "- Total: 18 questions, 80 marks, 3 hours.",
        "- Q1 (10m): పఠిత గద్యం + 5 MCQs×2m. Q2 (6m): లేఖ రచన. Q3 (5m): ప్రక్రియ.",
        "- Q4–Q7 (4m each): వ్యాకరణ MCQs — సంధి/ఛందస్సు/సమాసం/అలంకారాలు.",
        "- Q8–Q11 (2m each): పదజాల MCQs. Q12 (5m): పరిచిత గద్యం.",
        "- Q13–Q14 (4m each): సంగ్రహ జవాబులు. Q15–Q16 (4m each): విపులంగా జవాబులు.",
        "- Q17 (6m): పద్య అన్వయం. Q18 (8m): ఉపవాచకం రామాయణం — 4-do-2×4m.",
    ])
    return "\n".join(rules)


def build_blueprint_instructions(
    topic: str,
    difficulty: str,
    count: int,
    class_num: int = 10,
    subject: str = "science",
    plan: Optional[List[QuestionGenerationSlot]] = None,
    maths_basic: bool = False,
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
            maths_basic=maths_basic,
        )

    subject_norm = normalize_subject(subject)
    if subject_norm == "social science":
        return build_social_science_blueprint_instructions(difficulty, count, class_num)
    if subject_norm == "mathematics" and class_num == 10:
        return _build_mathematics_blueprint_instructions(difficulty, count, maths_basic=maths_basic)
    if subject_norm == "english" and class_num == 10:
        return _build_english_blueprint_instructions(difficulty, count)
    if subject_norm == "hindi" and class_num == 10:
        return _build_hindi_blueprint_instructions(difficulty, count)
    if subject_norm == "telugu" and class_num == 10:
        return _build_telugu_blueprint_instructions(difficulty, count)

    logger.info(f"[NEW_ENGINE] Compiling academic blueprint for Class {class_num}...")
    
    rules = [
        "ACADEMIC BLUEPRINT INSTRUCTIONS (MANDATORY):",
        f"- Board: CBSE | Class: {class_num} | Subject: {'EVS' if class_num <= 5 else 'Science'}",
        f"- Overall Difficulty Target: {difficulty.upper()}",
    ]
    if count > 0:
        rules.extend([
            f"- You MUST generate exactly {count} questions in total.",
            "LAYER 3 — COUNT VARIATION GATE: Custom Count Worksheet Mode",
            "- WORKSHEET MODE: ABANDON formal subject-track architecture (Hist/Geo/Civ/Econ or Bio/Chem/Phys).",
            "- Sections MUST be built dynamically based purely on QUESTION TYPES (e.g., Section A - Objective Questions, Section B - Short Answers).",
            "- Do NOT print subject-specific headers.",
            "- Scale question counts and types exactly as specified in the user's General Instructions.",
        ])
        return "\n".join(rules)
        
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
        # Off-syllabus exclusions — Class 10 Science only. Single source of
        # truth: services.syllabus_scope.
        rules.extend(excluded_topics_prose_block("science", class_num))

    return "\n".join(rules)


def default_cbse_question_count(subject: str, class_num: int) -> int:
    subject_norm = normalize_subject(subject)
    if class_num == 10 and subject_norm == "science":
        return 39
    if class_num == 10 and subject_norm == "social science":
        return 38
    if class_num == 10 and subject_norm == "mathematics":
        return 38
    if class_num == 10 and subject_norm == "english":
        return 11
    if class_num == 10 and subject_norm == "hindi":
        return 16
    if class_num == 10 and subject_norm == "telugu":
        return 18
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
    if qtype_name in ("CASE_STUDY", "READING_COMP"):
        return "CASE_STUDY"
    if qtype_name in ("LONG_ANSWER", "LETTER"):
        return "LONG"
    if qtype_name == "DIAGRAM":
        return "DIAGRAM"
    # GRAMMAR, SHORT_ANSWER, EXTRACT_PROSE, EXTRACT_POETRY, ANALYTICAL_PARAGRAPH → SHORT
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
    if qtype_name in {"MCQ", "ASSERTION_REASON"}:
        return "Section A - MCQ"
    if marks == 2:
        return "Section B - Very Short Answer"
    if marks == 3:
        return "Section C - Short Answer"
    if marks >= 5:
        return "Section D - Long Answer"
    if qtype_name == "CASE_STUDY" or marks == 4:
        return "Section E - Case-Based Questions"
    return "Questions"


# ---------------------------------------------------------------------------
# Mode-aware prompt builders (GRAMMAR / COMPOSITION / PASSAGE — never use RAG)
# ---------------------------------------------------------------------------

# Telugu prosody: each named వృత్తం maps to its fixed గణ sequence. Injected into
# the Chandas grammar prompt so the model cannot fabricate a mismatched pattern,
# and used by language_validation for a post-hoc consistency check.
TELUGU_METRE_GANA: Dict[str, str] = {
    "ఉత్పలమాల": "భ ర న భ భ ర వ",
    "చంపకమాల": "న జ భ జ జ జ ర",
    "శార్దూలవిక్రీడితం": "మ స జ స త త గ",
    "మత్తేభవిక్రీడితం": "స భ ర న మ య వ",
}

# Per-subject "attempt any N of M" counts for grammar clusters (M tasks generated).
_GRAMMAR_TASK_PLAN = {
    "english": {"tasks": 12, "attempt": 10},  # Q3: any 10 of 12
    "hindi":   {"tasks": 5,  "attempt": 4},   # Q3–Q6: any 4 of 5
}

# Cardinal rule repeated in every composition prompt.
_COMPOSITION_CARDINAL = (
    "CARDINAL RULE: Generate the QUESTION ONLY (scenario / stimulus / topic + hints + word limit). "
    "NEVER write the student's answer. The question MUST be fully answerable WITHOUT any textbook."
)


def _script_directive(subject_norm: str) -> str:
    if subject_norm == "hindi":
        return ("EVERY character — question text, tasks, options, and the answer key — MUST be in "
                "Devanagari Unicode (U+0900–U+097F). No Roman transliteration anywhere.")
    if subject_norm == "telugu":
        return ("EVERY character — question text, tasks, options, and the answer key — MUST be in "
                "Telugu Unicode (U+0C00–U+0C7F). No Roman transliteration anywhere.")
    return ""


def _slot_contract_footer(slot: QuestionGenerationSlot) -> List[str]:
    """Shared JSON-contract tail for non-CONTENT slots (OR/VI/image handling)."""
    subject_norm = normalize_subject(slot.subject)
    lines = [
        f"The JSON field 'marks' MUST be {slot.marks}.",
        f"The JSON field 'type' MUST be {slot.legacy_type}.",
        "Return exactly one top-level `question` object.",
        "Put the full question (and any sub-tasks/options) in `question.content`. "
        "Put the complete answer key in `question.answer`.",
    ]
    if slot.instruction_hint:
        lines.append(slot.instruction_hint)
    if slot.choice_required:
        or_label = {"hindi": "अथवा", "telugu": "లేదా"}.get(subject_norm, "OR")
        lines.append(
            f"Provide exactly TWO options and add one internal choice in `question.or_choice` "
            f"(the backend prints it as '{or_label}'). Do NOT output the alternative as a separate question object."
        )
    else:
        lines.append("Set `question.or_choice` to null.")
    lines.append("Set `question.vi_alternative` to null.")
    lines.append("Set `question.image_url` to an empty string.")
    return lines


def _build_grammar_instruction(slot: QuestionGenerationSlot) -> str:
    subject_norm = normalize_subject(slot.subject)
    if subject_norm == "english":
        body = _build_english_grammar_prompt(slot)
    elif subject_norm == "hindi":
        body = _build_hindi_grammar_prompt(slot)
    elif subject_norm == "telugu":
        body = _build_telugu_grammar_prompt(slot)
    else:
        body = [f"Generate a {slot.marks}-mark grammar task set. Each task is self-contained and rule-based."]
    return "\n".join(body + _slot_contract_footer(slot))


def _build_english_grammar_prompt(slot: QuestionGenerationSlot) -> List[str]:
    plan = _GRAMMAR_TASK_PLAN["english"]
    return [
        f"GRAMMAR SLOT (no retrieval — invent every sentence yourself).",
        f"Generate EXACTLY {plan['tasks']} one-mark grammar tasks, numbered I–XII. "
        f"The stem MUST instruct the student to 'Attempt any {plan['attempt']} of the {plan['tasks']} tasks'.",
        "Cover these DISTINCT CBSE Class-10 skills, one per task, with NO point repeated:",
        " I. Tense/verb-form transformation (fill-blank with a bracketed word, e.g. passive participle).",
        " II. Editing / error correction — WRITTEN: give an Error→Correction table for a sentence with ONE error.",
        " III. Tense — present perfect (fill-blank, bracketed verb).",
        " IV. Reported speech — STATEMENT (complete 'They told ... that ___').",
        " V. Prepositions — MCQ with 4 options.",
        " VI. Reported speech — COMMAND/REQUEST (complete 'She warned him ___').",
        " VII. Non-finite / gerund-participle — MCQ with 4 options.",
        " VIII. Editing / error correction — MCQ: identify error+correction from 4 options.",
        " IX. Reported speech — QUESTION (report a yes/no or wh- question).",
        " X. Modals — fill-blank choosing the right modal (must/may/should).",
        " XI. Determiners — MCQ (All/One/Every/A …).",
        " XII. Quantifiers / subject-verb concord — MCQ (little/any/few/least …).",
        "HARD RULES: reported speech appears EXACTLY 3 times (statement, command, question — all distinct); "
        "error correction appears EXACTLY twice (one written-table, one MCQ).",
        "Each sentence sits in its own realistic micro-context (market research, life-skills book, diary, "
        "order letter, opinion column, sports news) that YOU invent — NOT from any uploaded text.",
        "For each MCQ task: exactly 4 options with plausible distractors (common student errors), and mark which is correct. "
        "For each fill/transform task: give the transformed answer.",
        "In `question.answer`, list every task number with its answer (and the correct option letter for MCQ tasks).",
    ]


def _build_hindi_grammar_prompt(slot: QuestionGenerationSlot) -> List[str]:
    plan = _GRAMMAR_TASK_PLAN["hindi"]
    return [
        "व्याकरण स्लॉट (कोई retrieval नहीं — सभी वाक्य स्वयं रचें).",
        _script_directive("hindi"),
        f"EXACTLY {plan['tasks']} एक-अंकीय व्याकरण कार्य बनाइए; प्रश्न में लिखें 'किन्हीं {plan['attempt']} के उत्तर दीजिए' "
        f"(अर्थात् {plan['tasks']} में से कोई {plan['attempt']}).",
        "इस क्लस्टर के सटीक व्याकरण-बिंदु `instruction hint` में दिए गए हैं "
        "(पदबंध / वाक्य-रूपांतरण / समास / मुहावरे). प्रत्येक कार्य में एक भिन्न उप-बिंदु, कोई पुनरावृत्ति नहीं।",
        "प्रत्येक वाक्य एक भिन्न, यथार्थ सन्दर्भ (विद्यालय, प्रकृति, दैनिक जीवन) में हो — किसी पाठ्यपुस्तक से नहीं।",
        "MCQ कार्य हों तो ठीक 4 विकल्प और सही विकल्प चिह्नित करें; भरें/रूपांतरण कार्य का उत्तर दें।",
        "`question.answer` में हर कार्य-संख्या के सामने उसका उत्तर (MCQ के लिए सही विकल्प) दीजिए।",
    ]


def _build_telugu_grammar_prompt(slot: QuestionGenerationSlot) -> List[str]:
    num_tasks = max(1, int(slot.marks))  # 1 mark per MCQ in Telugu clusters
    lines = [
        "వ్యాకరణ స్లాట్ (retrieval లేదు — అన్ని ఉదాహరణలను మీరే సృష్టించండి).",
        _script_directive("telugu"),
        f"సరిగ్గా {num_tasks} బహుళైచ్ఛిక ప్రశ్నలను (ఒక్కొక్కటి 1 మార్కు) తయారు చేయండి. "
        "ప్రతి ప్రశ్నకు సరిగ్గా 4 తెలుగు ఎంపికలు, ఒక సరైన సమాధానం.",
        "ఈ క్లస్టర్ యొక్క ఖచ్చితమైన అంశాలు `instruction hint`లో ఉన్నాయి. ఏ అంశాన్నీ పునరావృతం చేయవద్దు.",
        "`question.answer`లో ప్రతి ప్రశ్నకు సరైన ఎంపిక అక్షరం + వివరణ ఇవ్వండి.",
    ]
    hint = slot.instruction_hint or ""
    if ("ఛందస్సు" in hint) or ("ఛందస" in hint):
        table = "; ".join(f"{metre} = {gana}" for metre, gana in TELUGU_METRE_GANA.items())
        lines.append(
            "ఛందస్సు: పేరు పెట్టిన వృత్తానికి గణ క్రమం ఈ పట్టికతో సరిగ్గా సరిపోలాలి (తప్పక ధృవీకరించండి): "
            + table + "."
        )
    return lines


def _build_passage_instruction(slot: QuestionGenerationSlot) -> str:
    subject_norm = normalize_subject(slot.subject)
    lines = [
        f"UNSEEN PASSAGE SLOT ({slot.marks} marks) — no retrieval.",
        "Generate an ORIGINAL, previously-unseen passage. NEVER reproduce or draw from any uploaded "
        "textbook or prescribed text — the student has not read this passage before.",
    ]
    sd = _script_directive(subject_norm)
    if sd:
        lines.append(sd)
    lines += [
        "Follow the EXACT sub-question count and marks distribution given in the instruction hint. "
        "Sub-questions must progress from lower-order to higher-order thinking.",
    ]
    return "\n".join(lines + _slot_contract_footer(slot))


def _build_composition_instruction(slot: QuestionGenerationSlot) -> str:
    subject_norm = normalize_subject(slot.subject)
    hint = slot.instruction_hint or ""
    lines = [f"WRITING / COMPOSITION SLOT ({slot.marks} marks) — no retrieval.", _COMPOSITION_CARDINAL]
    sd = _script_directive(subject_norm)
    if sd:
        lines.append(sd)

    if subject_norm == "hindi" and "अनुच्छेद" in hint:
        # Free-topic scaffolded paragraph: 3 topics × exactly 3 hint points.
        lines += [
            "Provide EXACTLY 3 topic options. Each topic MUST carry EXACTLY 3 संकेत-बिन्दु (hint points) "
            "that scaffold the paragraph: (1) परिभाषा/अर्थ, (2) आवश्यकता/महत्त्व, (3) भूमिका/प्रभाव.",
            "State the word limit (~120 शब्द) in the stem. A topic with fewer than 3 संकेत-बिन्दु is INVALID.",
            "Topics must be contemporary, socially relevant, age-appropriate (Class X) and NON-duplicative.",
        ]
    elif subject_norm == "english" and "Analytical" in hint:
        # Stimulus-based analytical paragraph.
        lines += [
            "This is a STIMULUS-BASED analytical paragraph — NOT a free-topic essay, NOT a letter.",
            "Generate the STIMULUS inside the question: either TWO excerpts/profiles OR THREE profiles, "
            "each option carrying 3–4 DISTINCT comparable attributes so a genuine comparison is possible.",
            "State the comparison criteria and instruct the student to analyse/justify a choice in ONE cohesive "
            "paragraph of 120–150 words. State the word limit explicitly in the stem.",
        ]
    else:
        # Scenario compositions: letters, notice, advert, diary, news report, story, email.
        lines += [
            "Generate a self-contained scenario with: named role/sender, recipient/audience, and clear purpose. "
            "State the word limit explicitly in the stem.",
            "Where the format requires mandatory inputs (news-report ఆధారాలు/hints, a story's opening line), "
            "GENERATE those inputs in the question.",
        ]
    return "\n".join(lines + _slot_contract_footer(slot))


def _slot_instruction(slot: QuestionGenerationSlot) -> str:
    mode = str(getattr(slot, "generation_mode", "CONTENT") or "CONTENT").upper()
    if mode == "GRAMMAR":
        return _build_grammar_instruction(slot)
    if mode == "COMPOSITION":
        return _build_composition_instruction(slot)
    if mode == "PASSAGE":
        return _build_passage_instruction(slot)
    # ---- CONTENT mode (default): unchanged behaviour for Science/Social/Math/Literature ----
    return _build_content_instruction(slot)


def _build_content_instruction(slot: QuestionGenerationSlot) -> str:
    qtype = slot.question_type
    subject_norm = normalize_subject(slot.subject)
    lines = [
        f"Generate exactly ONE {slot.marks}-mark {qtype} question.",
        f"Subject: {slot.subject} | Class: {slot.class_num} | Track: {slot.stream}.",
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
            "Format content as 'Assertion (A): ...\\nReason (R): ...' and provide the four standard CBSE "
            "assertion-reason direction options: (A) Both A and R true, R is correct explanation; "
            "(B) Both A and R true, R is NOT correct explanation; (C) A true R false; (D) A false R true."
        )
    elif qtype == "CASE_STUDY":
        if subject_norm in ("hindi", "telugu"):
            lines.append(
                "Create the passage and ALL sub-questions in the correct script "
                "(Devanagari for Hindi, Telugu Unicode for Telugu). "
                "Follow the sub-part structure specified in the instruction hint."
            )
        else:
            lines.append("Create a short source-backed passage followed by exactly three sub-questions (1+1+2 marks).")
    elif qtype == "READING_COMP":
        lines.append(
            "Generate an ORIGINAL passage (never reproduce prescribed textbook content). "
            "Follow the exact sub-question count and marks distribution in the instruction hint. "
            "Sub-questions must progress from lower to higher order thinking."
        )
        if subject_norm == "telugu":
            lines.append("EVERY word — passage text, sub-questions, options — MUST be in Telugu Unicode script. No Roman letters.")
    elif qtype == "GRAMMAR":
        lines.append(
            "Generate the exact number of grammar tasks specified in the instruction hint. "
            "Each task is self-contained and worth 1 mark. "
            "Cover the distinct grammar points listed — do not repeat types."
        )
        if subject_norm == "hindi":
            lines.append("ALL grammar tasks and sentences MUST be in Devanagari Unicode. No transliteration.")
    elif qtype == "LETTER":
        lines.append(
            "Generate a formal letter writing task with full format: "
            "sender/date, recipient/designation, subject line, body, closing, signature. "
            "State the word limit in the question stem."
        )
        if subject_norm == "hindi":
            lines.append("The letter task and all instructions MUST be in Devanagari Unicode.")
        elif subject_norm == "telugu":
            lines.append("The entire letter task MUST be in Telugu Unicode script. No Roman transliteration.")
    elif qtype == "LONG_ANSWER":
        lines.append("Require structured reasoning appropriate for a long-answer response.")
        if subject_norm == "telugu":
            lines.append("Generate ALL content in Telugu Unicode script. No Roman transliteration anywhere.")
        elif subject_norm == "hindi":
            lines.append("Generate ALL content in Devanagari Unicode. No transliteration.")

    # Mathematics-specific notes
    if subject_norm == "mathematics":
        lines.append("State π = 22/7 unless otherwise specified.")
        # Uniqueness directive — the parallel generation pipeline can issue
        # several Section A MCQ prompts with overlapping retrieval contexts
        # (this is what caused Q4 and Q7 to print identical sin-A right
        # triangle stems). Tying the slot's `index` and `instruction_hint`
        # into the per-slot prompt forces the model to produce a distinct
        # scenario for THIS slot rather than echoing the retrieval chunk
        # verbatim.
        if slot.instruction_hint:
            lines.append(
                f"UNIQUENESS (slot Q{slot.index}): write a question that "
                f"matches THIS slot's instruction hint exactly — do NOT "
                f"recycle a scenario, values, or wording that could equally "
                f"apply to another slot in the same section. The hint above "
                f"is the only allowed topic for this question."
            )
        # Delimiter contract: the editor parses ONLY \( ... \) and \[ ... \]
        # for KaTeX rendering. Bare $...$ collides with currency literals and
        # $$...$$ has no inline form, so both are rejected. Unicode glyphs
        # (²/³/√/×/÷/π) are still fine when no nesting is needed.
        lines.append(
            "Math typesetting: wrap inline math in \\( ... \\) and display equations in \\[ ... \\]. "
            "Do NOT use $...$ or $$...$$. Example inline: \"Solve \\( x^2 + 3x + 2 = 0 \\).\" "
            "Example display: \"\\[ \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a} \\]\"."
        )
        lines.append("MCQ distractors must be plausible (represent common errors), not random numbers.")

    if slot.instruction_hint:
        lines.append(slot.instruction_hint)

    if slot.choice_required:
        lines.append(
            "Add exactly one internal choice in `question.or_choice`. "
            "Do NOT output the OR alternative as a separate question object. "
            "Never write the word 'OR' before the first alternative or after "
            "the last one — the renderer inserts the OR separator BETWEEN the "
            "two alternatives itself. Never repeat these instructions or any "
            "field name in the question text."
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

    if getattr(slot, "requires_figure", False):
        lines.append(
            "MANDATORY FIGURE: This question MUST include an inline SVG diagram in the `figure` field. "
            "Emit `\"figure\": {\"type\": \"svg\", \"content\": \"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 200'>...</svg>\"}`. "
            "The SVG must DRAW the actual geometry with shape elements "
            "(<line>, <path>, <circle>, <polygon>, <rect>) — an SVG containing "
            "ONLY <text> labels is rejected as residue. "
            "Label vertices/sides/angles with <text> IN ADDITION to the shapes. "
            "NO <script>, NO <foreignObject>, NO external xlink:href. "
            "A response without a valid `figure` field will be rejected."
        )

    return "\n".join(lines)


def build_retrieval_query(
    *,
    mode: str,
    topic: str,
    subject: str,
    stream: str,
    qtype_name: str,
    marks: int,
    difficulty: str,
    class_num: int,
    requires_image: bool = False,
    vi_required: bool = False,
    choice_required: bool = False,
    instruction_hint: str = "",
    instructions: str = "",
) -> str:
    """
    Build the vector-search query for one slot.

    RAG is meaningful ONLY in CONTENT mode (questions ABOUT studied chapters).
    PASSAGE / GRAMMAR / COMPOSITION slots are generated from rules or a fresh
    scenario, so they MUST NOT retrieve educator-uploaded chunks — they return
    an empty query, and the assembler then injects no [CONTEXT] block.
    """
    if str(mode).upper() != "CONTENT":
        return ""
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
    return " ".join(part for part in query_parts if part)


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
    requires_figure: bool = False,
    vi_required: bool = False,
    instruction_hint: str = "",
    mode: str = "CONTENT",
) -> QuestionGenerationSlot:
    legacy_type = _legacy_question_type(qtype_name)
    retrieval_query = build_retrieval_query(
        mode=mode,
        topic=topic,
        subject=subject,
        stream=stream,
        qtype_name=qtype_name,
        marks=marks,
        difficulty=difficulty,
        class_num=class_num,
        requires_image=requires_image,
        vi_required=vi_required,
        choice_required=choice_required,
        instruction_hint=instruction_hint,
        instructions=instructions,
    )
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
        requires_figure=requires_figure,
        vi_required=vi_required,
        instruction_hint=instruction_hint,
        generation_mode=str(mode).upper(),
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


def _exact_class10_blueprint_entries_mathematics() -> List[Dict[str, Any]]:
    """38 questions, 80 marks — CBSE Class 10 Mathematics Standard (Code 041) SQP 2025-26."""
    entries: List[Dict[str, Any]] = []

    # Section A — Q1–Q18 MCQ (1m) + Q19–Q20 ASSERTION_REASON (1m) = 20m
    mcq_hints = [
        "Q1: LCM/HCF by prime factorisation — fundamental theorem of arithmetic",
        "Q2: Find point on y-axis equidistant from two given points (distance from y-axis)",
        "Q3: Condition for pair of linear equations to have no solution (non-parallel lines)",
        "Q4: Tangent lengths from external point to circumscribed circle",
        "Q5: Use sec²θ - tan²θ = 1 identity to evaluate a trigonometric expression",
        "Q6: Identify which of the given expressions is NOT a quadratic equation",
        "Q7: Area of sector or segment of a circle (VI alternative: find arc length from given angle)",
        "Q8: Probability of an event using complement rule (dice or standard cards)",
        "Q9: Solve 2sin2θ = √3 (or similar) to find the angle θ",
        "Q10: Find all possible HCF values given the product of two numbers",
        "Q11: Find height of a cone given its base circumference and volume",
        "Q12: Condition for a quadratic to have equal roots — sign condition on discriminant",
        "Q13: Find area of a sector given arc length and radius",
        "Q14: Find perimeter of a triangle similar to a given triangle using similarity ratio",
        "Q15: Word problem on probability — solve for a variable in a probability equation",
        "Q16: Classify a quadrilateral as parallelogram/rhombus/square from its vertices",
        "Q17: Effect on median when all observations are shifted by a constant (uniform shift rule)",
        "Q18: Find tangent length from an external point given its distance and circle radius",
    ]
    for hint in mcq_hints:
        entries.append({
            "section": "Section A - Objective Questions",
            "stream": "MATHEMATICS",
            "qtype": "MCQ",
            "marks": 1,
            "count": 1,
            "hint": hint,
        })

    # Q19 — ASSERTION_REASON (prime numbers and powers)
    entries.append({
        "section": "Section A - Objective Questions",
        "stream": "MATHEMATICS",
        "qtype": "ASSERTION_REASON",
        "marks": 1,
        "count": 1,
        "hint": (
            "Q19 (Assertion-Reason, Real Numbers): "
            "Assertion (A): 5^n cannot end in the digit 0 for any natural number n. "
            "Reason (R): Any number ending in 0 must have both 2 and 5 as prime factors, but 5^n has only the prime factor 5. "
            "Include the standard CBSE direction block verbatim."
        ),
    })
    # Q20 — ASSERTION_REASON (trigonometry identity)
    entries.append({
        "section": "Section A - Objective Questions",
        "stream": "MATHEMATICS",
        "qtype": "ASSERTION_REASON",
        "marks": 1,
        "count": 1,
        "hint": (
            "Q20 (Assertion-Reason, Trigonometry): "
            "Assertion (A): If cosA + cos²A = 1, then sin²A + sin⁴A = 1. "
            "Reason (R): From cosA = 1 - cos²A = sin²A, we get sin²A + sin⁴A = cosA + cos²A = 1. "
            "Include the standard CBSE direction block verbatim."
        ),
    })

    # Section B — Q21–Q25 VSA SHORT_ANSWER 2m = 10m
    # Tuples: (choice_required, hint, requires_figure)
    vsa_data = [
        (True,  "Q21 (VSA, internal choice): Find the sum of the last n terms of an AP OR find the middle term of an AP.", False),
        (False, "Q22 (VSA): Given sin(A+B) = 1 and cos(A-B) = √3/2, find angle A and angle B where 0 < A,B < 90°.", False),
        (False, "Q23 (VSA): Prove that the ratio of corresponding sides of similar triangles equals the ratio of their corresponding medians.", True),
        (True,  "Q24 (VSA, internal choice): A horse is tied to a peg by a rope; find the area it can graze (sector area) OR find the area of a major segment of a circle.", False),
        (False, "Q25 (VSA): A triangle is circumscribed about a circle; find its sides using tangent properties. VI alternative: find the inradius of a right triangle with legs 6 cm and 8 cm.", False),
    ]
    for choice, hint, req_fig in vsa_data:
        entries.append({
            "section": "Section B - Very Short Answer",
            "stream": "MATHEMATICS",
            "qtype": "SHORT_ANSWER",
            "marks": 2,
            "count": 1,
            "choice_required": choice,
            "requires_figure": req_fig,
            "hint": hint,
        })

    # Section C — Q26–Q31 SA SHORT_ANSWER 3m = 18m
    sa_data = [
        (False, "Q26 (SA): Prove that tangents drawn from an external point to a circle make equal angles with the line joining the point to the centre (∠AOB = 90°). VI alternative: prove ∠APB = 2∠OAB."),
        (False, "Q27 (SA): HCF application — find the maximum length of a measuring tape that can exactly measure two rooms of given dimensions."),
        (False, "Q28 (SA): Find the zeroes of a given quadratic polynomial and verify the relationship between zeroes and coefficients."),
        (True,  "Q29 (SA, internal choice): Prove a given trigonometric identity OR prove an alternate trigonometric identity of equal difficulty."),
        (False, "Q30 (SA): A real-life scenario with two bags containing different coloured balls; compare the probabilities of drawing a specific colour from each bag."),
        (True,  "Q31 (SA, internal choice): Solve a linear equations word problem (income/expenditure ratio) algebraically OR solve graphically and find the area of the triangle formed with the axes. VI alternative: frame and solve an ages-based linear system."),
    ]
    for choice, hint in sa_data:
        entries.append({
            "section": "Section C - Short Answer",
            "stream": "MATHEMATICS",
            "qtype": "SHORT_ANSWER",
            "marks": 3,
            "count": 1,
            "choice_required": choice,
            "hint": hint,
        })

    # Section D — Q32–Q35 LA LONG_ANSWER 5m = 20m
    # Tuples: (choice_required, hint, requires_figure)
    la_data = [
        (False, "Q32 (LA): Speed-distance-time quadratic word problem (e.g., a train covers a distance; if it travels 10 km/h slower it takes 3 h more — find original speed).", False),
        (False, "Q33 (LA): State and prove the Basic Proportionality Theorem (Thales' theorem). Then apply it to find a side length in a given figure.", True),
        (True,  "Q34 (LA, internal choice): Find the total surface area of a solid formed by combining a cone and a cylinder (or cylinder with hemispherical cavity) OR find the volume of an ice-cream cone (cone + hemisphere).", False),
        (True,  "Q35 (LA, internal choice): Find mode and mean from a grouped frequency distribution table, then use the empirical formula to find the median OR construct a 'less than' ogive from the given data and find the median graphically.", False),
    ]
    for choice, hint, req_fig in la_data:
        entries.append({
            "section": "Section D - Long Answer",
            "stream": "MATHEMATICS",
            "qtype": "LONG_ANSWER",
            "marks": 5,
            "count": 1,
            "choice_required": choice,
            "requires_figure": req_fig,
            "hint": hint,
        })

    # Section E — Q36–Q38 CASE_STUDY 4m = 12m (sub-part iii always has OR)
    cs_hints = [
        (
            "Q36 (Case Study, AP): Real-world Arithmetic Progression scenario "
            "(e.g. stadium seating rows, weekly savings, parade formations). "
            "Sub-parts: (i) 1m — identify if it is an AP or find first term/common difference; "
            "(ii) 1m — find a specific term; "
            "(iii) 2m — find sum or nth term (MUST include an internal OR choice for sub-part iii)."
        ),
        (
            "Q37 (Case Study, Coordinate Geometry): Real-world coordinate geometry scenario "
            "(e.g. park layout, town planning on a grid). "
            "VI alternative MUST state explicit numerical coordinates in the question text. "
            "Sub-parts: (i) 1m — find distance between two points; "
            "(ii) 1m — find midpoint or apply section formula; "
            "(iii) 2m — find area of triangle formed by three points OR find ratio in which a point divides a segment "
            "(MUST include internal OR for sub-part iii)."
        ),
        (
            "Q38 (Case Study, Heights & Distances): A ~42 m tall monument/tower with a ~1.6 m observer. "
            "Sub-parts: (i) 1m — find an angle of elevation or depression; "
            "(ii) 1m — find a horizontal distance using tan/sin/cos; "
            "(iii) 2m — find height or distance using two different angles of elevation "
            "(MUST include internal OR for sub-part iii). Use √3 ≈ 1.732."
        ),
    ]
    for hint in cs_hints:
        entries.append({
            "section": "Section E - Case Based Questions",
            "stream": "MATHEMATICS",
            "qtype": "CASE_STUDY",
            "marks": 4,
            "count": 1,
            "choice_required": True,
            "hint": hint,
        })

    return entries


def _exact_class10_blueprint_entries_english() -> List[Dict[str, Any]]:
    """11 questions, 80 marks — CBSE Class 10 English Language & Literature (Code 184) SQP 2025-26."""
    return [
        # Section A — Reading Comprehension (20m)
        {
            "section": "Section A - Reading Comprehension",
            "stream": "ENGLISH_READING",
            "qtype": "READING_COMP",
            "mode": "PASSAGE",
            "marks": 10,
            "count": 1,
            "hint": (
                "Q1 (10m): Generate an ORIGINAL ~400-word factual/discursive passage. "
                "NEVER reproduce any text from First Flight or Footprints Without Feet. "
                "Generate 8 sub-questions with marks distribution 1+1+1+1+1+2+1+2. "
                "Types: (i) inferential short-answer 1m, (ii) EXCEPT-type MCQ 1m, "
                "(iii) fill-blank-from-bracket 1m, (iv) select-True MCQ 1m, "
                "(v) complete-analogy 1m, (vi) 2-mark explanation, (vii) main-idea MCQ 1m, "
                "(viii) 2-mark synthesis. Questions must progress from lower to higher order thinking."
            ),
        },
        {
            "section": "Section A - Reading Comprehension",
            "stream": "ENGLISH_READING",
            "qtype": "READING_COMP",
            "mode": "PASSAGE",
            "marks": 10,
            "count": 1,
            "hint": (
                "Q2 (10m): Generate an ORIGINAL ~250-word data/survey/infographic passage "
                "(topic MUST differ from Q1; NEVER use prescribed text). "
                "Generate 9 sub-questions: 7×1m + 1×2m + 1×1m. "
                "Include: MCQ data-interpretation, phrase identification, "
                "data-comprehension fill-blank, relationship explanation, 2-mark elaboration. "
                "Final sub-question MUST be fill-blank-ONE-word type."
            ),
        },
        # Section B — Grammar & Writing (20m)
        {
            "section": "Section B - Grammar and Writing",
            "stream": "ENGLISH_GRAMMAR",
            "qtype": "GRAMMAR",
            "mode": "GRAMMAR",
            "marks": 10,
            "count": 1,
            "hint": (
                "Q3 (10m): Generate EXACTLY 12 one-mark grammar tasks; student attempts any 10. "
                "Cover DISTINCT grammar points without repetition: "
                "tense correction (×2), reported speech statement (×1), reported speech command (×1), "
                "reported speech question (×1), error-correction plain sentence (×1), "
                "error-correction MCQ-format with options (×1), preposition MCQ (×1), "
                "modal verb (×1), determiner (×1), quantifier (×1), participle/gerund MCQ (×1). "
                "Use realistic contexts: market research survey, diary entry, formal letter, public notice."
            ),
        },
        {
            "section": "Section B - Grammar and Writing",
            "stream": "ENGLISH_WRITING",
            "qtype": "LETTER",
            "mode": "COMPOSITION",
            "marks": 5,
            "count": 1,
            "choice_required": True,
            "hint": (
                "Q4 (5m): Two options — attempt ONE. State word limit (~120 words) in the question stem. "
                "(A) Formal letter to an authority (Municipal Corporation/School Principal/Editor) "
                "proposing a community scheme or school event; full format, named sender + city. "
                "(B) Letter to the Editor of a newspaper on a current social/environmental issue; "
                "full format, named sender + city."
            ),
        },
        {
            "section": "Section B - Grammar and Writing",
            "stream": "ENGLISH_WRITING",
            "qtype": "SHORT_ANSWER",
            "mode": "COMPOSITION",
            "marks": 5,
            "count": 1,
            "choice_required": True,
            "hint": (
                "Q5 (5m): Analytical Paragraph — Two options — attempt ONE (120–150 words). "
                "Provide 2 different excerpts/profiles/data points for each option. "
                "Student must analyse and justify a choice based on stated criteria. "
                "CRITICAL: Exactly ONE cohesive paragraph. NOT an essay. NOT a letter. NOT a list."
            ),
        },
        # Section C — Literature (40m)
        {
            "section": "Section C - Literature",
            "stream": "ENGLISH_LITERATURE",
            "qtype": "SHORT_ANSWER",
            "marks": 5,
            "count": 1,
            "choice_required": True,
            "hint": (
                "Q6 (5m): Two prose extract options (A and B) from DIFFERENT First Flight prose chapters. "
                "Each has 4 sub-questions: 2+1+1+1 marks. "
                "Prescribed chapters: A Letter to God, Nelson Mandela, Two Stories About Flying, "
                "Anne Frank, Glimpses of India, Mijbil the Otter, Madam Rides the Bus, "
                "The Sermon at Benares, The Proposal."
            ),
        },
        {
            "section": "Section C - Literature",
            "stream": "ENGLISH_LITERATURE",
            "qtype": "SHORT_ANSWER",
            "marks": 5,
            "count": 1,
            "choice_required": True,
            "hint": (
                "Q7 (5m): Two poetry extract options (A and B) from DIFFERENT First Flight poems. "
                "Each has 4 sub-questions: 1+2+1+1 marks. "
                "Test: identify poetic device/imagery (1m), explain theme/tone (2m), "
                "contextual meaning (1m), inferential (1m). "
                "Prescribed poems: Dust of Snow, Fire and Ice, A Tiger in the Zoo, "
                "How to Tell Wild Animals, The Ball Poem, Amanda!, Animals, The Trees, Fog, "
                "Custard the Dragon, For Anne Gregory."
            ),
        },
        {
            "section": "Section C - Literature",
            "stream": "ENGLISH_LITERATURE",
            "qtype": "SHORT_ANSWER",
            "marks": 12,
            "count": 1,
            "hint": (
                "Q8 (12m): Generate 5 short-answer questions; student answers any 4 (×3m, ~50 words each). "
                "MANDATORY coverage: at least 2 from First Flight Prose, "
                "at least 1 from First Flight Poetry, at least 1 from Footprints Without Feet. "
                "No chapter/poem repeated. ALL questions must require analysis or evaluation — "
                "reject pure factual recall."
            ),
        },
        {
            "section": "Section C - Literature",
            "stream": "ENGLISH_LITERATURE",
            "qtype": "SHORT_ANSWER",
            "marks": 6,
            "count": 1,
            "hint": (
                "Q9 (6m): Generate 3 questions from Footprints Without Feet ONLY; "
                "student answers any 2 (×3m, ~40-50 words each). "
                "All 3 from DIFFERENT Footprints stories. "
                "Stories: A Triumph of Surgery, The Thief's Story, The Midnight Visitor, "
                "A Question of Trust, Footprints Without Feet, Making of a Scientist, "
                "The Necklace, The Hack Driver, Bholi, The Book That Saved the Earth."
            ),
        },
        {
            "section": "Section C - Literature",
            "stream": "ENGLISH_LITERATURE",
            "qtype": "LONG_ANSWER",
            "marks": 6,
            "count": 1,
            "choice_required": True,
            "hint": (
                "Q10 (6m): Two options from First Flight — attempt ONE (~100-120 words). "
                "Thematic or comparative analysis across 2-3 First Flight chapters/poems. "
                "Higher-order: evaluate theme, character development, or moral message. "
                "NOT a plot summary."
            ),
        },
        {
            "section": "Section C - Literature",
            "stream": "ENGLISH_LITERATURE",
            "qtype": "LONG_ANSWER",
            "marks": 6,
            "count": 1,
            "choice_required": True,
            "hint": (
                "Q11 (6m): Two options from Footprints Without Feet — attempt ONE (~100-120 words). "
                "Both options from DIFFERENT Footprints stories. "
                "Require critical commentary on narrative technique, character significance, "
                "or thematic message. NOT a plot summary."
            ),
        },
    ]


def _exact_class10_blueprint_entries_hindi() -> List[Dict[str, Any]]:
    """16 questions, 80 marks — CBSE Class 10 Hindi Course B (Code 085) SQP 2025-26."""
    return [
        # खण्ड क — अपठित बोध (14m)
        {
            "section": "खण्ड क - अपठित बोध",
            "stream": "HINDI_READING",
            "mode": "PASSAGE",
            "qtype": "CASE_STUDY",
            "marks": 7,
            "count": 1,
            "hint": (
                "Q1 (7m): Original Hindi prose passage ~250-300 words on theme like कर्म/योग्यता/प्रेरणा. "
                "ALL content in Devanagari Unicode — no Roman transliteration. "
                "Sub-parts (7 total, 7m): (i) 1m MCQ on central fact, (ii) 1m MCQ on purpose/title, "
                "(iii) 1m कथन-कारण MCQ (4 options: i only, ii only, i and ii, neither), "
                "(iv) 1m शब्द-अर्थ/विलोम/समानार्थी, (v) 1m उपयुक्त शीर्षक, "
                "(vi) 1m inference MCQ, (vii) 1m fill-blank from passage."
            ),
        },
        {
            "section": "खण्ड क - अपठित बोध",
            "stream": "HINDI_READING",
            "mode": "PASSAGE",
            "qtype": "CASE_STUDY",
            "marks": 7,
            "count": 1,
            "hint": (
                "Q2 (7m): SECOND original Hindi passage ~250-300 words on a CLEARLY DIFFERENT theme from Q1 "
                "(e.g., प्रकाश/ज्ञान/परंपरा/प्रकृति — NOT कर्म or योग्यता). "
                "ALL content in Devanagari Unicode. "
                "Same 7 sub-part structure as Q1 but with different MCQ types. "
                "Both passages must be original compositions — never reproduce textbook content."
            ),
        },
        # खण्ड ख — व्यावहारिक व्याकरण (16m)
        {
            "section": "खण्ड ख - व्यावहारिक व्याकरण",
            "stream": "HINDI_GRAMMAR",
            "mode": "GRAMMAR",
            "qtype": "GRAMMAR",
            "marks": 4,
            "count": 1,
            "hint": (
                "Q3 (4m) पदबंध: Generate 5 tasks; student does any 4 (×1m each). "
                "ALL in Devanagari Unicode. "
                "Cover: सर्वनाम पदबंध, विशेषण पदबंध, क्रिया पदबंध, संज्ञा पदबंध, क्रिया-विशेषण पदबंध. "
                "Tasks: identify padband type, make padband from given words, substitute in sentence."
            ),
        },
        {
            "section": "खण्ड ख - व्यावहारिक व्याकरण",
            "stream": "HINDI_GRAMMAR",
            "mode": "GRAMMAR",
            "qtype": "GRAMMAR",
            "marks": 4,
            "count": 1,
            "hint": (
                "Q4 (4m) वाक्य रूपांतरण: Generate 5 tasks; student does any 4 (×1m). "
                "ALL in Devanagari Unicode. "
                "Cover: सरल→संयुक्त, संयुक्त→मिश्र, मिश्र→सरल वाक्य रूपांतरण, identify type. "
                "Use varied realistic contexts (school, nature, daily life)."
            ),
        },
        {
            "section": "खण्ड ख - व्यावहारिक व्याकरण",
            "stream": "HINDI_GRAMMAR",
            "mode": "GRAMMAR",
            "qtype": "GRAMMAR",
            "marks": 4,
            "count": 1,
            "hint": (
                "Q5 (4m) समास: Generate 5 tasks; student does any 4 (×1m). "
                "ALL in Devanagari Unicode. "
                "Cover समास bheds: द्वंद्व, द्विगु, कर्मधारय, बहुव्रीहि, नञ् समास. "
                "Tasks: form samashik pad + name bhed, give vigrah + name bhed."
            ),
        },
        {
            "section": "खण्ड ख - व्यावहारिक व्याकरण",
            "stream": "HINDI_GRAMMAR",
            "mode": "GRAMMAR",
            "qtype": "GRAMMAR",
            "marks": 4,
            "count": 1,
            "hint": (
                "Q6 (4m) मुहावरे: Generate 5 tasks; student does any 4 (×1m). "
                "ALL in Devanagari Unicode. "
                "Tasks: fill blank with correct muhavara, use in sentence, distinguish two similar muhavare, "
                "identify muhavara from a line. "
                "Common examples: नाक में दम करना, हाथ-पाँव फूलना, आँखें खुलना, मुँह में पानी आना."
            ),
        },
        # खण्ड ग — पाठ्यपुस्तक (28m)
        {
            "section": "खण्ड ग - पाठ्यपुस्तक",
            "stream": "HINDI_LITERATURE",
            "qtype": "MCQ",
            "marks": 5,
            "count": 1,
            "hint": (
                "Q7 (5m) पठित गद्यांश: Select extract from a स्पर्श गद्य chapter "
                "(बड़े भाई साहब / डायरी का एक पन्ना / तताँरा-वामीरो कथा / "
                "तीसरी कसम के शिल्पकार / गिरगिट / अब कहाँ दूसरे के दुख से...). "
                "ALL in Devanagari Unicode. "
                "Generate 5 MCQs (1m each) including one कथन-कारण MCQ. "
                "Test: comprehension, vocabulary, inference, character, theme."
            ),
        },
        {
            "section": "खण्ड ग - पाठ्यपुस्तक",
            "stream": "HINDI_LITERATURE",
            "qtype": "SHORT_ANSWER",
            "marks": 6,
            "count": 1,
            "hint": (
                "Q8 (6m) गद्य लघु-उत्तर: Generate 4 questions from 4 DIFFERENT स्पर्श गद्य chapters; "
                "student answers any 3 (×2m, ~25-30 words). "
                "ALL in Devanagari Unicode. No chapter repeated. "
                "Chapters: बड़े भाई साहब, डायरी का एक पन्ना, तताँरा-वामीरो कथा, "
                "तीसरी कसम के शिल्पकार शैलेंद्र, गिरगिट, अब कहाँ दूसरे के दुख से दुखी होने वाले."
            ),
        },
        {
            "section": "खण्ड ग - पाठ्यपुस्तक",
            "stream": "HINDI_LITERATURE",
            "qtype": "MCQ",
            "marks": 5,
            "count": 1,
            "hint": (
                "Q9 (5m) पठित काव्यांश: Select extract from a स्पर्श काव्य poem "
                "(साखी / मीरा के पद / बिहारी / मनुष्यता / पर्वत प्रदेश में पावस / "
                "मधुर-मधुर मेरे दीपक जल / तोप / कर चले हम फ़िदा / आत्मत्राण). "
                "ALL in Devanagari Unicode. "
                "Generate 5 MCQs (1m each) — meaning, poetic device, bhav, context, theme."
            ),
        },
        {
            "section": "खण्ड ग - पाठ्यपुस्तक",
            "stream": "HINDI_LITERATURE",
            "qtype": "SHORT_ANSWER",
            "marks": 6,
            "count": 1,
            "hint": (
                "Q10 (6m) काव्य लघु-उत्तर: Generate 4 questions from 4 DIFFERENT स्पर्श काव्य poems; "
                "student answers any 3 (×2m, ~25-30 words). "
                "ALL in Devanagari Unicode. No poem repeated. "
                "Poems: साखी, मीरा के पद, बिहारी, मनुष्यता, पर्वत प्रदेश में पावस, "
                "मधुर-मधुर मेरे दीपक जल, तोप, कर चले हम फ़िदा, आत्मत्राण."
            ),
        },
        {
            "section": "खण्ड ग - पाठ्यपुस्तक",
            "stream": "HINDI_LITERATURE",
            "qtype": "SHORT_ANSWER",
            "marks": 6,
            "count": 1,
            "hint": (
                "Q11 (6m) संचयन: Generate 3 questions covering ALL 3 संचयन texts; "
                "student answers any 2 (×3m, ~40-50 words). "
                "ALL in Devanagari Unicode. "
                "One question each from: हरिहर काका, सपनों के-से दिन, टोपी शुक्ला. "
                "Test character, theme, or social message — not mere plot recall."
            ),
        },
        # खण्ड घ — रचनात्मक लेखन (22m)
        {
            "section": "खण्ड घ - रचनात्मक लेखन",
            "stream": "HINDI_WRITING",
            "mode": "COMPOSITION",
            "qtype": "LONG_ANSWER",
            "marks": 5,
            "count": 1,
            "hint": (
                "Q12 (5m) अनुच्छेद लेखन: Provide EXACTLY 3 topic options, each with EXACTLY 3 संकेत-बिन्दु; "
                "student writes any 1 (~120 शब्द). "
                "ALL in Devanagari Unicode. State the word limit (शब्द-सीमा) in the stem. "
                "Topics: contemporary and relevant (e.g., डिजिटल भारत, पर्यावरण प्रदूषण, "
                "युवा और खेल, स्वास्थ्य और आहार). "
                "The 3 संकेत-बिन्दु per topic must scaffold: (1) परिभाषा/अर्थ, (2) आवश्यकता/महत्त्व, "
                "(3) भूमिका/प्रभाव. A topic with fewer than 3 संकेत-बिन्दु is INVALID."
            ),
        },
        {
            "section": "खण्ड घ - रचनात्मक लेखन",
            "stream": "HINDI_WRITING",
            "mode": "COMPOSITION",
            "qtype": "LETTER",
            "marks": 5,
            "count": 1,
            "choice_required": True,
            "hint": (
                "Q13 (5m) औपचारिक पत्र: Two options — write ONE (~100 words, full format). "
                "ALL in Devanagari Unicode. "
                "(A) Application to Principal requesting a school facility or addressing an issue. "
                "(B) Letter to Editor of a newspaper on a social/environmental issue. "
                "Full format: दिनांक, प्रेषक, सेवा में/श्रीमान् सम्पादक, विषय, विनम्र निवेदन, "
                "प्रार्थना, भवदीय, हस्ताक्षर."
            ),
        },
        {
            "section": "खण्ड घ - रचनात्मक लेखन",
            "stream": "HINDI_WRITING",
            "mode": "COMPOSITION",
            "qtype": "SHORT_ANSWER",
            "marks": 4,
            "count": 1,
            "choice_required": True,
            "hint": (
                "Q14 (4m) सूचना लेखन: Two options — write ONE (~60 words). "
                "ALL in Devanagari Unicode. "
                "Topics: school event notice / lost & found / cultural programme / meeting notice. "
                "Full format: शीर्षक सूचना, तिथि, सूचना का विषय, विवरण, हस्ताक्षर/पद."
            ),
        },
        {
            "section": "खण्ड घ - रचनात्मक लेखन",
            "stream": "HINDI_WRITING",
            "mode": "COMPOSITION",
            "qtype": "SHORT_ANSWER",
            "marks": 3,
            "count": 1,
            "choice_required": True,
            "hint": (
                "Q15 (3m) विज्ञापन: Two options — make ONE advertisement (~40 words with नारा/tagline). "
                "ALL in Devanagari Unicode. "
                "Topics: natural/organic product, health service, or environment awareness. "
                "Must include: उत्पाद/सेवा का नाम, मुख्य विशेषता, नारा, सम्पर्क (if relevant)."
            ),
        },
        {
            "section": "खण्ड घ - रचनात्मक लेखन",
            "stream": "HINDI_WRITING",
            "mode": "COMPOSITION",
            "qtype": "LONG_ANSWER",
            "marks": 5,
            "count": 1,
            "choice_required": True,
            "hint": (
                "Q16 (5m) लघुकथा/ई-मेल: Two options — write ONE (~100 words). "
                "ALL in Devanagari Unicode. "
                "(A) लघुकथा: Provide a vivid opening line (e.g., 'अचानक सन्नाटा टूटा...'); "
                "student continues with पात्र, संघर्ष, समाधान/निष्कर्ष. "
                "(B) ई-मेल: To a friend/official; To/Subject/body/closing format."
            ),
        },
    ]


def _exact_class10_blueprint_entries_telugu() -> List[Dict[str, Any]]:
    """18 questions, 80 marks — CBSE Class 10 Telugu Telangana (Code 089) SQP 2025-26."""
    return [
        # విభాగం ఎ (10m)
        {
            "section": "విభాగం ఎ",
            "stream": "TELUGU_READING",
            "mode": "PASSAGE",
            "qtype": "READING_COMP",
            "marks": 10,
            "count": 1,
            "hint": (
                "Q1 (10m): ORIGINAL ~300-word Telugu passage about a prominent Telugu/Telangana "
                "scholar, writer, poet, or social reformer. "
                "EVERY word — passage, questions, options, section headers — "
                "MUST be in Telugu Unicode script (U+0C00–U+0C7F). No Roman transliteration. "
                "Generate 5 MCQs ×2m (total 10m): "
                "(i) institution/place associated with the person, "
                "(ii) named literary/academic work, "
                "(iii) award/research/recognition, "
                "(iv) source of a quoted line in the passage, "
                "(v) activities/contributions described. "
                "Each MCQ: 4 Telugu-script options."
            ),
        },
        # విభాగం బి (11m)
        {
            "section": "విభాగం బి",
            "stream": "TELUGU_WRITING",
            "mode": "COMPOSITION",
            "qtype": "LETTER",
            "marks": 6,
            "count": 1,
            "hint": (
                "Q2 (6m) లేఖా-రచన: ENTIRE task in Telugu Unicode script only — no Roman letters. "
                "Provide a scenario: named student writer (e.g., రాముడు/లక్ష్మి) writing to a "
                "named recipient (ప్రధానాచార్యులు/తల్లిదండ్రులు/స్నేహితుడు) for a specific purpose "
                "(సౌకర్యం కోసం/సమాచారం/సమస్య పరిష్కారం). ~100 words. "
                "Full format: తేదీ, పంపే వారి పేరు+చిరునామా, స్వీకర్త, విషయం, ముఖ్య విషయం, ముగింపు."
            ),
        },
        {
            "section": "విభాగం బి",
            "stream": "TELUGU_WRITING",
            "mode": "COMPOSITION",
            "qtype": "LONG_ANSWER",
            "marks": 5,
            "count": 1,
            "choice_required": True,
            "hint": (
                "Q3 (5m) ప్రక్రియ: Two options — write ONE (~100 words). "
                "ENTIRE task in Telugu Unicode script only. "
                "(a) దినచర్య (Diary): entry for a meaningful day (school event/trip/achievement). "
                "Include: తేదీ, వారం, సమయం, అనుభవం, భావాలు, ముగింపు. "
                "(b) వార్తా-రచన (News report): Write using EXACTLY 4-6 given ఆధారాలు listed in Telugu. "
                "Include: శీర్షిక, తేదీ+స్థలం, ముఖ్య విషయం, వివరాలు, ముగింపు."
            ),
        },
        # విభాగం సి (29m)
        {
            "section": "విభాగం సి",
            "stream": "TELUGU_GRAMMAR",
            "mode": "GRAMMAR",
            "qtype": "MCQ",
            "marks": 4,
            "count": 1,
            "hint": (
                "Q4 (4m) సంధి: 4 MCQs in Telugu Unicode only (1m each). "
                "(i) identify సంధి సూత్రం for a given example, "
                "(ii) identify correct విభక్తి ప్రత్యయం, "
                "(iii) split (విడదీయడం) a sandhi word, "
                "(iv) combine (సంధి చేయడం) two words. "
                "Cover: అకార/ఇకార/ఉకార/గసడదవాదేశ సంధి. 4 Telugu options each."
            ),
        },
        {
            "section": "విభాగం సి",
            "stream": "TELUGU_GRAMMAR",
            "mode": "GRAMMAR",
            "qtype": "MCQ",
            "marks": 4,
            "count": 1,
            "hint": (
                "Q5 (4m) ఛందస్సు: 4 MCQs in Telugu Unicode only (1m each). "
                "Use a verse line from prescribed texts. "
                "(i) identify యతి మైత్రి, "
                "(ii) name the వృత్తం (ఉత్పలమాల/చంపకమాల/శార్దూలవిక్రీడితం/మత్తేభవిక్రీడితం), "
                "(iii) identify గణాలు (pattern), "
                "(iv) count పాదాక్షరం. "
                "Gana patterns MUST match the named metre exactly."
            ),
        },
        {
            "section": "విభాగం సి",
            "stream": "TELUGU_GRAMMAR",
            "mode": "GRAMMAR",
            "qtype": "MCQ",
            "marks": 4,
            "count": 1,
            "hint": (
                "Q6 (4m) సమాసం: 4 MCQs in Telugu Unicode only (1m each). "
                "Cover 4 different types: రూపక సమాసం, ద్విగు సమాసం, ద్వంద్వ సమాసం, బహువ్రీహి సమాసం. "
                "Test: lakshana of samasa, give example, identify type of given samashta-pada."
            ),
        },
        {
            "section": "విభాగం సి",
            "stream": "TELUGU_GRAMMAR",
            "mode": "GRAMMAR",
            "qtype": "MCQ",
            "marks": 4,
            "count": 1,
            "hint": (
                "Q7 (4m) అలంకారాలు: 4 MCQs in Telugu Unicode only (1m each). "
                "(i) identify అలంకారం in a given Telugu sentence, "
                "(ii) give lakshana of a named alankara, "
                "(iii) identify ఉపమానం in a given simile, "
                "(iv) choose correct example for a named alankara. "
                "Cover: ఉపమా, రూపక, ఉత్ప్రేక్ష, అతిశయోక్తి అలంకారాలు."
            ),
        },
        {
            "section": "విభాగం సి",
            "stream": "TELUGU_GRAMMAR",
            "mode": "GRAMMAR",
            "qtype": "MCQ",
            "marks": 2,
            "count": 1,
            "hint": (
                "Q8 (2m) పర్యాయ పదాలు: 2 MCQs in Telugu Unicode only (1m each). "
                "Test synonyms: (i) identify correct పర్యాయ పదం for a given word, "
                "(ii) find the word that does NOT belong to the synonym group."
            ),
        },
        {
            "section": "విభాగం సి",
            "stream": "TELUGU_GRAMMAR",
            "mode": "GRAMMAR",
            "qtype": "MCQ",
            "marks": 2,
            "count": 1,
            "hint": (
                "Q9 (2m) జాతీయాలు: 2 MCQs in Telugu Unicode only (1m each). "
                "(i) meaning of a given Telugu idiom (జాతీయం), "
                "(ii) identify the sentence that correctly uses a given idiom."
            ),
        },
        {
            "section": "విభాగం సి",
            "stream": "TELUGU_GRAMMAR",
            "mode": "GRAMMAR",
            "qtype": "MCQ",
            "marks": 2,
            "count": 1,
            "hint": (
                "Q10 (2m) సామెతలు: 2 MCQs in Telugu Unicode only (1m each). "
                "(i) meaning of a given Telugu proverb (సామెత), "
                "(ii) match a described situation to the appropriate సామెత."
            ),
        },
        {
            "section": "విభాగం సి",
            "stream": "TELUGU_GRAMMAR",
            "mode": "GRAMMAR",
            "qtype": "MCQ",
            "marks": 2,
            "count": 1,
            "hint": (
                "Q11 (2m) పాఠ్యాంశ ప్రక్రియ: 2 MCQs in Telugu Unicode only (1m each). "
                "(i) given a chapter name, identify its ప్రక్రియ (గద్యం/పద్యం/ఏకాంకిక/కథ/వ్యాసం), "
                "(ii) given a ప్రక్రియ, identify which prescribed chapter belongs to it."
            ),
        },
        {
            "section": "విభాగం సి",
            "stream": "TELUGU_LITERATURE",
            "qtype": "MCQ",
            "marks": 5,
            "count": 1,
            "hint": (
                "Q12 (5m) పరిచిత గద్యాంశం: Extract from a prescribed Telugu prose/verse chapter. "
                "ENTIRE question in Telugu Unicode only. "
                "5 MCQs (1m each): speaker/character identification, event sequence, "
                "vocabulary meaning in context, inference, author's purpose/tone."
            ),
        },
        # విభాగం డి (30m)
        {
            "section": "విభాగం డి",
            "stream": "TELUGU_LITERATURE",
            "qtype": "SHORT_ANSWER",
            "marks": 4,
            "count": 1,
            "hint": (
                "Q13 (4m) సంగ్రహ జవాబులు: 4 questions in Telugu Unicode; student answers any 2 (×2m, ~50-60 words). "
                "Theme: నీతి/పాత్ర/తాత్విక (ethics/character/philosophical). "
                "Chapters: గోలకొండ, కొత్తబాట, లక్ష్యసిద్ధి, భిక్ష. "
                "Questions must require interpretation — not mere factual recall."
            ),
        },
        {
            "section": "విభాగం డి",
            "stream": "TELUGU_LITERATURE",
            "qtype": "SHORT_ANSWER",
            "marks": 4,
            "count": 1,
            "hint": (
                "Q14 (4m) సంగ్రహ జవాబులు-2: 4 questions in Telugu Unicode; "
                "student answers any 2 (×2m, ~50-60 words). "
                "Theme: సమాజం/ప్రకృతి/జీవితం (society/nature/life). "
                "Use chapters DIFFERENT from Q13. Questions probe social/natural/life values."
            ),
        },
        {
            "section": "విభాగం డి",
            "stream": "TELUGU_LITERATURE",
            "qtype": "LONG_ANSWER",
            "marks": 4,
            "count": 1,
            "choice_required": True,
            "hint": (
                "Q15 (4m) విపులంగా: Two options in Telugu Unicode — write ONE (~120 words). "
                "(a) గోలకొండ పాఠం: analyse theme/characters/social message. "
                "(b) కొత్తబాట పాఠం: analyse theme/moral/significance. "
                "Analytical essay — NOT plot summary."
            ),
        },
        {
            "section": "విభాగం డి",
            "stream": "TELUGU_LITERATURE",
            "qtype": "LONG_ANSWER",
            "marks": 4,
            "count": 1,
            "choice_required": True,
            "hint": (
                "Q16 (4m) విపులంగా-2: Two options in Telugu Unicode — write ONE (~120 words). "
                "(a) శతక నీతులు: explain philosophical/ethical message of a given శతక verse. "
                "(b) జీవనభాషం సందేశం: explain life-message of a prescribed poem/prose piece. "
                "Critical reflection required — not mere paraphrase."
            ),
        },
        {
            "section": "విభాగం డి",
            "stream": "TELUGU_LITERATURE",
            "qtype": "LONG_ANSWER",
            "marks": 6,
            "count": 1,
            "choice_required": True,
            "hint": (
                "Q17 (6m) పద్య అన్వయ క్రమం + ప్రతిపదార్థాలు: Two padya options in Telugu Unicode — do ONE. "
                "question_text = full padya verse in Telugu Unicode. "
                "answer_key = అన్వయ క్రమం (prose order) + ప్రతిపదార్థాలు (word-by-word meanings). "
                "Source: కాళహస్తీశ్వర శతకం or జీవనభాషం (or other prescribed padya)."
            ),
        },
        {
            "section": "విభాగం డి",
            "stream": "TELUGU_LITERATURE",
            "qtype": "LONG_ANSWER",
            "marks": 8,
            "count": 1,
            "hint": (
                "Q18 (8m) ఉపవాచకం (రామాయణం): Generate ALL 4 questions in Telugu Unicode; "
                "student answers any 2 (×4m, ~100-120 words each). "
                "(i) వాలి-సుగ్రీవ విరోధం — causes and resolution, "
                "(ii) రామాయణం ఎందుకు చదవాలి — relevance and values, "
                "(iii) భరత పాదుక పట్టాభిషేకం — significance and devotion, "
                "(iv) రామ-రావణ యుద్ధం — key events and moral lessons. "
                "Answers require analytical/reflective response — not plot retelling."
            ),
        },
    ]


def _exact_class10_blueprint_entries(subject_norm: str) -> List[Dict[str, Any]]:
    if subject_norm == "mathematics":
        return _exact_class10_blueprint_entries_mathematics()
    if subject_norm == "english":
        return _exact_class10_blueprint_entries_english()
    if subject_norm == "hindi":
        return _exact_class10_blueprint_entries_hindi()
    if subject_norm == "telugu":
        return _exact_class10_blueprint_entries_telugu()
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
                    requires_figure=bool(entry.get("requires_figure")),
                    vi_required=bool(entry.get("vi_required")),
                    instruction_hint=str(entry.get("hint") or ""),
                    mode=str(entry.get("mode") or "CONTENT").upper(),
                )
            )

    total_marks = sum(slot.marks for slot in slots)
    if total_marks != 80:
        raise ValueError(f"Internal CBSE Class 10 blueprint error: expected 80 marks, got {total_marks}.")
    _expected_counts = {
        "mathematics": 38,
        "english": 11,
        "hindi": 16,
        "telugu": 18,
        "social science": 38,
        "science": 39,
    }
    expected_count = _expected_counts.get(subject_norm, 39)
    if len(slots) != expected_count:
        raise ValueError(f"Internal CBSE Class 10 blueprint error: expected {expected_count} questions, got {len(slots)}.")

    # ── Math-specific structural invariants ──────────────────────────────
    # Every real CBSE Class 10 Maths board paper places the 2 Assertion-Reason
    # questions at slots Q19 and Q20 of Section A (after 18 MCQs). Random
    # placement breaks teacher trust, so we hard-fail rather than emit a
    # paper that violates the official Sample Question Paper layout.
    if subject_norm == "mathematics":
        section_a_slots = [s for s in slots if str(s.section_title).startswith("Section A")]
        if len(section_a_slots) != 20:
            raise ValueError(
                f"Mathematics Section A must have exactly 20 questions, got {len(section_a_slots)}."
            )
        for idx, s in enumerate(section_a_slots[:18], start=1):
            if s.legacy_type != "MCQ":
                raise ValueError(
                    f"Mathematics Section A invariant: Q{idx} must be MCQ, got {s.legacy_type}."
                )
        for q_num, s in zip((19, 20), section_a_slots[18:20]):
            if s.legacy_type != "ASSERTION_REASON":
                raise ValueError(
                    f"Mathematics Section A invariant: Q{q_num} must be ASSERTION_REASON, got {s.legacy_type}."
                )

    # ── Mathematics-only picture/diagram cap (max 2) ─────────────────────
    # Math papers must contain at most 2 figure-bearing questions across
    # the whole paper; Social Science legitimately has more (History
    # image-MCQ + History map + Geography map + Civics cartoon), so the
    # cap is scoped to mathematics only.
    if subject_norm == "mathematics":
        picture_slots = [s for s in slots if s.requires_figure or s.requires_image]
        if len(picture_slots) > 2:
            raise ValueError(
                f"Mathematics picture-based cap exceeded: blueprint produced "
                f"{len(picture_slots)} figure/image slots; max 2."
            )
    return slots



def _is_explicit_section_breakdown(parsed_templates: List[dict]) -> bool:
    """
    A parsed template list is treated as an "explicit per-section breakdown"
    when EVERY entry names its own section (Section A / Part B / Sec C etc.).
    That signals the teacher deliberately authored a custom structure and
    wants it honoured even in `board` mode — the blueprint must NOT silently
    overwrite it.

    Loose instructions like "make it slightly harder" don't trip this; they
    parse to zero templates and the default blueprint stays in charge.
    """
    if not parsed_templates:
        return False
    if len(parsed_templates) < 2:
        return False
    return all(bool(t.get("section_title")) for t in parsed_templates)


def paper_plan_section_order(plan: List[QuestionGenerationSlot]) -> List[str]:
    """Ordered list of unique section titles as they appear in the plan.

    Section ordering is part of the user's intent (A → B → C). Concurrent
    LLM completion can produce sections in arbitrary insertion order; the
    streamer uses this list to re-sort `result["sections"]` before emitting
    `done`, so what the teacher typed is what they get.
    """
    seen: Set[str] = set()
    order: List[str] = []
    for slot in plan:
        title = slot.section_title
        if title and title not in seen:
            seen.add(title)
            order.append(title)
    return order


def _parse_instructions_for_slots(instructions: str):
    """
    Parse a teacher's free-text General Instructions into the structured slot
    list that `build_question_plan` consumes. Output schema per slot:
        {"section_title": Optional[str], "qtype": QuestionTypeCode,
         "marks": int, "count": int}
    Section names and clause order are preserved verbatim so the printed
    paper matches what the teacher typed (Section A → Section B → Section C).

    A clause is only accepted as a question spec when it carries an EXPLICIT
    cue:
      - a question-type keyword (mcq / short / long / case-study / VSA / SA / LA / AR), OR
      - an explicit `questions?` / `q[s]?` marker.
    Meta-clauses like "I have uploaded 2 pdfs" or "I want 3 sections" carry
    neither and are deliberately skipped — previously they were synthesised
    into bogus slots like "SECTION S" with type inferred from a stray digit.
    """
    from q_instructions.core.enums import QuestionTypeCode
    import re
    if not instructions:
        return []

    text = instructions.lower()

    # Define mapping of keywords to (QuestionTypeCode, marks)
    mappings = [
        (r'\bassertion[- ]?reason[s]?\b', (QuestionTypeCode.ASSERTION_REASON, 1)),
        (r'\bar\b', (QuestionTypeCode.ASSERTION_REASON, 1)),
        (r'\bmcq[s]?\b', (QuestionTypeCode.MCQ, 1)),
        (r'\bmultiple[- ]?choice[s]?\b', (QuestionTypeCode.MCQ, 1)),
        (r'\bvery[- ]?short[s]?\b', (QuestionTypeCode.SHORT_ANSWER, 2)),
        (r'\bvsa[s]?\b', (QuestionTypeCode.SHORT_ANSWER, 2)),
        (r'\bshort[- ]?answer[s]?\b', (QuestionTypeCode.SHORT_ANSWER, 3)),
        (r'\bsa[s]?\b', (QuestionTypeCode.SHORT_ANSWER, 3)),
        (r'\bshort[s]?\b', (QuestionTypeCode.SHORT_ANSWER, 3)),
        (r'\blong[- ]?answer[s]?\b', (QuestionTypeCode.LONG_ANSWER, 5)),
        (r'\bla[s]?\b', (QuestionTypeCode.LONG_ANSWER, 5)),
        (r'\blong[s]?\b', (QuestionTypeCode.LONG_ANSWER, 5)),
        (r'\bcase[- ]?based[s]?\b', (QuestionTypeCode.CASE_STUDY, 4)),
        (r'\bcase[- ]?study\b', (QuestionTypeCode.CASE_STUDY, 4)),
        (r'\bcase[- ]?studies\b', (QuestionTypeCode.CASE_STUDY, 4)),
        (r'\bcbq[s]?\b', (QuestionTypeCode.CASE_STUDY, 4)),
    ]

    number_words = {
        'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
        'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10
    }

    results = []

    # Split on newlines, commas, semicolons, "and", "with"
    clauses = re.split(r'[\r\n;,]|\band\b|\bwith\b', text)
    for clause in clauses:
        clause = clause.strip()
        if not clause:
            continue

        # Section header: "Section A", "Part B", "Sec C", "Section 1", etc.
        # `\b(section|part|sec)\b` requires a word boundary AFTER the keyword
        # so plurals like "sections" don't get truncated to ("section", "s").
        sec_match = re.search(
            r'\b(section|part|sec)\b\s*[-:]?\s*([a-zA-Z0-9]+)\b',
            clause,
            re.IGNORECASE,
        )
        section_title = None
        clause_for_nums = clause
        if sec_match:
            sec_type = sec_match.group(1).strip().capitalize()  # "Section" / "Part" / "Sec"
            if sec_type == "Sec":
                sec_type = "Section"
            sec_val = sec_match.group(2).strip().upper()
            section_title = f"{sec_type} {sec_val}"
            clause_for_nums = clause_for_nums.replace(sec_match.group(0), " ")

        # Number words → digits
        for word, val in number_words.items():
            clause_for_nums = re.sub(r'\b' + word + r'\b', str(val), clause_for_nums)

        count = None
        marks = None

        # 1. Count attached to a question-marker: "5 questions", "5 mcqs", "5 qs"
        count_match = re.search(
            r'\b(\d+)\s*(?:mcq|vsa|sa|la|cbq|ar|assertion)?\s*(?:questions?|q[s]?)\b',
            clause_for_nums,
            re.IGNORECASE,
        )
        if count_match:
            count = int(count_match.group(1))
            clause_for_nums = clause_for_nums.replace(count_match.group(0), " ")
        else:
            count_match_rev = re.search(
                r'\b(?:questions?|q[s]?)\s*[:\-]?\s*(\d+)\b',
                clause_for_nums,
                re.IGNORECASE,
            )
            if count_match_rev:
                count = int(count_match_rev.group(1))
                clause_for_nums = clause_for_nums.replace(count_match_rev.group(0), " ")

        # 2. Marks: "1 mark", "5 marks", "1m"
        marks_match = re.search(
            r'\b(\d+)\s*(?:marks?|m)\b',
            clause_for_nums,
            re.IGNORECASE,
        )
        if marks_match:
            marks = int(marks_match.group(1))
            clause_for_nums = clause_for_nums.replace(marks_match.group(0), " ")
        else:
            marks_match_alt = re.search(
                r'\b(?:carrying|of|each|marks?)\s*[:\-]?\s*(\d+)\b',
                clause_for_nums,
                re.IGNORECASE,
            )
            if marks_match_alt:
                marks = int(marks_match_alt.group(1))
                clause_for_nums = clause_for_nums.replace(marks_match_alt.group(0), " ")

        # 3. Question-type keyword (mcq/short/long/...)
        qtype = None
        for pattern, (qt, mk) in mappings:
            if re.search(pattern, clause, re.IGNORECASE):
                qtype = qt
                if marks is None:
                    marks = mk
                break

        # ── GUARD: require an explicit question cue ───────────────────────
        # Either an explicit question-type keyword (qtype is set) OR the word
        # "question(s)" / "q(s)" appears somewhere in the clause. Without
        # either, this clause is not a question spec — skip it. Drops
        # meta-clauses like "i want 3 sections" or "i have uploaded 2 pdfs"
        # that would otherwise synthesise a bogus slot from random digits.
        has_question_marker = bool(re.search(r'\b(questions?|q[s]?)\b', clause, re.IGNORECASE))
        if qtype is None and not has_question_marker:
            continue

        # 4. Remaining digits → count if still missing
        remaining_digits = [int(x) for x in re.findall(r'\b\d+\b', clause_for_nums)]
        if count is None and remaining_digits:
            count = remaining_digits[0]
            remaining_digits = remaining_digits[1:]

        # 5. Marks/qtype defaults
        if qtype is None:
            if marks is None:
                marks = remaining_digits[0] if remaining_digits else 1
            if marks == 1:
                qtype = QuestionTypeCode.MCQ
            elif marks in (2, 3):
                qtype = QuestionTypeCode.SHORT_ANSWER
            elif marks == 4:
                qtype = QuestionTypeCode.CASE_STUDY
            elif marks >= 5:
                qtype = QuestionTypeCode.LONG_ANSWER
            else:
                qtype = QuestionTypeCode.SHORT_ANSWER

        if count is not None and count > 0:
            results.append({
                "section_title": section_title,
                "qtype": qtype,
                "marks": marks,
                "count": count,
            })

    return results


def build_question_plan(
    topic: str,
    difficulty: str,
    count: int,
    class_num: int = 10,
    subject: str = "Science",
    instructions: str = "",
    count_variation: str = "exact",
) -> List[QuestionGenerationSlot]:
    """
    Materializes q_instructions into one LLM contract per question.

    This is intentionally deterministic. The LLM may write wording, but it does
    not decide counts, marks, sections, or subject-specific routing.
    """
    subject_norm = normalize_subject(subject)
    if subject_norm not in SUPPORTED_SUBJECTS:
        raise ValueError(f"Subject '{subject}' is not configured in q_instructions.")

    _label_map = {
        "social science": "Social Science",
        "mathematics": "Mathematics",
        "english": "English",
        "hindi": "Hindi",
        "telugu": "Telugu",
    }
    subject_label = _label_map.get(subject_norm, "Science")

    count_var_norm = str(count_variation).strip().lower().replace("_", " ")
    is_custom_mode = count_var_norm in ("custom", "custom count")

    # ── PaperPlan precedence (ISSUE 1) ────────────────────────────────────
    # Even in `board` mode (count_variation == "cbse"/"exact" with no count),
    # if the teacher wrote an explicit per-section breakdown in the free-text
    # General Instructions, that breakdown WINS over the fixed CBSE
    # blueprint. The blueprint is the default; explicit instructions are
    # never silently overwritten.
    parsed_templates_for_override: List[dict] = []
    if instructions:
        try:
            parsed_templates_for_override = _parse_instructions_for_slots(instructions)
        except Exception as exc:
            logger.warning("PaperPlan: parse failed for board-mode override: %s", exc)

    board_mode_override = (
        not is_custom_mode
        and parsed_templates_for_override
        and _is_explicit_section_breakdown(parsed_templates_for_override)
    )

    if class_num == 10 and (not count or count <= 0) and not is_custom_mode and not board_mode_override:
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

    if is_custom_mode or board_mode_override:
        from q_instructions.core.enums import QuestionTypeCode
        parsed_templates = parsed_templates_for_override or []
        if not parsed_templates and instructions:
            try:
                parsed_templates = _parse_instructions_for_slots(instructions)
            except Exception as e:
                logger.warning("Failed to parse custom instructions: %s", e)

        if parsed_templates:
            # Honour the teacher's per-section breakdown verbatim. If an
            # Exact Count is also set, log when the two disagree but
            # PREFER the explicit per-section breakdown (more specific
            # instruction wins). See PaperPlan precedence in AGENTS notes.
            planned_total = sum(int(t["count"]) for t in parsed_templates)
            if (
                is_custom_mode
                and count
                and count > 0
                and planned_total != count
            ):
                logger.info(
                    "PaperPlan: Exact Count (%s) differs from parsed section total (%s); "
                    "honouring the explicit per-section breakdown.",
                    count, planned_total,
                )

            for tpl in parsed_templates:
                qtype = tpl["qtype"]
                marks = tpl["marks"]
                num = tpl["count"]
                section_title = tpl["section_title"]
                if not section_title:
                    section_title = _section_title_for_question_type(subject_norm, class_num, qtype.name, marks)

                for _ in range(num):
                    slots.append(
                        _make_slot(
                            index=len(slots) + 1,
                            section_title=section_title,
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
        return slots[:len(slots)]


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
