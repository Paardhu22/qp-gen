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


def _printable_question_content(content: str, or_choice: Optional[dict], vi_alternative: Optional[str]) -> str:
    parts = [content.strip()]
    if or_choice:
        parts.extend(["OR", or_choice.get("content", "").strip()])
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


def _coerce_question(raw_payload: dict, slot, source_chunks: List[dict], is_retry: bool = False) -> dict:
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
    if slot.requires_image and not image_url and allowed_urls:
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

    printable_content = _printable_question_content(content, or_choice, vi_alternative)

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


def _single_question_schema() -> str:
    return (
        "{\n"
        '  "question": {\n'
        '    "content": "Question text",\n'
        '    "type": "MCQ | ASSERTION_REASON | SHORT | LONG | CASE_STUDY | DIAGRAM",\n'
        '    "options": ["Option 1", "Option 2", "Option 3", "Option 4"],\n'
        '    "answer": "Correct answer or scoring points",\n'
        '    "marks": 3,\n'
        '    "image_url": "Optional copied image URL, otherwise empty string",\n'
        '    "or_choice": null,\n'
        '    "vi_alternative": null,\n'
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
        "Rules: `or_choice` must be null when no OR choice is required. "
        "When OR is required, set `or_choice` to an object with content, options, answer, and image_url. "
        "Keep it inside this same question object; never create a second question for it. "
        "When VI is required, set `vi_alternative` to the full text-based replacement question.\n"
    )


