"""Regenerate exactly one question, leaving the rest of the paper alone.

A teacher usually likes the paper and dislikes one item. Re-running the
generator to fix that is the wrong shape of operation: it costs a full
generation, and it changes forty questions the teacher had already accepted.

This module answers a narrower question — "give me one more question that
could have filled this same blueprint slot" — and it answers it the cheap way
first:

    1. the bank        — the pool over-provisions every slot ~2×, so a
                         replacement almost always already exists, at zero cost
                         and no latency;
    2. the generator   — only when the bank is exhausted. Asset slots call
                         their own generator with a single slot; textbook slots
                         run one small Model 1 batch over the same chapter.

Everything that defines the slot is preserved by construction, because the
replacement is matched (or generated) against a reconstructed slot carrying
the original marks, question type, section, generator, asset type, chapter and
difficulty. `slot_accepts` is the same predicate the assembler uses, so a
replacement is eligible for the slot in exactly the sense the paper requires.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from services.pool.schema import (
    DEFAULT_GENERATOR,
    PoolQuestion,
    normalize_type,
    slot_accepts,
)

logger = logging.getLogger("[POOL_REPLACE]")


class ReplacementError(RuntimeError):
    """No replacement could be produced for this slot."""


@dataclass
class ReplacementSlot:
    """A blueprint slot reconstructed from what the editor knows about it.

    Deliberately duck-types `QuestionGenerationSlot` — `slot_accepts`,
    `batches_from_plan` and the asset generators all read attributes off a slot
    rather than requiring the concrete class, so the same code paths serve a
    replacement request and a full generation.
    """

    index: int
    marks: int
    question_type: str
    legacy_type: str
    section_title: str
    generator: str = DEFAULT_GENERATOR
    asset_type: str = ""
    difficulty: str = "medium"
    subject: str = ""
    chapter: str = ""
    topic: str = ""
    instruction_hint: str = ""
    choice_required: bool = False
    constraints: Dict[str, Any] = field(default_factory=dict)
    validation: tuple = ()
    class_num: int = 10


@dataclass
class ReplacementResult:
    question: PoolQuestion
    #: "bank" when an existing question was reused, "generated" when a
    #: generator ran. Surfaced so the UI can say which happened.
    source: str
    exhausted_bank: bool = False


def _legacy_type_for(question_type: str) -> str:
    """Coarse bucket for a pool type, mirroring the router's own mapping."""
    qtype = normalize_type(question_type) or "SHORT_ANSWER"
    if qtype in {"MCQ", "ASSERTION_REASON", "DIAGRAM"}:
        return qtype
    if qtype in {"CASE_STUDY", "READING_COMP"}:
        return "CASE_STUDY"
    if qtype in {"LONG_ANSWER", "LETTER", "COMPOSITION"}:
        return "LONG"
    return "SHORT"


def build_slot(spec: Dict[str, Any]) -> ReplacementSlot:
    """Reconstruct the slot from the editor's `slotMeta` payload."""
    question_type = normalize_type(spec.get("type")) or "SHORT_ANSWER"
    try:
        marks = int(spec.get("marks") or 1)
    except (TypeError, ValueError):
        marks = 1

    return ReplacementSlot(
        index=int(spec.get("slotIndex") or 0),
        marks=max(1, marks),
        question_type=question_type,
        legacy_type=_legacy_type_for(question_type),
        section_title=str(spec.get("section") or "Questions"),
        generator=str(spec.get("generator") or DEFAULT_GENERATOR),
        asset_type=str(spec.get("assetType") or ""),
        difficulty=str(spec.get("difficulty") or "medium"),
        subject=str(spec.get("subject") or ""),
        chapter=str(spec.get("chapter") or ""),
        topic=str(spec.get("topic") or ""),
        class_num=int(spec.get("classNum") or spec.get("class") or 10),
    )


# ── Stage 1: the bank ───────────────────────────────────────────────────


def _bank_candidates(
    *,
    user,
    slot: ReplacementSlot,
    exclude_ids: Sequence[str],
    exclude_hashes: Sequence[str],
) -> List[PoolQuestion]:
    """Saved questions that could fill this slot, minus what the paper uses.

    Scoped by subject and class. Chapter is applied only to textbook slots —
    an asset has no chapter, and filtering on one would return nothing for
    every Reading, Grammar and Writing slot.
    """
    from services.pool.store import load_bank

    excluded_ids = {str(x) for x in exclude_ids if str(x)}
    excluded_hashes = {str(x) for x in exclude_hashes if str(x)}

    def _eligible(pool: Sequence[PoolQuestion]) -> List[PoolQuestion]:
        return [
            q
            for q in pool
            if q.id not in excluded_ids
            and (not q.content_hash or q.content_hash not in excluded_hashes)
            and slot_accepts(q, slot)
        ]

    is_textbook = slot.generator == DEFAULT_GENERATOR
    scoped = is_textbook and bool(slot.chapter)

    candidates = _eligible(
        load_bank(
            user=user,
            subject=slot.subject or None,
            chapters=[slot.chapter] if scoped else None,
            class_num=slot.class_num,
        )
    )
    if candidates or not scoped:
        return candidates

    # The chapter filter is a preference, not a requirement: a teacher who
    # uploaded several chapters would rather have a replacement from a
    # different one than none at all. Widening is keyed on there being no
    # eligible CANDIDATE left, not on the chapter having no questions — the
    # common case is a chapter whose questions are all already on the paper.
    return _eligible(
        load_bank(user=user, subject=slot.subject or None, class_num=slot.class_num)
    )


