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

from services.pool.schema import normalize_type, normalize_type_code
from services.question_types import (
    FAMILIES,
    SHAPES,
    all_types,
    get as get_type,
    legacy_bucket,
    resolve_slot_type,
)
from services.question_types.subjects import CORE, OCCASIONAL, subject_types

logger = logging.getLogger("[TEMPLATES]")

#: Where a slot's question comes from. The Blueprint Builder exposes this per
#: slot AND as a whole-paper ratio; the ratio is just a bulk edit over slots, so
#: there is exactly one representation to reason about downstream.
SOURCE_GENERATE = "generate"
SOURCE_SAVED = "saved"
SOURCE_CHOICES = (SOURCE_GENERATE, SOURCE_SAVED)


# ── The question types a teacher may choose per slot ────────────────────────
#
# The menu is the question type catalogue (`services.question_types`): every
# type a paper can carry, grouped by family, narrowed to what the slot's
# subject and generator allow, and ranked for the class. Types that need a
# printed picture stay listed but disabled, so a teacher can see they exist
# without choosing one that could only come back empty.

#: Availabilities the menu lists. Internal and structural types are never a
#: slot's type, so they never appear.
_LISTED = frozenset({"available", "needs_picture"})


def _class_number(academic_class: Any) -> Optional[int]:
    """The first number in "10", "Class 10" or 10; None when there is none."""
    digits = ""
    for char in str(academic_class or ""):
        if char.isdigit():
            digits += char
        elif digits:
            break
    return int(digits) if digits else None


def _subject_key(subject: str) -> str:
    """The catalogue's subject name for whatever the Builder sent.

    "English Language & Literature" and "Hindi Course B" are display names:
    when the router does not recognise the whole name, the first word is the
    subject.
    """
    from services.generation_router import SUPPORTED_SUBJECTS, normalize_subject

    text = str(subject or "").strip()
    if not text:
        return ""
    normalised = normalize_subject(text)
    if normalised in SUPPORTED_SUBJECTS:
        return normalised
    first = text.lower().split()[0]
    return first if first in SUPPORTED_SUBJECTS else normalised


def _is_common(spec, class_num: Optional[int]) -> bool:
    """Whether a type is core when the subject has no map of its own.

    The types papers have always used, and for Classes 1–5 the worksheet
    activities those classes are actually set. A mapped subject grades its own
    types instead (`services.question_types.subjects`).
    """
    if spec.status == "LIVE":
        return True
    return class_num is not None and class_num <= 5 and spec.family == "PRIMARY_ACTIVITY"


def _menu_entry(
    spec, class_num: Optional[int], family_name: str, weight: str
) -> Dict[str, Any]:
    low, high = spec.classes
    in_class = class_num is None or low <= class_num <= high
    return {
        # The Builder writes `code` as the slot's typeCode and `shape` as its
        # questionType, so a client that only knows shapes still reads it.
        "code": spec.code,
        "shape": spec.shape,
        "label": spec.label,
        "group": family_name,
        "family": spec.family,
        "defaultMarks": spec.marks,
        "marksRange": list(spec.marks_range),
        "classes": [low, high],
        "availability": spec.resolved_availability,
        "reason": spec.unavailable_reason,
        "tests": spec.tests,
        "example": spec.example,
        "inClass": in_class,
        #: How often the subject sets it: "core", "occasional" or "rare".
        "weight": weight,
        #: The picker opens on these: core for the subject, set in this
        #: class, and printable today.
        "common": spec.is_available and in_class and weight == CORE,
    }

#: The pool types each asset generator can actually write, mirroring what
#: `services.assets.*` stamp on `build_pool_question`.
#:
#: `slot_accepts` gates on provenance BEFORE type, so a slot owned by the
#: Reading generator can never be filled by anything but a Reading asset. A
#: menu that offered "Short Answer" on such a slot would therefore be offering
#: a choice that always fails — after a spinner and a model call. This is the
#: data that keeps that choice off the menu.
#:
#: Held here as data rather than read off the generator classes so the catalog
#: endpoint does not have to import (and so autoload) the whole asset package.
GENERATOR_QUESTION_TYPES: Dict[str, tuple] = {
    "reading_asset_pool": ("READING_COMP",),
    "grammar_asset_pool": ("GRAMMAR",),
    "writing_asset_pool": ("LETTER", "COMPOSITION", "ANALYTICAL_PARAGRAPH"),
}

#: Types owned by an asset generator, and therefore NOT offered on a textbook
#: slot: Model 1 writes from the uploaded chapter, so a "Reading Comprehension"
#: it filled would be an unseen passage drawn from the seen textbook.
_ASSET_OWNED_TYPES = frozenset(
    code for codes in GENERATOR_QUESTION_TYPES.values() for code in codes
)