def _build_user_prompt(
    slot,
    total_slots: int,
    topic: str,
    image_urls: Optional[List[str]] = None,
    used_terms: Optional[Set[str]] = None,
) -> str:
    topic_line = f"Topic/focus: {topic}." if topic else "Topic/focus: infer from the retrieved chunks."
    image_line = ""
    if image_urls:
        image_line = f"\nAvailable image_url values: {', '.join(image_urls)}."
    reuse_line = ""
    if used_terms:
        reuse_line = f"\nDo not reuse these concepts or exact values: {', '.join(sorted(used_terms)[:30])}."
    return (
        f"Question {slot.index} of {total_slots}.\n"
        f"{topic_line}\n\n"
        f"{slot.exact_instruction}{image_line}{reuse_line}\n\n"
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
        build_general_instructions,
        build_question_plan,
        extract_class_number,
        normalize_subject,
        summarize_question_plan,
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
    count_variation = str(
        payload.get("count_variation")
        or payload.get("countVariation")
        or payload.get("countType")
        or ""
    ).strip().lower()
    resolved_count = -1 if count_variation in {"cbse exact pattern", "cbse", "exact"} else count

    try:
        plan = build_question_plan(
            topic=topic,
            difficulty=difficulty,
            count=resolved_count,
            class_num=class_num,
            subject=subject_raw,
            instructions=instructions,
        )
        blueprint_rules = build_blueprint_instructions(
            topic=topic,
            difficulty=difficulty,
            count=resolved_count,
            class_num=class_num,
            subject=subject_raw,
            plan=plan,
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
        total_max_tokens=5000,
        reserved_system_tokens=350,
        max_output_tokens=750,
    )
    assembler = PromptAssembler(version_id="v1")
    request_factory = LLMRequestFactory()
    provider = OpenAIProvider()
    result = _empty_result()
    general_instructions = build_general_instructions(plan, subject_raw, class_num)
    result["generalInstructions"] = general_instructions
    prompt_audit: List[dict] = []
    provider_failures = 0
    total_estimated_input_tokens = 0
    truncation_events = 0
    used_chunk_ids: Set[str] = set()
    used_terms: Set[str] = set()
    retrieval_cache: Dict[tuple, List[dict]] = {}

    yield _sse_event(
        {
            "total": len(plan),
            "subject": subject_label,
            "class": class_num,
            "blueprint": blueprint_rules,
            "summary": summarize_question_plan(plan),
            "generalInstructions": general_instructions,
        },
        event="plan",
    )

    for slot in plan:
        cache_key = (
            slot.retrieval_query,
            frozenset(used_chunk_ids),
            slot.requires_image
        )
        if cache_key in retrieval_cache:
            context = retrieval_cache[cache_key]
        else:
            context = retrieve_relevant_chunks(
                slot.retrieval_query,
                pdf_source_ids,
                limit=4,
                user=user,
                require_image=slot.requires_image,
                exclude_chunk_ids=used_chunk_ids,
            )
            retrieval_cache[cache_key] = context

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

        image_urls = _allowed_image_urls(context) if slot.requires_image else []
        vision_image_urls = _vision_image_payload_urls(context) if slot.requires_image else []
        raw_chunks = [_format_chunk_for_prompt(item) for item in context]
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
                reserved_system_tokens=350,
            ),
            generation_constraints=constraints,
            prompt_version="v1",
        )
        slot_blueprint = blueprint_rules
        prompt_document = assembler.assemble(
            context=gen_context,
            system_rules=default_system_rules(constraints),
            output_schema=_single_question_schema(),
            blueprint_instructions=slot_blueprint,
            extra_instructions=instructions if instructions else None,
        )
        prompt_audit.append(
            {
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
        )

        prompt = _build_user_prompt(
            slot,
            len(plan),
            topic,
            image_urls=image_urls,
            used_terms=used_terms,
        )
        llm_request = request_factory.build(
            prompt_document,
            prompt,
            model=settings.OPENAI_MODEL,
            image_urls=vision_image_urls,
        )
        question = None
        for attempt in range(2):
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
                if attempt == 0:
                    logger.warning("[LLM] Streaming failed for slot %s attempt 1: %s. Retrying...", slot.index, exc)
                    continue
                provider_failures += 1
                logger.error("[LLM] Streaming failed for slot %s: %s", slot.index, exc, exc_info=True)
                yield _sse_event({"error": str(exc), "index": slot.index}, event="warning")
                break

            if parsed_payload is None and buffer.strip():
                try:
                    parsed_payload = json.loads(buffer)
                except json.JSONDecodeError as exc:
                    if attempt == 0:
                        logger.warning("[LLM] Invalid JSON for slot %s attempt 1: %s. Retrying...", slot.index, exc)
                        continue
                    provider_failures += 1
                    logger.error("[LLM] Invalid JSON for slot %s: %s", slot.index, exc)
                    yield _sse_event(
                        {"error": f"Invalid JSON for question {slot.index}", "index": slot.index},
                        event="warning",
                    )
                    break

            if parsed_payload is None:
                if attempt == 0:
                    logger.warning("[LLM] No question content returned for slot %s attempt 1. Retrying...", slot.index)
                    continue
                provider_failures += 1
                yield _sse_event(
                    {"error": f"No question content returned for question {slot.index}", "index": slot.index},
                    event="warning",
                )
                break

            try:
                question = _coerce_question(parsed_payload, slot, context, is_retry=(attempt > 0))
                break
            except Exception as exc:
                if attempt == 0:
                    logger.warning("[LLM] Could not normalize slot %s attempt 1: %s. Retrying...", slot.index, exc)
                    continue
                provider_failures += 1
                logger.error("[LLM] Could not normalize slot %s: %s", slot.index, exc, exc_info=True)
                yield _sse_event({"error": str(exc), "index": slot.index}, event="warning")
                break

        if not question:
            continue

        section = _find_or_create_section(result, slot.section_title)
        section["questions"].append(question)
        for item in context:
            chunk_id = item.get("id")
            if chunk_id:
                used_chunk_ids.add(str(chunk_id))
        used_terms.update(_extract_reuse_terms(question))
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

    if total_questions < len(plan):
        limited_note = (
            "Questions generated from available source material only. "
            "Additional chapters are needed for complete CBSE coverage."
        )
        if limited_note not in result.get("generalInstructions", []):
            result.setdefault("generalInstructions", []).append(limited_note)

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
                "resolvedCountInput": resolved_count,
                "resolvedCount": len(plan),
                "countVariation": count_variation or ("cbse" if count <= 0 else "custom"),
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
