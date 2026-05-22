import json
import logging
from typing import Iterable, List, Optional

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
    get_all_chunks,
    retrieve_relevant_chunks,
    retrieval_quality_summary,
)

logger = logging.getLogger("[LEGACY_ENGINE]")


def _sse_event(data: dict, event: str = "update") -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def stream_generated_questions(
    user,
    pdf_source_ids: List[str],
    topic: str,
    count: int,
    difficulty: str,
    instructions: str = "",
    payload: Optional[dict] = None,
) -> Iterable[str]:
    from services.generation_router import should_use_new_engine, build_blueprint_instructions

    logger.info(f"[STREAM_SERVICE] Entered stream_generated_questions for topic '{topic}'")
    logger.info("[STREAM_SERVICE] Dispatching to hybrid router for eligibility check...")

    enhanced_instructions = instructions
    # Check eligibility for new engine routing
    if should_use_new_engine(payload):
        try:
            blueprint_rules = build_blueprint_instructions(
                topic=topic,
                difficulty=difficulty,
                count=count
            )
            if blueprint_rules:
                enhanced_instructions = f"{instructions}\n\n{blueprint_rules}" if instructions else blueprint_rules
                logger.info("[NEW_ENGINE] Successfully compiled structured blueprint instructions for LLM.")
        except Exception as exc:
            logger.error(f"[NEW_ENGINE] Blueprint compilation failed. Safely falling back. Error: {exc}", exc_info=True)
            
    logger.info("[LEGACY_ENGINE] Starting legacy question generation process with LLM...")
    # User requested FULL document context without arbitrary semantic limits
    context = get_all_chunks(pdf_source_ids)
    
    if not context:
        # Fallback to topic search if no PDFs provided (or chunking failed)
        context = retrieve_relevant_chunks(
            topic, pdf_source_ids, 30, user=user
        )
        
    if not context:
        yield _sse_event(
            {"error": "No relevant content found in the uploaded sources."},
            event="error",
        )
        return

    retrieval_metrics = retrieval_quality_summary(context)
    logger.info(f"[RETRIEVAL_METRICS] {retrieval_metrics}")

    raw_chunks = [item["content"] for item in context]
    max_input_tokens, max_output_tokens = allocate_budget(
        total_max_tokens=12000,
        reserved_system_tokens=600,
        max_output_tokens=1500,
    )
    budget_result = trim_chunks_to_budget(raw_chunks, max_input_tokens)

    constraints = GenerationConstraints(count=count, difficulty=difficulty)
    board = EducationBoard.CBSE
    academic_class = AcademicClass.CLASS_10
    if payload:
        board_raw = str(payload.get("board", "CBSE")).strip().upper()
        class_raw = str(
            payload.get("class", payload.get("class_level", payload.get("gradeClass", "CLASS_10")))
        ).strip()
        if board_raw in EducationBoard.__members__:
            board = EducationBoard[board_raw]
        digits = "".join(filter(str.isdigit, class_raw))
        if digits:
            class_name = f"CLASS_{digits}"
            if class_name in AcademicClass.__members__:
                academic_class = AcademicClass[class_name]
    gen_context = GenerationContext(
        subject="Science",
        board=board,
        academic_class=academic_class,
        difficulty=difficulty,
        retrieved_chunks=budget_result.selected_chunks,
        token_budget=TokenBudget(
            model=settings.OPENAI_MODEL,
            max_input_tokens=max_input_tokens,
            max_output_tokens=max_output_tokens,
            reserved_system_tokens=600,
        ),
        generation_constraints=constraints,
        prompt_version="v1",
    )

    output_schema = (
        "{\n"
        '  "sections": [\n'
        "    {\n"
        '      "title": "Section Name (e.g. Section A: Objective Type)",\n'
        '      "questions": [\n'
        "        {\n"
        '          "content": "Question text",\n'
        '          "type": "MCQ | ASSERTION_REASON | SHORT | LONG | CASE_STUDY",\n'
        '          "options": ["Option 1", "Option 2", "Option 3", "Option 4"], (Leave empty [] if not applicable)\n'
        '          "answer": "Correct Answer",\n'
        '          "marks": 3, (Assign strictly: MCQ=1, ASSERTION_REASON=1, SHORT=3, LONG=5, CASE_STUDY=4)\n'
        '          "metadata": {\n'
        '            "gradeClass": "e.g. 10th Grade",\n'
        '            "subject": "e.g. Science",\n'
        '            "inferredTopic": "e.g. Chemical Bonds",\n'
        '            "inferredChapter": "e.g. Chapter 3",\n'
        '            "sourcePdf": "Extracted filename/context",\n'
        '            "difficulty": "Easy | Medium | Hard"\n'
        '          }\n'
        "        }\n"
        "      ]\n"
        "    }\n"
        "  ]\n"
        "}\n"
    )

    assembler = PromptAssembler(version_id="v1")
    prompt_document = assembler.assemble(
        context=gen_context,
        system_rules=default_system_rules(constraints),
        output_schema=output_schema,
        blueprint_instructions=enhanced_instructions,
        extra_instructions=instructions if instructions else None,
    )

    prompt = (
        f"CRITICAL REQUIREMENT: You MUST generate EXACTLY {count} {difficulty} difficulty questions about '{topic}'.\n"
        "Do NOT stop early. You must fulfill the exact count requested.\n"
        "Also ensure that you assign realistic 'marks' based on question type (MCQ=1, ASSERTION_REASON=1, SHORT=3, LONG=5, CASE_STUDY=4)."
    )
    if enhanced_instructions:
        prompt += f"\n\nStructure instructions to follow strictly: {enhanced_instructions}"

    metrics = GenerationMetrics(
        prompt_version=gen_context.prompt_version,
        model=settings.OPENAI_MODEL,
        chunk_count=len(gen_context.retrieved_chunks),
        estimated_input_tokens=budget_result.estimated_tokens,
        estimated_output_tokens=max_output_tokens,
        truncation_events=budget_result.truncation_events,
        provider_failures=0,
    )
    logger.info(f"[PROMPT_METRICS] {metrics.to_dict()}")

    provider = OpenAIProvider()
    request_factory = LLMRequestFactory()
    llm_request = request_factory.build(prompt_document, prompt, model=settings.OPENAI_MODEL)
    try:
        stream = provider.stream_chat(llm_request)
    except Exception as exc:
        yield _sse_event({"error": str(exc)}, event="error")
        return

    buffer = ""
    last_valid = None
    usage_info = None

    # Consume ALL chunks in a single pass.
    # Usage statistics arrive in the final chunk (choices=[]) when
    # stream_options={"include_usage": True} is set. Breaking out early
    # and re-iterating the stream to grab usage does NOT work with the
    # OpenAI Python SDK — the stream cannot be iterated twice.
    for delta in stream:
        if delta:
            buffer += delta

    # Parse the accumulated buffer once, after the stream is exhausted
    if buffer:
        try:
            last_valid = json.loads(buffer)
        except json.JSONDecodeError:
            pass

    if last_valid is not None:
        yield _sse_event(last_valid)
        GenerationHistory.objects.create(
            prompt=prompt,
            settings={
                "topic": topic,
                "count": count,
                "difficulty": difficulty,
                "pdfSourceIds": pdf_source_ids,
                "instructions": instructions,
            },
            result=last_valid,
            user=user,
        )
        if usage_info:
            from services.openai_service import _record_usage

            _record_usage(user, "question_generation", settings.OPENAI_MODEL, usage_info)

    yield _sse_event({"done": True}, event="done")
