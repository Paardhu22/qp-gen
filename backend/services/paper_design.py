"""Turn free-form instructions into a paper structure.

General Instructions Mode lets a teacher describe a paper in their own words
instead of accepting a CBSE blueprint. The old parser (`services/pool/gim.py`)
read a narrow grammar — "5 MCQs, 3 short answers of 2 marks" — and nothing
else, so anything a teacher would actually type ("weekly test on
photosynthesis, mostly recall, 20 marks, half an hour") fell through to a
generic ten-question default that ignored what they wrote.

The shape here is: **a model designs, this module validates.**

    instructions ──► design_paper()   one structured OpenAI call
                          │
                          ▼
                   validate_design()  pure, deterministic
                          │           • question types in the vocabulary
                          │           • counts and marks positive
                          │           • totals recomputed, never trusted
                          ▼
                     PaperDesign ──► slots ──► Model 2

The split matters. A model is the only thing that can read arbitrary prose,
and it is also the thing that will confidently return a "20 mark" paper whose
sections add up to 23. So nothing the model says about arithmetic, question
types or counts is taken on faith; `validate_design` recomputes all of it and
reports what it had to correct.

Bloom's taxonomy is deliberately absent. The CBSE blueprint path targets Bloom
bands per slot because the board pattern demands it; General Instructions Mode
exists precisely for papers that follow a school's own template — a weekly
test, a revision sheet — where imposing a board's cognitive distribution would
override the thing the teacher asked for. Pool questions still carry a `blooms`
tag from Model 1; nothing here selects on it.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from django.conf import settings

from services.openai_service import _record_usage, get_openai_client

logger = logging.getLogger("[DESIGN]")


def _model() -> str:
    # Same model as the dashboard assistant: this is comprehension of a short
    # instruction, not question writing, and POOL_MODEL's budget belongs to the
    # questions themselves.
    return getattr(settings, "CHAT_MODEL", "gpt-4.1-mini")


# ── Vocabulary ──────────────────────────────────────────────────────────
#
# The question types Model 2 can actually fill. A design naming anything else
# is corrected to the nearest of these rather than rejected — the teacher's
# paper should still generate.

QUESTION_TYPES = (
    "MCQ",
    "ASSERTION_REASON",
    "SHORT_ANSWER",
    "LONG_ANSWER",
    "CASE_STUDY",
    "FILL_BLANK",
    "TRUE_FALSE",
    "MATCH_FOLLOWING",
    # A drawing question. This vocabulary is the entire menu the designer is
    # shown, so leaving DIAGRAM off it did not merely lose the label — a
    # teacher who wrote "10 image based questions" got ten CASE_STUDY slots,
    # because CASE_STUDY was the nearest thing on offer.
    #
    # It no longer causes any image to be produced: the image stage is gone
    # from the pipeline. A DIAGRAM slot now means what it means on a printed
    # CBSE paper — the STUDENT draws or labels — and Model 1 is instructed to
    # write such questions self-contained, never referring to a figure the
    # paper does not carry.
    "DIAGRAM",
)

DEFAULT_MARKS = {
    "MCQ": 1,
    "ASSERTION_REASON": 1,
    "FILL_BLANK": 1,
    "TRUE_FALSE": 1,
    "MATCH_FOLLOWING": 4,
    "SHORT_ANSWER": 2,
    "LONG_ANSWER": 5,
    "CASE_STUDY": 4,
    "DIAGRAM": 2,
}

# Everything a model might plausibly write for a type, mapped to the vocabulary.
_TYPE_ALIASES = {
    "multiple choice": "MCQ",
    "multiple-choice": "MCQ",
    "objective": "MCQ",
    "mcq": "MCQ",
    "assertion reason": "ASSERTION_REASON",
    "assertion-reason": "ASSERTION_REASON",
    "assertion and reason": "ASSERTION_REASON",
    "ar": "ASSERTION_REASON",
    "very short answer": "SHORT_ANSWER",
    "very short": "SHORT_ANSWER",
    "vsa": "SHORT_ANSWER",
    "short answer": "SHORT_ANSWER",
    "short": "SHORT_ANSWER",
    "sa": "SHORT_ANSWER",
    "long answer": "LONG_ANSWER",
    "long": "LONG_ANSWER",
    "la": "LONG_ANSWER",
    "essay": "LONG_ANSWER",
    "descriptive": "LONG_ANSWER",
    "case study": "CASE_STUDY",
    "case-based": "CASE_STUDY",
    "case based": "CASE_STUDY",
    "source based": "CASE_STUDY",
    "passage": "CASE_STUDY",
    "cbq": "CASE_STUDY",
    "fill in the blanks": "FILL_BLANK",
    "fill in the blank": "FILL_BLANK",
    "fill blank": "FILL_BLANK",
    "blanks": "FILL_BLANK",
    "true or false": "TRUE_FALSE",
    "true/false": "TRUE_FALSE",
    "true false": "TRUE_FALSE",
    "match the following": "MATCH_FOLLOWING",
    "matching": "MATCH_FOLLOWING",
    "match": "MATCH_FOLLOWING",
    # Everything a teacher calls a figure question. "image based" and "picture
    # based" are the two that actually get typed.
    "image based": "DIAGRAM",
    "image-based": "DIAGRAM",
    "images based": "DIAGRAM",
    "picture based": "DIAGRAM",
    "picture-based": "DIAGRAM",
    "diagram based": "DIAGRAM",
    "diagram-based": "DIAGRAM",
    "figure based": "DIAGRAM",
    "figure-based": "DIAGRAM",
    "map based": "DIAGRAM",
    "map-based": "DIAGRAM",
    "diagram": "DIAGRAM",
    "figure": "DIAGRAM",
    "picture": "DIAGRAM",
    "image": "DIAGRAM",
    "map": "DIAGRAM",
    "chart": "DIAGRAM",
    "graph": "DIAGRAM",
}


def normalize_question_type(raw: Any) -> str:
    """Map anything a model wrote onto the vocabulary Model 2 can fill."""
    text = str(raw or "").strip().lower().replace("_", " ")
    if not text:
        return "SHORT_ANSWER"

    direct = text.replace(" ", "_").upper()
    if direct in QUESTION_TYPES:
        return direct

    if text in _TYPE_ALIASES:
        return _TYPE_ALIASES[text]

    # Longest alias first so "very short answer" is not eaten by "short".
    for alias in sorted(_TYPE_ALIASES, key=len, reverse=True):
        if alias in text:
            return _TYPE_ALIASES[alias]

    return "SHORT_ANSWER"


# ── The design ──────────────────────────────────────────────────────────


@dataclass
class QuestionGroup:
    """N questions of one type and mark value, inside a section."""

    question_type: str
    marks: int
    count: int
    #: Optional narrowing the teacher asked for ("on photosynthesis").
    topic: str = ""
    #: Whether each question in the group carries an internal OR choice.
    choice: bool = False

    @property
    def total_marks(self) -> int:
        return self.marks * self.count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.question_type,
            "marks": self.marks,
            "count": self.count,
            "topic": self.topic,
            "choice": self.choice,
            "totalMarks": self.total_marks,
        }


@dataclass
class DesignSection:
    title: str
    groups: List[QuestionGroup] = field(default_factory=list)
    #: Section-level rubric line, printed under the heading.
    instruction: str = ""

    @property
    def total_marks(self) -> int:
        return sum(g.total_marks for g in self.groups)

    @property
    def total_questions(self) -> int:
        return sum(g.count for g in self.groups)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "instruction": self.instruction,
            "groups": [g.to_dict() for g in self.groups],
            "totalMarks": self.total_marks,
            "totalQuestions": self.total_questions,
        }


@dataclass
class DetectedSettings:
    """What the brief said about the paper's *identity*, as opposed to its shape.

    `PaperDesign` answers "how many of what kind, worth what". This answers
    "whose paper is it" — class, subject, scale — and it exists because those
    were the fields a plain-English brief silently lost. "Class 9 Maths, 80
    marks, one set" used to resolve against whatever the Builder's rail
    happened to be defaulted to (Science, Class 10, 1 set), so the teacher's
    first four words were read by the designer as prose and then contradicted
    by the settings actually sent to generation.

    Every field is empty/None unless the teacher *stated* it. An unstated
    subject must stay unstated: a guess here is worse than a blank, because a
    blank leaves the rail's default visible and a guess overwrites it.
    """

    subject: str = ""
    academic_class: str = ""
    total_marks: Optional[int] = None
    number_of_sets: Optional[int] = None
    difficulty: str = ""

    def is_empty(self) -> bool:
        return not any(
            (
                self.subject,
                self.academic_class,
                self.total_marks,
                self.number_of_sets,
                self.difficulty,
            )
        )

    def to_dict(self) -> Dict[str, Any]:
        """Only the fields that were actually read, in the client's casing.

        Omitting rather than nulling matters: the Builder applies this over a
        rail the teacher may have already touched, so `{}` has to mean "the
        brief said nothing", never "the brief said blank".
        """
        out: Dict[str, Any] = {}
        if self.subject:
            out["subject"] = self.subject
        if self.academic_class:
            out["academicClass"] = self.academic_class
        if self.total_marks:
            out["totalMarks"] = self.total_marks
        if self.number_of_sets:
            out["numberOfSets"] = str(self.number_of_sets)
        if self.difficulty:
            out["difficulty"] = self.difficulty
        return out


@dataclass
class PaperDesign:
    sections: List[DesignSection] = field(default_factory=list)
    #: Printed header lines, e.g. "Time: 1 hour". Free-form by design — a
    #: school's weekly test header is not the board's.
    title: str = ""
    duration: str = ""
    general_instructions: List[str] = field(default_factory=list)
    #: What `validate_design` had to correct. Surfaced, never silent.
    corrections: List[str] = field(default_factory=list)
    #: True when the design came from the offline fallback parser.
    degraded: bool = False
    #: Class/subject/scale read out of the brief. See `DetectedSettings`.
    detected: DetectedSettings = field(default_factory=DetectedSettings)

    @property
    def total_marks(self) -> int:
        return sum(s.total_marks for s in self.sections)

    @property
    def total_questions(self) -> int:
        return sum(s.total_questions for s in self.sections)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "duration": self.duration,
            "sections": [s.to_dict() for s in self.sections],
            "generalInstructions": list(self.general_instructions),
            "totalMarks": self.total_marks,
            "totalQuestions": self.total_questions,
            "corrections": list(self.corrections),
            "degraded": self.degraded,
            "detected": self.detected.to_dict(),
        }


_DESIGN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {
            "type": ["string", "null"],
            "description": "Paper title if the teacher named one, else null.",
        },
        "duration": {
            "type": ["string", "null"],
            "description": "Time allowed if stated, e.g. '1 hour'. Else null.",
        },
        "generalInstructions": {
            "type": ["array", "null"],
            "items": {"type": "string"},
            "description": (
                "Rubric lines to print under the header, e.g. 'All questions "
                "are compulsory.' Only rules the teacher actually stated or "
                "that follow directly from the structure."
            ),
        },
        "detected": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "description": (
                "What the teacher stated about the paper itself, as opposed "
                "to its structure. Every field is null unless they actually "
                "said it — these overwrite the form the teacher is looking "
                "at, so a guess is worse than a null."
            ),
            "properties": {
                "subject": {
                    "type": ["string", "null"],
                    "description": (
                        "One of: Science, Mathematics, Social Science, "
                        "English, Hindi, Telugu. Null if not stated. Map what "
                        "they wrote onto this list — 'maths'/'algebra' is "
                        "Mathematics, 'physics'/'biology'/'chemistry' is "
                        "Science, 'history'/'civics'/'geography' is Social "
                        "Science — but return null rather than forcing a "
                        "subject that is not one of these."
                    ),
                },
                "academicClass": {
                    "type": ["string", "null"],
                    "description": (
                        "The class/grade/standard as a number 1-12, e.g. "
                        "'9' for 'Class 9' or 'IX standard'. Null if not "
                        "stated."
                    ),
                },
                "totalMarks": {
                    "type": ["integer", "null"],
                    "description": (
                        "The paper's total marks if the teacher stated one, "
                        "e.g. 80 for '80 marks'. This is the same figure the "
                        "sections must add up to. Null if not stated."
                    ),
                },
                "numberOfSets": {
                    "type": ["integer", "null"],
                    "description": (
                        "How many variant sets of the paper: 1, 2 or 3. "
                        "'one set' is 1, 'sets A and B' is 2. Null if not "
                        "stated."
                    ),
                },
                "difficulty": {
                    "type": ["string", "null"],
                    "description": (
                        "One of: easy, medium, hard — only if the teacher "
                        "described the paper's overall difficulty ('keep it "
                        "easy', 'tough revision test'). Null otherwise. Do "
                        "NOT infer difficulty from question types."
                    ),
                },
            },
            "required": [
                "subject",
                "academicClass",
                "totalMarks",
                "numberOfSets",
                "difficulty",
            ],
        },
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "instruction": {"type": ["string", "null"]},
                    "groups": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "description": (
                                        "One of: MCQ, ASSERTION_REASON, "
                                        "SHORT_ANSWER, LONG_ANSWER, CASE_STUDY, "
                                        "FILL_BLANK, TRUE_FALSE, MATCH_FOLLOWING, "
                                        "DIAGRAM. Use DIAGRAM whenever the "
                                        "teacher asks for image / picture / "
                                        "figure / map / diagram based questions "
                                        "— it is what makes the paper carry "
                                        "figures at all."
                                    ),
                                },
                                "marks": {"type": "integer"},
                                "count": {"type": "integer"},
                                "topic": {"type": ["string", "null"]},
                                "choice": {"type": ["boolean", "null"]},
                            },
                            "required": ["type", "marks", "count", "topic", "choice"],
                        },
                    },
                },
                "required": ["title", "instruction", "groups"],
            },
        },
    },
    "required": [
        "title",
        "duration",
        "generalInstructions",
        "detected",
        "sections",
    ],
}


_DESIGN_PROMPT = """\
You lay out question papers for Indian school teachers. Read the teacher's \
instructions and return the structure of the paper they described.

