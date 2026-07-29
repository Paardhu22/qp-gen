"""The paper generation pipeline.

                        blueprint (routing engine)
                                  │
              ┌───────────────────┴────────────────────┐
              │                                        │
   slots naming an asset generator          slots naming `question_pool`
              │                                        │
   services.assets.runner                      chapter Markdown
   (reading / grammar / writing,                       │
    run in parallel, NO uploads)                   Model 1  ─────────┐
              │                                        │   (parallel batches)
              │                                  image stage ────────┤
              │                                        │             │
              └───────────────┬────────────────────────┴─────────────┘
                              ▼
                      merged Question Pool ──→ auto-saved to the user's bank
                              │
                              ▼
                          Model 2  ──→ assembled paper ──→ SSE
                                                            │
                                                            ▼
                                                       TipTap editor

Two things decide everything downstream, and both come from the blueprint:
which generator owns a slot, and — following from that — whether the uploaded
textbook is read at all. Science, Social Science and Mathematics declare no
generators, so every slot routes to `question_pool` and this file behaves
exactly as it did before the split. English routes Reading, Grammar and Writing
to independent generators that are never handed chapter text, and only its
Literature section reaches Model 1.

The blueprint layer still decides what a paper must contain — that is the
pedagogical core and was never the expensive part. What the pool changed was
how textbook questions are produced (one whole-chapter read instead of one
retrieval plus one LLM call per slot); what the asset split changes is *which*
questions come from the textbook at all.

The SSE contract is preserved exactly (`plan`, `question`, `update`, `notice`,
`warning`, `done`, and the question object's field names) so the editor,
review tray and auto-insert paths keep working without frontend changes. The
`plan` event gained an additive `routing` key; consumers that do not read it
are unaffected.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.conf import settings
from django.db import close_old_connections

from apps.generation.models import GenerationHistory
from services.assets import (
    DEFAULT_GENERATOR,
    generate_assets_for_plan,
    partition_plan,
)
from services.assets.registry import routing_summary
from services.pool import store
from services.pool.chapters import Chapter, build_chapters, split_chapter
from services.pool.image_model import (
    ImageQuestionResult,
    generate_image_questions,
    resolve_strategy,
)
from services.pool.model1 import PoolGenerationResult, generate_question_pool
from services.pool.model2 import PaperAssemblyError, assemble_paper
from services.pool.rendering import or_label_for, printable_content
from services.pool.schema import PoolQuestion, normalize_type, pool_summary
from utils.ids import generate_id

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


@dataclass
class _PoolGenerationUnit:
    """One bounded Model 1 input.

    `chapter` may be a whole detected chapter or one semantic section split
    from an oversized chapter. `bank_chapter` is the parent chapter name used
    for persistence/dedup so section splits merge back into one chapter pool.
    """

    chapter: Chapter
    bank_chapter: str
    target_total: int
    image_count: int = 0
    #: The slice of the blueprint this unit generates for, when the pool is
    #: spread across chapters (see `_distribute_plan_shapes`). `None` means the
    #: unit uses the caller's whole recipe plan — the behaviour for every
    #: upload small enough that spreading is unnecessary.
    plan_subset: Optional[Sequence[Any]] = None


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
            # Provenance is stamped explicitly rather than inherited from
            # `question.metadata`, which is only populated for asset questions.
            # Every question on the wire says where it came from, so a consumer
            # never has to infer it from the section heading.
            "generator": question.generator,
            "assetType": question.asset_type,
            "usesUploadedContent": question.uses_uploaded_content,
            "questionId": question.id,
            "poolId": question.pool_id,
            "subject": question.subject,
            "inferredChapter": question.chapter,
            "inferredTopic": question.topic,
            "marks": question.marks,
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


def _int_or_none(value: Any) -> Optional[int]:
    """A positive int, or None. Forms send "", "80", 80 and None for the same field."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _resolve_num_sets(payload: dict) -> int:
    """Clamp the requested set count to the supported 1–3 range.

    Accepts `sets`, `numberOfSets`, or `setCount` (snake/camel from the form).
    Anything unparseable falls back to a single set — the default that keeps
    behaviour identical to a build that never heard of multiple sets.
    """
    raw = payload.get(
        "sets", payload.get("numberOfSets", payload.get("setCount", 1))
    )
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 1
    return max(1, min(3, value))


