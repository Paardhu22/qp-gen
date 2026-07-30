"""Paper templates — the single way a paper's structure is chosen.

This replaces the "QP Type" fork. There used to be two ways to start a paper
and they behaved like different products: *board mode* compiled a CBSE
blueprint from `q_instructions/`, *general instructions mode* asked a model to
design one from prose. A teacher had to know which box to tick before they
could describe what they wanted.

Both are now **templates**. "CBSE Class 10 Science — Sample Paper 2025-26" is a
built-in template; a paper described in prose produces one too. What used to be
a mode is now a starting point, and every starting point is editable.

    built-in catalog ─┐
                      ├─► TemplateBlueprint ─► resolve_slots() ─► the pipeline
    saved custom  ────┘         ▲
                                │
                        the Blueprint Builder
                        (teacher edits slots)

## The two kinds of template, and why both exist

`PaperTemplate` deliberately did not store a resolved structure — its docstring
argues that a template pinned to one frozen layout stops responding to its own
instructions, so "Weekly Test" applied to next week's chapter should produce
next week's paper. That reasoning still holds, and this module does not
overturn it. It adds a second kind alongside it:

* **instruction-driven** (`blueprint` empty) — resolved fresh each time from
  `instructions` + `settings`. Unchanged behaviour, and still the right default
  for "same shape, new chapter".
* **pinned** (`blueprint` present) — the teacher opened the Blueprint Builder
  and changed slots: made question 7 an MCQ, dropped a long answer, moved marks
  around. Re-deriving that from prose would silently discard the edit, so a
  pinned blueprint is authoritative.

A template becomes pinned the moment someone edits a slot. Nothing else flips
it, and clearing the blueprint returns it to instruction-driven.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from services.pool.schema import QUESTION_TYPES, normalize_type

logger = logging.getLogger("[TEMPLATES]")

#: Where a slot's question comes from. The Blueprint Builder exposes this per
#: slot AND as a whole-paper ratio; the ratio is just a bulk edit over slots, so
#: there is exactly one representation to reason about downstream.
SOURCE_GENERATE = "generate"
SOURCE_SAVED = "saved"
SOURCE_CHOICES = (SOURCE_GENERATE, SOURCE_SAVED)


# ── The question types a teacher may choose per slot ────────────────────────
#
# Placeholders, per the spec: a subject-appropriate mapping is coming later.
# Until it does, every type in the pool vocabulary is offered to every subject,
# grouped so the picker is scannable rather than a flat list of twenty. The
# grouping is presentation only — `normalize_type` remains the authority on
# what a type string means.
#
# `subjects=None` means "offer everywhere". When the real mapping arrives it
# populates that field and `question_types_for()` starts filtering; no caller
# changes.
@dataclass(frozen=True)
class QuestionTypeOption:
    code: str
    label: str
    group: str
    default_marks: int
    #: None = every subject. A tuple restricts it.
    subjects: Optional[tuple] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "label": self.label,
            "group": self.group,
            "defaultMarks": self.default_marks,
        }


QUESTION_TYPE_CATALOG: tuple = (
    # Objective
    QuestionTypeOption("MCQ", "Multiple Choice", "Objective", 1),
    QuestionTypeOption("ASSERTION_REASON", "Assertion & Reason", "Objective", 1),
    QuestionTypeOption("TRUE_FALSE", "True / False", "Objective", 1),
    QuestionTypeOption("FILL_IN_THE_BLANK", "Fill in the Blank", "Objective", 1),
    QuestionTypeOption("ONE_WORD", "One Word Answer", "Objective", 1),
    QuestionTypeOption("MATCH_THE_FOLLOWING", "Match the Following", "Objective", 4),
    # Descriptive
    QuestionTypeOption("VERY_SHORT_ANSWER", "Very Short Answer", "Descriptive", 1),
    QuestionTypeOption("SHORT_ANSWER", "Short Answer", "Descriptive", 2),
    QuestionTypeOption("LONG_ANSWER", "Long Answer", "Descriptive", 5),
    QuestionTypeOption("HOTS", "Higher Order Thinking", "Descriptive", 3),
    QuestionTypeOption("COMPETENCY", "Competency Based", "Descriptive", 3),
    # Applied
    QuestionTypeOption("NUMERICAL", "Numerical / Calculation", "Applied", 3),
    QuestionTypeOption("EXPERIMENTAL", "Experimental", "Applied", 3),
    QuestionTypeOption("DIAGRAM", "Diagram (student draws)", "Applied", 3),
    QuestionTypeOption("CASE_STUDY", "Case Study", "Applied", 4),
    # Language
    QuestionTypeOption("READING_COMP", "Reading Comprehension", "Language", 10),
    QuestionTypeOption("EXTRACT_PROSE", "Prose Extract", "Language", 3),
    QuestionTypeOption("EXTRACT_POETRY", "Poetry Extract", "Language", 3),
    QuestionTypeOption("ANALYTICAL_PARAGRAPH", "Analytical Paragraph", "Language", 5),
    QuestionTypeOption("GRAMMAR", "Grammar", "Language", 1),
    QuestionTypeOption("LETTER", "Letter Writing", "Language", 5),
    QuestionTypeOption("COMPOSITION", "Composition / Essay", "Language", 5),
)

_CATALOG_BY_CODE: Dict[str, QuestionTypeOption] = {
    option.code: option for option in QUESTION_TYPE_CATALOG
}


def question_types_for(subject: str = "") -> List[Dict[str, Any]]:
    """The type menu the Blueprint Builder shows for a subject.

    Today every type is offered for every subject — the spec asks for standard
    placeholders until the subject-appropriate mapping is specified. The filter
    is already wired so that mapping is a data change here, not a code change
    at the call sites.
    """
    normalised = (subject or "").strip().lower()
    return [
        option.as_dict()
        for option in QUESTION_TYPE_CATALOG
        if option.subjects is None or normalised in option.subjects
    ]


def default_marks_for(question_type: str) -> int:
    option = _CATALOG_BY_CODE.get(normalize_type(question_type))
    return option.default_marks if option else 1


# ── A slot, as the Blueprint Builder sees it ────────────────────────────────


@dataclass
class SlotSpec:
    """One question position in a template's blueprint.

    This is the editable projection of `QuestionGenerationSlot`: everything a
    teacher may change in the Builder, and nothing they may not. The blueprint
    engine's internal fields (`generator`, `constraints`, `validation`) are
    deliberately absent — they are derived from the subject and section, and a
    teacher editing "question 7 should be an MCQ" must not be able to
    accidentally re-route that slot away from its generator.
    """

    index: int
    section_title: str
    question_type: str
    marks: int
    source: str = SOURCE_GENERATE
    choice_required: bool = False
    #: Carried through untouched so a round-trip through the Builder does not
    #: strip what the blueprint engine put there.
    passthrough: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        payload = {
            "index": self.index,
            "sectionTitle": self.section_title,
            "questionType": self.question_type,
            "marks": self.marks,
            "source": self.source,
            "choiceRequired": self.choice_required,
        }
        if self.passthrough:
            payload["passthrough"] = dict(self.passthrough)
        return payload

    @classmethod
    def from_dict(cls, raw: Any, *, index: int) -> "SlotSpec":
        if not isinstance(raw, dict):
            raise ValueError(f"Slot {index} is not an object.")

        requested_type = (
            raw.get("questionType") or raw.get("question_type") or "SHORT_ANSWER"
        )
        question_type = normalize_type(requested_type)
        if question_type not in QUESTION_TYPES:
            # normalize_type already folds aliases; anything still unknown is a
            # client sending a type this build does not have. Fall back rather
            # than reject — a paper with one mistyped slot is recoverable, a
            # 400 on the whole blueprint is not.
            #
            # Log what was SENT, not the normalised value: normalize_type
            # returns "" for everything it does not recognise, so logging its
            # output makes every one of these warnings identical and useless.
            logger.warning(
                "Unknown question type %r on slot %s; using SHORT_ANSWER.",
                requested_type, index,
            )
            question_type = "SHORT_ANSWER"

        try:
            marks = int(raw.get("marks") or default_marks_for(question_type))
        except (TypeError, ValueError):
            marks = default_marks_for(question_type)
        marks = max(1, min(20, marks))

        source = str(raw.get("source") or SOURCE_GENERATE).strip().lower()
        if source not in SOURCE_CHOICES:
            source = SOURCE_GENERATE

        return cls(
            index=index,
            section_title=str(
                raw.get("sectionTitle") or raw.get("section_title") or "Questions"
            ).strip()
            or "Questions",
            question_type=question_type,
            marks=marks,
            source=source,
            choice_required=bool(
                raw.get("choiceRequired") or raw.get("choice_required")
            ),
            passthrough=dict(raw.get("passthrough") or {}),
        )


@dataclass
class TemplateBlueprint:
    """An ordered slot list plus the totals derived from it.

    Totals are always recomputed, never read from the client. A blueprint that
    says "80 marks" while its slots add to 83 is the single most likely thing
    to arrive from an editing UI, and trusting it would print a paper whose
    header contradicts its own contents.
    """

    slots: List[SlotSpec] = field(default_factory=list)

    @property
    def total_questions(self) -> int:
        return len(self.slots)

    @property
    def total_marks(self) -> int:
        return sum(slot.marks for slot in self.slots)

    @property
    def generated_count(self) -> int:
        return sum(1 for s in self.slots if s.source == SOURCE_GENERATE)

    @property
    def saved_count(self) -> int:
        return sum(1 for s in self.slots if s.source == SOURCE_SAVED)

    def section_order(self) -> List[str]:
        seen: List[str] = []
        for slot in self.slots:
            if slot.section_title not in seen:
                seen.append(slot.section_title)
        return seen

    def summary(self) -> Dict[str, Any]:
        by_type: Dict[str, int] = {}
        by_section: Dict[str, Dict[str, int]] = {}
        for slot in self.slots:
            by_type[slot.question_type] = by_type.get(slot.question_type, 0) + 1
            entry = by_section.setdefault(
                slot.section_title, {"questions": 0, "marks": 0}
            )
            entry["questions"] += 1
            entry["marks"] += slot.marks
        return {
            "totalQuestions": self.total_questions,
            "totalMarks": self.total_marks,
            "generatedCount": self.generated_count,
            "savedCount": self.saved_count,
            "byType": by_type,
            "bySection": [
                {"title": title, **counts} for title, counts in by_section.items()
            ],
        }

    def as_dict(self) -> Dict[str, Any]:
        return {"slots": [slot.as_dict() for slot in self.slots], **self.summary()}

    @classmethod
    def from_dict(cls, raw: Any) -> "TemplateBlueprint":
        if isinstance(raw, dict):
            raw_slots = raw.get("slots")
        else:
            raw_slots = raw
        if not isinstance(raw_slots, list):
            return cls()
        slots: List[SlotSpec] = []
        for position, entry in enumerate(raw_slots, start=1):
            try:
                slots.append(SlotSpec.from_dict(entry, index=position))
            except ValueError as exc:
                logger.warning("Dropping malformed slot %s: %s", position, exc)
        return cls(slots=slots)

    @classmethod
    def from_plan(cls, plan: Sequence[Any]) -> "TemplateBlueprint":
        """Project the blueprint engine's slot objects into editable specs."""
        slots: List[SlotSpec] = []
        for position, slot in enumerate(plan, start=1):
            question_type = normalize_type(
                str(getattr(slot, "question_type", "") or "SHORT_ANSWER")
            )
            slots.append(
                SlotSpec(
                    index=position,
                    section_title=str(
                        getattr(slot, "section_title", "") or "Questions"
                    ),
                    question_type=question_type,
                    marks=int(getattr(slot, "marks", 0) or 1),
                    source=SOURCE_GENERATE,
                    choice_required=bool(getattr(slot, "choice_required", False)),
                    # Everything the engine decided that the Builder does not
                    # expose. Kept so re-resolving a pinned blueprint does not
                    # lose the generator routing or the VI requirement.
                    passthrough={
                        key: getattr(slot, key)
                        for key in (
                            "legacy_type",
                            "generator",
                            "vi_required",
                            "requires_image",
                            "requires_figure",
                            "asset_type",
                            "stream",
                        )
                        if getattr(slot, key, None) not in (None, "", False)
                    },
                )
            )
        return cls(slots=slots)