You do NOT write questions. You decide only how many of what kind, worth what, \
in which sections.

Rules:
- Follow the instructions given. They are the specification, not a hint. If \
they say four sections, return four sections; if they say no MCQs, use none.
- Do NOT impose a board pattern the teacher did not ask for. This mode exists \
for a school's own templates — weekly tests, revision sheets, unit tests.
- If a total mark figure is stated, the section marks must add up to exactly \
that. Adjust counts to make it true.
- If no structure is given at all, produce the simplest paper that satisfies \
what IS given, in a single section named "Questions".
- Name sections the way the teacher did ("Section A", "Part 1"). If they did \
not name any, use one section called "Questions".
- `marks` is per question, not per group.
- Use `topic` only when the teacher tied a specific group to a specific topic.
- `choice: true` only if they asked for internal choice / "or" options.
- `generalInstructions` are rubric lines to print on the paper. Keep them to \
what was stated or what plainly follows from the structure. No invented rules.

`detected` is separate from the structure and follows one rule: report only \
what the teacher SAID, and null everything else. It is written straight into \
the form on the teacher's screen, so a plausible guess silently overwrites a \
choice they made, while a null leaves their own setting alone. Any Subject/\
Class line given to you above the instructions is the form's current default, \
NOT a fact about the paper — if the instructions name a different class or \
subject, the instructions win and `detected` must say so.\
"""


def detected_from_prose(instructions: str) -> DetectedSettings:
    """`infer_settings` in `DetectedSettings` clothing, for the offline path.

    The regex reader already exists and is already the conservative one — it
    guards "of 2 marks each" against being read as the paper total, which a
    second implementation would have had to rediscover. So this is an adapter,
    not a parser: same rules, typed shape.
    """
    found = infer_settings(instructions)

    marks: Optional[int] = None
    if found.get("marks"):
        try:
            marks = int(found["marks"])
        except ValueError:
            marks = None

    sets: Optional[int] = None
    if found.get("numberOfSets"):
        try:
            sets = int(found["numberOfSets"])
        except ValueError:
            sets = None

    return DetectedSettings(
        subject=found.get("subject", ""),
        academic_class=found.get("academicClass", ""),
        total_marks=marks,
        number_of_sets=sets,
        difficulty=found.get("difficulty", ""),
    )


def _fallback_design(
    instructions: str,
    source_count: int,
    exact_count: Optional[int],
) -> PaperDesign:
    """The old regex parser, kept for when the model call cannot be made.

    Not a second opinion — a lifeboat. Losing the OpenAI call should degrade
    the paper's structure, not fail the generation outright, so a teacher
    offline or rate-limited still gets something shaped like what they asked
    for. `degraded` marks it so the interface can say so.
    """
    from services.pool.gim import _parse_gim_instructions

    parsed = _parse_gim_instructions(instructions, source_count, exact_count)
    sections: Dict[str, DesignSection] = {}
    order: List[str] = []
    for spec in parsed:
        title = spec.get("section_title") or "Questions"
        if title not in sections:
            sections[title] = DesignSection(title=title)
            order.append(title)
        sections[title].groups.append(
            QuestionGroup(
                question_type=normalize_question_type(spec.get("type")),
                marks=max(1, int(spec.get("marks") or 1)),
                count=max(1, int(spec.get("count") or 1)),
            )
        )
    return PaperDesign(
        sections=[sections[t] for t in order],
        degraded=True,
        detected=detected_from_prose(instructions),
        corrections=[
            "Designed from a simplified reading of your instructions — the "
            "paper designer was unavailable."
        ],
    )


def _degraded_design(
    text: str,
    source_count: int,
    exact_count: Optional[int],
    total_marks: Optional[int],
) -> PaperDesign:
    """The lifeboat, validated the way the model's design is.

    `design_paper` promises every caller a *validated* design. The fallback
    used to be returned raw — so the one design most likely to need checking
    was the one that skipped it, and a caller wanting the guarantee had to
    re-run the validator over everything to cover this branch.
    """
    design = _fallback_design(text, source_count, exact_count)
    return validate_design(
        design,
        total_marks=total_marks or design.detected.total_marks,
        exact_count=exact_count,
    )


def design_paper(
    instructions: str,
    *,
    subject: str = "",
    academic_class: str = "",
    total_marks: Optional[int] = None,
    exact_count: Optional[int] = None,
    source_count: int = 0,
    user: Any = None,
) -> PaperDesign:
    """Read free-form instructions and return the paper they describe."""
    text = (instructions or "").strip()
    if not text:
        return PaperDesign()

    # Subject and class are labelled as the form's defaults rather than stated
    # as fact. They usually ARE just defaults — the Builder's rail starts on
    # Science/Class 10 — and presenting them as given had the designer laying
    # out a Class 10 Science paper while the teacher's own words underneath
    # said Class 9 Maths. Marks and counts are different: those reach here only
    # when a caller genuinely fixed them, so they stay requirements.
    context_lines = []
    if subject:
        context_lines.append(f"Form default subject (may be wrong): {subject}")
    if academic_class:
        context_lines.append(f"Form default class (may be wrong): {academic_class}")
    if total_marks:
        context_lines.append(f"Total marks required: {total_marks}")
    if exact_count:
        context_lines.append(f"Total questions required: {exact_count}")
    if source_count:
        context_lines.append(f"Uploaded source documents: {source_count}")

    try:
        client = get_openai_client()
        completion = client.chat.completions.create(
            model=_model(),
            messages=[
                {"role": "system", "content": _DESIGN_PROMPT},
                {
                    "role": "user",
                    "content": (
                        ("\n".join(context_lines) + "\n\n" if context_lines else "")
                        + "Teacher's instructions:\n"
                        + text
                    ),
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "paper_design",
                    "schema": _DESIGN_SCHEMA,
                    "strict": False,
                },
            },
        )
    except Exception as exc:
        logger.warning("Paper design call failed, falling back to the parser: %s", exc)
        return _degraded_design(text, source_count, exact_count, total_marks)

    _record_usage(user, "paper_design", _model(), completion.usage)

    try:
        raw = json.loads(completion.choices[0].message.content or "{}")
    except (json.JSONDecodeError, TypeError):
        logger.warning("Paper design returned unparseable JSON")
        return _degraded_design(text, source_count, exact_count, total_marks)

    design = _design_from_raw(raw)
    if not design.sections:
        logger.warning("Paper design returned no sections; falling back")
        return _degraded_design(text, source_count, exact_count, total_marks)

    # A mark total the teacher wrote into the brief is as binding as one a
    # caller passed in — it is the same number, just arriving as prose. Without
    # this, "80 marks" was read by the model and then checked against nothing,
    # so a design that came to 74 was reported as fine.
    return validate_design(
        design,
        total_marks=total_marks or design.detected.total_marks,
        exact_count=exact_count,
    )


def _design_from_raw(raw: Any) -> PaperDesign:
    """Structural read of the model's JSON. No judgement, no arithmetic."""
    if not isinstance(raw, dict):
        return PaperDesign()

    sections: List[DesignSection] = []
    for raw_section in raw.get("sections") or []:
        if not isinstance(raw_section, dict):
            continue
        groups: List[QuestionGroup] = []
        for raw_group in raw_section.get("groups") or []:
            if not isinstance(raw_group, dict):
                continue
            try:
                marks = int(raw_group.get("marks") or 0)
                count = int(raw_group.get("count") or 0)
            except (TypeError, ValueError):
                continue
            groups.append(
                QuestionGroup(
                    question_type=normalize_question_type(raw_group.get("type")),
                    marks=marks,
                    count=count,
                    topic=str(raw_group.get("topic") or "").strip(),
                    choice=bool(raw_group.get("choice")),
                )
            )
        if not groups:
            continue
        sections.append(
            DesignSection(
                title=str(raw_section.get("title") or "Questions").strip() or "Questions",
                groups=groups,
                instruction=str(raw_section.get("instruction") or "").strip(),
            )
        )

    instructions = raw.get("generalInstructions")
    return PaperDesign(
        sections=sections,
        title=str(raw.get("title") or "").strip(),
        duration=str(raw.get("duration") or "").strip(),
        general_instructions=[
            str(line).strip()
            for line in (instructions if isinstance(instructions, list) else [])
            if str(line).strip()
        ],
        detected=_detected_from_raw(raw.get("detected")),
    )


