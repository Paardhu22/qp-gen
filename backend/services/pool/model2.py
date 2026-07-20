"""Model 2 — assemble a paper from the Question Pool.

Model 2 never writes questions. It selects them, in five stages:

    1. Python filters the pool to what is eligible for this paper.
    2. Python builds a constraint-satisfying candidate set: a valid pick for
       every slot, PLUS alternates so the review stage has real room to move.
    3. gpt-4.1-mini reviews only that candidate set and returns its choices.
    4. Those choices come back as slot → question-id pairs.
    5. Python validates the response and, if anything is wrong, ships its own
       stage-2 selection instead.

The split is deliberate. Constraint satisfaction — exact marks, exact counts,
no duplicate ids, Bloom and difficulty spread, chapter weighting — is a solver
problem, and a solver is cheaper, faster and more reliable at it than a model.
Judging whether two questions test the same idea in different words is not a
solver problem, and that is the only thing the model is asked to do.

Stage 5 is authoritative, not advisory. A model response that names an unknown
id, repeats an id, or breaks the marks total is discarded wholesale rather
than repaired, because a half-trusted selection is harder to reason about than
a deterministic one. The paper always renders.
"""

from __future__ import annotations

import json
import logging
import random
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from django.conf import settings

from apps.question_generation.infrastructure.providers.base import (
    LLMMessage,
    LLMRequest,
)
from apps.question_generation.infrastructure.providers.openai_provider import (
    OpenAIProvider,
)
from services.pool.schema import PoolQuestion, slot_accepts
from services.pool.streaming import parse_question_payload

logger = logging.getLogger("[MODEL2]")

#: Alternates offered per slot on top of the chosen question. 2 keeps the
#: review prompt small (a 38-slot paper → ~114 candidates → ~6k tokens) while
#: still giving the model a genuine choice. At 0 the review stage could only
#: rubber-stamp; much above 3 the prompt grows without improving the outcome.
DEFAULT_ALTERNATES = 2

#: Bloom's spread targeted across a whole paper. Not a hard constraint — the
#: pool may simply not contain enough CREATE-level questions — but it steers
#: stage 2 away from a paper that is entirely recall.
_BLOOM_TARGET_WEIGHTS: Dict[str, float] = {
    "REMEMBER": 0.20,
    "UNDERSTAND": 0.30,
    "APPLY": 0.25,
    "ANALYZE": 0.15,
    "EVALUATE": 0.06,
    "CREATE": 0.04,
}

_DIFFICULTY_TARGET_WEIGHTS: Dict[str, Dict[str, float]] = {
    "easy": {"easy": 0.55, "medium": 0.35, "hard": 0.10},
    "medium": {"easy": 0.30, "medium": 0.50, "hard": 0.20},
    "hard": {"easy": 0.15, "medium": 0.45, "hard": 0.40},
}


class PaperAssemblyError(RuntimeError):
    """The pool cannot support the requested blueprint at all."""


@dataclass
class SlotAssignment:
    slot: Any
    question: PoolQuestion
    alternates: List[PoolQuestion] = field(default_factory=list)
    #: The "OR" alternative for slots the blueprint marks `choice_required`.
    #: CBSE papers offer an internal choice on several slots; the pool makes
    #: this almost free, since a reserved alternate is by construction the same
    #: type and mark value as the main question but on a different topic.
    or_choice: Optional[PoolQuestion] = None
    #: True when the review stage moved this slot off the deterministic pick.
    swapped_by_review: bool = False


@dataclass
class UnfilledSlot:
    slot: Any
    reason: str


@dataclass
class AssembledPaper:
    assignments: List[SlotAssignment] = field(default_factory=list)
    unfilled: List[UnfilledSlot] = field(default_factory=list)
    review_applied: bool = False
    review_swaps: int = 0
    review_rejected_reason: str = ""

    @property
    def total_questions(self) -> int:
        return len(self.assignments)

    @property
    def total_marks(self) -> int:
        return sum(int(a.question.marks) for a in self.assignments)

    def questions_in_slot_order(self) -> List[PoolQuestion]:
        ordered = sorted(
            self.assignments, key=lambda a: int(getattr(a.slot, "index", 0) or 0)
        )
        return [a.question for a in ordered]


