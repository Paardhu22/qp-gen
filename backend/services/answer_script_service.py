"""
Answer Script / Marking Scheme Generator Service.

Completely separate from generation_service.py and the blueprint orchestration
system.  Reads an existing paper's questions and generates CBSE-style model
answers by retrieving relevant source chunks and calling the LLM.

Does NOT touch:
  - q_instructions
  - blueprint orchestration
  - streaming pipeline
"""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Set

from django.conf import settings

from apps.documents.models import PdfSource
from apps.projects.models import Paper
from services.embedding_service import generate_embeddings
from services.openai_service import get_openai_client, _record_usage
from services.retrieval_service import retrieve_relevant_chunks

logger = logging.getLogger("[ANSWER_SCRIPT]")


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a CBSE answer script / marking scheme generator.

Format rules:
- MCQ answer: letter + answer text only. Example: "B - The clergy"
- Assertion-Reason answer: full option text. Example:
  "A - Both A and R are true, and R is the correct explanation of A."
- Short answer (2-3 marks): 2-3 key points, numbered
- Long answer (5 marks): 5 numbered key points
- Each key point on its own line, numbered: "1. Point text"
- End with "(Any N points to be considered)" if answer has more points
  than marks require
- OR questions: write both answers separated by "OR"
- CBQ sub-answers: label each as Q[number].[sub] Answer [marks]
- Map questions: write "Location identified on map." + marks note
- All answers should be grounded in the source material, but you may use your general knowledge to complete the answer if the source is insufficient.
"""


def _build_user_prompt(
    question_number: int,
    question_text: str,
    marks: int,
    question_type: str,
    or_choice_text: Optional[str],
    sub_questions: Optional[List[dict]],
    source_material: str,
    options: Optional[List[str]] = None,
) -> str:
    """Build the per-question user prompt for answer generation."""

    prompt = (
        f"Question {question_number}: {question_text}\n"
        f"Marks: {marks}\n"
        f"Question type: {question_type}\n"
    )

    if options:
        prompt += "Options:\n"
        for i, opt in enumerate(options):
            prompt += f"  {chr(65 + i)}. {opt}\n"

    if or_choice_text:
        prompt += f"OR alternative: {or_choice_text}\n"

    if sub_questions:
        sub_lines = []
        for sq in sub_questions:
            sub_lines.append(
                f"  {sq.get('label', '')}: {sq.get('content', '')} [{sq.get('marks', 1)} mark(s)]"
            )
        prompt += "Sub-questions:\n" + "\n".join(sub_lines) + "\n"

    prompt += (
        f"\nSource material:\n{source_material}\n\n"
        "Generate the model answer in CBSE marking scheme format.\n"
        'Return JSON: { "answer": "...", "or_answer": "..." or null }\n'
        "If there is no OR alternative, set or_answer to null.\n"
        "Return ONLY valid JSON. Do not wrap in markdown code blocks."
    )

    return prompt


def _classify_question_type(q_type: str) -> str:
    """Normalise question type string to the type labels used in prompts."""
    t = (q_type or "").upper().replace(" ", "_")
    type_map = {
        "MCQ": "MCQ",
        "MULTIPLE_CHOICE": "MCQ",
        "ASSERTION_REASON": "ASSERTION_REASON",
        "AR": "ASSERTION_REASON",
        "SHORT_ANSWER": "SHORT_ANSWER",
        "SHORT": "SHORT_ANSWER",
        "VSA": "SHORT_ANSWER",
        "LONG_ANSWER": "LONG_ANSWER",
        "LONG": "LONG_ANSWER",
        "CASE_STUDY": "CBQ",
        "CBQ": "CBQ",
        "CASE_BASED": "CBQ",
        "MAP": "MAP",
    }
    return type_map.get(t, "SHORT_ANSWER")


# ---------------------------------------------------------------------------
# TipTap content parsing — questions live inside the paper's JSON content,
# NOT as separate Question model rows.
# ---------------------------------------------------------------------------


def _node_text(node: dict) -> str:
    """Recursively extract plain text from a TipTap node."""
    if node.get("text"):
        return node["text"]
    parts: List[str] = []
    for child in node.get("content", []):
        parts.append(_node_text(child))
    return " ".join(parts)


def _split_or_choice(text: str) -> tuple[str, Optional[str]]:
    """Split out an OR alternative when present as a standalone token."""
    match = re.search(r"\bOR\b", text)
    if not match:
        return text, None

    before = text[:match.start()].strip()
    after = text[match.end():].strip()
    if not before or not after:
        return text, None

    return before, after


def _sanitize_json_payload(raw_text: str) -> Optional[str]:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    payload = raw_text[start : end + 1]
    payload = re.sub(r",\s*([}\]])", r"\1", payload)
    return payload


def _parse_answer_payload(raw_text: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        payload = _sanitize_json_payload(raw_text)
        if not payload:
            return None
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return None


def _strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _extract_json_string_field(raw_text: str, field: str) -> Optional[str]:
    pattern = rf'"{re.escape(field)}"\s*:\s*"((?:[^"\\]|\\.)*)"'
    match = re.search(pattern, raw_text, re.DOTALL)
    if not match:
        return None
    raw_value = match.group(1)
    try:
        return json.loads(f'"{raw_value}"')
    except json.JSONDecodeError:
        return raw_value


def _fallback_answer_from_text(raw_text: str, or_choice_text: Optional[str]) -> tuple[str, Optional[str]]:
    cleaned = _strip_code_fences(raw_text)
    answer = _extract_json_string_field(cleaned, "answer")
    or_answer = _extract_json_string_field(cleaned, "or_answer")

    if answer is None:
        answer = cleaned.strip()

    if not or_choice_text:
        return answer, None

    if or_answer is None:
        or_answer = "[Answer to be filled by teacher]"

    return answer, or_answer


def _extract_questions_from_content(content_json: str) -> List[Dict[str, Any]]:
    """
    Parse the paper's TipTap JSON content and extract every
    ``questionBlock`` / ``groupedQuestionBlock`` node into a flat list
    of dicts with keys: content, marks, type, options, or_choice.

    The TipTap document has this rough shape:
      doc -> page -> pageContent -> [sectionBlock, questionBlock, ...]
    Questions may also appear as direct children of pageContent without
    a preceding sectionBlock.
    """
    try:
        doc = json.loads(content_json) if isinstance(content_json, str) else content_json
    except (json.JSONDecodeError, TypeError):
        return []

    # The persisted format may wrap the editor JSON inside a top-level
    # object:  { "editorJSON": { ... }, "pages": [...], ... }
    if "editorJSON" in doc and isinstance(doc["editorJSON"], dict):
        doc = doc["editorJSON"]

    questions: List[Dict[str, Any]] = []

    def _walk(node: dict) -> None:
        node_type = node.get("type", "")

        if node_type in ("questionBlock", "groupedQuestionBlock"):
            attrs = node.get("attrs", {})
            # Extract plain text from all children except orderedList (options)
            text_parts = []
            for child in node.get("content", []):
                if child.get("type") != "orderedList":
                    text_parts.append(_node_text(child))
            text = " ".join(text_parts).strip()
            text = re.sub(r"\s+", " ", text).strip()
            
            marks = int(attrs.get("marks", 1) or 1)
            q_type = attrs.get("questionType", "SHORT_ANSWER") or "SHORT_ANSWER"

            # Detect options (orderedList inside questionBlock)
            options: List[str] = []
            for child in node.get("content", []):
                if child.get("type") == "orderedList":
                    for item in child.get("content", []):
                        opt_text = _node_text(item).strip()
                        if opt_text:
                            options.append(opt_text)

            # Detect OR alternative embedded in text
            text, or_choice = _split_or_choice(text)

            questions.append({
                "content": text,
                "marks": marks,
                "type": q_type,
                "options": options,
                "or_choice": or_choice,
            })
            return  # don't recurse into question children again

        # Recurse into children
        for child in node.get("content", []):
            if isinstance(child, dict):
                _walk(child)

    _walk(doc)
    return questions


def _find_pdf_source_ids(paper: Paper, user) -> List[str]:
    """
    Discover the PDF source IDs associated with a paper.
    Falls back to user's most recent ready PDF sources.
    """
    # Use user's most recent ready PDF sources (the paper content
    # doesn't store source PDF references in a queryable way)
    pdf_sources = (
        PdfSource.objects.filter(user=user, status="ready")
        .order_by("-created_at")
        .values_list("id", flat=True)[:10]
    )
    return list(pdf_sources)


# ---------------------------------------------------------------------------
# Core generation
# ---------------------------------------------------------------------------


def _generate_single_answer_llm_only(
    client,
    question_number: int,
    question: Dict[str, Any],
    source_chunks: List[dict],
    user,
) -> tuple[int, Dict[str, Any]]:
    """Generate answer for a single question using provided chunks + LLM."""

    primary_content = question["content"]
    or_choice_text = question.get("or_choice")
    q_type = _classify_question_type(question["type"])
    marks = question.get("marks", 1)

    # Build source material text
    if source_chunks:
        source_material = "\n\n".join(
            f"[Chunk page={c.get('page', '?')}]\n{c.get('content', '')}"
            for c in source_chunks
        )
    else:
        source_material = "(No source material available)"

    user_prompt = _build_user_prompt(
        question_number=question_number,
        question_text=primary_content,
        marks=marks,
        question_type=q_type,
        or_choice_text=or_choice_text,
        sub_questions=None,
        source_material=source_material,
        options=question.get("options"),
    )

    # Call LLM
    try:
        def _request_completion(extra_instruction: Optional[str] = None):
            content = user_prompt
            if extra_instruction:
                content = f"{content}\n\n{extra_instruction}"
            return client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": content},
                ],
                response_format={"type": "json_object"},
                max_completion_tokens=1000,
                temperature=0,
            )

        completion = _request_completion()
        raw_text = (completion.choices[0].message.content or "").strip()
        _record_usage(user, "answer_script", settings.OPENAI_MODEL, completion.usage)

        parsed = _parse_answer_payload(raw_text)
        if parsed is None:
            logger.warning(
                "LLM answer generation invalid JSON for Q%d. Retrying once.",
                question_number,
            )
            retry = _request_completion(
                "Your previous response was invalid JSON. Return ONLY a valid JSON object with keys: answer, or_answer.",
            )
            retry_text = (retry.choices[0].message.content or "").strip()
            _record_usage(user, "answer_script", settings.OPENAI_MODEL, retry.usage)
            parsed = _parse_answer_payload(retry_text)

        if parsed is None:
            fallback_text = retry_text if "retry_text" in locals() else raw_text
            answer_text, or_answer_text = _fallback_answer_from_text(
                fallback_text,
                or_choice_text,
            )
        else:
            answer_text = parsed.get("answer") or "[Answer to be filled by teacher]"
            or_answer_text = parsed.get("or_answer")
            if or_choice_text and not or_answer_text:
                or_answer_text = "[Answer to be filled by teacher]"

    except Exception as exc:
        logger.warning(
            "LLM answer generation failed for Q%d: %s", question_number, exc
        )
        answer_text = "[Answer generation failed]"
        or_answer_text = "[Answer generation failed]" if or_choice_text else None

    return question_number, {
        "question_number": question_number,
        "question_text": primary_content,
        "question_type": q_type,
        "marks": marks,
        "answer": answer_text,
        "or_choice_text": or_choice_text,
        "or_answer": or_answer_text,
    }


def _build_answer_script_content(
    original_paper: Paper,
    answers: List[Dict[str, Any]],
) -> List[dict]:
    """
    Build the answer script document content as TipTap-compatible JSON blocks.
    These blocks will be saved as a standalone answer script document.
    """
    # Parse original paper metadata
    project_name = original_paper.project.name if original_paper.project else ""
    parts = project_name.split(" — ")
    class_label = parts[0].strip() if parts else ""
    subject_label = parts[1].strip() if len(parts) > 1 else ""

    # Build TipTap JSON document
    doc_content: List[dict] = []

    # Header block
    doc_content.append({
        "type": "heading",
        "attrs": {"level": 1, "textAlign": "center"},
        "content": [{"type": "text", "text": "MARKING SCHEME"}],
    })

    if subject_label:
        doc_content.append({
            "type": "heading",
            "attrs": {"level": 2, "textAlign": "center"},
            "content": [{"type": "text", "text": subject_label}],
        })

    if class_label:
        doc_content.append({
            "type": "paragraph",
            "attrs": {"textAlign": "center"},
            "content": [
                {"type": "text", "text": f"{class_label}"},
            ],
        })

    doc_content.append({
        "type": "paragraph",
        "content": [],
    })

    # Answer blocks
    for ans in answers:
        q_num = ans["question_number"]
        marks = ans["marks"]
        answer_text = ans["answer"] or "[Answer to be filled by teacher]"
        or_choice = ans.get("or_choice_text")
        or_answer = ans.get("or_answer")

        # Format marks display
        marks_display = f"{marks} M"

        # Build answer paragraph content
        answer_lines = [f"{q_num}.  {answer_text}"]

        if or_choice and or_answer:
            answer_lines.append("")
            answer_lines.append("OR")
            answer_lines.append("")
            answer_lines.append(f"    {or_answer}")

        # Add marks indicator at the end
        full_text = "\n".join(answer_lines)

        # Create the answer block as a paragraph with marks
        text_content: List[Dict[str, Any]] = [
            {"type": "text", "text": full_text},
        ]

        # Add marks as a separate bold text
        text_content.append(
            {
                "type": "text",
                "marks": [{"type": "bold"}],
                "text": f"    [{marks_display}]",
            }
        )

        doc_content.append({
            "type": "paragraph",
            "content": text_content,
        })

        # Add spacing between questions
        doc_content.append({
            "type": "paragraph",
            "content": [],
        })

    # Wrap the entire marking scheme in a new page node
    import uuid
    page_id = f"page-{uuid.uuid4().hex[:8]}"
    
    return [{
        "type": "page",
        "attrs": {"pageId": page_id},
        "content": doc_content,
    }]


def _build_pages_from_doc(answer_doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    pages: List[Dict[str, Any]] = []
    content = answer_doc.get("content") if isinstance(answer_doc, dict) else None
    if not isinstance(content, list):
        return pages

    for idx, node in enumerate(content, start=1):
        if not isinstance(node, dict) or node.get("type") != "page":
            continue
        attrs = node.get("attrs") or {}
        page_id = attrs.get("pageId") or f"page-{idx}"
        blocks = node.get("content") if isinstance(node.get("content"), list) else []
        pages.append({"id": page_id, "blocks": blocks})

    return pages


def _build_answer_paper_content(
    original_content: str,
    answer_doc: Dict[str, Any],
) -> Dict[str, Any]:
    try:
        original = json.loads(original_content) if original_content else {}
    except (json.JSONDecodeError, TypeError):
        original = {}

    if isinstance(original, dict) and isinstance(original.get("editorJSON"), dict):
        updated_at = int(time.time() * 1000)
        pages = _build_pages_from_doc(answer_doc)
        new_doc = {**original}
        new_doc["editorJSON"] = answer_doc
        if "pages" in new_doc:
            new_doc["pages"] = pages
        if isinstance(new_doc.get("layout"), dict):
            new_doc["layout"] = {
                **new_doc["layout"],
                "pages": pages,
            }
        if isinstance(new_doc.get("metadata"), dict):
            new_doc["metadata"] = {
                **new_doc["metadata"],
                "updatedAt": updated_at,
            }
        new_doc["updatedAt"] = updated_at
        return new_doc

    return answer_doc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_answer_script(paper_id: str, user) -> Dict[str, str]:
    """
    Generate a complete CBSE-style answer script / marking scheme for
    the given paper.

    Returns:
        { "answer_script_paper_id": "<id>", "editor_url": "/editor?paperId=<id>" }

    Raises:
        ValueError: if the paper is not found or has no questions
        RuntimeError: if source PDFs are unavailable
    """
    # Step 1: Load the paper
    try:
        paper = Paper.objects.select_related("project").get(
            id=paper_id, user=user
        )
    except Paper.DoesNotExist:
        raise ValueError(f"Paper '{paper_id}' not found.")

    # Step 2: Extract questions from TipTap JSON content
    questions = _extract_questions_from_content(paper.content or "")
    if not questions:
        raise ValueError("This paper has no questions. Cannot generate answer script.")

    logger.info(
        "Extracted %d questions from paper %s content",
        len(questions), paper_id,
    )

    # Step 3: Find PDF source IDs
    pdf_source_ids = _find_pdf_source_ids(paper, user)
    if not pdf_source_ids:
        raise RuntimeError(
            "Source files no longer available. Cannot generate answer script."
        )

    # Step 4: Retrieve chunks sequentially to avoid thread DB issues
    client = get_openai_client()
    used_chunk_ids: Set[str] = set()
    prepared_data = []

    question_embeddings: List[List[float]] = []
    if questions:
        try:
            question_texts = [q["content"] for q in questions]
            question_embeddings = generate_embeddings(question_texts, user=user)
            if len(question_embeddings) != len(questions):
                logger.warning(
                    "Embedding count mismatch (%d vs %d); falling back to per-question embeddings.",
                    len(question_embeddings),
                    len(questions),
                )
                question_embeddings = []
        except Exception as exc:
            logger.warning("Batch embedding generation failed: %s", exc)
            question_embeddings = []

    for idx, question in enumerate(questions, start=1):
        primary_content = question["content"]
        source_chunks = []
        query_embedding = None
        if question_embeddings:
            query_embedding = question_embeddings[idx - 1]
        if pdf_source_ids:
            try:
                source_chunks = retrieve_relevant_chunks(
                    query=primary_content,
                    pdf_source_ids=pdf_source_ids,
                    limit=4,
                    user=user,
                    exclude_chunk_ids=used_chunk_ids,
                    query_embedding=query_embedding,
                )
            except Exception as exc:
                logger.warning("Retrieval failed for Q%d: %s", idx, exc)

        for chunk in source_chunks:
            if chunk.get("id"):
                used_chunk_ids.add(str(chunk["id"]))

        prepared_data.append((idx, question, source_chunks))

    # Step 4.5: Call LLMs in parallel
    import concurrent.futures
    answers: List[Optional[Dict[str, Any]]] = [None] * len(questions)
    
    logger.info("Starting parallel LLM generation for %d questions...", len(questions))
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for (idx, question, source_chunks) in prepared_data:
            futures.append(
                executor.submit(
                    _generate_single_answer_llm_only,
                    client=client,
                    question_number=idx,
                    question=question,
                    source_chunks=source_chunks,
                    user=user,
                )
            )
            
        for future in concurrent.futures.as_completed(futures):
            try:
                idx, answer_data = future.result()
                answers[idx - 1] = answer_data
            except Exception as e:
                logger.error("A thread crashed during answer generation: %s", e)

    # Filter out any None values if threads crashed (shouldn't happen with our try blocks)
    valid_answers = [ans for ans in answers if ans is not None]

    # Step 5: Build the answer script document content blocks
    answer_blocks = _build_answer_script_content(paper, valid_answers)

    # Step 6: Create new paper for the answer script
    try:
        answer_doc = {"type": "doc", "content": answer_blocks}
        new_doc = _build_answer_paper_content(paper.content or "", answer_doc)

        new_paper = Paper.objects.create(
            title=f"{paper.title} - Answer Key",
            content=json.dumps(new_doc),
            project=paper.project,
            user=user
        )
        
    except Exception as e:
        logger.error(f"Failed to create answer script paper for {paper_id}: {e}")
        raise RuntimeError("Failed to create answer script paper.")

    logger.info(
        "Answer script created as new paper %s (%d answers)",
        new_paper.id,
        len(valid_answers),
    )

    return {
        "answer_script_paper_id": new_paper.id,
        "editor_url": f"/editor?paperId={new_paper.id}",
    }
