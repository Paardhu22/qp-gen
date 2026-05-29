import base64
import json
import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Set

from apps.generation.models import GenerationHistory
from django.conf import settings
from django.core.files.storage import default_storage

from apps.question_generation.domain.context import (
    GenerationConstraints,
    GenerationContext,
    TokenBudget,
)
from apps.question_generation.domain.enums import AcademicClass, EducationBoard
from apps.question_generation.infrastructure.observability.metrics import GenerationMetrics
from apps.question_generation.infrastructure.providers.openai_provider import OpenAIProvider
from apps.question_generation.infrastructure.token_budget.budgeter import (
    allocate_budget,
    trim_chunks_to_budget,
)
from apps.question_generation.services.prompting.assembler import PromptAssembler, default_system_rules
from apps.question_generation.services.prompting.request_factory import LLMRequestFactory
from apps.question_generation.services.retrieval.context_service import (
    retrieve_relevant_chunks,
    retrieval_quality_summary,
)
from services.language_validation import validate_language_question

logger = logging.getLogger("[LEGACY_ENGINE]")


def _system_rules_for_slot(slot, constraints) -> str:
    """
    Mode-aware system rules. CONTENT keeps the original chunk-grounded rules so
    Science/Social/Maths/literature are byte-for-byte unchanged. GRAMMAR/COMPOSITION/
    PASSAGE must NOT be told to use retrieved chunks (there are none) — they are
    generated from rules or a fresh scenario.
    """
    mode = str(getattr(slot, "generation_mode", "CONTENT") or "CONTENT").upper()
    if mode == "CONTENT":
        return default_system_rules(constraints)

    base = [
        "You are a CBSE examiner generating ONE question for a language paper.",
        "Generate the QUESTION ONLY — never the student's answer except in the answer key field.",
        "Do NOT use, quote, or rely on any uploaded textbook content; this slot is not content-retrieval based.",
        "Obey the exact slot contract and JSON schema. Never add extra question objects or split an OR into another question.",
    ]
    if mode == "GRAMMAR":
        base.append("Grammar tasks are rule-based and self-contained, each in a fresh micro-context you invent.")
    elif mode == "PASSAGE":
        base.append("Generate an ORIGINAL, previously-unseen passage; never reproduce prescribed/uploaded text.")
    elif mode == "COMPOSITION":
        base.append("Provide a self-contained scenario/stimulus/topic with hints and an explicit word limit.")
    if constraints:
        base.append(f"Resolved paper count: {constraints.count} question objects.")
    return "\n".join(base)


def _sse_event(data: dict, event: str = "update") -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


class JsonObjectStreamExtractor:
    """
    Incrementally detects complete JSON objects without trying to parse partial
    token buffers. json.loads is called only after brace depth returns to zero.
    """

    def __init__(self) -> None:
        self._buffer: List[str] = []
        self._depth = 0
        self._in_string = False
        self._escape = False
        self._started = False

    def feed(self, text: str) -> List[dict]:
        completed: List[dict] = []

        for ch in text:
            if not self._started:
                if ch == "{":
                    self._started = True
                    self._depth = 1
                    self._buffer = [ch]
                continue

            self._buffer.append(ch)

            if self._escape:
                self._escape = False
                continue

            if ch == "\\" and self._in_string:
                self._escape = True
                continue

            if ch == '"':
                self._in_string = not self._in_string
                continue

            if self._in_string:
                continue

            if ch == "{":
                self._depth += 1
            elif ch == "}":
                self._depth -= 1
                if self._depth == 0:
                    raw = "".join(self._buffer)
                    completed.append(json.loads(raw))
                    self._buffer = []
                    self._started = False
                    self._in_string = False
                    self._escape = False

        return completed


def _empty_result() -> Dict[str, Any]:
    return {"generalInstructions": [], "sections": []}


def _find_or_create_section(result: Dict[str, List[dict]], title: str) -> dict:
    for section in result["sections"]:
        if section.get("title") == title:
            return section
    section = {"title": title, "questions": []}
    result["sections"].append(section)
    return section


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _allowed_image_urls(source_chunks: List[dict]) -> List[str]:
    urls: List[str] = []
    seen: Set[str] = set()
    for chunk in source_chunks:
        metadata = chunk.get("metadata") or {}
        url = chunk.get("image_url") or metadata.get("image_url")
        if url and url not in seen:
            urls.append(str(url))
            seen.add(str(url))
    return urls


