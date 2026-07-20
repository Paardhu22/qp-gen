"""Parse free-form General Instructions into a structured blueprint.

General Instructions Mode lets a teacher describe a paper in prose — "Section
A: 5 MCQs, Section B: 3 short answers of 2 marks each" — instead of using the
CBSE blueprint. This turns that text into slots Model 2 can fill.

Deliberately regex-based rather than an LLM call. The grammar teachers
actually use is narrow and well covered, so a parser is free, instant and
deterministic where a model call would be none of those. If the parser returns
nothing the caller surfaces a "be more specific" error rather than guessing.

Moved here verbatim from the per-slot generation engine when that engine was
removed; the pool pipeline is now its only consumer.
"""

from __future__ import annotations

import re
from typing import List, Optional


def _parse_gim_instructions(instructions: str, pdf_count: int, exact_count: Optional[int] = None) -> List[dict]:
    """
    Parse teacher's general instructions text into a flat list of question slots.
    Returns a list of dicts:
        [{"section_title": Optional[str], "type": ..., "marks": ..., "count": ...}, ...]

    Issue 3 — `section_title` is preserved verbatim from the input ("Section A",
    "Part B", "Sec C", …) so the generator can honour an A/B/C-style breakdown
    instead of dumping everything into a single fall-back "Questions" section.
    Names and order are kept exactly as the teacher wrote them.
    """
    # (re is imported at module level)

    text_raw = instructions.strip()
    text = instructions.lower().strip()
    if not text:
        return []

    number_words = {
        'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
        'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
        'eleven': 11, 'twelve': 12, 'fifteen': 15, 'twenty': 20,
    }
    for word, val in number_words.items():
        text = re.sub(r'\b' + word + r'\b', str(val), text)

    type_map = {
        'mcq': 'MCQ', 'multiple choice': 'MCQ', 'multiple-choice': 'MCQ',
        'assertion reason': 'ASSERTION_REASON', 'assertion-reason': 'ASSERTION_REASON', 'ar': 'ASSERTION_REASON',
        'short answer': 'SHORT_ANSWER', 'short-answer': 'SHORT_ANSWER', 'short': 'SHORT_ANSWER',
        'vsa': 'SHORT_ANSWER', 'very short': 'SHORT_ANSWER', 'very-short': 'SHORT_ANSWER',
        'long answer': 'LONG_ANSWER', 'long-answer': 'LONG_ANSWER', 'long': 'LONG_ANSWER',
        'case study': 'CASE_STUDY', 'case-study': 'CASE_STUDY', 'case based': 'CASE_STUDY',
        'case-based': 'CASE_STUDY', 'cbq': 'CASE_STUDY',
    }

    default_marks = {
        'MCQ': 1, 'ASSERTION_REASON': 1, 'SHORT_ANSWER': 2,
        'LONG_ANSWER': 5, 'CASE_STUDY': 4,
    }

    slots = []

    # Check for "no mcq" / "no mcqs" patterns → exclusions
    no_types = set()
    for pattern_text, qtype in type_map.items():
        if re.search(r'\bno\s+' + re.escape(pattern_text) + r'[s]?\b', text):
            no_types.add(qtype)

    # Check for per-PDF distribution: "from each source/pdf N each" or "N from each"
    per_pdf_match = re.search(
        r'(?:from\s+each\s+(?:source|pdf|file|document)\s+(\d+))|'
        r'(?:(\d+)\s+(?:from\s+each|each|per)\s+(?:source|pdf|file|document))|'
        r'(?:(\d+)\s+each\s+questions?)|'
        r'(?:each\s+(?:source|pdf)\s+(\d+)\s+(?:each\s+)?questions?)',
        text
    )
    per_pdf_count = None
    if per_pdf_match:
        per_pdf_count = int(next(g for g in per_pdf_match.groups() if g is not None))

    # Parse explicit type+count clauses like "3 MCQs", "5 short answers of 2 marks"
    # Issue 3 — split on newlines/semicolons/commas/and AND propagate the
    # most-recently-seen "Section X" / "Part X" prefix to the slots that follow,
    # so the structure typed by the teacher is preserved verbatim in the output.
    clauses = re.split(r'[,;\n]+|\band\b', text)
    parsed_any = False
    current_section: Optional[str] = None

    for clause in clauses:
        clause = clause.strip()
        if not clause:
            continue
        # Skip exclusion clauses
        if re.match(r'\bno\s+', clause):
            continue

        # Section header at the start of the clause: "Section A: 5 short answers"
        sec_match = re.search(
            r'\b(section|part|sec)\b\s*[-:]?\s*([a-z0-9]+)\b',
            clause,
            re.IGNORECASE,
        )
        if sec_match:
            sec_type = sec_match.group(1).strip().capitalize()
            if sec_type == "Sec":
                sec_type = "Section"
            sec_val = sec_match.group(2).strip().upper()
            current_section = f"{sec_type} {sec_val}"
            clause = (clause[: sec_match.start()] + " " + clause[sec_match.end():]).strip()

        # Find count
        count_match = re.search(r'(\d+)', clause)
        if not count_match:
            continue
        count_val = int(count_match.group(1))

        # Find question type
        found_type = None
        for pattern_text, qtype in type_map.items():
            if re.search(r'\b' + re.escape(pattern_text) + r'[s]?\b', clause):
                found_type = qtype
                break

        if found_type is None:
            # Check if this looks like a marks spec ("2 marks") rather than a count
            if re.search(r'\bmarks?\b', clause):
                continue
            continue

        if found_type in no_types:
            continue

        # Find marks override
        marks_match = re.search(r'(\d+)\s*marks?', clause)
        marks_val = int(marks_match.group(1)) if marks_match else default_marks.get(found_type, 2)

        slots.append({
            "section_title": current_section,
            "type": found_type,
            "marks": marks_val,
            "count": count_val,
        })
        parsed_any = True

    # If per-PDF distribution is specified but no explicit types were parsed
    if per_pdf_count and not parsed_any:
        # Detect marks from instructions: "all 2 marks" / "2 marks each"
        all_marks_match = re.search(r'(?:all\s+)?(\d+)\s+marks?\s*(?:each)?', text)
        marks = int(all_marks_match.group(1)) if all_marks_match else 2

        # Determine type based on exclusions and marks
        qtype = 'SHORT_ANSWER'
        if 'SHORT_ANSWER' in no_types:
            qtype = 'LONG_ANSWER'
        if marks == 1 and 'MCQ' not in no_types:
            qtype = 'MCQ'
        elif marks >= 5:
            qtype = 'LONG_ANSWER'

        total = per_pdf_count * max(pdf_count, 1)
        slots.append({"section_title": None, "type": qtype, "marks": marks, "count": total})
        parsed_any = True

    # Fallback: if nothing was parsed, use exact_count with defaults
    if not parsed_any:
        total = exact_count or 10
        marks = 2
        all_marks_match = re.search(r'(?:all\s+)?(\d+)\s+marks?\s*(?:each)?', text)
        if all_marks_match:
            marks = int(all_marks_match.group(1))
        qtype = 'SHORT_ANSWER'
        if 'SHORT_ANSWER' in no_types:
            qtype = 'LONG_ANSWER' if 'LONG_ANSWER' not in no_types else 'MCQ'
        slots.append({"section_title": None, "type": qtype, "marks": marks, "count": total})

    # Touch the trailing argument-vs-warning so future code reviewers see
    # the unused-variable trail rather than guessing.
    _ = text_raw

    return slots
