import json
import logging
from typing import Any, Dict, Iterable, List, Optional

from apps.generation.models import GenerationHistory
from django.conf import settings

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

logger = logging.getLogger("[LEGACY_ENGINE]")


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


def _empty_result() -> Dict[str, List[dict]]:
    return {"sections": []}


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


def _coerce_question(raw_payload: dict, slot, source_chunks: List[dict]) -> dict:
    raw_question = raw_payload.get("question", raw_payload)
    if not isinstance(raw_question, dict):
        raise ValueError("LLM returned a non-object question payload.")

    content = _stringify(raw_question.get("content")).strip()
    if not content:
        raise ValueError("LLM returned an empty question.")

    options_raw = raw_question.get("options", [])
    options = [str(opt).strip() for opt in options_raw if str(opt).strip()] if isinstance(options_raw, list) else []

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

    return {
        "content": content,
        "type": slot.legacy_type,
        "options": options,
        "answer": _stringify(raw_question.get("answer")).strip(),
        "marks": slot.marks,
        "metadata": metadata,
    }


def _single_question_schema() -> str:
    return (
        "{\n"
        '  "question": {\n'
        '    "content": "Question text",\n'
        '    "type": "MCQ | ASSERTION_REASON | SHORT | LONG | CASE_STUDY | DIAGRAM",\n'
        '    "options": ["Option 1", "Option 2", "Option 3", "Option 4"],\n'
        '    "answer": "Correct answer or scoring points",\n'
        '    "marks": 3,\n'
        '    "metadata": {\n'
        '      "gradeClass": "Class 10",\n'
        '      "subject": "Science",\n'
        '      "inferredTopic": "Biology",\n'
        '      "inferredChapter": "Chapter/heading from context",\n'
        '      "sourcePdf": "source file or blank",\n'
        '      "difficulty": "easy | medium | hard"\n'
        "    }\n"
        "  }\n"
        "}\n"
    )


def _build_user_prompt(slot, total_slots: int, topic: str) -> str:
    topic_line = f"Topic/focus: {topic}." if topic else "Topic/focus: infer from the retrieved chunks."
    return (
        f"Question {slot.index} of {total_slots}.\n"
        f"{topic_line}\n\n"
        f"{slot.exact_instruction}\n\n"
        "Return only valid JSON matching the schema. Do not include markdown."
    )