@dataclass
class ResolvedSlot:
    """A blueprint slot in the shape the pipeline and Model 2 already read.

    The Builder edits `SlotSpec`; everything downstream expects the attribute
    surface of `QuestionGenerationSlot`. Rather than teach Model 2 a third slot
    shape (it already tolerates two — see `_GimSlot`), the spec is widened back
    out here, with the engine fields restored from `passthrough`.

    `legacy_type` matters more than it looks: it is what `slot_accepts` uses to
    decide which pool questions may fill a slot, so a slot that loses it during
    a Builder round trip becomes unfillable.
    """

    index: int
    marks: int
    question_type: str
    legacy_type: str
    section_title: str
    source: str = SOURCE_GENERATE
    choice_required: bool = False
    generator: str = "question_pool"
    vi_required: bool = False
    requires_image: bool = False
    requires_figure: bool = False
    asset_type: str = ""
    stream: str = ""
    constraints: Dict[str, Any] = field(default_factory=dict)
    validation: tuple = ()


#: Coarse bucket a question type falls into. Mirrors the mapping the pipeline
#: has always used; kept here so a blueprint built entirely in the Builder
#: derives the same value the engine would have set.
_LEGACY_TYPE_MAP = {
    "MCQ": "MCQ",
    "ASSERTION_REASON": "ASSERTION_REASON",
    "CASE_STUDY": "CASE_STUDY",
    "READING_COMP": "CASE_STUDY",
    "DIAGRAM": "DIAGRAM",
    "LONG_ANSWER": "LONG",
    "LETTER": "LONG",
    "COMPOSITION": "LONG",
}


