"""Create a paper from questions already in the user's bank.

This is the payoff of persisting the pool per-row. A chapter that has been
generated once never needs Model 1 again: the bank already holds ~84 questions
for it, so building another paper is a single Model 2 review call — roughly
two orders of magnitude cheaper than a fresh generation, and near-instant.

Reuses the same blueprint compiler and the same Model 2 as the live pipeline;
the only difference is where the pool comes from.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Iterable, List, Optional

from apps.generation.models import GenerationHistory
from services.pool import store
from services.pool.model2 import PaperAssemblyError, assemble_paper
from services.pool.pipeline import (
    _find_or_create_section,
    _GimSlot,
    _legacy_type_for,
    _question_to_wire,
    _sse,
)

logger = logging.getLogger("[POOL_FROM_BANK]")


def stream_paper_from_bank(
    user,
    *,
    subject: str = "",
    class_num: int = 10,
    chapters: Optional[List[str]] = None,
    project_ids: Optional[List[str]] = None,
    topic: str = "",
    difficulty: str = "medium",
    instructions: str = "",
    count: int = -1,
    count_variation: str = "cbse",
    qp_type: str = "board",
    deterministic: bool = False,
    payload: Optional[dict] = None,
) -> Iterable[str]:
    """Assemble a paper from saved questions. Model 1 never runs."""
    from services.generation_router import (
        build_blueprint_instructions,
        build_general_instructions,
        build_question_plan,
        build_realized_general_instructions,
        normalize_subject,
        paper_plan_section_order,
        resolve_maths_basic,
        summarize_question_plan,
    )
    from services.generation_service import _parse_gim_instructions

    payload = payload or {}
    started = time.monotonic()
    subject_norm = normalize_subject(subject)
    is_gim = str(qp_type or "").strip().lower() == "general_instructions"

    # ── Load the bank ───────────────────────────────────────────────────
    yield _sse(
        {"stage": "loading_bank", "message": "Loading your saved questions…"},
        event="status",
    )

    pool = store.load_bank(
        user=user,
        subject=subject or None,
        chapters=chapters,
        class_num=class_num,
        project_ids=project_ids,
    )

    if not pool:
        yield _sse(
            {
                "error": "No saved questions match this selection. Generate a "
                "paper from a chapter first, or widen the subject/chapter filter."
            },
            event="error",
        )
        return

    # ── Blueprint ───────────────────────────────────────────────────────
    if is_gim:
        if not instructions.strip():
            yield _sse(
                {
                    "error": "General Instructions Mode requires you to describe "
                    "what questions you want."
                },
                event="error",
            )
            return

        parsed = _parse_gim_instructions(
            instructions, 1, count if count and count > 0 else None
        )
        if not parsed:
            yield _sse(
                {
                    "error": "Could not parse any question specifications from "
                    "your instructions."
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
        subject_label = subject or "General"
    else:
        subject_label = (
            "Social Science" if subject_norm == "social science" else (subject or "Science")
        )
        try:
            plan = list(
                build_question_plan(
                    topic=topic,
                    difficulty=difficulty,
                    count=count,
                    class_num=class_num,
                    subject=subject or "Science",
                    instructions=instructions,
                    count_variation=count_variation,
                )
            )
            master_blueprint = build_blueprint_instructions(
                topic=topic,
                difficulty=difficulty,
                count=count,
                class_num=class_num,
                subject=subject or "Science",
                plan=plan,
                maths_basic=resolve_maths_basic(subject or "Science", payload),
            )
        except Exception as exc:
            logger.error("Blueprint compilation failed: %s", exc, exc_info=True)
            yield _sse({"error": str(exc)}, event="error")
            return

        if not plan:
            yield _sse({"error": "No question plan could be compiled."}, event="error")
            return

        general_instructions = build_general_instructions(
            plan, subject or "Science", class_num, instructions=instructions
        )
        summary = summarize_question_plan(plan)

    yield _sse(
        {
            "total": len(plan),
            "subject": subject_label,
            "class": class_num,
            "blueprint": master_blueprint,
            "summary": summary,
            "generalInstructions": general_instructions,
            "fromBank": True,
            "bankSize": len(pool),
        },
        event="plan",
    )

    # ── Model 2 ─────────────────────────────────────────────────────────
    yield _sse(
        {
            "stage": "assembling",
            "message": f"Selecting {len(plan)} questions from {len(pool)} saved…",
        },
        event="status",
    )

    try:
        paper = assemble_paper(
            pool,
            plan,
            subject=subject_label,
            class_num=class_num,
            difficulty=difficulty,
            chapters=chapters,
            # `deterministic` skips the review call, so the same bank + blueprint
            # always yields the identical paper.
            use_review=not deterministic,
            user=user,
        )
    except PaperAssemblyError as exc:
        yield _sse({"error": str(exc)}, event="error")
        return

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
        )
        wire["metadata"]["fromBank"] = True
        if assignment.swapped_by_review:
            wire["metadata"]["reviewSwapped"] = True

        _find_or_create_section(result, section_title)["questions"].append(wire)

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

    if not is_gim:
        plan_order = paper_plan_section_order(plan)
        if plan_order:
            position = {title: i for i, title in enumerate(plan_order)}
            result["sections"].sort(
                key=lambda s: position.get(s.get("title", ""), len(position))
            )
        result["generalInstructions"] = build_realized_general_instructions(
            result,
            subject or "Science",
            class_num,
            scope_policy="strict",
            fallback_count=0,
            requested_count=len(plan),
        )

    synthetic_count = sum(
        1 for a in paper.assignments if a.question.source_type == "synthetic_image"
    )
    result["meta"] = {
        "fromBank": True,
        "bankSize": len(pool),
        "totalQuestions": paper.total_questions,
        "totalMarks": paper.total_marks,
        "unfilledSlots": len(paper.unfilled),
        "reviewApplied": paper.review_applied,
        "reviewSwaps": paper.review_swaps,
        "syntheticImageCount": synthetic_count,
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
                    f"{len(paper.unfilled)} of {len(plan)} slots could not be "
                    f"filled from your saved questions ({'; '.join(sorted(reasons))}). "
                    "Generate from more chapters to widen the bank."
                ),
            },
            event="notice",
        )

    try:
        GenerationHistory.objects.create(
            prompt=json.dumps(
                {"blueprint": master_blueprint, "source": "question_bank"},
                ensure_ascii=False,
            ),
            settings={
                "engine": "pool_from_bank",
                "subject": subject_label,
                "class": class_num,
                "chapters": list(chapters or []),
                "projectIds": list(project_ids or []),
                "bankSize": len(pool),
                "blueprintTotal": len(plan),
                "realizedTotal": paper.total_questions,
                "deterministic": deterministic,
                "reviewApplied": paper.review_applied,
                "reviewSwaps": paper.review_swaps,
            },
            result=result,
            user=user,
        )
    except Exception as exc:
        logger.warning("Could not persist generation history: %s", exc)

    logger.info(
        "Paper from bank: %d questions from %d saved in %.2fs (Model 1 skipped)",
        paper.total_questions, len(pool), time.monotonic() - started,
    )

    yield _sse({"done": True, "result": result}, event="done")
