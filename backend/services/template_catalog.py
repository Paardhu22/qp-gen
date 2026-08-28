"""The built-in template catalog.

Every paper now starts from a template, so the two things that used to be
*modes* have to exist here as starting points:

    "QP Type: board"                -> the CBSE Sample Paper templates below
    "QP Type: general_instructions" -> the "Describe It Yourself" template

A teacher no longer picks a mode and then discovers what it implies. They pick
a paper — "CBSE Class 10 Science, Sample Paper 2025-26" — see its blueprint,
and change whatever they like.

## Why the catalog is generated, not typed out

The supported (subject, class) matrix already exists in one place:
`generation_router._NEW_ENGINE_ELIGIBILITY`. Hand-listing ~30 catalog entries
beside it would create a second list to keep in step, and the failure mode is
silent — a subject the engine supports but the picker never offers. So the
board templates are derived from that matrix, and adding a class to the engine
adds its template for free.

## Resolution is lazy

A catalog entry is a *promise* of a blueprint, not a blueprint. Listing the
catalog must stay cheap — the picker renders on every modal open — and
compiling a blueprint means running the engine. So `list_templates()` returns
metadata only, and `resolve_builtin()` compiles on demand when a teacher
actually picks one.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field as dataclass_field
from typing import Any, Dict, List, Optional

from services.templates import TemplateBlueprint

logger = logging.getLogger("[TEMPLATES]")

#: How a built-in resolves into slots.
KIND_CBSE = "cbse_blueprint"
KIND_BLANK = "blank"
KIND_INSTRUCTIONS = "instructions"

#: The CBSE sample-paper session these blueprints target. Surfaced in the name
#: so a teacher can see at a glance which pattern they are getting, and so the
#: next session's templates are distinguishable rather than a silent change.
CBSE_SESSION = "2025-26"

_SUBJECT_LABELS: Dict[str, str] = {
    "science": "Science",
    "social science": "Social Science",
    "mathematics": "Mathematics",
    "english": "English Language & Literature",
    "hindi": "Hindi Course B",
    "telugu": "Telugu",
}

#: Shown under the template name in the picker. A teacher choosing between
#: twenty cards needs to know what makes this one different in one line.
_SUBJECT_BLURBS: Dict[str, str] = {
    "science": "Sections A–E. MCQs, assertion-reason, short and long answers, case studies.",
    "social science": "History, Geography, Civics and Economics across sections A–F.",
    "mathematics": "38 questions, sections A–E, with internal choices.",
    "english": "Reading, Grammar & Writing, and Literature.",
    "hindi": "अपठित गद्यांश, व्याकरण, पाठ्यपुस्तक और लेखन।",
    "telugu": "పఠన, వ్యాకరణం, పాఠ్యపుస్తకం మరియు రచన.",
}


@dataclass(frozen=True)
class CatalogEntry:
    """A built-in starting point. Metadata only — see the module docstring."""

    id: str
    name: str
    description: str
    kind: str
    board: str = ""
    academic_class: str = ""
    subject: str = ""
    #: Ordering weight in the picker. Lower sorts first.
    rank: int = 100

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "kind": self.kind,
            "builtin": True,
            "board": self.board,
            "academicClass": self.academic_class,
            "subject": self.subject,
            "settings": {
                "board": self.board,
                "academicClass": self.academic_class,
                "subject": self.subject,
            },
        }


def _cbse_entries() -> List[CatalogEntry]:
    # Imported here rather than at module scope: generation_router pulls in the
    # whole blueprint engine, and the catalog is imported by the API layer on
    # every request.
    from services.generation_router import _NEW_ENGINE_ELIGIBILITY

    entries: List[CatalogEntry] = []
    for subject_norm, classes in _NEW_ENGINE_ELIGIBILITY.items():
        label = _SUBJECT_LABELS.get(subject_norm, subject_norm.title())
        blurb = _SUBJECT_BLURBS.get(subject_norm, "")
        for class_num in classes:
            entries.append(
                CatalogEntry(
                    id=f"cbse-{subject_norm.replace(' ', '-')}-{class_num}",
                    name=f"CBSE Class {class_num} {label} — Sample Paper {CBSE_SESSION}",
                    description=blurb,
                    kind=KIND_CBSE,
                    board="CBSE",
                    academic_class=str(class_num),
                    subject=label,
                    # Class 10 first: it is the board year, and the reason most
                    # of these blueprints exist.
                    rank=10 if class_num == 10 else 50,
                )
            )
    return entries


#: Templates that are not tied to a subject at all.
_UNIVERSAL_ENTRIES: List[CatalogEntry] = [
    CatalogEntry(
        id="describe-it-yourself",
        name="Describe It Yourself",
        description=(
            "Write what you want in plain English — \"20 mark photosynthesis "
            "test, mostly recall\" — and we will lay out the paper."
        ),
        kind=KIND_INSTRUCTIONS,
        rank=1,
    ),
    CatalogEntry(
        id="blank",
        name="Blank Paper",
        description="Start with nothing and add every question slot yourself.",
        kind=KIND_BLANK,
        rank=2,
    ),
]


def list_templates(
    *, subject: str = "", academic_class: str = ""
) -> List[Dict[str, Any]]:
    """Catalog metadata, optionally narrowed to a subject/class.

    Filtering is a convenience for the picker, never a restriction: the
    universal entries always survive it, because "Describe It Yourself" is a
    valid choice for a subject that has no board blueprint at all.
    """
    from services.generation_router import normalize_subject

    entries = _UNIVERSAL_ENTRIES + _cbse_entries()

    wanted_subject = normalize_subject(subject) if subject else ""
    wanted_class = str(academic_class).strip()

    def keep(entry: CatalogEntry) -> bool:
        if entry.kind != KIND_CBSE:
            return True
        if wanted_subject and normalize_subject(entry.subject) != wanted_subject:
            return False
        if wanted_class and entry.academic_class != wanted_class:
            return False
        return True

    return [
        entry.as_dict()
        for entry in sorted(
            (e for e in entries if keep(e)), key=lambda e: (e.rank, e.name)
        )
    ]


def get_entry(template_id: str) -> Optional[CatalogEntry]:
    for entry in _UNIVERSAL_ENTRIES + _cbse_entries():
        if entry.id == template_id:
            return entry
    return None


@dataclass
class ResolvedTemplate:
    """A compiled blueprint plus everything else the compile learned.

    `resolve_builtin` used to return the blueprint alone, which is fine for a
    board template — a CBSE card already knows its class and subject, because
    the teacher picked them off the card. It is not fine for "Describe It
    Yourself", where the brief is the only place the class, subject, marks and
    set count are ever stated. Dropping those on the floor is what let a paper
    described as Class 9 Maths generate as Class 10 Science.
    """

    blueprint: TemplateBlueprint
    #: Settings read out of a plain-English brief, in the client's casing.
    #: Only ever carries keys the brief actually settled.
    detected: Dict[str, Any] = dataclass_field(default_factory=dict)
    #: What the designer had to correct — e.g. a stated total the structure
    #: misses. Empty unless something needs saying.
    corrections: List[str] = dataclass_field(default_factory=list)


def resolve_builtin(
    template_id: str,
    *,
    subject: str = "",
    academic_class: str = "",
    difficulty: str = "medium",
    instructions: str = "",
    user=None,
) -> TemplateBlueprint:
    """The blueprint alone, for callers that only need slots.

    Kept as the narrow entry point because most callers genuinely do not want
    the rest; `resolve_detailed` is for the one surface — the Builder — that
    can act on what the brief said.
    """
    return resolve_detailed(
        template_id,
        subject=subject,
        academic_class=academic_class,
        difficulty=difficulty,
        instructions=instructions,
        user=user,
    ).blueprint


def resolve_detailed(
    template_id: str,
    *,
    subject: str = "",
    academic_class: str = "",
    difficulty: str = "medium",
    instructions: str = "",
    user=None,
) -> ResolvedTemplate:
    """Compile a built-in entry into an editable blueprint.

    Overrides win over the entry's own subject/class so one CBSE template can
    be pointed at a different class without a separate catalog entry — the
    picker offers the specific card, but the Builder stays editable.
    """
    entry = get_entry(template_id)
    if entry is None:
        raise ValueError(f"Unknown template {template_id!r}.")

    if entry.kind == KIND_BLANK:
        return ResolvedTemplate(blueprint=TemplateBlueprint())

    resolved_subject = subject or entry.subject
    resolved_class = academic_class or entry.academic_class or "10"

    if entry.kind == KIND_INSTRUCTIONS:
        if not instructions.strip():
            # No prose yet — the Builder opens empty and the teacher types.
            # Calling the designer with nothing would spend a model call to be
            # told it has nothing to work with.
            return ResolvedTemplate(blueprint=TemplateBlueprint())
        from services.paper_design import (
            design_paper,
            design_to_slot_specs,
            validate_design,
        )

        design = validate_design(
            design_paper(
                instructions,
                subject=resolved_subject or "General",
                academic_class=str(resolved_class),
                user=user,
            )
        )
        return ResolvedTemplate(
            blueprint=_blueprint_from_design_specs(design_to_slot_specs(design)),
            detected=design.detected.to_dict(),
            corrections=list(design.corrections),
        )

    # KIND_CBSE — the blueprint engine is the authority.
    from services.generation_router import build_question_plan, extract_class_number

    plan = list(
        build_question_plan(
            topic="",
            difficulty=difficulty or "medium",
            count=-1,  # -1 = the exact board pattern
            class_num=extract_class_number(resolved_class, default=10),
            subject=resolved_subject,
            instructions="",
            count_variation="cbse",
        )
    )
    # A board card states its own class and subject, so echo them back through
    # the same channel a brief uses. That keeps one rule on the client — "apply
    # what the resolve told you" — instead of a second copy of the adopt-the-
    # card logic that already lives above.
    return ResolvedTemplate(
        blueprint=TemplateBlueprint.from_plan(plan),
        detected={
            key: value
            for key, value in (
                ("subject", entry.subject),
                ("academicClass", entry.academic_class),
            )
            if value
        },
    )


def _blueprint_from_design_specs(specs: List[Dict[str, Any]]) -> TemplateBlueprint:
    """Expand `design_to_slot_specs`' grouped output into one entry per slot.

    The designer returns "5 × MCQ worth 1 mark"; the Builder edits individual
    questions, so the group is expanded here. Doing it at the boundary means
    nothing downstream has to know the designer ever grouped them.
    """
    from services.templates import SlotSpec

    slots: List[SlotSpec] = []
    for spec in specs:
        for _ in range(int(spec.get("count") or 0)):
            slots.append(
                SlotSpec(
                    index=len(slots) + 1,
                    section_title=str(spec.get("section_title") or "Questions"),
                    question_type=str(spec.get("type") or "SHORT_ANSWER").upper(),
                    marks=int(spec.get("marks") or 1),
                )
            )
    return TemplateBlueprint(slots=slots)