def types_for_generator(generator: str) -> Optional[frozenset]:
    """The shapes `generator` can write, or None for "do not restrict".

    An empty name means the caller did not say, which is how the Blueprint
    Builder asks — it edits slots before any routing has happened, so it gets
    the whole catalogue.
    """
    name = str(generator or "").strip()
    if not name:
        return None

    owned = GENERATOR_QUESTION_TYPES.get(name)
    if owned is not None:
        return frozenset(owned)

    # The textbook pool, and any unregistered name (which `generator_for_slot`
    # falls back to it anyway).
    return frozenset(s.code for s in SHAPES if not s.retired) - _ASSET_OWNED_TYPES


def question_types_for(
    subject: str = "", generator: str = "", academic_class: Any = ""
) -> List[Dict[str, Any]]:
    """The type menu for one slot.

    `subject` keeps the types that belong to it — a chronology MCQ is a Social
    Science type, a grammar gap-fill a language one — and grades each by how
    often that subject sets it (`services.question_types.subjects`). A subject
    without a map falls back to each type's own `subjects`. `academic_class` marks the
    types that class is usually set, so the picker can suggest those first;
    nothing is hidden for being outside the class, only ranked below.

    `generator` is what the editor's "swap and change type" menu passes: it is
    changing the type of a slot that has ALREADY been routed, so the menu is
    what that slot's generator can write. An independent generator writes only
    the types routed to it; the textbook pool writes every other type except
    those that must come from an independent generator.
    """
    subject_key = _subject_key(subject)
    graded = subject_types(subject_key) if subject_key else None
    class_num = _class_number(academic_class)
    name = str(generator or "").strip()
    shapes = types_for_generator(name)
    asset_generator = name in GENERATOR_QUESTION_TYPES
    family_names = {family.code: family.name for family in FAMILIES}

    menu: List[Dict[str, Any]] = []
    for spec in all_types():
        if spec.resolved_availability not in _LISTED:
            continue
        if graded is not None:
            if spec.code not in graded:
                continue
            weight = graded[spec.code]
        else:
            if subject_key and spec.subjects and subject_key not in spec.subjects:
                continue
            weight = CORE if _is_common(spec, class_num) else OCCASIONAL
        if shapes is not None:
            if spec.shape not in shapes:
                continue
            routed_here = spec.route is not None and spec.route.generator == name
            if asset_generator and not routed_here:
                continue
            if not asset_generator and spec.lane == "original" and spec.route is not None:
                continue
        menu.append(_menu_entry(spec, class_num, family_names[spec.family], weight))
    return menu


def default_marks_for(question_type: str) -> int:
    """The usual marks for a type, by catalogue code or shape; 1 if unknown."""
    code = normalize_type_code(question_type)
    spec = get_type(code) if code else None
    return spec.marks if spec else 1


# ── A slot, as the Blueprint Builder sees it ────────────────────────────────