def _detected_from_raw(raw: Any) -> DetectedSettings:
    """Pull `detected` back onto the closed sets the rest of the app accepts.

    The same argument the module header makes about arithmetic applies to these
    fields, and more sharply: they are written into a form the teacher is
    looking at. A subject outside `SUBJECTS` would render as a blank select; a
    class of "10th" would not match the option list. Anything that does not
    land cleanly on a known value is dropped back to "not stated", which leaves
    the teacher's own setting standing.
    """
    if not isinstance(raw, dict):
        return DetectedSettings()

    subject = ""
    stated_subject = str(raw.get("subject") or "").strip()
    if stated_subject:
        for known in SUBJECTS:
            if known.lower() == stated_subject.lower():
                subject = known
                break

    academic_class = ""
    stated_class = str(raw.get("academicClass") or "").strip()
    if stated_class:
        digits = re.search(r"\d{1,2}", stated_class)
        if digits and 1 <= int(digits.group()) <= 12:
            academic_class = str(int(digits.group()))

    def positive_int(key: str, ceiling: int) -> Optional[int]:
        try:
            value = int(raw.get(key) or 0)
        except (TypeError, ValueError):
            return None
        return value if 1 <= value <= ceiling else None

    difficulty = ""
    stated_difficulty = str(raw.get("difficulty") or "").strip().lower()
    if stated_difficulty in {"easy", "medium", "hard"}:
        difficulty = stated_difficulty

    return DetectedSettings(
        subject=subject,
        academic_class=academic_class,
        # The ceiling is `MAX_QUESTIONS * MAX_MARKS_PER_QUESTION` in spirit;
        # in practice no school paper is worth four figures, and a total that
        # large is a misread digit rather than a request.
        total_marks=positive_int("totalMarks", 999),
        number_of_sets=positive_int("numberOfSets", 3),
        difficulty=difficulty,
    )