def _is_model_readable_image_url(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://") or url.startswith("data:")


def _storage_image_data_url(metadata: dict) -> str:
    stored_path = metadata.get("image_storage_path")
    if not stored_path:
        return ""

    try:
        with default_storage.open(stored_path, "rb") as handle:
            payload = base64.b64encode(handle.read()).decode("ascii")
    except Exception as exc:
        logger.warning("[VISION] Could not read stored image %s: %s", stored_path, exc)
        return ""

    mime_type = metadata.get("mimeType") or "image/png"
    return f"data:{mime_type};base64,{payload}"


def _vision_image_payload_urls(source_chunks: List[dict]) -> List[str]:
    urls: List[str] = []
    seen: Set[str] = set()
    for chunk in source_chunks:
        metadata = chunk.get("metadata") or {}
        image_url = str(chunk.get("image_url") or metadata.get("image_url") or "").strip()
        vision_url = image_url if _is_model_readable_image_url(image_url) else _storage_image_data_url(metadata)
        if vision_url and vision_url not in seen:
            urls.append(vision_url)
            seen.add(vision_url)
    return urls


def _coerce_or_choice(raw_question: dict, allowed_urls: List[str]) -> Optional[dict]:
    raw_choice = (
        raw_question.get("or_choice")
        or raw_question.get("orChoice")
        or raw_question.get("alternative")
        or raw_question.get("internal_choice")
    )
    if raw_choice in (None, "", False):
        return None

    if isinstance(raw_choice, str):
        raw_choice = {"content": raw_choice}
    if not isinstance(raw_choice, dict):
        return None

    options_raw = raw_choice.get("options", [])
    options = [str(opt).strip() for opt in options_raw if str(opt).strip()] if isinstance(options_raw, list) else []
    candidate_url = str(raw_choice.get("image_url") or raw_choice.get("imageUrl") or "").strip()
    image_url = candidate_url if candidate_url in allowed_urls else ""
    content = _stringify(raw_choice.get("content")).strip()
    if not content:
        return None

    return {
        "content": content,
        "options": options,
        "answer": _stringify(raw_choice.get("answer")).strip(),
        "image_url": image_url,
    }


def _coerce_vi_alternative(raw_question: dict) -> Optional[str]:
    raw_vi = (
        raw_question.get("vi_alternative")
        or raw_question.get("viAlternative")
        or raw_question.get("visually_impaired_alternative")
        or raw_question.get("visual_alternative")
    )
    if raw_vi in (None, "", False):
        return None
    if isinstance(raw_vi, dict):
        raw_vi = raw_vi.get("content") or raw_vi.get("question") or raw_vi.get("text")
    content = _stringify(raw_vi).strip()
    return content or None


def _printable_question_content(content: str, or_choice: Optional[dict], vi_alternative: Optional[str], or_label: str = "OR") -> str:
    parts = [content.strip()]
    if or_choice:
        parts.extend([or_label, or_choice.get("content", "").strip()])
    if vi_alternative:
        parts.extend(
            [
                "- - - - - - - - - - - - - - - - - - -",
                "Note: The following question is for Visually Impaired Students only in lieu of the visual question above.",
                vi_alternative.strip(),
                "- - - - - - - - - - - - - - - - - - -",
            ]
        )
    return "\n\n".join(part for part in parts if part)


def _format_chunk_for_prompt(chunk: dict) -> str:
    metadata = chunk.get("metadata") or {}
    page = chunk.get("page")
    image_url = chunk.get("image_url") or metadata.get("image_url")
    header_parts = []
    if page:
        header_parts.append(f"page={page}")
    if metadata.get("semanticSection"):
        header_parts.append(f"section={metadata.get('semanticSection')}")
    if image_url:
        header_parts.append(f"image_url={image_url}")

    header = f"[Retrieved chunk {' | '.join(header_parts)}]" if header_parts else "[Retrieved chunk]"
    return f"{header}\n{chunk.get('content', '')}".strip()


def _extract_reuse_terms(question: dict) -> Set[str]:
    terms: Set[str] = set()
    metadata = question.get("metadata") or {}
    for key in ["inferredTopic", "inferredChapter"]:
        value = str(metadata.get(key) or "").strip().lower()
        if value:
            terms.add(value)
    content = str(question.get("content") or "")
    for number in re.findall(r"\b\d+(?:\.\d+)?\b", content):
        terms.add(f"value:{number}")
    return terms


def _coerce_question(raw_payload: dict, slot, source_chunks: List[dict], is_retry: bool = False, is_visual_mandatory: bool = False) -> dict:
    raw_question = raw_payload.get("question", raw_payload)
    if not isinstance(raw_question, dict):
        raise ValueError("LLM returned a non-object question payload.")

    content = _stringify(raw_question.get("content")).strip()
    if not content:
        raise ValueError("LLM returned an empty question.")

    options_raw = raw_question.get("options", [])
    options = [str(opt).strip() for opt in options_raw if str(opt).strip()] if isinstance(options_raw, list) else []
    if slot.question_type == "ASSERTION_REASON":
        options = [
            "Both A and R are true, and R is the correct explanation of A.",
            "Both A and R are true, and R is not the correct explanation of A.",
            "A is true but R is false.",
            "A is false but R is true.",
        ]
    allowed_urls = _allowed_image_urls(source_chunks)
    candidate_image_url = str(raw_question.get("image_url") or raw_question.get("imageUrl") or "").strip()
    image_url = candidate_image_url if candidate_image_url in allowed_urls else ""
    
    if (slot.requires_image or is_visual_mandatory) and not image_url and allowed_urls:
        if not is_retry:
            raise ValueError("LLM omitted the mandatory visual image_url.")
        image_url = allowed_urls[0]

    or_choice = _coerce_or_choice(raw_question, allowed_urls)
    if slot.choice_required and not or_choice:
        raise ValueError("LLM omitted the required nested OR choice.")

    vi_alternative = _coerce_vi_alternative(raw_question)
    if slot.vi_required and not vi_alternative:
        if is_retry:
            vi_alternative = "[Placeholder: The AI failed to generate a visually impaired alternative for this question.]"
        else:
            raise ValueError("LLM omitted the required Visually Impaired alternative.")

    first_chunk = source_chunks[0] if source_chunks else {}
    first_meta = first_chunk.get("metadata") or {}
    metadata_raw = raw_question.get("metadata", {})
    metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
    metadata = {
        **metadata,
        "gradeClass": metadata.get("gradeClass") or f"Class {slot.class_num}",
        "subject": metadata.get("subject") or slot.subject,
        "inferredTopic": metadata.get("inferredTopic") or slot.stream.replace("_", " ").title(),
        "inferredChapter": metadata.get("inferredChapter") or first_meta.get("chapter") or first_meta.get("semanticSection") or "",
        "sourcePdf": metadata.get("sourcePdf") or first_meta.get("sourcePdf") or "",
        "difficulty": metadata.get("difficulty") or slot.difficulty,
        "section": slot.section_title,
    }
    if image_url:
        metadata["image_url"] = image_url
    if vi_alternative:
        metadata["vi_alternative"] = True

    _subj = str(getattr(slot, "subject", "")).strip().lower()
    or_label = {"hindi": "अथवा", "telugu": "లేదా"}.get(_subj, "OR")
    printable_content = _printable_question_content(content, or_choice, vi_alternative, or_label=or_label)

    return {
        "content": printable_content,
        "type": slot.legacy_type,
        "options": options,
        "answer": _stringify(raw_question.get("answer")).strip(),
        "marks": slot.marks,
        "image_url": image_url,
        "or_choice": or_choice,
        "vi_alternative": vi_alternative,
        "metadata": metadata,
    }


def _single_question_schema(is_visual_mandatory: bool, slot) -> str:
    schema = (
        "{\n"
        '  "question": {\n'
        f'    "content": "String (Question text)",\n'
        f'    "type": "String ({slot.legacy_type})",\n'
    )
    if slot.legacy_type in ["MCQ", "ASSERTION_REASON"]:
        schema += '    "options": ["Option 1", "Option 2", "Option 3", "Option 4"],\n'
    
    schema += '    "answer": "String (Correct answer or scoring points)",\n'
    schema += f'    "marks": {slot.marks},\n'
    
    if is_visual_mandatory:
        schema += '    "image_url": "String (CRITICAL: MUST include the provided image URL)",\n'
    else:
        schema += '    "image_url": "String or omit entirely if no image is mandated",\n'
        
    if slot.choice_required:
        schema += '    "or_choice": { "content": "String", "options": ["(if MCQ)"], "answer": "String", "image_url": "String" },\n'
    else:
        schema += '    "or_choice": "CRITICAL: Omit this key entirely unless internal choice is mandated",\n'
        
    if slot.vi_required:
        schema += '    "vi_alternative": { "content": "String (Full text replacement question)" },\n'
    else:
        schema += '    "vi_alternative": "CRITICAL: Omit this key entirely unless visually impaired alternative is mandated",\n'
        
    schema += (
        '    "metadata": {\n'
        '      "gradeClass": "String",\n'
        '      "subject": "String",\n'
        '      "inferredTopic": "String",\n'
        '      "inferredChapter": "String",\n'
        '      "difficulty": "easy | medium | hard"\n'
        '    }\n'
        '  }\n'
        '}\n'
        'Rules: Do NOT use null. If a field is not required (like or_choice or vi_alternative), omit the key entirely from the JSON object.\n'
    )
    return schema


def _build_user_prompt(
    slot,
    total_slots: int,
    topic: str,
    image_urls: Optional[List[str]] = None,
    used_terms: Optional[Set[str]] = None,
    is_visual_mandatory: bool = False,
) -> str:
    topic_line = f"Topic/focus: {topic}." if topic else "Topic/focus: infer from the retrieved chunks."
    image_line = ""
    if image_urls:
        image_line = f"\nAvailable image_url values: {', '.join(image_urls)}."
    reuse_line = ""
    if used_terms:
        reuse_line = f"\nDo not reuse these concepts or exact values: {', '.join(sorted(used_terms)[:30])}."
        
    visual_override = ""
    if is_visual_mandatory:
        visual_override = "\nCRITICAL SYSTEM OVERRIDE: The context provided for this question contains a textbook diagram/image. You MUST formulate a pictorial question (e.g., 'Observe the given diagram...', 'Identify the parts labeled in the figure...'). You MUST include the provided image URL in the `image_url` key of your JSON output. Failure to output a visual question will result in system failure.\n"
        
    return (
        f"Question {slot.index} of {total_slots}.\n"
        f"{topic_line}\n\n"
        f"{slot.exact_instruction}{image_line}{reuse_line}{visual_override}\n\n"
        "Return only valid JSON matching the schema. Do not include markdown."
    )


def _parse_gim_instructions(instructions: str, pdf_count: int, exact_count: Optional[int] = None) -> List[dict]:
    """
    Parse teacher's general instructions text into a flat list of question slots.
    Returns a list of dicts: [{"type": ..., "marks": ..., "count": ...}, ...]
    """
    import re

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
    clauses = re.split(r'[,;\n]+|\band\b', text)
    parsed_any = False

    for clause in clauses:
        clause = clause.strip()
        if not clause:
            continue
        # Skip exclusion clauses
        if re.match(r'\bno\s+', clause):
            continue

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

        slots.append({"type": found_type, "marks": marks_val, "count": count_val})
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
        slots.append({"type": qtype, "marks": marks, "count": total})
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
        slots.append({"type": qtype, "marks": marks, "count": total})

    return slots


def _build_gim_system_prompt(instructions: str, source_chunks_text: str) -> str:
    """Build the minimal, direct system prompt for General Instructions Mode."""
    return (
        "You are a question paper generator. Generate questions STRICTLY "
        "from the provided source material below. Do not add any information "
        "not present in the source text.\n\n"
        "Follow the teacher's instructions EXACTLY as written. Do not add "
        "extra questions, extra sections, or extra structure beyond what "
        "the teacher asked for.\n\n"
        f"Teacher's instructions: {instructions}\n\n"
        "For each question, return valid JSON with these fields:\n"
        "  content: the question text\n"
        "  type: MCQ / SHORT_ANSWER / LONG_ANSWER / ASSERTION_REASON\n"
        "  marks: number of marks\n"
        "  options: list of 4 options if MCQ, empty list otherwise\n"
        "  answer: correct answer text\n"
        "  Do NOT include or_choice unless the teacher explicitly asked for internal choice.\n\n"
        "Rules:\n"
        "- Generate ONLY the question types the teacher specified\n"
        "- Use ONLY the marks values the teacher specified\n"
        "- Do NOT add section headers or labels unless teacher asked for them\n"
        "- Do NOT enforce any board exam pattern\n"
        "- Do NOT add questions beyond the count the teacher asked for\n"
        "- Every question must be answerable from the source material alone\n"
        "- Do NOT use null for any field. Omit optional keys entirely.\n\n"
        "SOURCE MATERIAL:\n"
        f"{source_chunks_text}\n"
    )


def stream_general_instructions_questions(
    user,
    pdf_source_ids: List[str],
    topic: str,
    count: int,
    difficulty: str,
    instructions: str = "",
    payload: Optional[dict] = None,
) -> Iterable[str]:
    """
    General Instructions Mode handler.
    The teacher's instructions text IS the complete specification.
    No q_instructions, no blueprint, no CBSE structure.
    """
    import concurrent.futures

    from apps.question_generation.infrastructure.providers.openai_provider import OpenAIProvider
    from apps.question_generation.infrastructure.token_budget.budgeter import (
        allocate_budget,
        trim_chunks_to_budget,
    )
    from apps.question_generation.services.retrieval.context_service import (
        retrieve_relevant_chunks,
        retrieval_quality_summary,
    )

    logger.info("[GIM] Entered stream_general_instructions_questions")

    payload = payload or {}

    # Step 1: Validate instructions
    if not instructions or not instructions.strip():
        yield _sse_event(
            {"error": "General Instructions Mode requires you to describe what questions you want. "
                      "Please write your instructions in the text box."},
            event="error",
        )
        return

    # Extract basic metadata for context/labeling
    class_raw = payload.get("class", payload.get("class_level", payload.get("gradeClass", "10")))
    class_str = str(class_raw or "").strip()
    class_digits = "".join(filter(str.isdigit, class_str))
    class_num = int(class_digits) if class_digits else 10
    subject_raw = str(payload.get("subject", "")).strip() or "General"

    # Step 2: Parse instructions into a flat slot list
    exact_count = count if count and count > 0 else None
    parsed_slots = _parse_gim_instructions(instructions, len(pdf_source_ids), exact_count)

    if not parsed_slots:
        yield _sse_event(
            {"error": "Could not parse any question specifications from your instructions. "
                      "Please be more specific (e.g., '5 MCQs, 3 short answers of 2 marks each')."},
            event="error",
        )
        return

    # Expand parsed slots into a flat list of individual question entries
    flat_plan: List[dict] = []
    for slot_spec in parsed_slots:
        for _ in range(slot_spec["count"]):
            flat_plan.append({
                "type": slot_spec["type"],
                "marks": slot_spec["marks"],
                "index": len(flat_plan) + 1,
            })

    total_questions = len(flat_plan)
    total_marks = sum(s["marks"] for s in flat_plan)

    logger.info("[GIM] Parsed plan: %d questions, %d total marks", total_questions, total_marks)

    # Step 3: Build general instructions for the paper header
    general_instructions_lines = [
        f"There are {total_questions} questions. All questions are compulsory.",
        instructions.strip(),
    ]

    # Step 4: Emit plan event
    yield _sse_event(
        {
            "total": total_questions,
            "subject": subject_raw,
            "class": class_num,
            "blueprint": f"General Instructions Mode: {total_questions} questions, {total_marks} marks",
            "summary": {
                "total_questions": total_questions,
                "total_marks": total_marks,
                "or_choices": 0,
                "image_questions": 0,
                "vi_alternatives": 0,
                "exact_counts": [f"{s['count']} {s['type'].replace('_', ' ').title()} ({s['marks']}m)" for s in parsed_slots],
                "section_marks": {"Questions": total_marks},
                "section_questions": {"Questions": total_questions},
            },
            "generalInstructions": general_instructions_lines,
        },
        event="plan",
    )

    # Step 5: Retrieval — same shared system as Board Mode
    max_input_tokens, max_output_tokens = allocate_budget(
        total_max_tokens=5000, reserved_system_tokens=350, max_output_tokens=750,
    )
    provider = OpenAIProvider()
    result = _empty_result()
    result["generalInstructions"] = general_instructions_lines

    used_chunk_ids: Set[str] = set()
    _topic_cache: Dict[str, List[dict]] = {}

    # Phase 1: Allocate chunks for each slot
    allocated_slots: List[dict] = []

    for slot_entry in flat_plan:
        # Build retrieval query from instructions + type
        query_parts = [
            topic.strip() if topic else "",
            subject_raw,
            f"class {class_num}",
            slot_entry["type"].replace("_", " "),
            f"{slot_entry['marks']} mark",
            instructions[:200].strip(),
        ]
        retrieval_query = " ".join(part for part in query_parts if part)

        cache_key = retrieval_query
        if cache_key not in _topic_cache:
            _topic_cache[cache_key] = retrieve_relevant_chunks(
                retrieval_query,
                pdf_source_ids,
                limit=50,
                user=user,
                require_image=False,
                exclude_chunk_ids=None,
            )

        top_50 = _topic_cache[cache_key]
        valid_chunks = [c for c in top_50 if str(c.get("id")) not in used_chunk_ids]
        context = valid_chunks[:4]

        for item in context:
            if item.get("id"):
                used_chunk_ids.add(str(item["id"]))

        allocated_slots.append({
            "slot_entry": slot_entry,
            "context": context,
            "retrieval_query": retrieval_query,
        })

    # Phase 2: Generate questions in parallel
    def _generate_gim_slot(allocated: dict) -> tuple:
        slot_entry = allocated["slot_entry"]
        context = allocated["context"]
        idx = slot_entry["index"]

        if not context:
            return (
                [_sse_event(
                    {"error": f"No relevant content found for question {idx}.", "index": idx},
                    event="warning",
                )],
                None,
            )

        # Build source material text
        raw_chunks = [_format_chunk_for_prompt(item) for item in context]
        budget_result = trim_chunks_to_budget(raw_chunks, max_input_tokens)
        source_text = "\n\n".join(budget_result.selected_chunks)

        # Build the minimal system prompt
        system_prompt = _build_gim_system_prompt(instructions, source_text)

        # Build user prompt for this specific question
        user_prompt = (
            f"Generate question {idx} of {total_questions}.\n"
            f"Question type: {slot_entry['type']}\n"
            f"Marks: {slot_entry['marks']}\n\n"
            "Return ONLY valid JSON matching this schema:\n"
            "{\n"
            '  "question": {\n'
            f'    "content": "String (Question text)",\n'
            f'    "type": "{slot_entry["type"]}",\n'
        )
        if slot_entry["type"] in ["MCQ", "ASSERTION_REASON"]:
            user_prompt += '    "options": ["Option 1", "Option 2", "Option 3", "Option 4"],\n'
        user_prompt += (
            '    "answer": "String (Correct answer)",\n'
            f'    "marks": {slot_entry["marks"]}\n'
            '  }\n'
            '}\n'
            "Do not include markdown. Return only the JSON object."
        )

        # Call LLM
        events = []
        question = None

        for attempt in range(2):
            extractor = JsonObjectStreamExtractor()
            buffer = ""
            parsed_payload = None

            try:
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
                llm_request = {
                    "model": settings.OPENAI_MODEL,
                    "messages": messages,
                    "max_tokens": max_output_tokens,
                    "temperature": 0.7,
                    "stream": True,
                }

                for delta in provider.stream_chat(llm_request):
                    if not delta:
                        continue
                    buffer += delta
                    for parsed in extractor.feed(delta):
                        parsed_payload = parsed
            except Exception as exc:
                if attempt == 0:
                    logger.warning("[GIM] Streaming failed for slot %s attempt 1: %s. Retrying...", idx, exc)
                    continue
                logger.error("[GIM] Streaming failed for slot %s: %s", idx, exc, exc_info=True)
                events.append(_sse_event({"error": str(exc), "index": idx}, event="warning"))
                break

            if parsed_payload is None and buffer.strip():
                try:
                    parsed_payload = json.loads(buffer)
                except json.JSONDecodeError:
                    if attempt == 0:
                        continue
                    events.append(_sse_event({"error": f"Invalid JSON for question {idx}", "index": idx}, event="warning"))
                    break

            if parsed_payload is None:
                if attempt == 0:
                    continue
                events.append(_sse_event({"error": f"No content returned for question {idx}", "index": idx}, event="warning"))
                break

            try:
                raw_q = parsed_payload.get("question", parsed_payload)
                if not isinstance(raw_q, dict):
                    raise ValueError("LLM returned non-object")

                content = _stringify(raw_q.get("content")).strip()
                if not content:
                    raise ValueError("Empty question content")

                options_raw = raw_q.get("options", [])
                options = [str(opt).strip() for opt in options_raw if str(opt).strip()] if isinstance(options_raw, list) else []

                if slot_entry["type"] == "ASSERTION_REASON":
                    options = [
                        "Both A and R are true, and R is the correct explanation of A.",
                        "Both A and R are true, and R is not the correct explanation of A.",
                        "A is true but R is false.",
                        "A is false but R is true.",
                    ]

                # Map type to legacy display type
                legacy_type_map = {
                    "MCQ": "MCQ", "ASSERTION_REASON": "ASSERTION_REASON",
                    "SHORT_ANSWER": "SHORT", "LONG_ANSWER": "LONG",
                    "CASE_STUDY": "CASE_STUDY",
                }
                display_type = legacy_type_map.get(slot_entry["type"], "SHORT")

                first_chunk = context[0] if context else {}
                first_meta = first_chunk.get("metadata") or {}

                question = {
                    "content": content,
                    "type": display_type,
                    "options": options,
                    "answer": _stringify(raw_q.get("answer")).strip(),
                    "marks": slot_entry["marks"],
                    "image_url": "",
                    "or_choice": None,
                    "vi_alternative": None,
                    "metadata": {
                        "gradeClass": f"Class {class_num}",
                        "subject": subject_raw,
                        "inferredTopic": first_meta.get("chapter") or first_meta.get("semanticSection") or "",
                        "inferredChapter": first_meta.get("chapter") or first_meta.get("semanticSection") or "",
                        "sourcePdf": first_meta.get("sourcePdf") or "",
                        "difficulty": difficulty,
                        "section": "Questions",
                    },
                }
                break
            except Exception as exc:
                if attempt == 0:
                    logger.warning("[GIM] Normalization failed for slot %s attempt 1: %s", idx, exc)
                    continue
                logger.error("[GIM] Normalization failed for slot %s: %s", idx, exc, exc_info=True)
                events.append(_sse_event({"error": str(exc), "index": idx}, event="warning"))
                break

        if question:
            events.append(_sse_event({
                "index": idx,
                "total": total_questions,
                "section": "Questions",
                "question": question,
            }, event="question"))

        return events, question

    # Execute generation in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_slot = {executor.submit(_generate_gim_slot, a): a for a in allocated_slots}
        for future in concurrent.futures.as_completed(future_to_slot):
            try:
                events, question = future.result()
                for event in events:
                    yield event

                if question:
                    section = _find_or_create_section(result, "Questions")
                    section["questions"].append(question)
                    yield _sse_event(result, event="update")
            except Exception as exc:
                logger.error("[GIM] Future failed: %s", exc)

    total_generated = sum(len(s.get("questions", [])) for s in result["sections"])
    if total_generated == 0:
        yield _sse_event({"error": "Generation failed before any questions could be produced."}, event="error")
        return

    # Persist history
    try:
        GenerationHistory.objects.create(
            prompt=json.dumps({"mode": "general_instructions", "instructions": instructions}, ensure_ascii=False),
            settings={
                "topic": topic, "count": count, "resolvedCount": total_questions,
                "qp_type": "general_instructions",
                "difficulty": difficulty, "pdfSourceIds": pdf_source_ids,
                "instructions": instructions, "subject": subject_raw, "class": class_num,
            },
            result=result, user=user,
        )
    except Exception as exc:
        logger.warning("[GIM_HISTORY] Could not persist generation history: %s", exc)

    yield _sse_event({"done": True, "result": result}, event="done")


def stream_generated_questions(
    user,
    pdf_source_ids: List[str],
    topic: str,
    count: int,
    difficulty: str,
    instructions: str = "",
    payload: Optional[dict] = None,
) -> Iterable[str]:
    import concurrent.futures
    from services.generation_router import (
        build_slot_blueprint_instructions,
        build_blueprint_instructions,
        build_general_instructions,
        build_question_plan,
        extract_class_number,
        normalize_subject,
        summarize_question_plan,
        should_use_new_engine,
    )

    logger.info(f"[STREAM_SERVICE] Entered stream_generated_questions for topic '{topic}'")

    payload = payload or {}

    # ── HARD BRANCH: Route based on qp_type ──────────────────────────
    qp_type = str(
        payload.get("qp_type")
        or payload.get("qpType")
        or payload.get("qp_type", "")
    ).strip().lower()

    if qp_type == "general_instructions":
        logger.info("[STREAM_SERVICE] QP Type = general_instructions → routing to GIM handler")
        yield from stream_general_instructions_questions(
            user=user,
            pdf_source_ids=pdf_source_ids,
            topic=topic,
            count=count,
            difficulty=difficulty,
            instructions=instructions,
            payload=payload,
        )
        return
    # ── END BRANCH — Board Mode continues below unchanged ─────────────

    logger.info("[STREAM_SERVICE] Building q_instructions plan before retrieval/LLM...")

    if not should_use_new_engine(payload):
        yield _sse_event({"error": "This CBSE subject/class is not configured in q_instructions. Supported: Science & Social Science (Classes 1-10); Mathematics, English, Hindi, Telugu (Class 10)."}, event="error")
        return

    class_raw = payload.get("class", payload.get("class_level", payload.get("gradeClass", "10")))
    class_num = extract_class_number(class_raw, default=10)
    subject_raw = str(payload.get("subject", "Science")).strip() or "Science"
    subject_norm = normalize_subject(subject_raw)
    subject_label = "Social Science" if subject_norm == "social science" else "Science"
    count_variation = str(payload.get("count_variation") or payload.get("countVariation") or payload.get("countType") or "").strip().lower()
    resolved_count = -1 if count_variation in {"cbse exact pattern", "cbse", "exact"} else count

    try:
        plan = build_question_plan(
            topic=topic, difficulty=difficulty, count=resolved_count, class_num=class_num, subject=subject_raw, instructions=instructions, count_variation=count_variation,
        )
        # We still generate the master blueprint for history logging
        master_blueprint = build_blueprint_instructions(
            topic=topic, difficulty=difficulty, count=resolved_count, class_num=class_num, subject=subject_raw, plan=plan,
        )
    except Exception as exc:
        logger.error("[AOS] Failed to compile q_instructions plan: %s", exc, exc_info=True)
        yield _sse_event({"error": str(exc)}, event="error")
        return

    if not plan:
        yield _sse_event({"error": "No question plan could be compiled."}, event="error")
        return

    constraints = GenerationConstraints(count=len(plan), difficulty=difficulty)
    board = EducationBoard.CBSE
    academic_class = AcademicClass.CLASS_10
    board_raw = str(payload.get("board", "CBSE")).strip().upper()
    if board_raw in EducationBoard.__members__:
        board = EducationBoard[board_raw]
    class_name = f"CLASS_{class_num}"
    if class_name in AcademicClass.__members__:
        academic_class = AcademicClass[class_name]

    max_input_tokens, max_output_tokens = allocate_budget(
        total_max_tokens=5000, reserved_system_tokens=350, max_output_tokens=750,
    )
    assembler = PromptAssembler(version_id="v1")
    request_factory = LLMRequestFactory()
    provider = OpenAIProvider()
    result = _empty_result()
    general_instructions = build_general_instructions(plan, subject_raw, class_num, instructions=instructions)
    result["generalInstructions"] = general_instructions

    # Phase 1: The Allocation Loop (Sequential & Instantaneous)
    allocated_slots = []
    used_chunk_ids = set()
    _topic_cache = {}

    for slot in plan:
        slot_mode = str(getattr(slot, "generation_mode", "CONTENT") or "CONTENT").upper()
        # RAG only for CONTENT slots. GRAMMAR/COMPOSITION/PASSAGE are rule-/scenario-based and
        # must never receive educator-uploaded chunks (empty retrieval_query → no retrieval call).
        if slot_mode != "CONTENT" or not slot.retrieval_query:
            allocated_slots.append({"slot": slot, "context": [], "is_visual_mandatory": False})
            continue

        cache_key = (slot.retrieval_query, slot.requires_image)
        if cache_key not in _topic_cache:
            _topic_cache[cache_key] = retrieve_relevant_chunks(
                slot.retrieval_query,
                pdf_source_ids,
                limit=50,
                user=user,
                require_image=slot.requires_image,
                exclude_chunk_ids=None,
            )

        top_50 = _topic_cache[cache_key]
        valid_chunks = [c for c in top_50 if str(c.get("id")) not in used_chunk_ids]
        context = valid_chunks[:4]
        
        for item in context:
            if item.get("id"):
                used_chunk_ids.add(str(item["id"]))
                
        is_visual_mandatory = False
        if slot.requires_image:
            is_visual_mandatory = True
        else:
            for c in context:
                if c.get("metadata", {}).get("image_url") or c.get("image_url"):
                    is_visual_mandatory = True
                    break
                    
        allocated_slots.append({
            "slot": slot,
            "context": context,
            "is_visual_mandatory": is_visual_mandatory
        })

    yield _sse_event(
        {
            "total": len(plan),
            "subject": subject_label,
            "class": class_num,
            "blueprint": master_blueprint,
            "summary": summarize_question_plan(plan),
            "generalInstructions": general_instructions,
        },
        event="plan",
    )

    prompt_audit = []
    total_estimated_input_tokens = 0
    truncation_events = 0
    provider_failures = 0

    def _generate_slot(allocated):
        slot = allocated["slot"]
        context = allocated["context"]
        is_visual_mandatory = allocated["is_visual_mandatory"]
        
        slot_mode = str(getattr(slot, "generation_mode", "CONTENT") or "CONTENT").upper()

        # CONTENT slots genuinely need textbook chunks; GRAMMAR/COMPOSITION/PASSAGE do not.
        if slot_mode == "CONTENT" and not context:
            return (
                [_sse_event({"error": f"No relevant textbook chunks found for {slot.section_title} question {slot.index}.", "index": slot.index}, event="warning")],
                None, None, None
            )

        if context:
            retrieval_metrics = retrieval_quality_summary(context)
            logger.info("[RAG] slot=%s metrics=%s", slot.index, retrieval_metrics)

        image_urls = _allowed_image_urls(context) if slot.requires_image or is_visual_mandatory else []
        vision_image_urls = _vision_image_payload_urls(context) if slot.requires_image or is_visual_mandatory else []
        raw_chunks = [_format_chunk_for_prompt(item) for item in context]
        budget_result = trim_chunks_to_budget(raw_chunks, max_input_tokens)

        gen_context = GenerationContext(
            subject=subject_label,
            board=board,
            academic_class=academic_class,
            difficulty=difficulty,
            retrieved_chunks=budget_result.selected_chunks,
            token_budget=TokenBudget(
                model=settings.OPENAI_MODEL,
                max_input_tokens=max_input_tokens,
                max_output_tokens=max_output_tokens,
                reserved_system_tokens=350,
            ),
            generation_constraints=constraints,
            prompt_version="v1",
        )
        
        # Directive 5: Truncated prompt
        slot_blueprint = build_slot_blueprint_instructions(slot, difficulty, class_num, subject_raw)
        
        prompt_document = assembler.assemble(
            context=gen_context,
            system_rules=_system_rules_for_slot(slot, constraints),
            output_schema=_single_question_schema(is_visual_mandatory, slot),
            blueprint_instructions=slot_blueprint,
            extra_instructions=instructions if instructions else None,
        )
        
        audit_info = {
            "index": slot.index,
            "section": slot.section_title,
            "type": slot.legacy_type,
            "marks": slot.marks,
            "query": slot.retrieval_query,
            "chunks": len(context),
            "orChoice": slot.choice_required,
            "imageUrls": len(image_urls),
            "visionImages": len(vision_image_urls),
        }

        # used_terms is dropped for parallel generation since slots are mutually exclusive via chunks
        prompt = _build_user_prompt(
            slot,
            len(plan),
            topic,
            image_urls=image_urls,
            used_terms=set(), 
            is_visual_mandatory=is_visual_mandatory,
        )
        llm_request = request_factory.build(
            prompt_document, prompt, model=settings.OPENAI_MODEL, image_urls=vision_image_urls,
        )
        
        question = None
        events = []
        failures = 0

        # Language (non-CONTENT) slots get an extra attempt so a hard validation/script
        # failure can be regenerated rather than silently streamed to the editor.
        max_attempts = 3 if slot_mode != "CONTENT" else 2

        for attempt in range(max_attempts):
            is_last = attempt >= max_attempts - 1
            extractor = JsonObjectStreamExtractor()
            buffer = ""
            parsed_payload = None

            try:
                for delta in provider.stream_chat(llm_request):
                    if not delta:
                        continue
                    buffer += delta
                    for parsed in extractor.feed(delta):
                        parsed_payload = parsed
            except Exception as exc:
                if not is_last:
                    logger.warning("[LLM] Streaming failed for slot %s (attempt %s): %s. Retrying...", slot.index, attempt + 1, exc)
                    continue
                failures += 1
                logger.error("[LLM] Streaming failed for slot %s: %s", slot.index, exc, exc_info=True)
                events.append(_sse_event({"error": str(exc), "index": slot.index}, event="warning"))
                break

            if parsed_payload is None and buffer.strip():
                try:
                    parsed_payload = json.loads(buffer)
                except json.JSONDecodeError as exc:
                    if not is_last:
                        logger.warning("[LLM] Invalid JSON for slot %s (attempt %s): %s. Retrying...", slot.index, attempt + 1, exc)
                        continue
                    failures += 1
                    logger.error("[LLM] Invalid JSON for slot %s: %s", slot.index, exc)
                    events.append(_sse_event({"error": f"Invalid JSON for question {slot.index}", "index": slot.index}, event="warning"))
                    break

            if parsed_payload is None:
                if not is_last:
                    logger.warning("[LLM] No question content returned for slot %s (attempt %s). Retrying...", slot.index, attempt + 1)
                    continue
                failures += 1
                events.append(_sse_event({"error": f"No question content returned for question {slot.index}", "index": slot.index}, event="warning"))
                break

            try:
                candidate = _coerce_question(parsed_payload, slot, context, is_retry=(attempt > 0), is_visual_mandatory=is_visual_mandatory)
            except Exception as exc:
                if not is_last:
                    logger.warning("[LLM] Could not normalize slot %s (attempt %s): %s. Retrying...", slot.index, attempt + 1, exc)
                    continue
                failures += 1
                logger.error("[LLM] Could not normalize slot %s: %s", slot.index, exc, exc_info=True)
                events.append(_sse_event({"error": str(exc), "index": slot.index}, event="warning"))
                break

            # Hard language gate (no-op for CONTENT slots). Never stream a malformed
            # grammar/composition/passage question — regenerate, then surface a clear error.
            is_valid, reason = validate_language_question(slot, candidate)
            if not is_valid:
                if not is_last:
                    logger.warning("[VALIDATION] slot %s rejected (%s). Regenerating...", slot.index, reason)
                    continue
                failures += 1
                logger.error("[VALIDATION] slot %s failed after %s attempts: %s", slot.index, max_attempts, reason)
                events.append(_sse_event({"error": f"Question {slot.index} failed validation: {reason}", "index": slot.index}, event="warning"))
                break

            question = candidate
            break

        if question:
            events.append(_sse_event({
                "index": slot.index,
                "total": len(plan),
                "section": slot.section_title,
                "question": question,
            }, event="question"))
            
        return events, audit_info, question, (failures, budget_result.estimated_tokens, budget_result.truncation_events)

    # Phase 2: The Generation Loop (Parallel)
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_slot = {executor.submit(_generate_slot, a): a for a in allocated_slots}
        for future in concurrent.futures.as_completed(future_to_slot):
            try:
                events, audit_info, question, metrics_tuple = future.result()
                for event in events:
                    yield event
                
                if audit_info:
                    prompt_audit.append(audit_info)
                if question:
                    slot = future_to_slot[future]["slot"]
                    section = _find_or_create_section(result, slot.section_title)
                    section["questions"].append(question)
                    yield _sse_event(result, event="update")
                    
                if metrics_tuple:
                    provider_failures += metrics_tuple[0]
                    total_estimated_input_tokens += metrics_tuple[1]
                    truncation_events += metrics_tuple[2]
            except Exception as exc:
                logger.error("Future failed: %s", exc)

    metrics = GenerationMetrics(
        prompt_version="v1",
        model=settings.OPENAI_MODEL,
        chunk_count=sum(item["chunks"] for item in prompt_audit),
        estimated_input_tokens=total_estimated_input_tokens,
        estimated_output_tokens=max_output_tokens * len(plan),
        truncation_events=truncation_events,
        provider_failures=provider_failures,
    )
    logger.info(f"[PROMPT_METRICS] {metrics.to_dict()}")

    total_questions = sum(len(section.get("questions", [])) for section in result["sections"])
    if total_questions == 0:
        yield _sse_event({"error": "Generation failed before any questions could be produced."}, event="error")
        return

    if total_questions < len(plan):
        limited_note = (
            "Questions generated from available source material only. "
            "Additional chapters are needed for complete CBSE coverage."
        )
        if limited_note not in result.get("generalInstructions", []):
            result.setdefault("generalInstructions", []).append(limited_note)

    try:
        GenerationHistory.objects.create(
            prompt=json.dumps({"blueprint": master_blueprint, "plan": prompt_audit}, ensure_ascii=False),
            settings={
                "topic": topic, "count": count, "resolvedCountInput": resolved_count, "resolvedCount": len(plan),
                "countVariation": count_variation or ("cbse" if count <= 0 else "custom"),
                "difficulty": difficulty, "pdfSourceIds": pdf_source_ids, "instructions": instructions,
                "subject": subject_label, "class": class_num,
            },
            result=result, user=user,
        )
    except Exception as exc:
        logger.warning("[HISTORY] Could not persist generation history: %s", exc)

    yield _sse_event({"done": True, "result": result}, event="done")