def _render_variant_result(
    variant,
    *,
    section_order: List[str],
    general_instructions: List[Any],
    include_vi_alternatives: bool,
    base_meta: Dict[str, Any],
) -> Dict[str, Any]:
    """Render a derived set into the same `result` shape Set A emits.

    `variant.assignments` are already in display order (shuffled within their
    sections), so they are rendered in list order and NOT re-sorted by slot
    index — that would undo the shuffle the variant exists to introduce. The
    section order is realigned to the master's so every set opens with the
    same sections in the same sequence.
    """
    result: Dict[str, Any] = {
        "sections": [],
        "generalInstructions": list(general_instructions or []),
        "meta": {},
    }

    for assignment in variant.assignments:
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
        wire["metadata"]["setLabel"] = variant.label
        _find_or_create_section(result, section_title)["questions"].append(wire)

    if section_order:
        position = {title: i for i, title in enumerate(section_order)}
        result["sections"].sort(
            key=lambda s: position.get(s.get("title", ""), len(position))
        )

    total_questions = sum(len(s["questions"]) for s in result["sections"])
    total_marks = sum(
        int(w.get("marks", 0) or 0)
        for s in result["sections"]
        for w in s["questions"]
    )
    synthetic_count = sum(
        1
        for a in variant.assignments
        if a.question.source_type == "synthetic_image"
    )

    carried = {
        k: v
        for k, v in (base_meta or {}).items()
        if k in ("poolId", "chapter", "poolSize", "fromBank", "bankSize")
    }
    footer_notes: List[str] = []
    if synthetic_count:
        footer_notes.append(
            "‡ Questions marked with a double dagger use an AI-generated "
            "diagram. Review the figure before using this paper in an exam."
        )
    result["meta"] = {
        **carried,
        "setLabel": variant.label,
        "isVariant": True,
        "totalQuestions": total_questions,
        "totalMarks": total_marks,
        "replacedCount": variant.replaced_count,
        "retainedCount": variant.retained_count,
        "fixedCount": variant.fixed_count,
        "syntheticImageCount": synthetic_count,
        "footerNotes": footer_notes,
    }
    return result