# ── Stage 1: filter ─────────────────────────────────────────────────────


def filter_pool(
    pool: Sequence[PoolQuestion],
    *,
    subject: Optional[str] = None,
    chapters: Optional[Iterable[str]] = None,
    difficulty: Optional[str] = None,
    exclude_ids: Optional[Iterable[str]] = None,
) -> List[PoolQuestion]:
    """Narrow the pool to what may appear on this paper.

    Difficulty is deliberately NOT filtered on: a 'medium' paper still wants
    some easy and some hard questions, and that spread is handled by the
    scoring in stage 2. Passing `difficulty` here only drops questions whose
    difficulty is missing entirely.
    """
    wanted_chapters = {str(c).strip().lower() for c in (chapters or []) if str(c).strip()}
    excluded = {str(x) for x in (exclude_ids or [])}

    filtered: List[PoolQuestion] = []
    for question in pool:
        if question.id in excluded:
            continue
        if not str(question.question or "").strip():
            continue
        if subject and question.subject and question.subject.strip().lower() != subject.strip().lower():
            continue
        if wanted_chapters and str(question.chapter or "").strip().lower() not in wanted_chapters:
            continue
        filtered.append(question)

    return filtered


# ── Stage 2: constraint-satisfying candidate set ────────────────────────


def _score_question(
    question: PoolQuestion,
    *,
    used_topics: Counter,
    used_blooms: Counter,
    used_difficulty: Counter,
    used_chapters: Counter,
    total_slots: int,
    difficulty_target: str,
    rng: random.Random,
    vi_required: bool = False,
) -> float:
    """Higher is better. Every term pushes toward a well-spread paper."""
    score = 0.0

    # Topic diversity dominates: repeating a topic is the most visible defect
    # in a generated paper, and the old engine's duplicate-stem warnings were
    # almost entirely topic collisions.
    topic = (question.topic or "").strip().lower()
    score -= 4.0 * used_topics.get(topic, 0)

    # Bloom spread — reward levels that are under their target share.
    bloom_target = _BLOOM_TARGET_WEIGHTS.get(question.blooms, 0.05) * total_slots
    bloom_used = used_blooms.get(question.blooms, 0)
    if bloom_used < bloom_target:
        score += 2.0
    else:
        score -= 1.0 * (bloom_used - bloom_target)

    # Difficulty spread against the requested overall level.
    weights = _DIFFICULTY_TARGET_WEIGHTS.get(
        difficulty_target, _DIFFICULTY_TARGET_WEIGHTS["medium"]
    )
    difficulty_target_count = weights.get(question.difficulty, 0.1) * total_slots
    difficulty_used = used_difficulty.get(question.difficulty, 0)
    if difficulty_used < difficulty_target_count:
        score += 1.5
    else:
        score -= 0.75 * (difficulty_used - difficulty_target_count)

    # Chapter weighting — with several chapters uploaded, spread across them
    # instead of drawing the whole paper from whichever one is longest.
    score -= 1.5 * used_chapters.get((question.chapter or "").strip().lower(), 0)

    # A question with a worked explanation is more useful downstream (answer
    # keys, answer scripts), so prefer it, gently.
    if question.explanation.strip():
        score += 0.5

    # CBSE requires a visually-impaired alternative on picture and map slots.
    # Weighted heavily: a vi_required slot filled with a question that has no
    # VI text is a compliance defect, not a stylistic one.
    if vi_required:
        score += 6.0 if (question.vi_alternative or "").strip() else -6.0

    # Tiny jitter breaks ties without making the result unreproducible in any
    # way that matters — the rng is seeded by the caller.
    score += rng.random() * 0.01

    return score