# Beyond this a "paper" is a runaway model, not a teacher's intent. The pool
# is sized off the slot count, so an unbounded design is also an unbounded bill.
MAX_QUESTIONS = 120
MAX_MARKS_PER_QUESTION = 30


def validate_design(
    design: PaperDesign,
    *,
    total_marks: Optional[int] = None,
    exact_count: Optional[int] = None,
) -> PaperDesign:
    """Make the design internally consistent, and say what had to change.

    Pure and deterministic — nothing here calls a model. Every correction is
    recorded on `design.corrections` so the interface can show the teacher what
    was adjusted instead of quietly producing a paper that is not what they
    asked for.
    """
    corrections: List[str] = list(design.corrections)

    clean_sections: List[DesignSection] = []
    for section in design.sections:
        groups: List[QuestionGroup] = []
        for group in section.groups:
            question_type = normalize_question_type(group.question_type)

            count = group.count
            if count < 1:
                corrections.append(
                    f"{section.title}: dropped a group with a count of {count}."
                )
                continue

            marks = group.marks
            if marks < 1:
                marks = DEFAULT_MARKS.get(question_type, 2)
                corrections.append(
                    f"{section.title}: {question_type.replace('_', ' ').lower()} "
                    f"had no mark value; used {marks}."
                )
            elif marks > MAX_MARKS_PER_QUESTION:
                corrections.append(
                    f"{section.title}: capped {marks} marks per question at "
                    f"{MAX_MARKS_PER_QUESTION}."
                )
                marks = MAX_MARKS_PER_QUESTION

            groups.append(
                QuestionGroup(
                    question_type=question_type,
                    marks=marks,
                    count=count,
                    topic=group.topic,
                    choice=group.choice,
                )
            )

        if not groups:
            continue
        clean_sections.append(
            DesignSection(
                title=section.title or "Questions",
                groups=groups,
                instruction=section.instruction,
            )
        )

    design.sections = clean_sections
    design.corrections = corrections

    if not clean_sections:
        return design

    # Hard ceiling before anything else reads the totals.
    while design.total_questions > MAX_QUESTIONS:
        largest = max(
            (g for s in design.sections for g in s.groups),
            key=lambda g: g.count,
        )
        excess = design.total_questions - MAX_QUESTIONS
        largest.count = max(1, largest.count - excess)
        corrections.append(
            f"Trimmed the paper to {MAX_QUESTIONS} questions — the design asked "
            "for more than one paper can hold."
        )
        break

    # A stated total is the teacher's, not the model's. Report the mismatch
    # rather than silently reshaping the paper to hit the number: which
    # questions to drop is a pedagogical choice, and guessing it is exactly the
    # kind of help nobody asked for.
    if total_marks and design.total_marks != total_marks:
        corrections.append(
            f"You asked for {total_marks} marks; this structure comes to "
            f"{design.total_marks}."
        )
    if exact_count and design.total_questions != exact_count:
        corrections.append(
            f"You asked for {exact_count} questions; this structure has "
            f"{design.total_questions}."
        )

    design.corrections = corrections
    return design


