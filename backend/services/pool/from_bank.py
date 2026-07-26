"""Create a paper from questions already in the user's bank.

This is the payoff of persisting the pool per-row. A chapter that has been
generated once never needs Model 1 again: the bank already holds ~84 questions
for it, so building another paper is a single Model 2 review call — roughly
two orders of magnitude cheaper than a fresh generation, and near-instant.

Reuses the same blueprint compiler and the same Model 2 as the live pipeline;
the only difference is where the pool comes from.

One wrinkle the asset split introduces: the bank is selected by chapter, and
Reading, Grammar and Writing assets have no chapter. They are loaded separately
(by subject and class) and, for any asset slot the bank still cannot cover, the
generators run to fill the gap. Without that, "Create Paper from Saved
Questions" would quietly return an English paper missing 40 of its 80 marks.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Iterable, List, Optional

from apps.generation.models import GenerationHistory
from services.assets import (
    DEFAULT_GENERATOR,
    generate_assets_for_plan,
    partition_plan,
)
from services.assets.registry import routing_summary
from services.assets.store import load_reusable_assets
from services.pool import store
from services.pool.model2 import PaperAssemblyError, assemble_paper
from services.pool.schema import slot_accepts
from services.pool.pipeline import (
    _build_variant_results,
    _find_or_create_section,
    _GimSlot,
    _legacy_type_for,
    _persist_pool_by_chapter,
    _question_to_wire,
    _resolve_num_sets,
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
    from services.pool.gim import _parse_gim_instructions

    payload = payload or {}
    started = time.monotonic()
    subject_norm = normalize_subject(subject)
    is_gim = str(qp_type or "").strip().lower() == "general_instructions"
    num_sets = _resolve_num_sets(payload)

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

    # The empty-bank check is deliberately NOT here. A blueprint whose slots
    # are owned by asset generators can be filled without a single saved
    # question, so "is there anything to work with" can only be answered after
    # the plan is compiled and the asset stage has run.

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

    routing = routing_summary(plan)
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
            "sets": num_sets,
            "routing": routing,
        },
        event="plan",
    )

    # ── Asset slots ─────────────────────────────────────────────────────
    # Assets have no chapter, so the chapter-scoped bank query above cannot see
    # them. Load them by subject and class instead, then generate only what the
    # bank still cannot cover — the cheap path stays cheap for a user who has
    # generated an English paper before.
    asset_reports: List[Dict[str, Any]] = []
    asset_result = None
    routed = partition_plan(plan)
    asset_slots = [
        slot
        for name, slots in routed.items()
        if name != DEFAULT_GENERATOR
        for slot in slots
    ]

    if asset_slots:
        known_ids = {q.id for q in pool}
        banked_assets = [
            q
            for q in load_reusable_assets(
                user=user,
                subject=subject_label,
                class_num=class_num,
                generators=[n for n in routed if n != DEFAULT_GENERATOR],
            )
            if q.id not in known_ids
        ]
        pool.extend(banked_assets)

        uncovered = [
            slot
            for slot in asset_slots
            if not any(slot_accepts(q, slot) for q in pool)
        ]
        if uncovered:
            yield _sse(
                {
                    "stage": "generating_assets",
                    "message": (
                        f"Writing {len(uncovered)} question(s) your bank does not "
                        "cover yet…"
                    ),
                },
                event="status",
            )
            asset_result, asset_reports = generate_assets_for_plan(
                uncovered,
                subject=subject_label,
                subject_norm=subject_norm,
                class_num=class_num,
                difficulty=difficulty,
                user=user,
                # These already came back from the bank above; asking the
                # store for them again would just re-run the same query.
                reuse=False,
            )
            pool.extend(asset_result.questions)
            # Bank them, so the next paper for this subject takes the cheap
            # path and this whole branch is skipped.
            if asset_result.questions:
                banked = _persist_pool_by_chapter(
                    user=user,
                    questions=asset_result.questions,
                    subject=subject_label,
                    class_num=class_num,
                )
                if not banked.ok:
                    logger.warning(
                        "Could not bank generated assets: %s", banked.error
                    )
            for report in asset_reports:
                if report.get("failures"):
                    yield _sse(
                        {
                            "message": (
                                f"{report['label']} reported a problem: "
                                + "; ".join(str(f) for f in report["failures"])
                            )
                        },
                        event="warning",
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
        "routing": routing,
        "assetGenerators": asset_reports,
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

    # ── Additional sets (B, C) ──────────────────────────────────────────
    variant_sets: List[Dict[str, Any]] = []
    if num_sets > 1:
        try:
            variant_sets = _build_variant_results(
                master_assignments=paper.assignments,
                pool=pool,
                num_variants=num_sets - 1,
                section_order=[s.get("title", "") for s in result["sections"]],
                general_instructions=result["generalInstructions"],
                include_vi_alternatives=True,
                base_meta=result["meta"],
            )
        except Exception as exc:
            logger.warning("Set variant generation failed: %s", exc, exc_info=True)
            variant_sets = []

        for entry in variant_sets:
            yield _sse(
                {
                    "label": entry["label"],
                    "setIndex": entry["setIndex"],
                    "totalSets": num_sets,
                    "replacedCount": entry["replacedCount"],
                    "result": entry["result"],
                },
                event="set",
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
        "Paper from bank: %d questions from %d saved in %.2fs (Model 1 skipped, "
        "%d set(s))",
        paper.total_questions, len(pool), time.monotonic() - started,
        len(variant_sets) + 1,
    )

    done_payload: Dict[str, Any] = {"done": True, "result": result}
    if variant_sets:
        done_payload["sets"] = [
            {"label": "A", "setIndex": 0, "result": result},
            *(
                {
                    "label": e["label"],
                    "setIndex": e["setIndex"],
                    "result": e["result"],
                }
                for e in variant_sets
            ),
        ]
    yield _sse(done_payload, event="done")
