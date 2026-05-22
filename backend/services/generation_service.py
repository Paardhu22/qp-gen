import json
import logging
from typing import Iterable, List, Optional

from apps.generation.models import GenerationHistory
from django.conf import settings

from services.openai_service import get_openai_client
from services.retrieval_service import retrieve_relevant_chunks

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
    from services.retrieval_service import get_all_chunks
    
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

    context_text = "\n\n".join(item["content"] for item in context)

    system_prompt = (
        "You are an expert exam question generator. "
        "Your task is to generate high-quality exam questions based ONLY on the provided context.\n\n"
        "STRICT RULES:\n"
        "1. Do NOT hallucinate.\n"
        "2. ONLY use the retrieved context below.\n"
        "3. If a question or its answer cannot be fully supported by the context, do NOT generate it.\n"
        "4. If there is insufficient context to generate the requested questions, generate only what is possible.\n"
        "5. Distribute questions across realistic CBSE formats (MCQ, ASSERTION_REASON, SHORT, LONG, CASE_STUDY) and strictly align them with the requested Bloom's Taxonomy targets (e.g., use ASSERTION_REASON for Analyze, CASE_STUDY for Evaluate/Apply).\n"
        "6. STRICT LIMITS: Do NOT over-generate CASE_STUDY or ASSERTION_REASON questions. Even for 'hard' papers, an exam should contain a MAXIMUM of 3 CASE_STUDY questions and 4 ASSERTION_REASON questions. The vast majority of questions MUST be MCQ, SHORT, and LONG.\n"
        "7. For MCQ: Provide exactly 4 options in the options array.\n"
        "8. For ASSERTION_REASON: Format the content as 'Assertion (A): [statement]\nReason (R): [statement]'. The options array MUST be exactly: ['Both A and R are true and R is the correct explanation of A', 'Both A and R are true but R is not the correct explanation of A', 'A is true but R is false', 'A is false but R is true'].\n"
        "9. For CASE_STUDY: Format the content as a passage followed by 3 sub-questions ((i), (ii), (iii)). Leave the options array empty [].\n"
        "10. Return the output as a valid JSON object matching the schema below.\n\n"
        "Schema:\n"
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
        "}\n\n"
        f"Context:\n{context_text}"
    )

    if enhanced_instructions:
        system_prompt = system_prompt.replace(
            f"Context:\n{context_text}",
            (
                "QUESTION PAPER STRUCTURE INSTRUCTIONS (MUST FOLLOW EXACTLY):\n"
                f"{enhanced_instructions}\n\n"
                "You MUST create sections and distribute questions EXACTLY as specified above.\n\n"
                f"Context:\n{context_text}"
            ),
        )

    prompt = (
        f"CRITICAL REQUIREMENT: You MUST generate EXACTLY {count} {difficulty} difficulty questions about '{topic}'.\n"
        "Do NOT stop early. You must fulfill the exact count requested.\n"
        "Also ensure that you assign realistic 'marks' based on question type (MCQ=1, ASSERTION_REASON=1, SHORT=3, LONG=5, CASE_STUDY=4)."
    )
    if enhanced_instructions:
        prompt += f"\n\nStructure instructions to follow strictly: {enhanced_instructions}"

    client = get_openai_client()
    try:
        stream = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            stream=True,
            stream_options={"include_usage": True},
        )
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
    for chunk in stream:
        # Capture usage whenever it appears (typically the last chunk)
        if hasattr(chunk, "usage") and chunk.usage is not None:
            usage_info = chunk.usage

        if not chunk.choices:
            continue

        delta = chunk.choices[0].delta.content or ""
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

            _record_usage(
                user, "question_generation", settings.OPENAI_MODEL, usage_info
            )

    yield _sse_event({"done": True}, event="done")