# ── Gaps ────────────────────────────────────────────────────────────────
#
# Derived here, not asked of the model — the same argument `chat_service`
# makes for its follow-ups. Every constraint the generator needs has a closed
# set of answers, so a model can only add the chance of offering a seventh
# subject. What the model reads is the teacher's prose; what fills the form is
# this.


@dataclass
class Gap:
    """One thing the instructions did not settle."""

    field: str
    label: str
    #: "required" blocks generation; "assumed" is filled and shown as changeable.
    kind: str
    options: List[Dict[str, str]] = field(default_factory=list)
    #: The value used when `kind == "assumed"`.
    value: str = ""
    #: Why this default, in the teacher's terms.
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "label": self.label,
            "kind": self.kind,
            "options": list(self.options),
            "value": self.value,
            "note": self.note,
        }


SUBJECTS = ["Science", "Mathematics", "Social Science", "English", "Hindi", "Telugu"]

_DIFFICULTY_OPTIONS = [
    {"value": "easy", "label": "Easy"},
    {"value": "medium", "label": "Medium"},
    {"value": "hard", "label": "Hard"},
]

_SET_OPTIONS = [
    {"value": "1", "label": "1 set"},
    {"value": "2", "label": "2 sets"},
    {"value": "3", "label": "3 sets"},
]