def _build_variant_results(
    *,
    master_assignments: Sequence[Any],
    pool: Sequence[PoolQuestion],
    num_variants: int,
    section_order: List[str],
    general_instructions: List[Any],
    include_vi_alternatives: bool,
    base_meta: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Derive and render the extra sets (B, C) from an assembled master.

    Returns one entry per variant: `{"label", "setIndex", "result",
    "replacedCount"}`. Never raises — variant generation is best-effort and
    must never jeopardise Set A, which the caller has already delivered.
    """
    from services.pool.set_variants import derive_variants

    variants = derive_variants(master_assignments, pool, num_variants=num_variants)
    out: List[Dict[str, Any]] = []
    for i, variant in enumerate(variants):
        result = _render_variant_result(
            variant,
            section_order=section_order,
            general_instructions=general_instructions,
            include_vi_alternatives=include_vi_alternatives,
            base_meta=base_meta,
        )
        out.append(
            {
                "label": variant.label,
                "setIndex": i + 1,
                "result": result,
                "replacedCount": variant.replaced_count,
            }
        )
    return out


def _build_pool_streaming(
    *,
    units: Sequence[_PoolGenerationUnit],
    subject: str,
    subject_norm: str,
    class_num: int,
    difficulty: str,
    pool_id: str,
    user,
    plan: Optional[Sequence[Any]] = None,
) -> Iterable[Any]:
    """Run per-chapter Model 1 + image stages on workers, yielding progress.

    Each unit is already bounded by `split_chapter`. Units run with bounded
    chapter concurrency; inside each unit Model 1 still uses its process-wide
    request semaphore, so chapter_count × batch_count can never fan out into
    unbounded API streams.
    """
    progress: "queue.Queue[Any]" = queue.Queue()
    outcome: Dict[str, Any] = {}

    def _metadata_for(unit: _PoolGenerationUnit) -> Dict[str, Any]:
        metadata = unit.chapter.question_metadata()
        metadata["chapterTitle"] = unit.bank_chapter
        metadata["sourceDocument"] = metadata.get("sourcePdf")
        if unit.chapter.title != unit.bank_chapter:
            metadata["semanticSection"] = unit.chapter.title
        for key in ("sectionIndex", "sectionCount"):
            if key in unit.chapter.metadata:
                metadata[key] = unit.chapter.metadata[key]
        return metadata

    def _run_unit(unit: _PoolGenerationUnit):
        metadata = _metadata_for(unit)
        result = generate_question_pool(
            chapter=unit.chapter,
            subject=subject,
            subject_norm=subject_norm,
            chapter_name=unit.bank_chapter,
            class_num=class_num,
            difficulty=difficulty,
            target_total=unit.target_total,
            user=user,
            pool_id=pool_id,
            question_metadata=metadata,
            on_question=progress.put,
            plan=unit.plan_subset if unit.plan_subset else plan,
        )

        image_result = generate_image_questions(
            chapter=unit.chapter,
            subject=subject,
            chapter_name=unit.bank_chapter,
            class_num=class_num,
            pool_id=pool_id,
            difficulty=difficulty,
            count=unit.image_count,
            user=user,
            question_metadata=metadata,
            on_question=progress.put,
        )
        # Both stages record API usage, so this thread has opened its own
        # connection. With CONN_MAX_AGE=600 Django hands it back to the pool
        # rather than closing it, and a thread that exits without this call
        # abandons a live Postgres backend — a few dozen generations is enough
        # to hit max_connections. services/hsat_service.py and
        # services/document_service.py do the same in their worker threads.
        close_old_connections()
        return unit, result, image_result

    def _worker():
        try:
            merged = PoolGenerationResult(
                pool_id=pool_id, subject=subject, chapter="Unified Question Bank"
            )
            merged_images = ImageQuestionResult()

            workers = max(1, int(getattr(settings, "POOL_CHAPTER_CONCURRENCY", 3)))
            with ThreadPoolExecutor(max_workers=min(workers, max(1, len(units)))) as executor:
                futures = {executor.submit(_run_unit, unit): unit for unit in units}
                for future in as_completed(futures):
                    unit = futures[future]
                    try:
                        unit, result, image_result = future.result()
                    except Exception as exc:
                        logger.error(
                            "Pool unit failed for %r: %s",
                            unit.bank_chapter,
                            exc,
                            exc_info=True,
                        )
                        merged.batch_failures.append(
                            f"{unit.bank_chapter}: {type(exc).__name__}: {exc}"
                        )
                        continue
                    merged.questions.extend(result.questions)
                    merged.batch_failures.extend(
                        f"{unit.bank_chapter}: {failure}"
                        for failure in result.batch_failures
                    )
                    merged.duplicates_dropped += result.duplicates_dropped
                    merged.invalid_dropped += result.invalid_dropped

                    merged_images.questions.extend(image_result.questions)
                    merged_images.generated_count += image_result.generated_count
                    merged_images.reused_count += image_result.reused_count
                    merged_images.cache_hits += image_result.cache_hits
                    merged_images.failures.extend(
                        f"{unit.bank_chapter}: {failure}"
                        for failure in image_result.failures
                    )
                    merged_images.estimated_cost_usd += image_result.estimated_cost_usd

            outcome["pool"] = merged
            outcome["images"] = merged_images
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


def _unit_weight(chapter: Chapter) -> int:
    return max(1, int(chapter.estimated_tokens or (chapter.char_count // 4) or 1))


def _allocate_targets(
    items: Sequence[Chapter],
    *,
    total: int,
    min_each: int = 0,
) -> List[int]:
    """Weighted integer allocation with an optional floor per item."""
    if not items:
        return []
    if total <= 0:
        return [0 for _ in items]

    floor = max(0, int(min_each or 0))
    if floor and total <= floor * len(items):
        return [floor for _ in items]

    allocation = [floor for _ in items]
    remaining = max(0, total - sum(allocation))
    if remaining == 0:
        return allocation

    weights = [_unit_weight(item) for item in items]
    total_weight = sum(weights) or len(items)
    raw = [(remaining * weight) / total_weight for weight in weights]
    whole = [int(value) for value in raw]
    allocation = [base + extra for base, extra in zip(allocation, whole)]

    leftover = total - sum(allocation)
    order = sorted(
        range(len(items)), key=lambda index: raw[index] - whole[index], reverse=True
    )
    for index in order[:leftover]:
        allocation[index] += 1
    return allocation


def _image_weight(chapter: Chapter) -> int:
    return max(1, len(getattr(chapter, "figures", []) or []))


def _allocate_image_targets(
    units: Sequence["_PoolGenerationUnit"], *, total: int
) -> List[int]:
    """Prefer units that actually carry textbook figures for image questions."""
    if not units:
        return []
    if total <= 0:
        return [0 for _ in units]

    allocation = [0 for _ in units]
    order = sorted(
        range(len(units)),
        key=lambda index: (
            _image_weight(units[index].chapter),
            _unit_weight(units[index].chapter),
        ),
        reverse=True,
    )
    for offset in range(total):
        allocation[order[offset % len(order)]] += 1
    return allocation


# The most images one paper may draw, however many DIAGRAM slots the blueprint
# declares. Matches the upper bound on IMAGE_QUESTIONS_PER_POOL, so an explicit
# request can exceed the configured default but never the hard limit.
EXPLICIT_IMAGE_SLOT_CEILING = 40


def _plan_image_slots(plan: Sequence[Any]) -> int:
    return sum(
        1
        for slot in plan
        if str(getattr(slot, "question_type", "") or "").upper() == "DIAGRAM"
    )


def _contextual_image_total(
    *,
    plan: Sequence[Any],
    chapters: Sequence[Chapter],
    subject_norm: str,
    configured_cap: int,
) -> int:
    """Pick a small, subject-aware image budget for the pool.

    Explicit DIAGRAM slots are honoured first. Otherwise image questions are
    supplemental, so they should help the final paper without dominating cost
    or hammering the image API.
    """
    cap = max(0, int(configured_cap or 0))
    # A configured cap of zero is the deliberate off switch — no images at all,
    # however many the plan asks for. Honour it before anything else.
    if cap <= 0 or not plan:
        return 0

    diagram_slots = _plan_image_slots(plan)
    if diagram_slots:
        # An explicitly requested figure slot is not the same thing as a
        # supplemental one. `IMAGE_QUESTIONS_PER_POOL` exists to stop images the
        # teacher never asked for from dominating the bill; clamping an explicit
        # ask to it means someone who types "10 image based questions" silently
        # gets eight, with nothing saying why. The blueprint is the teacher's,
        # so it wins — bounded by the hard ceiling that keeps a runaway plan
        # from becoming a runaway invoice.
        return min(EXPLICIT_IMAGE_SLOT_CEILING, diagram_slots)

    subject = (subject_norm or "").strip().lower()
    if subject in {"english", "hindi", "telugu", "sanskrit"}:
        return 0

    available_figures = sum(
        len(getattr(chapter, "figures", []) or []) for chapter in chapters
    )
    if subject in {"science", "mathematics", "maths", "math"}:
        desired = max(1, min(3, len(plan) // 12))
    elif subject == "social science":
        desired = 1 if available_figures else 0
    else:
        desired = 1 if available_figures else 0

    if available_figures:
        desired = min(desired, available_figures)
    return min(cap, desired)


def _plan_shape_groups(plan: Sequence[Any]) -> List[List[Any]]:
    """Group a plan's slots by the (type, marks, asset_type) shape they ask for.

    Mirrors the keying `recipes.batches_from_plan` uses, so one group here is
    exactly one Model 1 batch there.
    """
    groups: Dict[Any, List[Any]] = {}
    order: List[Any] = []
    for slot in plan or []:
        qtype = normalize_type(getattr(slot, "question_type", "") or "")
        if not qtype:
            continue
        try:
            marks = int(getattr(slot, "marks", 0) or 0)
        except (TypeError, ValueError):
            continue
        if marks <= 0:
            continue
        key = (qtype, marks, str(getattr(slot, "asset_type", "") or ""))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(slot)
    return [groups[key] for key in order]


def _distribute_plan_shapes(
    units: Sequence["_PoolGenerationUnit"],
    plan: Optional[Sequence[Any]],
    *,
    target_total: int,
) -> None:
    """Spread the blueprint's question shapes across units, in place.

    `recipes.batches_from_plan` floors every shape it is given at one question
    so that no blueprint shape is missing from the pool — `slot_accepts` matches
    on EXACT marks, and a shape the pool lacks leaves its slot unfillable. That
    floor is per Model 1 call, so handing every chapter the whole plan makes the
    real pool size `chapters × distinct shapes`, no matter how small a target
    each chapter was allocated. A 20-chapter English upload with 4 literature
    shapes generated 80 questions against a 40-question budget.

    The floor only has to hold once across the *merged* pool, so shapes are
    dealt round-robin instead: every chapter still contributes, every shape is
    still covered (several times over), and the total tracks the budget.

    No-ops when the plan already fits — small uploads keep the previous
    behaviour of asking each chapter for every shape, which gives Model 2 the
    widest choice when there is room for it.
    """
    if not units or not plan or target_total <= 0:
        return
    groups = _plan_shape_groups(plan)
    if len(groups) <= 1:
        return
    if len(groups) * len(units) <= target_total:
        return  # every unit can afford the full plan; leave it alone

    # Deal shapes round-robin so consecutive chapters cover different shapes
    # and each shape recurs every `len(groups)` chapters.
    for index, unit in enumerate(units):
        assigned = groups[index % len(groups)]
        # Give a unit a second shape when its own allocation can pay for it,
        # so a generous budget still buys variety per chapter.
        subset = list(assigned)
        if unit.target_total > 1 and len(groups) > 1:
            subset += list(groups[(index + 1) % len(groups)])
        unit.plan_subset = subset


def _build_generation_units(
    chapters: Sequence[Chapter],
    *,
    target_total: int,
    image_total: int,
    recipe_plan: Optional[Sequence[Any]] = None,
) -> List[_PoolGenerationUnit]:
    """Split oversized chapters and assign text/image quotas to each unit."""
    # POOL_MIN_QUESTIONS_PER_CHAPTER is a *quality* floor — it stops a chapter
    # being represented by one or two questions when only a handful were
    # uploaded. It is not a per-chapter licence to grow the pool: applied
    # unconditionally, `_allocate_targets` returns the floor for every chapter
    # whenever `floor * len(chapters) >= target_total`, so the caller's budget
    # is discarded and the pool becomes 12 × (chapters uploaded). Uploading a
    # full 13-chapter textbook then generated ~160 questions for a 38-slot
    # paper — Model 1 calls, tokens and wall-clock spent on questions no
    # blueprint slot could ever consume.
    #
    # Capping the floor at each chapter's affordable share keeps the intent
    # (never allocate a chapter 0) while honouring `target_total`, so pool size
    # now tracks the blueprint rather than the size of the upload.
    configured_floor = max(
        1, int(getattr(settings, "POOL_MIN_QUESTIONS_PER_CHAPTER", 12))
    )
    affordable_floor = (target_total // len(chapters)) if chapters else 0
    min_per_chapter = max(1, min(configured_floor, affordable_floor))
    chapter_targets = _allocate_targets(
        chapters, total=target_total, min_each=min_per_chapter
    )

    units: List[_PoolGenerationUnit] = []
    for chapter, chapter_target in zip(chapters, chapter_targets):
        sections = split_chapter(chapter)
        # Same reasoning as the chapter floor above, one level down. A chapter
        # split into more sections than its own allocation cannot give each
        # section a question without exceeding that allocation, so the floor is
        # dropped and the weighted split decides which sections are worth a
        # question. Sections allocated none are skipped rather than rounded up
        # to one — otherwise an 8-way split would silently produce 8 units.
        section_floor = 1 if 0 < len(sections) <= chapter_target else 0
        section_targets = _allocate_targets(
            sections, total=chapter_target, min_each=section_floor
        )
        chapter_units = [
            _PoolGenerationUnit(
                chapter=section,
                bank_chapter=chapter.title,
                target_total=section_target,
            )
            for section, section_target in zip(sections, section_targets)
            if section_target > 0
        ]
        # A chapter always contributes something: if rounding zeroed every
        # section, keep the largest one with a single question.
        if not chapter_units and sections:
            largest = max(sections, key=lambda s: getattr(s, "char_count", 0) or 0)
            chapter_units = [
                _PoolGenerationUnit(
                    chapter=largest,
                    bank_chapter=chapter.title,
                    target_total=1,
                )
            ]
        units.extend(chapter_units)

    _distribute_plan_shapes(units, recipe_plan, target_total=target_total)

    image_targets = _allocate_image_targets(units, total=image_total)
    for unit, image_count in zip(units, image_targets):
        unit.image_count = image_count
    return units


@dataclass
class _PersistAggregate:
    saved: int = 0
    duplicates_skipped: int = 0
    project_name: str = ""
    project_id: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


def _persist_pool_by_chapter(
    *,
    user,
    questions: Sequence[PoolQuestion],
    subject: str,
    class_num: int,
) -> _PersistAggregate:
    grouped: Dict[str, List[PoolQuestion]] = {}
    for question in questions:
        chapter = question.chapter or "Generated Chapter"
        grouped.setdefault(chapter, []).append(question)

    aggregate = _PersistAggregate()
    project_names: List[str] = []
    project_ids: List[str] = []

    for chapter, chapter_questions in grouped.items():
        result = store.persist_pool(
            user=user,
            questions=chapter_questions,
            subject=subject,
            chapter=chapter,
            class_num=class_num,
        )
        aggregate.saved += result.saved
        aggregate.duplicates_skipped += result.duplicates_skipped
        if result.project_name:
            project_names.append(result.project_name)
        if result.project_id:
            project_ids.append(result.project_id)
        if not result.ok:
            aggregate.error = result.error
            break

    if len(project_names) == 1:
        aggregate.project_name = project_names[0]
        aggregate.project_id = project_ids[0] if project_ids else ""
    elif project_names:
        aggregate.project_name = f"{len(project_names)} chapter projects"
        aggregate.project_id = ",".join(project_ids)
    return aggregate


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

    # ── Authoritative source-readiness gate ─────────────────────────────────
    # The async upload flow returns a PdfSource id before ingestion finishes, so
    # readiness can no longer be assumed from "the client has an id". Validate
    # here — ownership-scoped, ready-state, and persisted-chunk checks — BEFORE
    # any blueprint / chapter work. A not-ready source would otherwise build an
    # empty/thin chapter and dead-end on the generic "No questions could be
    # generated" error; instead emit a dedicated DOCUMENTS_NOT_READY event with
    # the offending documents. This is the source of truth; the frontend gate is
    # only UX. (Skipped when no sources are supplied — e.g. instruction-only
    # flows — so those keep their existing downstream handling.)
    if pdf_source_ids or hsat_source_ids:
        from services.source_readiness import (
            build_not_ready_payload,
            check_sources_ready,
        )

        pending_sources = check_sources_ready(
            user=user,
            pdf_source_ids=pdf_source_ids,
            hsat_source_ids=hsat_source_ids,
        )
        if pending_sources:
            yield _sse(build_not_ready_payload(pending_sources), event="error")
            return

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

    # How many parallel sets to emit. Set A is always produced; 2 adds Set B,
    # 3 adds Set C. The pool and Model 1 run once regardless — B and C are
    # derived from A's selection, never freshly generated.
    num_sets = _resolve_num_sets(payload)

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

        # The design may already have been computed by `/design-paper` while
        # the teacher was reviewing it. Reusing it keeps the paper they
        # approved — re-designing here would spend a second model call and
        # could return a different structure than the one they said yes to.
        from services.paper_design import (
            PaperDesign,
            _design_from_raw,
            design_paper,
            design_to_slot_specs,
            header_lines,
            validate_design,
        )

        exact_count = count if count and count > 0 else None
        approved = payload.get("design") or payload.get("paperDesign")
        if isinstance(approved, dict) and approved.get("sections"):
            design: PaperDesign = validate_design(_design_from_raw(approved))
        else:
            design = design_paper(
                instructions,
                subject=subject_raw,
                academic_class=str(class_num),
                total_marks=_int_or_none(payload.get("marks")),
                exact_count=exact_count,
                source_count=len(pdf_source_ids) + len(hsat_source_ids),
                user=user,
            )

        parsed = design_to_slot_specs(design)
        if not parsed:
            yield _sse(
                {
                    "error": "Could not work out a paper from those instructions. "
                    "Try naming what you want — for example '5 MCQs and 3 short "
                    "answers of 2 marks each'."
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
        general_instructions = header_lines(design, {"instructions": instructions})
        summary = {
            "total_questions": len(plan),
            "total_marks": sum(s.marks for s in plan),
        }
        # Anything the validator had to correct is the teacher's to see — a
        # paper that quietly came out 3 marks short is worse than one that
        # says so.
        for correction in design.corrections:
            yield _sse({"message": correction}, event="notice")
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

    # ── Route the blueprint ─────────────────────────────────────────────
    # The single decision this whole file turns on. `routed` says which
    # generator owns which slots; `textbook_slots` is the subset that may see
    # an upload. For every subject that declares no generators — Science,
    # Social Science, Mathematics, Hindi, Telugu, General Instructions mode —
    # `textbook_slots` is the whole plan and nothing below changes behaviour.
    routed = partition_plan(plan)
    textbook_slots: List[Any] = list(routed.get(DEFAULT_GENERATOR) or [])
    asset_slots: List[Any] = [
        slot
        for name, slots in routed.items()
        if name != DEFAULT_GENERATOR
        for slot in slots
    ]
    routing = routing_summary(plan)
    logger.info(
        "Blueprint routing: %s",
        "; ".join(
            f"{entry['generator']}={entry['questions']}q/{entry['marks']}m"
            for entry in routing
        ),
    )

    # ── Chapter source material ─────────────────────────────────────────
    # Read only when some slot actually needs it. An all-asset paper skips
    # this entirely, which is what lets a language paper's Reading, Grammar
    # and Writing sections generate with no upload at all.
    chapters: List[Chapter] = []
    if textbook_slots:
        yield _sse(
            {"stage": "reading_chapters", "message": "Reading source chapters…"},
            event="status",
        )
        chapters = list(
            build_chapters(
                pdf_source_ids=pdf_source_ids, hsat_source_ids=hsat_source_ids
            )
        )

    if textbook_slots and not chapters:
        if not asset_slots:
            yield _sse(
                {
                    "error": "No readable content was found in the selected sources. "
                    "Check that the upload finished processing, then try again."
                },
                event="error",
            )
            return
        # Part of this paper does not need an upload. Drop the textbook slots,
        # keep everything else, and say plainly what will be missing.
        missing_marks = sum(int(getattr(s, "marks", 0) or 0) for s in textbook_slots)
        yield _sse(
            {
                "message": (
                    f"No readable textbook content was found, so the "
                    f"{len(textbook_slots)} question(s) worth {missing_marks} marks "
                    "that draw on the uploaded chapters will be left out. The rest "
                    "of the paper does not need an upload and will be generated."
                )
            },
            event="warning",
        )
        textbook_slots = []

    chapter_name = (
        chapters[0].title
        if len(chapters) == 1
        else (topic or (f"{len(chapters)} chapters" if chapters else subject_label))
    )

    yield _sse(
        {
            "total": len(plan),
            "subject": subject_label,
            "class": class_num,
            "blueprint": master_blueprint,
            "summary": summary,
            "generalInstructions": general_instructions,
            "sets": num_sets,
            # Additive: which generator owns which part of the paper.
            "routing": routing,
        },
        event="plan",
    )

    # ── Generation stage ────────────────────────────────────────────────
    # The textbook pool is sized to over-provision its own slots so Model 2 has
    # real choice; a 38-slot board paper draws on ~84 questions. That total is
    # allocated across detected chapters instead of sending the whole upload to
    # Model 1. Sizing off `textbook_slots` rather than the whole plan is what
    # stops an English paper generating 84 Literature questions for the six
    # slots that can actually use them.
    pool_id = generate_id()
    target_total = max(len(textbook_slots) * 2, 40) if textbook_slots else 0
    configured_image_cap = max(0, int(getattr(settings, "IMAGE_QUESTIONS_PER_POOL", 8)))
    image_total = _contextual_image_total(
        plan=textbook_slots,
        chapters=chapters,
        subject_norm=subject_norm,
        configured_cap=configured_image_cap,
    )
    # Composite-question papers (the CBSE language blueprints, and any explicit
    # General-Instructions plan) ask for mark values the fixed per-subject
    # recipes never produce. Deriving Model 1's recipe from the plan itself
    # guarantees the pool can fill every slot. The tuned Science/Maths/Social
    # recipes still win for their board papers.
    #
    # Resolved here rather than at the streaming call because unit construction
    # needs it too: it is what lets the pool's shapes be spread across chapters
    # instead of every chapter being asked for every shape.
    recipe_plan = (
        textbook_slots
        if is_gim or subject_norm in {"english", "hindi", "telugu", "sanskrit"}
        else None
    )
    units = (
        _build_generation_units(
            chapters,
            target_total=target_total,
            image_total=image_total,
            recipe_plan=recipe_plan,
        )
        if textbook_slots and chapters
        else []
    )
    max_prompt_tokens = max((unit.chapter.estimated_tokens for unit in units), default=0)

    pool_questions: List[PoolQuestion] = []
    outcome: Dict[str, Any] = {}
    asset_reports: List[Dict[str, Any]] = []
    asset_result = None

    # The asset generators need nothing from the chapter read, so they run
    # alongside Model 1 rather than in front of it. Started first, joined last.
    # A daemon thread rather than an executor: this is a generator, and a
    # client that disconnects mid-stream closes it without running the join —
    # a daemon thread cannot then hold up interpreter shutdown. Same reason
    # `_build_pool_streaming` uses one.
    asset_outcome: Dict[str, Any] = {}
    asset_thread: Optional[threading.Thread] = None
    if asset_slots:
        yield _sse(
            {
                "stage": "generating_assets",
                "message": "Writing passages, grammar tasks and writing prompts…",
                "generators": [
                    entry
                    for entry in routing
                    if entry["generator"] != DEFAULT_GENERATOR
                ],
            },
            event="status",
        )

        def _run_assets():
            try:
                asset_outcome["result"], asset_outcome["reports"] = (
                    generate_assets_for_plan(
                        plan,
                        subject=subject_label,
                        subject_norm=subject_norm,
                        class_num=class_num,
                        difficulty=difficulty,
                        pool_id=pool_id,
                        user=user,
                    )
                )
            except Exception as exc:  # pragma: no cover - runner catches its own
                logger.error("Asset stage failed: %s", exc, exc_info=True)
                asset_outcome["error"] = str(exc)
            finally:
                # The asset generators persist questions and record usage;
                # release this thread's connection (see _run_unit).
                close_old_connections()

        asset_thread = threading.Thread(
            target=_run_assets, name="asset-generation", daemon=True
        )
        asset_thread.start()

    if units:
        yield _sse(
            {
                "stage": "generating_pool",
                "message": "Writing a pool of questions…",
                "chapter": chapter_name,
                "chapters": [
                    {
                        "number": chapter.number,
                        "title": chapter.title,
                        "sourcePages": chapter.question_metadata().get("sourcePages"),
                        "sourcePdf": chapter.question_metadata().get("sourcePdf"),
                        "estimatedTokens": chapter.estimated_tokens,
                    }
                    for chapter in chapters
                ],
                "generationUnits": len(units),
                "maxPromptTokens": max_prompt_tokens,
            },
            event="status",
        )

        for item in _build_pool_streaming(
            units=units,
            subject=subject_label,
            subject_norm=subject_norm,
            class_num=class_num,
            difficulty=difficulty,
            pool_id=pool_id,
            user=user,
            plan=recipe_plan,
        ):
            if isinstance(item, PoolQuestion):
                pool_questions.append(item)
                # Progress only — these are pool questions, not paper questions.
                # The paper is assembled after the pool is complete.
                yield _sse(
                    {
                        "stage": "pool_progress",
                        "produced": len(pool_questions),
                        "target": sum(unit.target_total for unit in units),
                    },
                    event="status",
                )
            elif isinstance(item, dict):
                outcome = item

    if asset_thread is not None:
        asset_thread.join()
        asset_result = asset_outcome.get("result")
        asset_reports = list(asset_outcome.get("reports") or [])
        if asset_result is not None:
            pool_questions.extend(asset_result.questions)

        if asset_outcome.get("error"):
            yield _sse(
                {
                    "message": (
                        "The Reading / Grammar / Writing stage could not run: "
                        f"{asset_outcome['error']}. Those sections will be missing."
                    )
                },
                event="warning",
            )

        if asset_reports:
            yield _sse(
                {
                    "stage": "assets_ready",
                    "message": "Reading, grammar and writing material is ready.",
                    "generators": asset_reports,
                },
                event="status",
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

    if outcome.get("error"):
        yield _sse({"error": outcome["error"]}, event="error")
        return

    if not pool_questions:
        yield _sse(
            {
                "error": "No questions could be generated. The source may be too "
                "short or unreadable, and no independent generator produced "
                "material either."
            },
            event="error",
        )
        return

    pool_result = outcome.get("pool")
    image_result = outcome.get("images")
    pool_id = getattr(pool_result, "pool_id", "") or pool_id

    summary_stats = pool_summary(pool_questions)
    yield _sse(
        {
            "poolId": pool_id,
            "chapter": chapter_name,
            "chapters": [
                {
                    "number": chapter.number,
                    "title": chapter.title,
                    "sourcePages": chapter.question_metadata().get("sourcePages"),
                    "sourcePdf": chapter.question_metadata().get("sourcePdf"),
                }
                for chapter in chapters
            ],
            "generationUnits": len(units),
            **summary_stats,
            "assetGenerators": asset_reports,
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
    persist = _persist_pool_by_chapter(
        user=user,
        questions=pool_questions,
        subject=subject_label,
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
        "routing": routing,
        "assetGenerators": asset_reports,
        "textbookQuestions": sum(
            1 for a in paper.assignments if a.question.uses_uploaded_content
        ),
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
        # Name the generator that fell short, not "this chapter" — an unfilled
        # Reading slot has nothing to do with the upload, and telling a teacher
        # to upload more chapters would be actively misleading.
        short_generators = sorted(
            {
                str(getattr(u.slot, "generator", "") or DEFAULT_GENERATOR)
                for u in paper.unfilled
            }
        )
        remedy = (
            "Upload more chapters for a complete paper."
            if short_generators == [DEFAULT_GENERATOR]
            else "Try generating again; the affected sections are produced "
            "independently of the uploaded chapters."
        )
        yield _sse(
            {
                "requested": len(plan),
                "realized": paper.total_questions,
                "generators": short_generators,
                "message": (
                    f"{len(paper.unfilled)} of {len(plan)} blueprint slots could "
                    f"not be filled ({'; '.join(sorted(reasons))}). {remedy}"
                ),
            },
            event="notice",
        )

    if asset_result is not None and asset_result.validation_warnings:
        yield _sse(
            {
                "message": (
                    "Some generated material did not match the blueprint exactly: "
                    + "; ".join(asset_result.validation_warnings[:6])
                ),
                "validationWarnings": asset_result.validation_warnings,
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

    # ── Additional sets (B, C) ──────────────────────────────────────────
    # Derived from Set A's selection and the same pool — no new questions,
    # no second Model 1 run. Best-effort: a failure here leaves Set A intact.
    variant_sets: List[Dict[str, Any]] = []
    if num_sets > 1:
        try:
            variant_sets = _build_variant_results(
                master_assignments=paper.assignments,
                pool=pool_questions,
                num_variants=num_sets - 1,
                section_order=[s.get("title", "") for s in result["sections"]],
                general_instructions=result["generalInstructions"],
                include_vi_alternatives=include_vi_alternatives,
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
                "textbookSlots": len(textbook_slots),
                "assetSlots": len(asset_slots),
                "assetGenerators": asset_reports,
                "realizedTotal": paper.total_questions,
                "savedToBank": persist.saved,
                "duplicatesSkipped": persist.duplicates_skipped,
                "reviewApplied": paper.review_applied,
                "reviewSwaps": paper.review_swaps,
                "imageStrategy": resolve_strategy(),
                "syntheticImageCount": synthetic_count,
                "numberOfSets": num_sets,
            },
            result=result,
            user=user,
        )
    except Exception as exc:
        logger.warning("Could not persist generation history: %s", exc)

    logger.info(
        "Pool pipeline complete: pool=%s %d questions from a pool of %d in %.1fs "
        "(%d set(s))",
        pool_id, paper.total_questions, len(pool_questions),
        time.monotonic() - started, len(variant_sets) + 1,
    )

    done_payload: Dict[str, Any] = {"done": True, "result": result}
    if variant_sets:
        # Set A first, then the derived sets — a single place a consumer can
        # read every set from, with Set A's `result` still the default.
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