def legacy_type_for(question_type: str) -> str:
    return _LEGACY_TYPE_MAP.get(normalize_type(question_type), "SHORT")


def blueprint_to_plan(blueprint: TemplateBlueprint) -> List[ResolvedSlot]:
    """Widen an edited blueprint back into slots the pipeline can run.

    A slot's `legacy_type` is taken from `passthrough` when the engine set it
    and derived from the (possibly edited) question type otherwise — because a
    teacher who changed question 7 from MCQ to Long Answer changed which pool
    questions may fill it, and carrying the old bucket forward would let an
    MCQ land in a slot that now asks for prose.
    """
    slots: List[ResolvedSlot] = []
    for spec in blueprint.slots:
        carried = spec.passthrough or {}
        engine_type = str(carried.get("legacy_type") or "")
        derived_type = legacy_type_for(spec.question_type)
        # Trust the engine's bucket only while the type it described is still
        # the type on the slot.
        keep_engine_type = bool(engine_type) and engine_type == derived_type

        slots.append(
            ResolvedSlot(
                index=spec.index,
                marks=spec.marks,
                question_type=spec.question_type,
                legacy_type=engine_type if keep_engine_type else derived_type,
                section_title=spec.section_title,
                source=spec.source,
                choice_required=spec.choice_required,
                generator=str(carried.get("generator") or "question_pool"),
                vi_required=bool(carried.get("vi_required")),
                requires_image=bool(carried.get("requires_image")),
                requires_figure=bool(carried.get("requires_figure")),
                asset_type=str(carried.get("asset_type") or ""),
                stream=str(carried.get("stream") or ""),
            )
        )
    return slots


def apply_source_ratio(
    blueprint: TemplateBlueprint, *, saved: int, generated: Optional[int] = None
) -> TemplateBlueprint:
    """Bulk-set how many slots draw from the bank vs. fresh generation.

    The Builder offers this as one slider over the whole paper, but it is
    stored per slot, so this is a bulk edit rather than a second source of
    truth. Slots are assigned bank-first in blueprint order: the earlier
    sections of a CBSE paper are the objective ones, which is exactly what a
    stocked bank fills best.

    `generated` is accepted for symmetry and validated against the total, but
    `saved` is the authority — one number cannot contradict the other.
    """
    total = blueprint.total_questions
    wanted_saved = max(0, min(total, int(saved or 0)))
    if generated is not None:
        implied = max(0, min(total, int(generated)))
        if implied + wanted_saved != total:
            logger.info(
                "Source ratio saved=%s generated=%s does not total %s; "
                "honouring saved and deriving the rest.",
                wanted_saved, implied, total,
            )

    for position, slot in enumerate(blueprint.slots):
        slot.source = SOURCE_SAVED if position < wanted_saved else SOURCE_GENERATE
    return blueprint