def find_gaps(
    settings_in: Dict[str, Any],
    design: Optional[PaperDesign] = None,
    *,
    source_count: int = 0,
) -> List[Gap]:
    """What is missing, split into what blocks and what gets assumed.

    Only two things genuinely block. Subject decides which generator writes the
    questions, and no default can stand in for it. Content — a chapter upload or
    a named topic — is what the questions are drawn FROM; without it there is
    nothing to write about. Everything else has a defensible default, so the
    teacher gets to press Generate and see the assumptions rather than answer a
    form first.
    """
    gaps: List[Gap] = []

    def value_of(key: str) -> str:
        return str(settings_in.get(key) or "").strip()

    if not value_of("subject"):
        gaps.append(
            Gap(
                field="subject",
                label="Which subject?",
                kind="required",
                options=[{"value": s, "label": s} for s in SUBJECTS],
            )
        )

    if not value_of("academicClass"):
        gaps.append(
            Gap(
                field="academicClass",
                label="Which class?",
                kind="required",
                options=[
                    {"value": str(n), "label": f"Class {n}"} for n in range(1, 11)
                ],
            )
        )

    if source_count == 0:
        gaps.append(
            Gap(
                field="sources",
                label="Add the chapter this paper covers",
                kind="required",
                note=(
                    "Upload a PDF or pick a textbook chapter — the questions are "
                    "written from it."
                ),
            )
        )

    if not value_of("difficulty"):
        gaps.append(
            Gap(
                field="difficulty",
                label="Difficulty",
                kind="assumed",
                options=_DIFFICULTY_OPTIONS,
                value="medium",
                note="Assumed medium.",
            )
        )

    if not value_of("numberOfSets"):
        gaps.append(
            Gap(
                field="numberOfSets",
                label="Parallel sets",
                kind="assumed",
                options=_SET_OPTIONS,
                value="1",
                note="Assumed one set.",
            )
        )

    if not value_of("marks"):
        total = design.total_marks if design else 0
        gaps.append(
            Gap(
                field="marks",
                label="Total marks",
                kind="assumed",
                value=str(total) if total else "20",
                note=(
                    f"Taken from your instructions ({total} marks)."
                    if total
                    else "Assumed 20 marks."
                ),
            )
        )

    return gaps