def stream_generated_questions(
    user,
    pdf_source_ids: List[str],
    topic: str,
    count: int,
    difficulty: str,
    instructions: str = "",
    payload: Optional[dict] = None,
) -> Iterable[str]:
    from services.generation_router import (
        build_blueprint_instructions,
        build_question_plan,
        extract_class_number,
        normalize_subject,
        should_use_new_engine,
    )

    logger.info(f"[STREAM_SERVICE] Entered stream_generated_questions for topic '{topic}'")
    logger.info("[STREAM_SERVICE] Building q_instructions plan before retrieval/LLM...")

    payload = payload or {}
    if not should_use_new_engine(payload):
        yield _sse_event(
            {
                "error": "Only CBSE Science and CBSE Social Science are configured in q_instructions right now."
            },
            event="error",
        )
        return

    class_raw = payload.get("class", payload.get("class_level", payload.get("gradeClass", "10")))
    class_num = extract_class_number(class_raw, default=10)
    subject_raw = str(payload.get("subject", "Science")).strip() or "Science"
    subject_norm = normalize_subject(subject_raw)
    subject_label = "Social Science" if subject_norm == "social science" else "Science"

    try:
        blueprint_rules = build_blueprint_instructions(
            topic=topic,
            difficulty=difficulty,
            count=count,
            class_num=class_num,
            subject=subject_raw,
        )
        plan = build_question_plan(
            topic=topic,
            difficulty=difficulty,
            count=count,
            class_num=class_num,
            subject=subject_raw,
            instructions=instructions,
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
        total_max_tokens=8000,
        reserved_system_tokens=700,
        max_output_tokens=900,
    )
    assembler = PromptAssembler(version_id="v1")
    request_factory = LLMRequestFactory()
    provider = OpenAIProvider()
    result = _empty_result()
    retrieval_cache: Dict[str, List[dict]] = {}
    prompt_audit: List[dict] = []
    provider_failures = 0
    total_estimated_input_tokens = 0
    truncation_events = 0

    yield _sse_event(
        {
            "total": len(plan),
            "subject": subject_label,
            "class": class_num,
            "blueprint": blueprint_rules,
        },
        event="plan",
    )

    for slot in plan:
        context = retrieval_cache.get(slot.retrieval_query)
        if context is None:
            context = retrieve_relevant_chunks(slot.retrieval_query, pdf_source_ids, limit=4, user=user)
            retrieval_cache[slot.retrieval_query] = context

        if not context:
            provider_failures += 1
            yield _sse_event(
                {
                    "error": f"No relevant textbook chunks found for {slot.section_title} question {slot.index}.",
                    "index": slot.index,
                },
                event="warning",
            )
            continue

        retrieval_metrics = retrieval_quality_summary(context)
        logger.info("[RAG] slot=%s metrics=%s", slot.index, retrieval_metrics)

        raw_chunks = [item["content"] for item in context]
        budget_result = trim_chunks_to_budget(raw_chunks, max_input_tokens)
        total_estimated_input_tokens += budget_result.estimated_tokens
        truncation_events += budget_result.truncation_events

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
                reserved_system_tokens=700,
            ),
            generation_constraints=constraints,
            prompt_version="v1",
        )
        slot_blueprint = f"{blueprint_rules}\n\nQUESTION-SPECIFIC CONTRACT:\n{slot.exact_instruction}"
        prompt_document = assembler.assemble(
            context=gen_context,
            system_rules=default_system_rules(constraints),
            output_schema=_single_question_schema(),
            blueprint_instructions=slot_blueprint,
            extra_instructions=instructions if instructions else None,
        )
        prompt = _build_user_prompt(slot, len(plan), topic)
        prompt_audit.append(
            {
                "index": slot.index,
                "section": slot.section_title,
                "type": slot.legacy_type,
                "marks": slot.marks,
                "query": slot.retrieval_query,
                "chunks": len(context),
            }
        )

        llm_request = request_factory.build(prompt_document, prompt, model=settings.OPENAI_MODEL)
        extractor = JsonObjectStreamExtractor()
        buffer = ""
        parsed_payload: Optional[dict] = None

        try:
            for delta in provider.stream_chat(llm_request):
                if not delta:
                    continue
                buffer += delta
                for parsed in extractor.feed(delta):
                    parsed_payload = parsed
        except Exception as exc:
            provider_failures += 1
            logger.error("[LLM] Streaming failed for slot %s: %s", slot.index, exc, exc_info=True)
            yield _sse_event({"error": str(exc), "index": slot.index}, event="warning")
            continue

        if parsed_payload is None and buffer.strip():
            try:
                parsed_payload = json.loads(buffer)
            except json.JSONDecodeError as exc:
                provider_failures += 1
                logger.error("[LLM] Invalid JSON for slot %s: %s", slot.index, exc)
                yield _sse_event(
                    {"error": f"Invalid JSON for question {slot.index}", "index": slot.index},
                    event="warning",
                )
                continue

        if parsed_payload is None:
            provider_failures += 1
            yield _sse_event(
                {"error": f"No question content returned for question {slot.index}", "index": slot.index},
                event="warning",
            )
            continue

        try:
            question = _coerce_question(parsed_payload, slot, context)
        except Exception as exc:
            provider_failures += 1
            logger.error("[LLM] Could not normalize slot %s: %s", slot.index, exc, exc_info=True)
            yield _sse_event({"error": str(exc), "index": slot.index}, event="warning")
            continue

        section = _find_or_create_section(result, slot.section_title)
        section["questions"].append(question)
        yield _sse_event(
            {
                "index": slot.index,
                "total": len(plan),
                "section": slot.section_title,
                "question": question,
            },
            event="question",
        )
        yield _sse_event(result, event="update")

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
        yield _sse_event(
            {"error": "Generation failed before any questions could be produced."},
            event="error",
        )
        return

    try:
        GenerationHistory.objects.create(
            prompt=json.dumps(
                {
                    "blueprint": blueprint_rules,
                    "plan": prompt_audit,
                },
                ensure_ascii=False,
            ),
            settings={
                "topic": topic,
                "count": count,
                "resolvedCount": len(plan),
                "difficulty": difficulty,
                "pdfSourceIds": pdf_source_ids,
                "instructions": instructions,
                "subject": subject_label,
                "class": class_num,
            },
            result=result,
            user=user,
        )
    except Exception as exc:
        logger.warning("[HISTORY] Could not persist generation history: %s", exc)

    yield _sse_event({"done": True, "result": result}, event="done")
