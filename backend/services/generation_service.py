import json
from typing import Iterable, List

from django.conf import settings

from apps.generation.models import GenerationHistory
from services.openai_service import get_openai_client
from services.retrieval_service import retrieve_relevant_chunks


def _sse_event(data: dict, event: str = "update") -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def stream_generated_questions(user, document_ids: List[str], topic: str, count: int, difficulty: str, instructions: str = "") -> Iterable[str]:
    context = retrieve_relevant_chunks(topic, document_ids, 15, user=user)
    if not context:
        yield _sse_event({"error": "No relevant content found in the uploaded documents."}, event="error")
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
        "5. Provide a mix of types: MCQ, SHORT, LONG, and TF.\n"
        "6. For MCQ, provide exactly 4 options.\n"
        "7. For TF questions: do NOT include an options array. Instead, prefix the question content with 'State whether the given statement is true or false. ' and append ' (True/False)' at the end of the content field. Leave options as an empty list [].\n"
        "8. Return the output as a valid JSON object matching the schema below.\n\n"
        "Schema:\n"
        "{\n"
        "  \"sections\": [\n"
        "    {\n"
        "      \"title\": \"Section Name (e.g. Section A: Multiple Choice)\",\n"
        "      \"questions\": [\n"
        "        {\n"
        "          \"content\": \"Question text\",\n"
        "          \"type\": \"MCQ | SHORT | LONG | TF\",\n"
        "          \"options\": [\"Option 1\", \"Option 2\", \"Option 3\", \"Option 4\"], (for MCQ only; empty [] for TF)\n"
        "          \"answer\": \"Correct Answer\",\n"
        "          \"marks\": 1\n"
        "        }\n"
        "      ]\n"
        "    }\n"
        "  ]\n"
        "}\n\n"
        f"Context:\n{context_text}"
    )

    if instructions:
        system_prompt = (
            system_prompt.replace(
                f"Context:\n{context_text}",
                (
                    "QUESTION PAPER STRUCTURE INSTRUCTIONS (MUST FOLLOW EXACTLY):\n"
                    f"{instructions}\n\n"
                    "You MUST create sections and distribute questions EXACTLY as specified above.\n\n"
                    f"Context:\n{context_text}"
                ),
            )
        )

    prompt = f"Generate {count} {difficulty} difficulty questions about '{topic}'."
    if instructions:
        prompt += f"\n\nStructure instructions to follow strictly: {instructions}"

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
                "documentIds": document_ids,
                "instructions": instructions,
            },
            result=last_valid,
            user=user,
        )
        if usage_info:
            from services.openai_service import _record_usage
            _record_usage(user, "question_generation", settings.OPENAI_MODEL, usage_info)

    yield _sse_event({"done": True}, event="done")