def build_candidates(
    pool: Sequence[PoolQuestion],
    plan: Sequence[Any],
    *,
    alternates: int = DEFAULT_ALTERNATES,
    difficulty: str = "medium",
    seed: Optional[int] = None,
) -> Tuple[List[SlotAssignment], List[UnfilledSlot]]:
    """Assign a question to every slot, plus `alternates` runners-up.

    Two passes, and the split matters.

    Pass 1 fills each slot most-constrained-first: a slot with three eligible
    questions is filled before one with forty, so scarce questions are not
    consumed by a slot that had plenty of other options. Filling in blueprint
    order instead is what starves the rare slots (5-mark case studies, say)
    and leaves them unfilled at the end.

    Pass 2 hands out alternates from what is LEFT OVER, and reserves each one
    to a single slot. That makes the offered sets pairwise disjoint, which in
    turn means any per-slot choice the review stage makes is automatically
    free of duplicates. Drawing alternates in pass 1 instead would let one
    slot offer a question that is another slot's chosen answer — a swap to it
    would collide, and stage 5 would have to throw the whole review away.

    A slot may end up with fewer than `alternates` alternates (or none) when
    the pool is thin. That is deliberate: an unfillable alternate is not worth
    starving a slot for.
    """
    rng = random.Random(seed if seed is not None else 0xA05)

    eligible: Dict[int, List[PoolQuestion]] = {}
    for position, slot in enumerate(plan):
        eligible[position] = [q for q in pool if slot_accepts(q, slot)]

    order = sorted(range(len(plan)), key=lambda p: len(eligible[p]))

    used_ids: set[str] = set()
    used_topics: Counter = Counter()
    used_blooms: Counter = Counter()
    used_difficulty: Counter = Counter()
    used_chapters: Counter = Counter()

    assignments: Dict[int, SlotAssignment] = {}
    unfilled: List[UnfilledSlot] = []
    total_slots = max(1, len(plan))

    def _rank(
        candidates: List[PoolQuestion], *, vi_required: bool = False
    ) -> List[PoolQuestion]:
        return sorted(
            candidates,
            key=lambda q: _score_question(
                q,
                used_topics=used_topics,
                used_blooms=used_blooms,
                used_difficulty=used_difficulty,
                used_chapters=used_chapters,
                total_slots=total_slots,
                difficulty_target=difficulty,
                rng=rng,
                vi_required=vi_required,
            ),
            reverse=True,
        )

    # ── Pass 1: one question per slot ───────────────────────────────────
    for position in order:
        slot = plan[position]
        available = [q for q in eligible[position] if q.id not in used_ids]

        if not available:
            reason = (
                "no question of this type and mark value in the pool"
                if not eligible[position]
                else "every matching question was already used by another slot"
            )
            unfilled.append(UnfilledSlot(slot=slot, reason=reason))
            continue

        chosen = _rank(
            available, vi_required=bool(getattr(slot, "vi_required", False))
        )[0]
        used_ids.add(chosen.id)
        used_topics[(chosen.topic or "").strip().lower()] += 1
        used_blooms[chosen.blooms] += 1
        used_difficulty[chosen.difficulty] += 1
        used_chapters[(chosen.chapter or "").strip().lower()] += 1

        assignments[position] = SlotAssignment(slot=slot, question=chosen)

    # ── Pass 2: alternates from the leftovers, reserved per slot ────────
    # Slots the blueprint marks `choice_required` consume one extra leftover
    # as their OR alternative. Those are filled first, because an OR-bearing
    # slot without its alternative is a structural defect in the paper, while
    # a slot merely short of review alternates is not.
    reserved: set[str] = set(used_ids)
    positions_by_need = sorted(
        (p for p in order if p in assignments),
        key=lambda p: not bool(getattr(plan[p], "choice_required", False)),
    )

    for position in positions_by_need:
        assignment = assignments[position]
        needs_choice = bool(getattr(assignment.slot, "choice_required", False))
        wanted = alternates + (1 if needs_choice else 0)
        if wanted <= 0:
            continue

        spare = [q for q in eligible[position] if q.id not in reserved]
        if not spare:
            continue

        picked = _rank(spare)[:wanted]
        if needs_choice and picked:
            # The OR alternative is held out of `alternates` so the review
            # stage cannot swap the main question onto it and collapse the
            # choice into a duplicate.
            assignment.or_choice = picked[0]
            assignment.alternates = picked[1:]
        else:
            assignment.alternates = picked
        reserved.update(q.id for q in picked)

    ordered = [assignments[p] for p in sorted(assignments)]
    return ordered, unfilled


