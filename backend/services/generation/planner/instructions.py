"""Paper-level instruction text: blueprint prose, general instructions and the realized-paper header."""

import logging
from typing import List, Dict, Any, Optional

from services.generation.rules.syllabus_scope import (
    excluded_topics_prose_block,
    excluded_topics_compact_line,
    social_science_bloom_bias_block,
    social_science_bloom_bias_line,
    maths_cognitive_band_block,
    maths_cognitive_band_line,
)
from services.generation.planner.slots import QuestionGenerationSlot, summarize_question_plan
from services.generation.planner.subjects import normalize_subject

logger = logging.getLogger("[GEN_ROUTER]")


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

    # Off-syllabus exclusions (single source of truth: services.generation.rules.syllabus_scope).
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
            "The question paper contains THREE sections — Section A: Reading Skills; "
            "Section B: Grammar and Writing Skills; Section C: Literature Textbook.",
            "Attempt questions based on the specific instructions given for each part. "
            "Marks are indicated against each question.",
            "Section A (20 marks): Q1–Q2, two unseen passages of 10 marks each.",
            "Section B (20 marks): Q3, grammar — attempt any ten of twelve tasks (10 marks); "
            "Q4–Q5, writing tasks of 5 marks each with an internal choice.",
            "Section C (40 marks): Q6–Q7, extract-based questions (5 marks each); "
            "Q8, answer any four of five (12 marks); Q9, answer any two of three (6 marks); "
            "Q10–Q11, long answers of 6 marks each with an internal choice.",
            "All names and details in the Writing section are imaginary and created "
            "for assessment purposes.",
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
        # only. Single source of truth: services.generation.rules.syllabus_scope.
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
        "- Total: 11 questions, 80 marks, 3 hours, in THREE sections.",
        "- SECTION A — Reading Skills (20m): Q1 a discursive passage, Q2 a case-based "
        "passage, 10 marks each. Both passages are ORIGINAL and unseen. They are "
        "written by the Reading generator and MUST NOT come from any uploaded chapter.",
        "- SECTION B — Grammar and Writing Skills (20m): Q3 twelve one-mark grammar "
        "tasks of which any ten are attempted; Q4 a formal letter and Q5 an analytical "
        "paragraph, 5 marks each with an internal choice. Grammar and Writing are "
        "rule- and scenario-based and MUST NOT be built from any uploaded chapter.",
        "- SECTION C — Literature Textbook (40m): Q6 a prose extract, Q7 a poetry "
        "extract (5m each), Q8 answer any four of five (12m), Q9 answer any two of "
        "three (6m), Q10 and Q11 long answers with internal choice (6m each). This is "
        "the ONLY section drawn from the uploaded textbook.",
        "- Sections A and B carry 40 of the 80 marks and are produced by independent "
        "generators. A question in either section that references a prescribed story, "
        "poem, character or author is a structural defect.",
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
        # truth: services.generation.rules.syllabus_scope.
        rules.extend(excluded_topics_prose_block("science", class_num))

    return "\n".join(rules)