def apply_assumed(settings_in: Dict[str, Any], gaps: List[Gap]) -> Dict[str, Any]:
    """Fill the assumed gaps into a copy of the settings."""
    resolved = dict(settings_in)
    for gap in gaps:
        if gap.kind == "assumed" and gap.value:
            resolved.setdefault(gap.field, gap.value)
            if not str(resolved.get(gap.field) or "").strip():
                resolved[gap.field] = gap.value
    return resolved


def is_ready(gaps: List[Gap]) -> bool:
    """Whether generation can start — no required gap left open."""
    return not any(gap.kind == "required" for gap in gaps)


def design_to_slot_specs(design: PaperDesign) -> List[Dict[str, Any]]:
    """Flatten a design into the slot dicts the pool pipeline consumes.

    Deliberately the same shape `_parse_gim_instructions` returned, so the
    pipeline's General Instructions branch keeps one input format.
    """
    specs: List[Dict[str, Any]] = []
    for section in design.sections:
        for group in section.groups:
            specs.append(
                {
                    "section_title": section.title,
                    "type": group.question_type,
                    "marks": group.marks,
                    "count": group.count,
                    "topic": group.topic,
                    "choice": group.choice,
                }
            )
    return specs


def header_lines(design: PaperDesign, settings_in: Dict[str, Any]) -> List[str]:
    """The rubric block printed above the questions."""
    lines: List[str] = []
    total_questions = design.total_questions
    if total_questions:
        lines.append(
            f"There are {total_questions} question"
            f"{'' if total_questions == 1 else 's'}. "
            "All questions are compulsory unless a choice is given."
        )
    lines.extend(design.general_instructions)

    # The teacher's own words last, and only if they said something the
    # structure does not already state.
    raw = str(settings_in.get("instructions") or "").strip()
    if raw and raw not in lines:
        lines.append(raw)
    return lines