# ── Stage 3/4: model review ─────────────────────────────────────────────


_REVIEW_SYSTEM_PROMPT = (
    "You are a senior CBSE examiner doing a final quality pass on a question "
    "paper that has already been assembled.\n\n"
    "Each slot below shows the CHOSEN question and a few ALTERNATES. Every "
    "option already satisfies the paper's structural requirements, so you must "
    "not worry about marks, counts, or question types — those are fixed and "
    "already correct.\n\n"
    "Your ONLY job is to improve quality:\n"
    "  • If two slots test essentially the same idea, swap one for an "
    "alternate that covers different ground.\n"
    "  • If an alternate is a clearly better question than the chosen one "
    "(sharper wording, more precise, better discrimination), swap to it.\n"
    "  • Otherwise keep the chosen question. Keeping is the default — do not "
    "swap for the sake of swapping.\n\n"
    "Hard constraints:\n"
    "  • You may ONLY pick an id listed for that specific slot.\n"
    "  • The same id must never appear twice in your answer.\n"
    "  • You must return exactly one entry per slot.\n\n"
    'Return ONLY JSON: {"selections": [{"slot": <number>, "id": "<id>"}]}'
)


def _review_payload(assignments: Sequence[SlotAssignment]) -> List[Dict[str, Any]]:
    payload = []
    for assignment in assignments:
        slot_index = int(getattr(assignment.slot, "index", 0) or 0)
        payload.append(
            {
                "slot": slot_index,
                "section": str(getattr(assignment.slot, "section_title", "") or ""),
                "chosen": assignment.question.to_wire(),
                "alternates": [alt.to_wire() for alt in assignment.alternates],
            }
        )
    return payload


def _apply_review(
    assignments: List[SlotAssignment],
    selections: Sequence[Dict[str, Any]],
) -> Tuple[bool, int, str]:
    """Stage 5. Validate the model's selection, then apply it — or reject it.

    Returns (applied, swap_count, rejection_reason). Rejection is all-or-
    nothing: a partially applied selection would be neither the model's
    judgement nor the solver's, and impossible to reason about later.
    """
    by_slot = {
        int(getattr(a.slot, "index", 0) or 0): a for a in assignments
    }

    if len(selections) != len(assignments):
        return False, 0, (
            f"expected {len(assignments)} selections, got {len(selections)}"
        )

    resolved: Dict[int, PoolQuestion] = {}
    seen_ids: set[str] = set()

    for entry in selections:
        try:
            slot_index = int(entry.get("slot"))
        except (TypeError, ValueError):
            return False, 0, f"non-numeric slot in selection: {entry!r}"

        assignment = by_slot.get(slot_index)
        if assignment is None:
            return False, 0, f"selection names unknown slot {slot_index}"
        if slot_index in resolved:
            return False, 0, f"slot {slot_index} selected twice"

        chosen_id = str(entry.get("id") or "")
        permitted = {assignment.question.id: assignment.question}
        permitted.update({alt.id: alt for alt in assignment.alternates})

        question = permitted.get(chosen_id)
        if question is None:
            return False, 0, (
                f"slot {slot_index} selected id {chosen_id!r}, which was not "
                "offered for that slot"
            )
        if chosen_id in seen_ids:
            return False, 0, f"id {chosen_id!r} used for more than one slot"

        seen_ids.add(chosen_id)
        resolved[slot_index] = question

    # Marks must be untouched — this is the invariant a CBSE paper cannot
    # afford to get wrong, and the one thing a swap could silently break.
    original_marks = sum(int(a.question.marks) for a in assignments)
    new_marks = sum(int(q.marks) for q in resolved.values())
    if original_marks != new_marks:
        return False, 0, (
            f"selection changes total marks from {original_marks} to {new_marks}"
        )

    swaps = 0
    for slot_index, question in resolved.items():
        assignment = by_slot[slot_index]
        if assignment.question.id != question.id:
            assignment.question = question
            assignment.swapped_by_review = True
            swaps += 1

    return True, swaps, ""