def _pick(candidates: Sequence[PoolQuestion], slot: ReplacementSlot, seed: int):
    """Prefer a different topic to the one being replaced, then vary."""
    if not candidates:
        return None
    rng = random.Random(seed)
    current_topic = str(slot.topic or "").strip().lower()

    def score(question: PoolQuestion) -> float:
        value = rng.random()
        if current_topic and str(question.topic or "").strip().lower() == current_topic:
            value -= 1.0
        if slot.asset_type and question.asset_type == slot.asset_type:
            value += 2.0
        if question.explanation.strip():
            value += 0.1
        return value

    return max(candidates, key=score)


# ── Stage 2: generate ───────────────────────────────────────────────────


def _generate_asset(slot: ReplacementSlot, *, user) -> Optional[PoolQuestion]:
    """Run this slot's asset generator for one slot only."""
    from services.assets.base import AssetRequest
    from services.assets.registry import get_generator

    generator = get_generator(slot.generator)
    if generator is None:
        return None

    request = AssetRequest(
        slots=(slot,),
        subject=slot.subject or "English",
        subject_norm=(slot.subject or "english").strip().lower(),
        class_num=slot.class_num,
        difficulty=slot.difficulty,
        pool_id="",
        user=user,
        # One replacement, one candidate — the teacher is choosing by looking
        # at the result, so a second unused candidate is pure cost.
        over_provision=1,
        existing=(),
    )
    result = generator.generate(request)
    for question in result.questions:
        if slot_accepts(question, slot):
            return question
    return None


def _generate_textbook(slot: ReplacementSlot, *, user, pdf_source_ids, hsat_source_ids):
    """Run one small Model 1 batch over the slot's own chapter."""
    from services.pool.chapters import build_chapters
    from services.pool.model1 import generate_question_pool

    chapters = build_chapters(
        pdf_source_ids=list(pdf_source_ids or []),
        hsat_source_ids=list(hsat_source_ids or []),
    )
    if not chapters:
        return None

    wanted = str(slot.chapter or "").strip().lower()
    chapter = next(
        (c for c in chapters if str(c.title or "").strip().lower() == wanted),
        chapters[0],
    )

    result = generate_question_pool(
        chapter=chapter,
        subject=slot.subject or "",
        subject_norm=(slot.subject or "").strip().lower(),
        chapter_name=chapter.title,
        class_num=slot.class_num,
        difficulty=slot.difficulty,
        # Three candidates for one slot: Model 1 drops anything that fails
        # validation, so asking for exactly one regularly returns nothing.
        target_total=3,
        user=user,
        plan=[slot],
        question_metadata=chapter.question_metadata(),
    )

    for question in result.questions:
        if slot_accepts(question, slot):
            return question
    return None


# ── Entry point ─────────────────────────────────────────────────────────


def replace_question(
    *,
    user,
    spec: Dict[str, Any],
    exclude_ids: Optional[Sequence[str]] = None,
    exclude_hashes: Optional[Sequence[str]] = None,
    pdf_source_ids: Optional[Sequence[str]] = None,
    hsat_source_ids: Optional[Sequence[str]] = None,
    allow_generation: bool = True,
) -> ReplacementResult:
    """One replacement for one slot. Never touches any other question."""
    slot = build_slot(spec)
    exclude_ids = list(exclude_ids or [])
    exclude_hashes = list(exclude_hashes or [])

    candidates = _bank_candidates(
        user=user,
        slot=slot,
        exclude_ids=exclude_ids,
        exclude_hashes=exclude_hashes,
    )
    chosen = _pick(candidates, slot, seed=len(exclude_ids) + slot.index)
    if chosen is not None:
        logger.info(
            "Replaced slot %s from the bank (%d candidate(s)).",
            slot.index, len(candidates),
        )
        return ReplacementResult(question=chosen, source="bank")

    if not allow_generation:
        raise ReplacementError(
            "No other saved question fits this slot. Generate more questions "
            "for this chapter, or allow a fresh one to be written."
        )

    if slot.generator != DEFAULT_GENERATOR:
        generated = _generate_asset(slot, user=user)
    else:
        generated = _generate_textbook(
            slot,
            user=user,
            pdf_source_ids=pdf_source_ids,
            hsat_source_ids=hsat_source_ids,
        )

    if generated is None:
        raise ReplacementError(
            "A replacement could not be written for this question. The slot's "
            "source material may no longer be available."
        )

    # Bank it, so the next replacement for this slot is free.
    try:
        from services.pool.store import persist_pool

        persist_pool(
            user=user,
            questions=[generated],
            subject=generated.subject or slot.subject,
            chapter=generated.chapter or slot.chapter or "Generated Chapter",
            class_num=slot.class_num,
        )
    except Exception as exc:  # pragma: no cover - persistence is best effort
        logger.warning("Could not bank the replacement question: %s", exc)

    logger.info("Replaced slot %s by generating a new question.", slot.index)
    return ReplacementResult(
        question=generated, source="generated", exhausted_bank=True
    )
