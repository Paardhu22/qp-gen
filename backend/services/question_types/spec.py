"""What a question type IS — the shape every catalogue entry is written in.

A question type used to be one flat string (`MCQ`, `SHORT_ANSWER`) doing four
jobs at once: how the student answers, what the question asks them to do, what
it comes attached to, and how hard the thinking is. That is why "MCQ" was one
entry when a real school picker shows nine kinds of MCQ, and why a "HOTS MCQ"
could not be expressed at all.

A `TypeSpec` separates those jobs into axes. A named type such as
`MCQ_ODD_ONE_OUT` is a *preset* over the axes, not a new string for every
combination — which is how one MCQ becomes twenty without a combinatorial
explosion of codes. Cognitive level is deliberately NOT an axis here: Bloom is
modelled per question, and `hots` is a slot attribute, so it can apply to any
type.

This module is Django-free and has no dependencies beyond the standard
library. The pool, the blueprint engine, the Builder menu, the DB seed and the
frontend all derive from it, so it sits at the very bottom of the graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

# ── Axes ────────────────────────────────────────────────────────────────

#: How the student answers.
FORMATS = (
    "MCQ_4",       # choose one printed option
    "MCQ_MULTI",   # choose every correct printed option
    "SHORT_TEXT",  # a word, a phrase, a line or two
    "LONG_TEXT",   # a paragraph or more
    "DRAW",        # draw, label, construct, plot
    "MARK",        # tick, cross, circle, colour — no writing
    "MATCH",       # pair items across columns
    "ORDER",       # arrange into a sequence
    "NUMERIC",     # an exact number
)

#: What the question asks the student to do.
TASKS = (
    "IDENTIFY",
    "RECALL",
    "COMPARE",
    "CLASSIFY",
    "SEQUENCE",
    "JUSTIFY",
    "APPLY",
    "CORRECT",
    "INTERPRET",
    "CREATE",
)

#: What must be printed with the question.
STIMULI = (
    "NONE",
    "PASSAGE",    # a prose passage or extract
    "SCENARIO",   # a short described situation
    "DIALOGUE",   # a conversation
    "NOTICE",     # a notice, report or other functional text
    "TABLE",      # a data or partially filled table
    "GRAPH",      # a chart the deterministic renderer can draw
    "CODE",       # a code block
    "WORD_BANK",  # a box of words shared by several items
    "IMAGE",      # a photograph, illustration, labelled diagram or template
    "MAP",        # an outline map
    "CARTOON",    # a political or social cartoon
    "AUDIO",      # listening/viewing material — never printable
)

#: Stimuli that need a printed picture the pipeline cannot produce yet.
PICTURE_STIMULI = frozenset({"IMAGE", "MAP", "CARTOON"})

#: Stimuli that are text (or rendered deterministically) and so can be
#: generated today.
PRINTABLE_STIMULI = frozenset(
    {"NONE", "PASSAGE", "SCENARIO", "DIALOGUE", "NOTICE", "TABLE", "GRAPH", "CODE", "WORD_BANK"}
)

#: How the item holds other items.
CONTAINERS = (
    "NONE",
    "SUB_PARTS",    # parts (i), (ii), (iii) whose marks sum to the parent
    "OR_GROUP",     # N alternatives, attempt exactly one
    "CHOICE_POOL",  # N items, attempt any K
    "COMMON_STEM",  # one stimulus serving separately numbered questions
)

#: How an answer is judged.
MARKINGS = (
    "EXACT",        # a fixed string or small set of accepted strings
    "KEYWORD_SET",  # any valid member of an open set
    "SCHEME",       # marks allocated to named points or steps
    "RUBRIC",       # structure and evidence, no single right answer
)

#: Whether the item's content may come from the uploaded textbook.
LANES = (
    "textbook",  # written from the chapter by Model 1
    "original",  # must be invented fresh — never drawn from the textbook
)

#: Whether the type can be put on a paper today.
AVAILABILITY = (
    "available",      # generatable now
    "needs_picture",  # needs a printed picture the pipeline cannot produce
    "internal",       # internal assessment or not a printed paper item
    "structural",     # a shape that holds questions, never a slot type
)

STATUSES = ("LIVE", "DB", "NEW")


@dataclass(frozen=True)
class OptionRule:
    """How many printed options an option-bearing type carries.

    `fixed` is for types whose options are always the same words (the four
    Assertion–Reason directions); the pool stores those verbatim rather than
    trusting a model to restate them.
    """

    min: int = 4
    max: int = 4
    multi_correct: bool = False
    fixed: Tuple[str, ...] = ()

    def accepts(self, count: int) -> bool:
        return self.min <= count <= self.max

    def describe(self) -> str:
        span = str(self.min) if self.min == self.max else f"{self.min} to {self.max}"
        if self.multi_correct:
            return f"{span} options, two or more of them correct"
        return f"exactly {span} options, exactly one correct" if self.min == self.max else f"{span} options, exactly one correct"


@dataclass(frozen=True)
class Route:
    """The independent generator that writes this type when a slot does not
    already name one — see `services.assets`."""

    generator: str
    asset_type: str = ""
    #: Other formats of the same generator that produce this same type — six
    #: letter formats are all a Letter.
    also: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Family:
    code: str
    letter: str
    name: str
    response_mode: str
    is_auto_markable: bool
    sort_order: int


@dataclass(frozen=True)
class TypeSpec:
    """One named question type.

    `shape` is the runtime question shape the rest of the pipeline already
    understands (`MCQ`, `SHORT_ANSWER`, `CASE_STUDY`, …). It decides option
    handling, which blueprint buckets may accept the question, and how the
    editor lays it out — so a new preset inherits all of that correctly without
    any consumer learning its name.
    """

    code: str
    label: str
    family: str
    ref: str
    status: str
    shape: str
    tests: str
    marks: int
    marks_range: Tuple[int, int]
    classes: Tuple[int, int]
    format: str
    task: str
    stimulus: str = "NONE"
    container: str = "NONE"
    options: Optional[OptionRule] = None
    marking: str = "EXACT"
    lane: str = "textbook"
    availability: str = ""
    #: Structure and rules, written for Model 1 and shown in the picker.
    brief: str = ""
    #: One example as it appears on a paper. Format only — never reused.
    example: str = ""
    answer: str = ""
    notes: str = ""
    #: Extra names that resolve to this type: old codes, teacher phrases.
    aliases: Tuple[str, ...] = ()
    #: Normalised subject names this type belongs to, or None for any.
    subjects: Optional[Tuple[str, ...]] = None
    #: Other catalogue references that list this same type ("I2").
    also_in: Tuple[str, ...] = ()
    auto_markable: Optional[bool] = None
    answer_lines: Optional[int] = None
    route: Optional[Route] = None
    #: Why an unavailable type cannot be used, for the picker.
    reason: str = ""

    @property
    def resolved_availability(self) -> str:
        if self.availability:
            return self.availability
        if self.stimulus in PICTURE_STIMULI:
            return "needs_picture"
        if self.stimulus == "AUDIO":
            return "internal"
        return "available"

    @property
    def is_available(self) -> bool:
        return self.resolved_availability == "available"

    @property
    def is_container(self) -> bool:
        return self.container != "NONE"

    @property
    def requires_stimulus(self) -> bool:
        return self.stimulus != "NONE"

    @property
    def requires_figure(self) -> bool:
        return self.stimulus in PICTURE_STIMULI or self.stimulus == "GRAPH"

    @property
    def produces_figure(self) -> bool:
        """True when the pipeline draws the figure itself (charts)."""
        return self.stimulus == "GRAPH"

    @property
    def unavailable_reason(self) -> str:
        if self.reason:
            return self.reason
        availability = self.resolved_availability
        if availability == "needs_picture":
            return "Needs a picture — not generated yet."
        if availability == "internal":
            return "Not a printed paper item."
        if availability == "structural":
            return "A structure that holds questions, not a question type."
        return ""


def validate_spec(spec: TypeSpec, family_codes) -> None:
    """Raise ValueError when an entry breaks the catalogue's own rules.

    Run over every entry at import, so a typo in the data fails the first test
    that imports the package rather than surfacing as an unfillable slot.
    """
    problems = []
    if not spec.code or spec.code != spec.code.upper():
        problems.append("code must be non-empty upper case")
    if spec.family not in family_codes:
        problems.append(f"unknown family {spec.family!r}")
    if spec.status not in STATUSES:
        problems.append(f"unknown status {spec.status!r}")
    if spec.format not in FORMATS:
        problems.append(f"unknown format {spec.format!r}")
    if spec.task not in TASKS:
        problems.append(f"unknown task {spec.task!r}")
    if spec.stimulus not in STIMULI:
        problems.append(f"unknown stimulus {spec.stimulus!r}")
    if spec.container not in CONTAINERS:
        problems.append(f"unknown container {spec.container!r}")
    if spec.marking not in MARKINGS:
        problems.append(f"unknown marking {spec.marking!r}")
    if spec.lane not in LANES:
        problems.append(f"unknown lane {spec.lane!r}")
    if spec.availability and spec.availability not in AVAILABILITY:
        problems.append(f"unknown availability {spec.availability!r}")
    low, high = spec.marks_range
    if not (1 <= low <= spec.marks <= high):
        problems.append(f"marks {spec.marks} outside range {spec.marks_range}")
    first, last = spec.classes
    if not (1 <= first <= last <= 10):
        problems.append(f"classes {spec.classes} outside 1–10")
    if spec.is_available and spec.resolved_availability != "structural":
        if not spec.brief.strip():
            problems.append("an available type needs a brief")
    if problems:
        raise ValueError(f"{spec.code}: " + "; ".join(problems))