@dataclass
class SlotSpec:
    """One question position in a template's blueprint.

    This is the editable projection of `QuestionGenerationSlot`: everything a
    teacher may change in the Builder, and nothing they may not. `generator`
    is deliberately absent as an editable field — it is derived from the
    subject and section, and a teacher editing "question 7 should be an MCQ"
    must not be able to accidentally re-route that slot away from its
    generator. `constraints`, `validation` and `instruction_hint`, by
    contrast, are NOT routing decisions — they are the structural parameters
    an asset generator needs (word counts, sub-question patterns, which
    validation rules to run) and the CBSE composite-question hints Model 1
    needs. Neither can be re-derived from `question_type`/`marks` alone, so
    they ride through `passthrough` like `asset_type` does, or a Builder round
    trip silently strips the very thing that made the slot work.
    """

    index: int
    section_title: str
    #: The runtime shape ("MCQ", "SHORT_ANSWER"). It stays the slot's
    #: `questionType` on the wire, so a client that only knows shapes keeps
    #: reading and writing blueprints exactly as it always has.
    question_type: str
    marks: int
    source: str = SOURCE_GENERATE
    choice_required: bool = False
    #: The catalogue type the teacher picked ("MCQ_ODD_ONE_OUT").
    type_code: str = ""
    #: Slot attributes: higher-order thinking and real-world framing.
    hots: bool = False
    competency: bool = False
    #: Carried through untouched so a round-trip through the Builder does not
    #: strip what the blueprint engine put there.
    passthrough: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # However the spec was built — the Builder, the designer, the engine's
        # projection — its shape, catalogue type and attributes must agree.
        slot_type = resolve_slot_type(
            self.type_code,
            self.question_type,
            hots=self.hots,
            competency=self.competency,
        )
        self.question_type = slot_type.shape
        self.type_code = slot_type.code
        self.hots = slot_type.hots
        self.competency = slot_type.competency

    def as_dict(self) -> Dict[str, Any]:
        payload = {
            "index": self.index,
            "sectionTitle": self.section_title,
            "questionType": self.question_type,
            "typeCode": self.type_code,
            "marks": self.marks,
            "source": self.source,
            "choiceRequired": self.choice_required,
        }
        if self.hots:
            payload["hots"] = True
        if self.competency:
            payload["competency"] = True
        if self.passthrough:
            payload["passthrough"] = dict(self.passthrough)
        return payload

    @classmethod
    def from_dict(cls, raw: Any, *, index: int) -> "SlotSpec":
        if not isinstance(raw, dict):
            raise ValueError(f"Slot {index} is not an object.")

        requested_type = raw.get("questionType") or raw.get("question_type") or ""
        requested_code = raw.get("typeCode") or raw.get("type_code") or ""
        if (requested_type or requested_code) and not (
            normalize_type(requested_type) or normalize_type_code(requested_code)
        ):
            # A client sending a type this build does not have. Fall back
            # rather than reject — a paper with one mistyped slot is
            # recoverable, a 400 on the whole blueprint is not.
            #
            # Log what was SENT: the normalisers return "" for everything they
            # do not recognise, so logging their output would make every one
            # of these warnings identical and useless.
            logger.warning(
                "Unknown question type %r (type code %r) on slot %s; using SHORT_ANSWER.",
                requested_type, requested_code, index,
            )
        slot_type = resolve_slot_type(
            requested_code,
            requested_type,
            hots=bool(raw.get("hots")),
            competency=bool(raw.get("competency")),
        )
        question_type = slot_type.shape

        try:
            marks = int(raw.get("marks") or default_marks_for(slot_type.code))
        except (TypeError, ValueError):
            marks = default_marks_for(slot_type.code)
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
            type_code=slot_type.code,
            hots=slot_type.hots,
            competency=slot_type.competency,
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
                    type_code=str(getattr(slot, "type_code", "") or ""),
                    hots=bool(getattr(slot, "hots", False)),
                    competency=bool(getattr(slot, "competency", False)),
                    marks=int(getattr(slot, "marks", 0) or 1),
                    source=SOURCE_GENERATE,
                    choice_required=bool(getattr(slot, "choice_required", False)),
                    # Everything the engine decided that the Builder does not
                    # expose. Kept so re-resolving a pinned blueprint does not
                    # lose the generator routing OR the structural detail
                    # (`constraints`, `validation`, `instruction_hint`) an
                    # asset generator or Model 1 needs to fill the slot
                    # correctly — none of those are re-derivable from
                    # `question_type`/`marks` the way `legacy_type` is.
                    passthrough={
                        key: getattr(slot, key)
                        for key in (
                            "legacy_type",
                            "generator",
                            "requires_figure",
                            "asset_type",
                            "stream",
                            "constraints",
                            "validation",
                            "instruction_hint",
                        )
                        if getattr(slot, key, None)
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
    requires_figure: bool = False
    asset_type: str = ""
    stream: str = ""
    constraints: Dict[str, Any] = field(default_factory=dict)
    validation: tuple = ()
    #: Structural detail a generator can't derive from type/marks alone (word
    #: counts, sub-question breakdowns, "answer any 4 of 5") plus the CBSE
    #: composite-question notes `batches_from_plan` folds into Model 1's
    #: instructions. Read by `services.language_validation` too.
    instruction_hint: str = ""
    #: The catalogue type and slot attributes the teacher chose. Model 1's
    #: recipe, assembly and set variants all read these off the slot.
    type_code: str = ""
    hots: bool = False
    competency: bool = False


def legacy_type_for(question_type: str) -> str:
    """The coarse bucket a question type falls into.

    Answered by the catalogue, the same place the engine and the pipeline ask,
    so a blueprint built entirely in the Builder derives exactly the value the
    engine would have set.
    """
    return legacy_bucket(question_type)


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

        # A slot the engine routed keeps its generator. A slot the teacher
        # added has none, and a type whose content must never come from the
        # textbook — an unseen passage, a grammar set, a notice — goes to the
        # independent generator that writes it instead of to Model 1.
        generator = str(carried.get("generator") or "")
        asset_type = str(carried.get("asset_type") or "")
        constraints = dict(carried.get("constraints") or {})
        type_entry = get_type(spec.type_code)
        if (
            not generator
            and type_entry is not None
            and type_entry.lane == "original"
            and type_entry.route is not None
        ):
            generator = type_entry.route.generator
            asset_type = asset_type or type_entry.route.asset_type
            constraints = {**type_entry.route.constraint_dict(), **constraints}

        slots.append(
            ResolvedSlot(
                index=spec.index,
                marks=spec.marks,
                question_type=spec.question_type,
                type_code=spec.type_code,
                hots=spec.hots,
                competency=spec.competency,
                legacy_type=engine_type if keep_engine_type else derived_type,
                section_title=spec.section_title,
                source=spec.source,
                choice_required=spec.choice_required,
                generator=generator or "question_pool",
                requires_figure=bool(carried.get("requires_figure")),
                asset_type=asset_type,
                stream=str(carried.get("stream") or ""),
                constraints=constraints,
                validation=tuple(carried.get("validation") or ()),
                instruction_hint=str(carried.get("instruction_hint") or ""),
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
