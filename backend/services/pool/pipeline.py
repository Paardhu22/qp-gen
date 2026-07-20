"""The pool generation pipeline.

    chapter Markdown
          │
          ▼
      Model 1  ──────────┐
          │              │  (parallel batches)
          ▼              │
    image stage ─────────┤
          │              │
          ▼              ▼
     Question Pool ──→ auto-saved to the user's bank
          │
          ▼
      Model 2  ──→ assembled paper ──→ SSE
                                        │
                                        ▼
                                   TipTap editor

The blueprint layer is untouched. `build_question_plan` and friends in
services.generation_router still decide what a CBSE paper must contain — that
is the pedagogical core and it was never the expensive part. What changes is
how questions are produced: one whole-chapter read instead of one retrieval
plus one LLM call per slot.

The SSE contract is preserved exactly (`plan`, `question`, `update`, `notice`,
`warning`, `done`, and the question object's field names) so the editor,
review tray and auto-insert paths keep working without frontend changes.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

from django.conf import settings

from apps.generation.models import GenerationHistory
from services.chapter_markdown import build_chapter_markdown, infer_chapter_name
from services.pool import store
from services.pool.image_model import generate_image_questions, resolve_strategy
from services.pool.model1 import generate_question_pool
from services.pool.model2 import (
    AssembledPaper,
    PaperAssemblyError,
    assemble_paper,
)
from services.pool.rendering import or_label_for, printable_content
from services.pool.schema import PoolQuestion, pool_summary

logger = logging.getLogger("[POOL_PIPELINE]")

#: Sentinel pushed onto the progress queue when Model 1's worker finishes.
_DONE = object()


def _sse(data: dict, event: str = "update") -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@dataclass
class _GimSlot:
    """Adapter so General Instructions Mode slots satisfy Model 2's interface.

    `_parse_gim_instructions` yields plain dicts; Model 2 reads attributes
    (index, marks, question_type, legacy_type, section_title). Rather than
    teach Model 2 about two slot shapes, the dict is wrapped here.
    """

    index: int
    marks: int
    question_type: str
    legacy_type: str
    section_title: str


def _legacy_type_for(question_type: str) -> str:
    mapping = {
        "MCQ": "MCQ",
        "ASSERTION_REASON": "ASSERTION_REASON",
        "CASE_STUDY": "CASE_STUDY",
        "READING_COMP": "CASE_STUDY",
        "DIAGRAM": "DIAGRAM",
        "LONG_ANSWER": "LONG",
        "LETTER": "LONG",
        "COMPOSITION": "LONG",
    }
    return mapping.get(question_type, "SHORT")


def _question_to_wire(
    question: PoolQuestion,
    *,
    slot,
    section_title: str,
    or_choice: Optional[PoolQuestion] = None,
    include_vi_alternatives: bool = True,
) -> Dict[str, Any]:
    """Render a pool question in the shape the editor already consumes.

    Field names here are the frontend's contract, not the pool's: `content`
    rather than `question`, `image_url` rather than `image`.

    An internal choice is baked into `content` (the editor takes one string per
    question) and also exposed as `or_choice` so the review tray can show the
    two halves separately.
    """
    label = or_label_for(getattr(slot, "subject", "") or question.subject)

    # VI text is printed only when the paper opts in AND the blueprint marks
    # the slot as needing it. A VI block on a slot that never called for one
    # just pads the paper.
    vi_alternative = None
    if include_vi_alternatives and getattr(slot, "vi_required", False):
        vi_alternative = (question.vi_alternative or "").strip() or None

    content = printable_content(
        question.question,
        or_alternative=or_choice.question if or_choice else None,
        vi_alternative=vi_alternative,
        or_label=label,
    )

    wire: Dict[str, Any] = {
        "content": content,
        "type": question.type,
        "options": list(question.options or []),
        "answer": question.answer,
        "marks": int(question.marks),
        "image_url": question.image or "",
        "explanation": question.explanation,
        "bloom": question.blooms,
        "sourceType": question.source_type,
        "metadata": {
            **(question.metadata or {}),
            "slotIndex": int(getattr(slot, "index", 0) or 0),
            "section": section_title,
            "sourceType": question.source_type,
            "questionId": question.id,
            "poolId": question.pool_id,
            "subject": question.subject,
            "inferredChapter": question.chapter,
            "inferredTopic": question.topic,
            "difficulty": question.difficulty,
            "blooms": question.blooms,
            "image_url": question.image or "",
        },
    }

    if vi_alternative:
        wire["vi_alternative"] = vi_alternative
        wire["metadata"]["vi_alternative"] = True

    if or_choice:
        wire["or_choice"] = {
            "content": or_choice.question,
            "options": list(or_choice.options or []),
            "answer": or_choice.answer,
            "image_url": or_choice.image or "",
        }
        wire["metadata"]["hasOrChoice"] = True
        wire["metadata"]["orChoiceQuestionId"] = or_choice.id

    return wire


def _find_or_create_section(result: Dict[str, Any], title: str) -> Dict[str, Any]:
    for section in result["sections"]:
        if section.get("title") == title:
            return section
    section = {"title": title, "questions": []}
    result["sections"].append(section)
    return section


def _build_pool_streaming(
    *,
    chapter,
    subject: str,
    subject_norm: str,
    chapter_name: str,
    class_num: int,
    difficulty: str,
    target_total: int,
    user,
) -> Iterable[Any]:
    """Run Model 1 + the image stage on a worker thread, yielding progress.

    Model 1 blocks until all four batches finish, but each batch emits
    questions as it parses them. Running it on a thread and draining a queue
    turns that into live progress instead of a 30-60s silence — which is what
    the per-slot engine gave for free and what users would otherwise notice
    losing.
    """
    progress: "queue.Queue[Any]" = queue.Queue()
    outcome: Dict[str, Any] = {}

    def _worker():
        try:
            result = generate_question_pool(
                chapter=chapter,
                subject=subject,
                subject_norm=subject_norm,
                chapter_name=chapter_name,
                class_num=class_num,
                difficulty=difficulty,
                target_total=target_total,
                user=user,
                on_question=progress.put,
            )
            outcome["pool"] = result

            image_result = generate_image_questions(
                chapter=chapter,
                subject=subject,
                chapter_name=chapter_name,
                class_num=class_num,
                pool_id=result.pool_id,
                difficulty=difficulty,
                user=user,
                on_question=progress.put,
            )
            outcome["images"] = image_result
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Pool worker crashed: %s", exc, exc_info=True)
            outcome["error"] = str(exc)
        finally:
            progress.put(_DONE)

    thread = threading.Thread(target=_worker, name="pool-generation", daemon=True)
    thread.start()

    while True:
        item = progress.get()
        if item is _DONE:
            break
        yield item

    thread.join(timeout=5)
    yield outcome


def stream_pool_questions(
    user,
    pdf_source_ids: List[str],
    topic: str,
    count: int,
    difficulty: str,
    instructions: str = "",
    payload: Optional[dict] = None,
    hsat_source_ids: Optional[List[str]] = None,
) -> Iterable[str]:
    """Generate a pool from the uploaded chapter, then assemble a paper from it."""
    from services.generation_router import (
        build_blueprint_instructions,
        build_general_instructions,
        build_question_plan,
        build_realized_general_instructions,
        extract_class_number,
        normalize_subject,
        paper_plan_section_order,
        resolve_maths_basic,
        should_use_new_engine,
        summarize_question_plan,
    )
    from services.pool.gim import _parse_gim_instructions

    payload = payload or {}
    hsat_source_ids = list(hsat_source_ids or [])
    started = time.monotonic()

    qp_type = str(
        payload.get("qp_type") or payload.get("qpType") or ""
    ).strip().lower()
    is_gim = qp_type == "general_instructions"

    # Per-paper VI toggle. Defaults to on, matching CBSE Sample Paper
    # convention; accepts snake_case, camelCase, and the false-ish strings a
    # form can send.
    raw_vi_flag = payload.get(
        "include_vi_alternatives", payload.get("includeViAlternatives", True)
    )
    include_vi_alternatives = bool(raw_vi_flag) and str(
        raw_vi_flag
    ).strip().lower() not in {"false", "0", "no", "off"}

    class_raw = payload.get(
        "class", payload.get("class_level", payload.get("gradeClass", "10"))
    )
    class_num = extract_class_number(class_raw, default=10)
    subject_raw = str(payload.get("subject", "Science")).strip() or "Science"
    subject_norm = normalize_subject(subject_raw)

    # ── Blueprint ───────────────────────────────────────────────────────
    if is_gim:
        if not instructions.strip():
            yield _sse(
                {
                    "error": "General Instructions Mode requires you to describe "
                    "what questions you want. Please write your instructions in "
                    "the text box."
                },
                event="error",
            )
            return

        exact_count = count if count and count > 0 else None
        parsed = _parse_gim_instructions(
            instructions, len(pdf_source_ids) + len(hsat_source_ids), exact_count
        )
        if not parsed:
            yield _sse(
                {
                    "error": "Could not parse any question specifications from "
                    "your instructions. Please be more specific (e.g. '5 MCQs, "
                    "3 short answers of 2 marks each')."
                },
                event="error",
            )
            return

        plan: List[Any] = []
        for spec in parsed:
            section_title = spec.get("section_title") or "Questions"
            question_type = str(spec.get("type") or "SHORT_ANSWER").upper()
            for _ in range(int(spec.get("count") or 0)):
                plan.append(
                    _GimSlot(
                        index=len(plan) + 1,
                        marks=int(spec.get("marks") or 1),
                        question_type=question_type,
                        legacy_type=_legacy_type_for(question_type),
                        section_title=section_title,
                    )
                )
        master_blueprint = (
            f"General Instructions Mode: {len(plan)} questions, "
            f"{sum(s.marks for s in plan)} marks"
        )
        general_instructions = [
            f"There are {len(plan)} questions. All questions are compulsory.",
            instructions.strip(),
        ]
        summary = {
            "total_questions": len(plan),
            "total_marks": sum(s.marks for s in plan),
        }
        subject_label = subject_raw
    else:
        if not should_use_new_engine(payload):
            yield _sse(
                {
                    "error": "This CBSE subject/class is not configured. Supported: "
                    "Science & Social Science (Classes 1-10); Mathematics, English, "
                    "Hindi, Telugu (Class 10)."
                },
                event="error",
            )
            return

        subject_label = (
            "Social Science" if subject_norm == "social science" else subject_raw
        )
        maths_basic = resolve_maths_basic(subject_raw, payload)
        count_variation = str(
            payload.get("count_variation")
            or payload.get("countVariation")
            or payload.get("countType")
            or ""
        ).strip().lower()
        resolved_count = (
            -1 if count_variation in {"cbse exact pattern", "cbse", "exact"} else count
        )

        try:
            plan = list(
                build_question_plan(
                    topic=topic,
                    difficulty=difficulty,
                    count=resolved_count,
                    class_num=class_num,
                    subject=subject_raw,
                    instructions=instructions,
                    count_variation=count_variation,
                )
            )
            master_blueprint = build_blueprint_instructions(
                topic=topic,
                difficulty=difficulty,
                count=resolved_count,
                class_num=class_num,
                subject=subject_raw,
                plan=plan,
                maths_basic=maths_basic,
            )
        except Exception as exc:
            logger.error("Failed to compile the blueprint: %s", exc, exc_info=True)
            yield _sse({"error": str(exc)}, event="error")
            return

        if not plan:
            yield _sse({"error": "No question plan could be compiled."}, event="error")
            return

        general_instructions = build_general_instructions(
            plan, subject_raw, class_num, instructions=instructions
        )
        summary = summarize_question_plan(plan)

    # ── Chapter source material ─────────────────────────────────────────
    yield _sse(
        {"stage": "reading_chapter", "message": "Reading the chapter…"},
        event="status",
    )

    chapter = build_chapter_markdown(
        pdf_source_ids=pdf_source_ids, hsat_source_ids=hsat_source_ids
    )
    if chapter.is_empty:
        yield _sse(
            {
                "error": "No readable content was found in the selected sources. "
                "Check that the upload finished processing, then try again."
            },
            event="error",
        )
        return

    chapter_name = infer_chapter_name(chapter, fallback=topic or "Generated Chapter")

    yield _sse(
        {
            "total": len(plan),
            "subject": subject_label,
            "class": class_num,
            "blueprint": master_blueprint,
            "summary": summary,
            "generalInstructions": general_instructions,
        },
        event="plan",
    )

    # ── Model 1 + image stage ───────────────────────────────────────────
    # The pool is sized to over-provision the blueprint so Model 2 has real
    # choice; a 38-slot paper draws on ~84 questions.
    target_total = max(len(plan) * 2, 40)

    yield _sse(
        {
            "stage": "generating_pool",
            "message": f"Writing a pool of ~{target_total} questions from the chapter…",
            "chapter": chapter_name,
            "chapterChars": chapter.char_count,
        },
        event="status",
    )

    pool_questions: List[PoolQuestion] = []
    outcome: Dict[str, Any] = {}

    for item in _build_pool_streaming(
        chapter=chapter,
        subject=subject_label,
        subject_norm=subject_norm,
        chapter_name=chapter_name,
        class_num=class_num,
        difficulty=difficulty,
        target_total=target_total,
        user=user,
    ):
        if isinstance(item, PoolQuestion):
            pool_questions.append(item)
            # Progress only — these are pool questions, not paper questions.
            # The paper is assembled after the pool is complete.
            yield _sse(
                {
                    "stage": "pool_progress",
                    "produced": len(pool_questions),
                    "target": target_total,
                },
                event="status",
            )
        elif isinstance(item, dict):
            outcome = item

    if outcome.get("error"):
        yield _sse({"error": outcome["error"]}, event="error")
        return

    if not pool_questions:
        yield _sse(
            {
                "error": "No questions could be generated from this chapter. The "
                "source may be too short or unreadable."
            },
            event="error",
        )
        return

    pool_result = outcome.get("pool")
    image_result = outcome.get("images")
    pool_id = getattr(pool_result, "pool_id", "") or ""

    summary_stats = pool_summary(pool_questions)
    yield _sse(
        {
            "poolId": pool_id,
            "chapter": chapter_name,
            **summary_stats,
            "imageStrategy": resolve_strategy(),
            "imagesGenerated": getattr(image_result, "generated_count", 0),
            "imagesReused": getattr(image_result, "reused_count", 0),
            "imageCacheHits": getattr(image_result, "cache_hits", 0),
            "estimatedImageCostUsd": round(
                getattr(image_result, "estimated_cost_usd", 0.0), 4
            ),
        },
        event="pool",
    )

    # ── Auto-save ───────────────────────────────────────────────────────
    # Runs before assembly so the bank keeps the WHOLE pool, not just the
    # questions this particular paper happened to use. That is what makes
    # "Create Paper from Saved Questions" worth having.
    persist = store.persist_pool(
        user=user,
        questions=pool_questions,
        subject=subject_label,
        chapter=chapter_name,
        class_num=class_num,
    )
    if persist.ok:
        yield _sse(
            {
                "saved": persist.saved,
                "duplicatesSkipped": persist.duplicates_skipped,
                "projectName": persist.project_name,
                "projectId": persist.project_id,
                "message": (
                    f"{persist.saved} question(s) saved to your question bank"
                    + (
                        f" ({persist.duplicates_skipped} already there)."
                        if persist.duplicates_skipped
                        else "."
                    )
                ),
            },
            event="saved",
        )
    else:
        yield _sse(
            {
                "message": "Questions were generated but could not be saved to "
                f"your question bank: {persist.error}"
            },
            event="warning",
        )

    # ── Model 2 ─────────────────────────────────────────────────────────
    yield _sse(
        {"stage": "assembling", "message": "Selecting questions for the paper…"},
        event="status",
    )

    try:
        paper = assemble_paper(
            pool_questions,
            plan,
            subject=subject_label,
            class_num=class_num,
            difficulty=difficulty,
            user=user,
        )
    except PaperAssemblyError as exc:
        yield _sse({"error": str(exc)}, event="error")
        return

    # ── Emit the assembled paper ────────────────────────────────────────
    result: Dict[str, Any] = {
        "sections": [],
        "generalInstructions": general_instructions,
        "meta": {},
    }

    ordered = sorted(
        paper.assignments, key=lambda a: int(getattr(a.slot, "index", 0) or 0)
    )
    for assignment in ordered:
        section_title = str(
            getattr(assignment.slot, "section_title", "") or "Questions"
        )
        wire = _question_to_wire(
            assignment.question,
            slot=assignment.slot,
            section_title=section_title,
            or_choice=assignment.or_choice,
            include_vi_alternatives=include_vi_alternatives,
        )
        if assignment.swapped_by_review:
            wire["metadata"]["reviewSwapped"] = True

        section = _find_or_create_section(result, section_title)
        section["questions"].append(wire)

        yield _sse(
            {
                "index": int(getattr(assignment.slot, "index", 0) or 0),
                "total": len(plan),
                "section": section_title,
                "question": wire,
                "sourceType": assignment.question.source_type,
            },
            event="question",
        )

    # Restore the blueprint's declared section order — sections are created in
    # slot order above, but a plan may declare an order the slot indices alone
    # do not imply.
    if not is_gim:
        plan_order = paper_plan_section_order(plan)
        if plan_order:
            position = {title: i for i, title in enumerate(plan_order)}
            result["sections"].sort(
                key=lambda s: position.get(s.get("title", ""), len(position))
            )

    if not is_gim:
        result["generalInstructions"] = build_realized_general_instructions(
            result,
            subject_raw,
            class_num,
            scope_policy="strict",
            fallback_count=0,
            requested_count=len(plan),
        )

    synthetic_count = sum(
        1 for a in paper.assignments if a.question.source_type == "synthetic_image"
    )
    result["meta"] = {
        "poolId": pool_id,
        "chapter": chapter_name,
        "totalQuestions": paper.total_questions,
        "totalMarks": paper.total_marks,
        "poolSize": len(pool_questions),
        "unfilledSlots": len(paper.unfilled),
        "reviewApplied": paper.review_applied,
        "reviewSwaps": paper.review_swaps,
        "syntheticImageCount": synthetic_count,
        "savedToBank": persist.saved,
        "footerNotes": [],
    }

    if synthetic_count:
        result["meta"]["footerNotes"].append(
            "‡ Questions marked with a double dagger use an AI-generated "
            "diagram. Review the figure before using this paper in an exam."
        )

    yield _sse(result, event="update")

    if paper.unfilled:
        reasons = {u.reason for u in paper.unfilled}
        yield _sse(
            {
                "requested": len(plan),
                "realized": paper.total_questions,
                "message": (
                    f"{len(paper.unfilled)} of {len(plan)} blueprint slots could "
                    "not be filled from this chapter's question pool "
                    f"({'; '.join(sorted(reasons))}). Upload more chapters for a "
                    "complete paper."
                ),
            },
            event="notice",
        )

    if synthetic_count:
        yield _sse(
            {
                "message": (
                    f"{synthetic_count} question(s) use an AI-generated diagram. "
                    "Check each figure before using this paper in an exam."
                ),
                "syntheticImageCount": synthetic_count,
            },
            event="notice",
        )

    if image_result and image_result.failures:
        logger.warning("Image stage reported failures: %s", image_result.failures)

    try:
        GenerationHistory.objects.create(
            prompt=json.dumps(
                {"blueprint": master_blueprint, "chapter": chapter_name},
                ensure_ascii=False,
            ),
            settings={
                "engine": "pool",
                "poolId": pool_id,
                "topic": topic,
                "count": count,
                "difficulty": difficulty,
                "subject": subject_label,
                "class": class_num,
                "pdfSourceIds": pdf_source_ids,
                "hsatSourceIds": hsat_source_ids,
                "instructions": instructions,
                "poolSize": len(pool_questions),
                "blueprintTotal": len(plan),
                "realizedTotal": paper.total_questions,
                "savedToBank": persist.saved,
                "duplicatesSkipped": persist.duplicates_skipped,
                "reviewApplied": paper.review_applied,
                "reviewSwaps": paper.review_swaps,
                "imageStrategy": resolve_strategy(),
                "syntheticImageCount": synthetic_count,
            },
            result=result,
            user=user,
        )
    except Exception as exc:
        logger.warning("Could not persist generation history: %s", exc)

    logger.info(
        "Pool pipeline complete: pool=%s %d questions from a pool of %d in %.1fs",
        pool_id, paper.total_questions, len(pool_questions), time.monotonic() - started,
    )

    yield _sse({"done": True, "result": result}, event="done")