_WORD_NUMBERS = {
    "one": 1, "single": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def infer_settings(instructions: str) -> Dict[str, str]:
    """Pull the settings a teacher stated in prose, so they are not re-asked.

    Deliberately conservative and regex-only: this runs before the design call
    and only claims a value when the text is unambiguous. Anything it misses is
    picked up as a gap, which is a question — not a wrong answer.
    """
    text = (instructions or "").strip().lower()
    if not text:
        return {}

    found: Dict[str, str] = {}

    marks = re.search(r"\b(\d{1,3})\s*(?:total\s*)?marks?\b", text)
    if marks:
        # "of 2 marks each" is a per-question value, not the paper total.
        tail = text[marks.end(): marks.end() + 6]
        if "each" not in tail:
            found["marks"] = marks.group(1)

    class_match = re.search(r"\bclass\s*(\d{1,2})\b", text)
    if class_match and 1 <= int(class_match.group(1)) <= 10:
        found["academicClass"] = class_match.group(1)

    for subject in SUBJECTS:
        if re.search(rf"\b{re.escape(subject.lower())}\b", text):
            found["subject"] = subject
            break
    else:
        if re.search(r"\bmaths?\b", text):
            found["subject"] = "Mathematics"
        elif re.search(r"\bsst\b|\bsocial\b", text):
            found["subject"] = "Social Science"

    for level in ("easy", "medium", "hard"):
        if re.search(rf"\b{level}\b", text):
            found["difficulty"] = level
            break

    # "one"/"single" belong here as much as "two": the Studio dock's own
    # placeholder reads "…80 marks, one set", and leaving the word out meant
    # the interface advertised an input this function then dropped.
    sets = re.search(r"\b(\d|one|single|two|three)\s*(?:parallel\s*)?sets?\b", text)
    if sets:
        raw = sets.group(1)
        count = _WORD_NUMBERS.get(raw, None)
        if count is None:
            try:
                count = int(raw)
            except ValueError:
                count = None
        if count in (1, 2, 3):
            found["numberOfSets"] = str(count)

    return found