def _run_review(
    assignments: List[SlotAssignment],
    *,
    subject: str,
    class_num: int,
    model: str,
    provider: OpenAIProvider,
    user=None,
) -> Tuple[bool, int, str]:
    payload = _review_payload(assignments)
    instruction = (
        f"Class {class_num} {subject} paper. Review these {len(payload)} slots:\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )

    request = LLMRequest(
        model=model,
        messages=[
            LLMMessage(role="system", content=_REVIEW_SYSTEM_PROMPT),
            LLMMessage(role="user", content=instruction),
        ],
        response_format={"type": "json_object"},
        # One compact object per slot; 60 tokens each is generous.
        max_output_tokens=max(1500, len(payload) * 60),
        user=user,
        operation="pool_model2_review",
    )

    try:
        response = provider.chat(request)
    except Exception as exc:
        return False, 0, f"review call failed: {type(exc).__name__}: {exc}"

    parsed = parse_question_payload(response.content)
    selections: List[Dict[str, Any]] = []
    for item in parsed:
        if isinstance(item, dict) and "selections" in item:
            raw = item.get("selections")
            if isinstance(raw, list):
                selections = [s for s in raw if isinstance(s, dict)]
            break
        if isinstance(item, dict) and "slot" in item:
            selections.append(item)

    if not selections:
        return False, 0, "review returned no parseable selections"

    return _apply_review(assignments, selections)


# ── Orchestration ───────────────────────────────────────────────────────


def assemble_paper(
    pool: Sequence[PoolQuestion],
    plan: Sequence[Any],
    *,
    subject: str = "",
    class_num: int = 10,
    difficulty: str = "medium",
    chapters: Optional[Iterable[str]] = None,
    alternates: int = DEFAULT_ALTERNATES,
    use_review: bool = True,
    seed: Optional[int] = None,
    model: Optional[str] = None,
    user=None,
) -> AssembledPaper:
    """Select and order questions from `pool` to satisfy `plan`.

    `use_review=False` skips stage 3 entirely, making assembly fully
    deterministic for a given (pool, plan, seed) — two teachers generating from
    the same saved bank then get byte-identical papers.
    """
    if not plan:
        raise PaperAssemblyError("The blueprint is empty — nothing to assemble.")

    started = time.monotonic()

    eligible = filter_pool(pool, subject=subject or None, chapters=chapters)
    if not eligible:
        raise PaperAssemblyError(
            "No saved questions match this paper's subject and chapters."
        )

    assignments, unfilled = build_candidates(
        eligible, plan, alternates=alternates, difficulty=difficulty, seed=seed
    )

    paper = AssembledPaper(assignments=assignments, unfilled=unfilled)

    if not assignments:
        raise PaperAssemblyError(
            "The pool could not fill a single slot of this blueprint. It likely "
            "holds no questions of the required types and mark values."
        )

    if use_review and assignments:
        resolved_model = model or getattr(settings, "POOL_MODEL", settings.OPENAI_MODEL)
        applied, swaps, reason = _run_review(
            assignments,
            subject=subject,
            class_num=class_num,
            model=resolved_model,
            provider=OpenAIProvider(),
            user=user,
        )
        paper.review_applied = applied
        paper.review_swaps = swaps
        paper.review_rejected_reason = reason
        if not applied:
            # Stage 5 rejected the model's answer. The stage-2 selection is
            # already valid and still in place, so the paper is unaffected.
            logger.warning(
                "Model 2 review rejected, keeping the deterministic selection: %s",
                reason,
            )

    logger.info(
        "Model 2 assembled %d/%d slots (%d marks, %d unfilled, review=%s "
        "swaps=%d) in %.2fs",
        paper.total_questions, len(plan), paper.total_marks,
        len(paper.unfilled), paper.review_applied, paper.review_swaps,
        time.monotonic() - started,
    )

    return paper
