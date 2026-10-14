"""Turns a request into an ordered list of question slots: `build_question_plan` is the entry point."""

import logging
from typing import List, Dict, Optional, Set

from services.generation.planner.class10 import _build_exact_cbse_class10_plan
from services.generation.planner.factory import _make_slot
from services.generation.planner.slots import QuestionGenerationSlot, _section_title_for_question_type, _section_title_for_stream
from services.generation.planner.subjects import SUPPORTED_SUBJECTS, default_cbse_question_count, normalize_subject

logger = logging.getLogger("[GEN_ROUTER]")


def _build_primary_progression(total_questions: int, class_num: int, subject_norm: str):
    from services.generation.blueprint.core.enums import QuestionTypeCode

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
    from services.generation.blueprint.core.enums import QuestionTypeCode
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
    Materializes services.generation.blueprint into one LLM contract per question.

    This is intentionally deterministic. The LLM may write wording, but it does
    not decide counts, marks, sections, or subject-specific routing.
    """
    subject_norm = normalize_subject(subject)
    if subject_norm not in SUPPORTED_SUBJECTS:
        raise ValueError(f"Subject '{subject}' is not configured in services.generation.blueprint.")

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
        from services.generation.blueprint.core.enums import QuestionTypeCode
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
        from services.generation.blueprint.core.enums import StreamType
        from services.generation.blueprint.subjects.science.orchestrator import ScienceOrchestratorV2

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
        from services.generation.blueprint.core.enums import StreamType
        from services.generation.blueprint.subjects.social_science.orchestrator import SocialScienceOrchestratorV2

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
