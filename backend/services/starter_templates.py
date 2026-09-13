"""Class starter templates: a ready paper for a class band, built from the catalogue.

Nothing that generates today changes shape because of this module. The board
cards, the engine's own progressions for Classes 1–9, every default — all stay
exactly as they are. A starter is an extra card: a pinned slot list authored
from catalogue types that suit its classes, offered first in the template
picker to a class it fits. The teacher sees every slot in the Builder before
anything is written and can change any of them, so a starter never changes a
paper without being seen.

This is also where "Mathematics blueprints for Classes 1–9" live: as editable
starting points rather than hard-coded engine paths.

Starters never run the blueprint engine. They are data, resolved straight into
a `TemplateBlueprint`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class StarterSection:
    title: str
    #: (catalogue type, marks each, how many)
    slots: Tuple[Tuple[str, int, int], ...]


@dataclass(frozen=True)
class Starter:
    id: str
    name: str
    blurb: str
    #: The subject as the rail shows it, and as the catalogue names it.
    subject: str
    subject_key: str
    classes: Tuple[int, int]
    sections: Tuple[StarterSection, ...]

    @property
    def total_questions(self) -> int:
        return sum(count for section in self.sections for _, _, count in section.slots)

    @property
    def total_marks(self) -> int:
        return sum(
            marks * count for section in self.sections for _, marks, count in section.slots
        )

    @property
    def description(self) -> str:
        return f"{self.total_questions} questions · {self.total_marks} marks. {self.blurb}"


def _s(title: str, *slots: Tuple[str, int, int]) -> StarterSection:
    return StarterSection(title, tuple(slots))


_LANGUAGE_NINE = (
    _s("Section A — Reading", ("PASSAGE_UNSEEN", 10, 2)),
    _s(
        "Section B — Grammar and Writing",
        ("GAP_FILL_GRAMMAR", 10, 1),
        ("LETTER_WRITING", 5, 1),
        ("NOTICE_WRITING", 5, 1),
    ),
    _s(
        "Section C — Literature",
        ("EXTRACT_SEEN", 5, 1),
        ("POETRY_APPRECIATION", 5, 1),
        ("SA", 3, 6),
        ("LA", 6, 2),
    ),
)

STARTERS: Tuple[Starter, ...] = (
    # ── Classes 1–2: worksheets, answered with marks rather than sentences ──
    Starter(
        "starter-science-1-2", "Class 1–2 EVS Worksheet",
        "Circle, tick, word-bank blanks, join and sort.",
        "Science", "science", (1, 2),
        (
            _s("Section A", ("CIRCLE_CORRECT", 1, 5), ("TICK_CROSS", 3, 1)),
            _s("Section B", ("FILL_BLANK_BANK", 3, 2), ("JOIN_LINES", 3, 1)),
            _s("Section C", ("CLASSIFY_SORT", 2, 1), ("CROSS_OUT", 1, 2)),
        ),
    ),
    Starter(
        "starter-mathematics-1-2", "Class 1–2 Maths Worksheet",
        "Missing numbers, comparing, patterns, number grids and story sums.",
        "Mathematics", "mathematics", (1, 2),
        (
            _s("Section A", ("MISSING_NUMBER", 1, 4), ("COMPARE_QUANTITY", 1, 4)),
            _s("Section B", ("PATTERN_COMPLETE", 1, 3), ("NUMBER_GRID", 2, 2)),
            _s("Section C", ("WORD_PROBLEM", 2, 3)),
        ),
    ),
    Starter(
        "starter-english-1-2", "Class 1–2 English Worksheet",
        "Circle the word, opposites, rhymes, word forms and a word bank.",
        "English", "english", (1, 2),
        (
            _s("Section A", ("CIRCLE_CORRECT", 1, 4), ("OPPOSITE_WRITE", 1, 4)),
            _s("Section B", ("RHYMING_WORDS", 1, 4), ("WORD_FORM_CHANGE", 1, 3)),
            _s("Section C", ("PUNCTUATION", 1, 2), ("FILL_BLANK_BANK", 3, 1)),
        ),
    ),
    # ── Classes 3–5: unit tests ─────────────────────────────────────────
    Starter(
        "starter-science-3-5", "Class 3–5 Science Unit Test",
        "Varied MCQs, blanks, true/false, matching and short answers.",
        "Science", "science", (3, 5),
        (
            _s("Section A", ("MCQ_SINGLE", 1, 5), ("MCQ_ODD_ONE_OUT", 1, 2), ("MCQ_IDENTIFY", 1, 2)),
            _s("Section B", ("FILL_BLANK", 1, 5), ("TRUE_FALSE", 1, 5)),
            _s("Section C", ("MATCH_FOLLOWING", 4, 1), ("DEFINE", 1, 2)),
            _s("Section D", ("VSA", 2, 3), ("SA", 3, 3)),
        ),
    ),
    Starter(
        "starter-social-science-3-5", "Class 3–5 Social Studies Unit Test",
        "MCQs, blanks, true/false, matching and short answers.",
        "Social Science", "social science", (3, 5),
        (
            _s("Section A", ("MCQ_SINGLE", 1, 9)),
            _s("Section B", ("FILL_BLANK", 1, 5), ("TRUE_FALSE", 1, 5)),
            _s("Section C", ("MATCH_FOLLOWING", 4, 1), ("VSA", 2, 4)),
            _s("Section D", ("SA", 3, 3)),
        ),
    ),
    Starter(
        "starter-mathematics-3-5", "Class 3–5 Maths Unit Test",
        "MCQs, missing numbers, simplifying, story sums, patterns and estimation.",
        "Mathematics", "mathematics", (3, 5),
        (
            _s("Section A", ("MCQ_SINGLE", 1, 6), ("MISSING_NUMBER", 1, 4)),
            _s("Section B", ("SIMPLIFY_EVALUATE", 2, 4), ("NUMBER_PATTERN", 2, 2)),
            _s("Section C", ("ESTIMATION_ROUNDING", 2, 3), ("WORD_PROBLEM", 3, 4)),
        ),
    ),
    Starter(
        "starter-english-3-5", "Class 3–5 English Unit Test",
        "An unseen passage, word work, a word bank and short writing.",
        "English", "english", (3, 5),
        (
            _s("Section A — Reading", ("PASSAGE_UNSEEN", 8, 1), ("DIALOGUE_BASED", 2, 1)),
            _s(
                "Section B — Words and Grammar",
                ("REARRANGE_WORDS", 1, 4),
                ("SYNONYM_ANTONYM", 1, 4),
                ("SPELLING", 1, 3),
                ("WORD_FORM_CHANGE", 1, 3),
                ("PUNCTUATION", 1, 2),
                ("FILL_BLANK_BANK", 5, 1),
            ),
            _s("Section C — Writing", ("PARAGRAPH_WRITING", 4, 1), ("STORY_WRITING", 5, 1)),
        ),
    ),
    # ── Classes 6–8: periodic tests ─────────────────────────────────────
    Starter(
        "starter-science-6-8", "Class 6–8 Science Periodic Test",
        "Statement and sequencing MCQs, reasons, differences, long answers and a case study.",
        "Science", "science", (6, 8),
        (
            _s("Section A", ("MCQ_SINGLE", 1, 6), ("MCQ_CORRECT", 1, 2), ("MCQ_SEQUENCE", 1, 2)),
            _s("Section B", ("FILL_BLANK", 1, 4), ("SHORT_JUSTIFY", 2, 3)),
            _s("Section C", ("DIFFERENTIATE", 3, 2), ("SA", 3, 2)),
            _s("Section D", ("LA", 5, 2)),
            _s("Section E", ("CASE_STUDY", 4, 1), ("EXPERIMENT_OBSERVATION", 4, 1)),
        ),
    ),
    Starter(
        "starter-social-science-6-8", "Class 6–8 Social Science Periodic Test",
        "Chronology and cause-and-effect MCQs, short and long answers, case studies.",
        "Social Science", "social science", (6, 8),
        (
            _s("Section A", ("MCQ_SINGLE", 1, 6), ("MCQ_CHRONOLOGY", 1, 2), ("MCQ_CAUSE_EFFECT", 1, 2)),
            _s("Section B", ("FILL_BLANK", 1, 4), ("VSA", 2, 3)),
            _s("Section C", ("SA", 3, 4)),
            _s("Section D", ("LA", 5, 2)),
            _s("Section E", ("CASE_STUDY", 4, 2)),
        ),
    ),
    Starter(
        "starter-mathematics-6-8", "Class 6–8 Maths Periodic Test",
        "Numerical MCQs, equations, simplifying, mensuration, word problems and case studies.",
        "Mathematics", "mathematics", (6, 8),
        (
            _s("Section A", ("MCQ_NUMERICAL", 1, 8), ("MCQ_SINGLE", 1, 2)),
            _s("Section B", ("SOLVE_EQUATION", 2, 5)),
            _s("Section C", ("SIMPLIFY_EVALUATE", 3, 2), ("MENSURATION_APPLIED", 3, 2)),
            _s("Section D", ("WORD_PROBLEM", 5, 2)),
            _s("Section E", ("CASE_STUDY", 4, 2)),
        ),
    ),
    Starter(
        "starter-english-6-8", "Class 6–8 English Periodic Test",
        "Reading, grammar tasks, a notice and a letter, and literature.",
        "English", "english", (6, 8),
        (
            _s("Section A — Reading", ("PASSAGE_UNSEEN", 10, 1)),
            _s(
                "Section B — Grammar",
                ("GAP_FILL_GRAMMAR", 6, 1),
                ("ERROR_CORRECTION", 2, 2),
                ("REPORTED_SPEECH", 1, 3),
            ),
            _s("Section C — Writing", ("NOTICE_WRITING", 4, 1), ("LETTER_WRITING", 5, 1)),
            _s("Section D — Literature", ("EXTRACT_SEEN", 5, 1), ("SA", 2, 4), ("LA", 5, 1)),
        ),
    ),
    # ── Class 9 where the board engine has no card ──────────────────────
    Starter(
        "starter-mathematics-9", "Class 9 Maths Paper",
        "Sections A–E on the Class 10 pattern, with proofs and case studies.",
        "Mathematics", "mathematics", (9, 9),
        (
            _s("Section A", ("MCQ_SINGLE", 1, 16), ("ASSERTION_REASON", 1, 4)),
            _s("Section B", ("SOLVE_EQUATION", 2, 5)),
            _s("Section C", ("PROOF_DERIVATION", 3, 3), ("MENSURATION_APPLIED", 3, 3)),
            _s("Section D", ("LA", 5, 4)),
            _s("Section E", ("CASE_STUDY_MATHS", 4, 3)),
        ),
    ),
    Starter(
        "starter-english-9", "Class 9 English Paper",
        "Reading, grammar and writing, and literature on the Class 10 pattern.",
        "English", "english", (9, 9), _LANGUAGE_NINE,
    ),
    Starter(
        "starter-hindi-9", "Class 9 Hindi Paper",
        "अपठित गद्यांश, व्याकरण, लेखन और पाठ्यपुस्तक।",
        "Hindi", "hindi", (9, 9), _LANGUAGE_NINE,
    ),
    Starter(
        "starter-telugu-9", "Class 9 Telugu Paper",
        "పఠనం, వ్యాకరణం, రచన మరియు పాఠ్యపుస్తకం.",
        "Telugu", "telugu", (9, 9), _LANGUAGE_NINE,
    ),
)


def get_starter(template_id: str) -> Optional[Starter]:
    return next((starter for starter in STARTERS if starter.id == template_id), None)


def starters_for(*, subject_key: str = "", class_num: Optional[int] = None) -> List[Starter]:
    """The starters that fit a subject and class; either may be unknown."""
    return [
        starter
        for starter in STARTERS
        if (not subject_key or starter.subject_key == subject_key)
        and (class_num is None or starter.classes[0] <= class_num <= starter.classes[1])
    ]


def starter_blueprint(starter: Starter):
    """The starter's slots, in order, as an editable blueprint."""
    from services.templates import SlotSpec, TemplateBlueprint

    slots = []
    for section in starter.sections:
        for code, marks, count in section.slots:
            for _ in range(count):
                slots.append(
                    SlotSpec(
                        index=len(slots) + 1,
                        section_title=section.title,
                        question_type=code,
                        type_code=code,
                        marks=marks,
                    )
                )
    return TemplateBlueprint(slots=slots)
