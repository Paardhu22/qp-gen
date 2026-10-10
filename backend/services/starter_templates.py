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
from typing import Optional, Tuple


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


# ── Shared structures ───────────────────────────────────────────────────────
# Formats per band follow how schools actually assess, since CBSE publishes
# sample papers only for the board years:
#
#   Classes 1–2   a worksheet (~20 marks) and a term assessment (30)
#   Classes 3–5   a unit test (20) and a term exam (40)
#   Classes 6–8   a periodic test (40–50) and an annual exam (80, the uniform
#                 assessment scheme's written paper)
#   Classes 9–10  a periodic test and an annual exam on the board pattern; at
#                 Class 10 the board card sits beside them
#
# Hindi, Telugu and Sanskrit share one set of structures — the catalogue grades
# them alike, and their papers have the same reading / grammar / writing /
# textbook shape. Section titles stay in English like the rest of the Builder.

#: Classes 1–2 term assessment where the subject has no drawing or number work.
_TERM_1_2 = (
    _s("Section A", ("CIRCLE_CORRECT", 1, 5), ("MCQ_ODD_ONE_OUT", 1, 3)),
    _s("Section B", ("FILL_BLANK", 1, 5), ("TRUE_FALSE", 1, 5)),
    _s("Section C", ("MATCH_FOLLOWING", 4, 1), ("SEQUENCE_WRITE", 2, 1)),
    _s("Section D", ("EXAMPLE_GIVE", 2, 3)),
)

#: Classes 3–5 unit test for the non-language, non-maths subjects.
_UNIT_3_5 = (
    _s("Section A", ("MCQ_SINGLE", 1, 5)),
    _s("Section B", ("FILL_BLANK", 1, 3), ("TRUE_FALSE", 1, 3)),
    _s("Section C", ("MATCH_FOLLOWING", 3, 1)),
    _s("Section D", ("VSA", 2, 3)),
)

_COMPUTER_UNIT_3_5 = (
    _s("Section A", ("MCQ_SINGLE", 1, 5)),
    _s("Section B", ("FILL_BLANK", 1, 3), ("TRUE_FALSE", 1, 3)),
    _s("Section C", ("SHORTCUT_KEY", 1, 3)),
    _s("Section D", ("VSA", 2, 3)),
)

_LANG_WORKSHEET_1_2 = (
    _s("Section A — Letters and Words", ("CIRCLE_CORRECT", 1, 4), ("OPPOSITE_WRITE", 1, 4)),
    _s("Section B — Word Work", ("SPELLING", 1, 4), ("WORD_FORM_CHANGE", 1, 3)),
    _s("Section C", ("FILL_BLANK_BANK", 3, 1), ("MATCH_FOLLOWING", 2, 1)),
)

_LANG_TERM_1_2 = (
    _s("Section A — Letters and Words", ("CIRCLE_CORRECT", 1, 5), ("SPELLING", 1, 5)),
    _s("Section B — Word Work", ("OPPOSITE_WRITE", 1, 5), ("WORD_FORM_CHANGE", 1, 4)),
    _s("Section C", ("FILL_BLANK", 1, 5), ("RHYMING_WORDS", 1, 2)),
    _s("Section D", ("MATCH_FOLLOWING", 4, 1)),
)

_LANG_UNIT_3_5 = (
    _s("Section A — Reading", ("PASSAGE_UNSEEN", 5, 1)),
    _s(
        "Section B — Words and Grammar",
        ("SYNONYM_ANTONYM", 1, 4),
        ("WORD_FORM_CHANGE", 1, 3),
        ("SPELLING", 1, 3),
    ),
    _s("Section C — Writing", ("PARAGRAPH_WRITING", 5, 1)),
)

_LANG_TERM_3_5 = (
    _s("Section A — Reading", ("PASSAGE_UNSEEN", 8, 1)),
    _s(
        "Section B — Grammar",
        ("GRAMMAR_ITEM", 1, 4),
        ("SYNONYM_ANTONYM", 1, 4),
        ("WORD_FORM_CHANGE", 1, 4),
        ("REARRANGE_WORDS", 1, 3),
    ),
    _s("Section C — Writing", ("PARAGRAPH_WRITING", 5, 1), ("STORY_WRITING", 5, 1)),
    _s("Section D — Textbook", ("VSA", 1, 3), ("SA", 2, 2)),
)

_LANG_PERIODIC_6_8 = (
    _s("Section A — Reading", ("PASSAGE_UNSEEN", 8, 1)),
    _s("Section B — Grammar", ("GRAMMAR_ITEM", 1, 6), ("SYNONYM_ANTONYM", 1, 4)),
    _s("Section C — Writing", ("LETTER_WRITING", 5, 1), ("NOTICE_WRITING", 4, 1)),
    _s("Section D — Textbook", ("EXTRACT_SEEN", 5, 1), ("SA", 2, 4)),
)

_LANG_ANNUAL_6_8 = (
    _s("Section A — Reading", ("PASSAGE_UNSEEN", 10, 2)),
    _s(
        "Section B — Grammar",
        ("GRAMMAR_ITEM", 1, 8),
        ("IDIOM_PHRASE", 1, 4),
        ("SYNONYM_ANTONYM", 1, 4),
    ),
    _s(
        "Section C — Writing",
        ("LETTER_WRITING", 5, 1),
        ("ESSAY_WRITING", 5, 1),
        ("NOTICE_WRITING", 4, 1),
    ),
    _s(
        "Section D — Textbook",
        ("EXTRACT_SEEN", 5, 2),
        ("POETRY_APPRECIATION", 5, 1),
        ("SA", 3, 5),
    ),
)

_LANG_PERIODIC_9_10 = (
    _s("Section A — Reading", ("PASSAGE_UNSEEN", 8, 1)),
    _s("Section B — Grammar", ("GRAMMAR_ITEM", 1, 8)),
    _s("Section C — Writing", ("LETTER_WRITING", 5, 1), ("PARAGRAPH_WRITING", 5, 1)),
    _s("Section D — Textbook", ("EXTRACT_SEEN", 5, 1), ("SA", 3, 3)),
)

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

#: Sanskrit (122) on its board layout: unseen passage, composition, applied
#: grammar and the textbook — 10 / 15 / 25 / 30.
_SANSKRIT_ANNUAL_9_10 = (
    _s("Section A — Unseen Passage", ("PASSAGE_UNSEEN", 10, 1)),
    _s(
        "Section B — Composition",
        ("LETTER_WRITING", 5, 1),
        ("PARAGRAPH_WRITING", 5, 1),
        ("TRANSLATION", 5, 1),
    ),
    _s(
        "Section C — Applied Grammar",
        ("GAP_FILL_GRAMMAR", 4, 4),
        ("GAP_FILL_GRAMMAR", 3, 2),
        ("ERROR_CORRECTION", 3, 1),
    ),
    _s(
        "Section D — Textbook",
        ("EXTRACT_SEEN", 5, 2),
        ("POETRY_APPRECIATION", 5, 1),
        ("SA", 3, 3),
        ("VSA", 1, 6),
    ),
)

_LANGUAGE_BLURBS = {
    "hindi": {
        "worksheet": "अक्षर और शब्द पहचान, विलोम, वर्तनी, वचन-लिंग और शब्द-बैंक।",
        "term_1_2": "शब्द पहचान, वर्तनी, विलोम, रिक्त स्थान, तुकांत शब्द और मिलान।",
        "unit": "अपठित गद्यांश, शब्द-ज्ञान और अनुच्छेद लेखन।",
        "term_3_5": "अपठित गद्यांश, व्याकरण, अनुच्छेद व कहानी लेखन और पाठ्यपुस्तक।",
        "periodic_6_8": "अपठित गद्यांश, व्याकरण, पत्र व सूचना लेखन और पाठ्यपुस्तक।",
        "annual_6_8": "अपठित गद्यांश, व्याकरण व मुहावरे, पत्र-निबंध-सूचना और पाठ्यपुस्तक।",
        "periodic_9_10": "अपठित गद्यांश, व्याकरण, पत्र व अनुच्छेद लेखन और पाठ्यपुस्तक।",
    },
    "telugu": {
        "worksheet": "అక్షరాలు, పదాలు, వ్యతిరేక పదాలు, వర్ణక్రమం మరియు పద బ్యాంకు.",
        "term_1_2": "పదాల గుర్తింపు, వర్ణక్రమం, వ్యతిరేక పదాలు, ఖాళీలు మరియు జతపరచడం.",
        "unit": "అపరిచిత గద్యం, పద పరిజ్ఞానం మరియు పేరా రచన.",
        "term_3_5": "అపరిచిత గద్యం, వ్యాకరణం, పేరా మరియు కథ రచన, పాఠ్యపుస్తకం.",
        "periodic_6_8": "అపరిచిత గద్యం, వ్యాకరణం, లేఖ మరియు ప్రకటన రచన, పాఠ్యపుస్తకం.",
        "annual_6_8": "అపరిచిత గద్యం, వ్యాకరణం, లేఖ-వ్యాసం-ప్రకటన మరియు పాఠ్యపుస్తకం.",
        "periodic_9_10": "అపరిచిత గద్యం, వ్యాకరణం, లేఖ మరియు పేరా రచన, పాఠ్యపుస్తకం.",
    },
    "sanskrit": {
        "worksheet": "वर्ण-शब्द परिचयः, विलोमशब्दाः, वर्तनी, वचनम् शब्दकोशः च।",
        "term_1_2": "शब्दपरिचयः, वर्तनी, विलोमशब्दाः, रिक्तस्थानानि मेलनं च।",
        "unit": "अपठित-अवबोधनम्, शब्दज्ञानम् अनुच्छेदलेखनं च।",
        "term_3_5": "अपठित-अवबोधनम्, व्याकरणम्, अनुच्छेद-कथालेखनं पाठ्यपुस्तकं च।",
        "periodic_6_8": "अपठित-अवबोधनम्, व्याकरणम्, पत्र-सूचनालेखनं पाठ्यपुस्तकं च।",
        "annual_6_8": "अपठित-अवबोधनम्, व्याकरणम्, पत्र-निबन्ध-सूचनालेखनं पाठ्यपुस्तकं च।",
        "periodic_9_10": "अपठित-अवबोधनम्, व्याकरणम्, पत्र-अनुच्छेदलेखनं पाठ्यपुस्तकं च।",
    },
}


def _language_starters(subject: str, key: str) -> Tuple[Starter, ...]:
    """Classes 1–8 and the 9–10 periodic test for Hindi, Telugu or Sanskrit."""
    slug = key.replace(" ", "-")
    blurb = _LANGUAGE_BLURBS[key]
    return (
        Starter(
            f"starter-{slug}-1-2", f"Class 1–2 {subject} Worksheet",
            blurb["worksheet"], subject, key, (1, 2), _LANG_WORKSHEET_1_2,
        ),
        Starter(
            f"starter-{slug}-1-2-term", f"Class 1–2 {subject} Term Assessment",
            blurb["term_1_2"], subject, key, (1, 2), _LANG_TERM_1_2,
        ),
        Starter(
            f"starter-{slug}-3-5-unit", f"Class 3–5 {subject} Unit Test",
            blurb["unit"], subject, key, (3, 5), _LANG_UNIT_3_5,
        ),
        Starter(
            f"starter-{slug}-3-5", f"Class 3–5 {subject} Term Exam",
            blurb["term_3_5"], subject, key, (3, 5), _LANG_TERM_3_5,
        ),
        Starter(
            f"starter-{slug}-6-8", f"Class 6–8 {subject} Periodic Test",
            blurb["periodic_6_8"], subject, key, (6, 8), _LANG_PERIODIC_6_8,
        ),
        Starter(
            f"starter-{slug}-6-8-annual", f"Class 6–8 {subject} Annual Exam",
            blurb["annual_6_8"], subject, key, (6, 8), _LANG_ANNUAL_6_8,
        ),
        Starter(
            f"starter-{slug}-9-10-periodic", f"Class 9–10 {subject} Periodic Test",
            blurb["periodic_9_10"], subject, key, (9, 10), _LANG_PERIODIC_9_10,
        ),
    )


STARTERS: Tuple[Starter, ...] = (
    # ── Science (EVS in Classes 1–5) ─────────────────────────────────────
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
        "starter-science-1-2-term", "Class 1–2 EVS Term Assessment",
        "Circle and odd-one-out, blanks, true/false, matching, examples and a drawing.",
        "Science", "science", (1, 2),
        (
            _s("Section A", ("CIRCLE_CORRECT", 1, 5), ("MCQ_ODD_ONE_OUT", 1, 3)),
            _s("Section B", ("FILL_BLANK", 1, 5), ("TRUE_FALSE", 1, 5)),
            _s("Section C", ("MATCH_FOLLOWING", 4, 1), ("CLASSIFY_SORT", 2, 1)),
            _s("Section D", ("EXAMPLE_GIVE", 2, 2), ("DRAW_COLOUR", 2, 1)),
        ),
    ),
    Starter(
        "starter-science-3-5-unit", "Class 3–5 Science Unit Test",
        "MCQs, blanks, true/false, matching and very short answers.",
        "Science", "science", (3, 5), _UNIT_3_5,
    ),
    Starter(
        "starter-science-3-5", "Class 3–5 Science Term Exam",
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
        "starter-science-6-8-annual", "Class 6–8 Science Annual Exam",
        "Sections A–E: MCQs, very short, short and long answers, and case studies.",
        "Science", "science", (6, 8),
        (
            _s("Section A", ("MCQ_SINGLE", 1, 12), ("MCQ_CORRECT", 1, 2), ("MCQ_CAUSE_EFFECT", 1, 2)),
            _s("Section B", ("VSA", 2, 6), ("SHORT_JUSTIFY", 2, 2)),
            _s("Section C", ("SA", 3, 7)),
            _s("Section D", ("LA", 5, 3)),
            _s("Section E", ("CASE_STUDY", 4, 3)),
        ),
    ),
    Starter(
        "starter-science-9-annual", "Class 9 Science Annual Exam",
        "Sections A–E on the Class 10 board pattern, with assertion-reason and case studies.",
        "Science", "science", (9, 9),
        (
            _s("Section A", ("MCQ_SINGLE", 1, 16), ("ASSERTION_REASON", 1, 4)),
            _s("Section B", ("VSA", 2, 6)),
            _s("Section C", ("SA", 3, 7)),
            _s("Section D", ("LA", 5, 3)),
            _s("Section E", ("CASE_STUDY", 4, 3)),
        ),
    ),
    Starter(
        "starter-science-9-10-periodic", "Class 9–10 Science Periodic Test",
        "A shorter paper on the board pattern: MCQs, assertion-reason, short and long answers.",
        "Science", "science", (9, 10),
        (
            _s("Section A", ("MCQ_SINGLE", 1, 9), ("ASSERTION_REASON", 1, 2)),
            _s("Section B", ("VSA", 2, 4)),
            _s("Section C", ("SA", 3, 4)),
            _s("Section D", ("LA", 5, 1)),
            _s("Section E", ("CASE_STUDY", 4, 1)),
        ),
    ),
    # ── Social Science (Social Studies in Classes 1–5) ───────────────────
    Starter(
        "starter-social-science-1-2", "Class 1–2 Social Studies Worksheet",
        "Family, home and neighbourhood: circle, tick, word bank, join and sort.",
        "Social Science", "social science", (1, 2),
        (
            _s("Section A", ("CIRCLE_CORRECT", 1, 5), ("TICK_CROSS", 3, 1)),
            _s("Section B", ("FILL_BLANK_BANK", 3, 1), ("JOIN_LINES", 3, 1)),
            _s("Section C", ("CLASSIFY_SORT", 2, 1), ("EXAMPLE_GIVE", 2, 2)),
        ),
    ),
    Starter(
        "starter-social-science-1-2-term", "Class 1–2 Social Studies Term Assessment",
        "Circle, blanks, true/false, matching, ordering and examples.",
        "Social Science", "social science", (1, 2), _TERM_1_2,
    ),
    Starter(
        "starter-social-science-3-5-unit", "Class 3–5 Social Studies Unit Test",
        "MCQs, blanks, true/false, matching and very short answers.",
        "Social Science", "social science", (3, 5), _UNIT_3_5,
    ),
    Starter(
        "starter-social-science-3-5", "Class 3–5 Social Studies Term Exam",
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
        "starter-social-science-6-8-annual", "Class 6–8 Social Science Annual Exam",
        "History, Geography and Civics across MCQs, short and long answers and case studies.",
        "Social Science", "social science", (6, 8),
        (
            _s("Section A", ("MCQ_SINGLE", 1, 12), ("MCQ_CHRONOLOGY", 1, 2), ("MCQ_CAUSE_EFFECT", 1, 2)),
            _s("Section B", ("VSA", 2, 6), ("SHORT_JUSTIFY", 2, 2)),
            _s("Section C", ("SA", 3, 7)),
            _s("Section D", ("LA", 5, 3)),
            _s("Section E", ("CASE_STUDY", 4, 3)),
        ),
    ),
    Starter(
        "starter-social-science-9-annual", "Class 9 Social Science Annual Exam",
        "History, Geography, Political Science and Economics on the Class 10 board pattern.",
        "Social Science", "social science", (9, 9),
        (
            _s("Section A", ("MCQ_SINGLE", 1, 16), ("ASSERTION_REASON", 1, 2), ("MCQ_CHRONOLOGY", 1, 2)),
            _s("Section B", ("VSA", 2, 4)),
            _s("Section C", ("SA", 3, 5)),
            _s("Section D", ("LA", 5, 5)),
            _s("Section E — Source-based", ("SOURCE_BASED", 4, 3)),
        ),
    ),
    Starter(
        "starter-social-science-9-10-periodic", "Class 9–10 Social Science Periodic Test",
        "A shorter paper on the board pattern, with a source-based question.",
        "Social Science", "social science", (9, 10),
        (
            _s("Section A", ("MCQ_SINGLE", 1, 8), ("ASSERTION_REASON", 1, 2)),
            _s("Section B", ("VSA", 2, 3)),
            _s("Section C", ("SA", 3, 5)),
            _s("Section D", ("LA", 5, 1)),
            _s("Section E — Source-based", ("SOURCE_BASED", 4, 1)),
        ),
    ),
    # ── Mathematics ──────────────────────────────────────────────────────
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
        "starter-mathematics-1-2-term", "Class 1–2 Maths Term Assessment",
        "Missing numbers, comparing, blanks, number patterns, grids and story sums.",
        "Mathematics", "mathematics", (1, 2),
        (
            _s("Section A", ("MISSING_NUMBER", 1, 5), ("COMPARE_QUANTITY", 1, 5)),
            _s("Section B", ("FILL_BLANK", 1, 4), ("NUMBER_PATTERN", 1, 2)),
            _s("Section C", ("NUMBER_GRID", 2, 1), ("MATCH_FOLLOWING", 3, 1)),
            _s("Section D", ("WORD_PROBLEM", 3, 3)),
        ),
    ),
    Starter(
        "starter-mathematics-3-5-unit", "Class 3–5 Maths Unit Test",
        "MCQs, missing numbers, simplifying and story sums.",
        "Mathematics", "mathematics", (3, 5),
        (
            _s("Section A", ("MCQ_SINGLE", 1, 4), ("MISSING_NUMBER", 1, 2)),
            _s("Section B", ("SIMPLIFY_EVALUATE", 2, 3)),
            _s("Section C", ("WORD_PROBLEM", 4, 2)),
        ),
    ),
    Starter(
        "starter-mathematics-3-5", "Class 3–5 Maths Term Exam",
        "MCQs, missing numbers, simplifying, story sums, patterns and estimation.",
        "Mathematics", "mathematics", (3, 5),
        (
            _s("Section A", ("MCQ_SINGLE", 1, 6), ("MISSING_NUMBER", 1, 4)),
            _s("Section B", ("SIMPLIFY_EVALUATE", 2, 4), ("NUMBER_PATTERN", 2, 2)),
            _s("Section C", ("ESTIMATION_ROUNDING", 2, 3), ("WORD_PROBLEM", 3, 4)),
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
        "starter-mathematics-6-8-annual", "Class 6–8 Maths Annual Exam",
        "Sections A–E: MCQs, equations, mensuration, constructions, word problems and case studies.",
        "Mathematics", "mathematics", (6, 8),
        (
            _s("Section A", ("MCQ_NUMERICAL", 1, 12), ("MCQ_SINGLE", 1, 4)),
            _s("Section B", ("SOLVE_EQUATION", 2, 6), ("VSA", 2, 2)),
            _s(
                "Section C",
                ("SIMPLIFY_EVALUATE", 3, 3),
                ("MENSURATION_APPLIED", 3, 2),
                ("GEOM_CONSTRUCTION", 3, 2),
            ),
            _s("Section D", ("WORD_PROBLEM", 5, 3)),
            _s("Section E", ("CASE_STUDY", 4, 3)),
        ),
    ),
    Starter(
        "starter-mathematics-9", "Class 9 Maths Annual Exam",
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
        "starter-mathematics-9-10-periodic", "Class 9–10 Maths Periodic Test",
        "A shorter paper on the board pattern, ending in a case study.",
        "Mathematics", "mathematics", (9, 10),
        (
            _s("Section A", ("MCQ_SINGLE", 1, 9), ("ASSERTION_REASON", 1, 2)),
            _s("Section B", ("SOLVE_EQUATION", 2, 3), ("VSA", 2, 1)),
            _s("Section C", ("PROOF_DERIVATION", 3, 2), ("MENSURATION_APPLIED", 3, 2)),
            _s("Section D", ("LA", 5, 1)),
            _s("Section E", ("CASE_STUDY_MATHS", 4, 1)),
        ),
    ),
    # ── English ──────────────────────────────────────────────────────────
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
    Starter(
        "starter-english-1-2-term", "Class 1–2 English Term Assessment",
        "Words and spelling, opposites and rhymes, blanks, punctuation and matching.",
        "English", "english", (1, 2),
        (
            _s("Section A — Words", ("CIRCLE_CORRECT", 1, 5), ("SPELLING", 1, 5)),
            _s("Section B — Word Work", ("OPPOSITE_WRITE", 1, 5), ("RHYMING_WORDS", 1, 4)),
            _s("Section C — Grammar", ("FILL_BLANK", 1, 5), ("PUNCTUATION", 1, 2)),
            _s("Section D", ("MATCH_FOLLOWING", 4, 1)),
        ),
    ),
    Starter(
        "starter-english-3-5-unit", "Class 3–5 English Unit Test",
        "A short passage, synonyms, word order and spelling, and a paragraph.",
        "English", "english", (3, 5),
        (
            _s("Section A — Reading", ("PASSAGE_UNSEEN", 5, 1)),
            _s(
                "Section B — Words and Grammar",
                ("SYNONYM_ANTONYM", 1, 4),
                ("REARRANGE_WORDS", 1, 3),
                ("SPELLING", 1, 3),
            ),
            _s("Section C — Writing", ("PARAGRAPH_WRITING", 5, 1)),
        ),
    ),
    Starter(
        "starter-english-3-5", "Class 3–5 English Term Exam",
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
    Starter(
        "starter-english-6-8-annual", "Class 6–8 English Annual Exam",
        "Two passages, grammar, a notice, letter and diary entry, and literature.",
        "English", "english", (6, 8),
        (
            _s("Section A — Reading", ("PASSAGE_UNSEEN", 10, 2)),
            _s(
                "Section B — Grammar",
                ("GAP_FILL_GRAMMAR", 5, 1),
                ("ERROR_CORRECTION", 2, 2),
                ("REPORTED_SPEECH", 1, 3),
                ("ACTIVE_PASSIVE", 1, 3),
            ),
            _s(
                "Section C — Writing",
                ("NOTICE_WRITING", 5, 1),
                ("LETTER_WRITING", 5, 1),
                ("DIARY_ENTRY", 5, 1),
            ),
            _s("Section D — Literature", ("EXTRACT_SEEN", 5, 2), ("SA", 2, 5), ("LA", 5, 2)),
        ),
    ),
    Starter(
        "starter-english-9", "Class 9 English Annual Exam",
        "Reading, grammar and writing, and literature on the Class 10 pattern.",
        "English", "english", (9, 9), _LANGUAGE_NINE,
    ),
    Starter(
        "starter-english-9-10-periodic", "Class 9–10 English Periodic Test",
        "A passage, grammar and a letter, and literature with one long answer.",
        "English", "english", (9, 10),
        (
            _s("Section A — Reading", ("PASSAGE_UNSEEN", 10, 1)),
            _s("Section B — Grammar and Writing", ("GAP_FILL_GRAMMAR", 5, 1), ("LETTER_WRITING", 5, 1)),
            _s("Section C — Literature", ("EXTRACT_SEEN", 5, 1), ("SA", 3, 3), ("LA", 6, 1)),
        ),
    ),
    # ── Hindi, Telugu, Sanskrit ──────────────────────────────────────────
    *_language_starters("Hindi", "hindi"),
    Starter(
        "starter-hindi-9", "Class 9 Hindi Annual Exam",
        "अपठित गद्यांश, व्याकरण, लेखन और पाठ्यपुस्तक।",
        "Hindi", "hindi", (9, 9), _LANGUAGE_NINE,
    ),
    *_language_starters("Telugu", "telugu"),
    Starter(
        "starter-telugu-9", "Class 9 Telugu Annual Exam",
        "పఠనం, వ్యాకరణం, రచన మరియు పాఠ్యపుస్తకం.",
        "Telugu", "telugu", (9, 9), _LANGUAGE_NINE,
    ),
    # Sanskrit has no board engine at any class, so 9–10 gets its own annual.
    *_language_starters("Sanskrit", "sanskrit"),
    Starter(
        "starter-sanskrit-9-10-annual", "Class 9–10 Sanskrit Annual Exam",
        "अपठित-अवबोधनम्, रचनात्मककार्यम्, अनुप्रयुक्तव्याकरणं पठित-अवबोधनं च (10/15/25/30)।",
        "Sanskrit", "sanskrit", (9, 10), _SANSKRIT_ANNUAL_9_10,
    ),
    # ── Computer Science: no board engine at any class ───────────────────
    Starter(
        "starter-computer-science-1-2", "Class 1–2 Computer Worksheet",
        "Parts and uses of a computer: circle, tick, word bank, join and sort.",
        "Computer Science", "computer science", (1, 2),
        (
            _s("Section A", ("CIRCLE_CORRECT", 1, 5), ("TICK_CROSS", 3, 1)),
            _s("Section B", ("FILL_BLANK_BANK", 3, 1), ("JOIN_LINES", 3, 1)),
            _s("Section C", ("CLASSIFY_SORT", 2, 1), ("CROSS_OUT", 1, 4)),
        ),
    ),
    Starter(
        "starter-computer-science-1-2-term", "Class 1–2 Computer Term Assessment",
        "Circle, blanks, true/false, matching, ordering steps and examples.",
        "Computer Science", "computer science", (1, 2), _TERM_1_2,
    ),
    Starter(
        "starter-computer-science-3-5-unit", "Class 3–5 Computer Unit Test",
        "MCQs, blanks, true/false, shortcut keys and very short answers.",
        "Computer Science", "computer science", (3, 5), _COMPUTER_UNIT_3_5,
    ),
    Starter(
        "starter-computer-science-3-5", "Class 3–5 Computer Term Exam",
        "MCQs and tools, blanks, true/false, shortcut keys, matching and software steps.",
        "Computer Science", "computer science", (3, 5),
        (
            _s("Section A", ("MCQ_SINGLE", 1, 6), ("TOOL_IDENTIFY", 1, 2)),
            _s("Section B", ("FILL_BLANK", 1, 5), ("TRUE_FALSE", 1, 5)),
            _s("Section C", ("MATCH_FOLLOWING", 4, 1), ("SHORTCUT_KEY", 1, 4)),
            _s("Section D", ("VSA", 2, 4), ("SOFTWARE_STEPS", 3, 2)),
        ),
    ),
    Starter(
        "starter-computer-science-6-8", "Class 6–8 Computer Science Periodic Test",
        "MCQs, full forms and shortcuts, differences, an algorithm and a flowchart.",
        "Computer Science", "computer science", (6, 8),
        (
            _s("Section A", ("MCQ_SINGLE", 1, 8), ("MCQ_SEQUENCE", 1, 2)),
            _s("Section B", ("FILL_BLANK", 1, 4), ("FULL_FORM", 1, 3), ("SHORTCUT_KEY", 1, 3)),
            _s("Section C", ("DIFFERENTIATE", 3, 2), ("SA", 3, 2)),
            _s("Section D", ("ALGORITHM_DESIGN", 4, 1), ("FLOWCHART_DRAW", 4, 1)),
        ),
    ),
    Starter(
        "starter-computer-science-6-8-annual", "Class 6–8 Computer Science Annual Exam",
        "Sections A–E: MCQs, short answers, code output, algorithms, flowcharts and case studies.",
        "Computer Science", "computer science", (6, 8),
        (
            _s("Section A", ("MCQ_SINGLE", 1, 12), ("MCQ_CORRECT", 1, 2), ("MCQ_SEQUENCE", 1, 2)),
            _s(
                "Section B",
                ("FILL_BLANK", 1, 5),
                ("TRUE_FALSE", 1, 2),
                ("FULL_FORM", 1, 3),
                ("SHORTCUT_KEY", 1, 4),
            ),
            _s("Section C", ("SA", 3, 4), ("DIFFERENTIATE", 3, 2), ("CODE_OUTPUT", 3, 1)),
            _s(
                "Section D",
                ("ALGORITHM_DESIGN", 4, 1),
                ("FLOWCHART_DRAW", 4, 1),
                ("SOFTWARE_STEPS", 4, 1),
                ("LA", 5, 1),
            ),
            _s("Section E", ("CASE_STUDY", 4, 3)),
        ),
    ),
    Starter(
        "starter-computer-science-9-10-periodic", "Class 9–10 Computer Applications Periodic Test",
        "MCQs and assertion-reason, short answers, code and a case study.",
        "Computer Science", "computer science", (9, 10),
        (
            _s("Section A — Objective", ("MCQ_SINGLE", 1, 6), ("ASSERTION_REASON", 1, 2)),
            _s("Section B — Short Answer", ("SA", 2, 4)),
            _s("Section C — Code", ("CODE_OUTPUT", 3, 1), ("CODE_WRITE", 3, 1)),
            _s("Section D — Case Study", ("CASE_STUDY", 3, 1)),
        ),
    ),
    Starter(
        "starter-computer-science-9-10-annual", "Class 9–10 Computer Applications Annual Exam",
        "50-mark theory paper: objective, short answers, code and case studies.",
        "Computer Science", "computer science", (9, 10),
        (
            _s("Section A — Objective", ("MCQ_SINGLE", 1, 10), ("ASSERTION_REASON", 1, 2)),
            _s("Section B — Short Answer", ("SA", 2, 7)),
            _s("Section C — Long Answer", ("SA", 3, 2), ("CODE_OUTPUT", 3, 1), ("CODE_WRITE", 3, 1)),
            _s("Section D — Case Study", ("CASE_STUDY", 4, 3)),
        ),
    ),
    # ── ICT: no board engine at any class ────────────────────────────────
    Starter(
        "starter-ict-1-2", "Class 1–2 ICT Worksheet",
        "Circle, tick, word-bank blanks, join and sort the parts of a computer.",
        "ICT", "ict", (1, 2),
        (
            _s("Section A", ("CIRCLE_CORRECT", 1, 5), ("TICK_CROSS", 3, 1)),
            _s("Section B", ("FILL_BLANK_BANK", 3, 1), ("JOIN_LINES", 4, 1)),
            _s("Section C", ("CLASSIFY_SORT", 2, 1), ("CROSS_OUT", 1, 3)),
        ),
    ),
    Starter(
        "starter-ict-1-2-term", "Class 1–2 ICT Term Assessment",
        "Circle, blanks, true/false, matching, ordering steps and examples.",
        "ICT", "ict", (1, 2), _TERM_1_2,
    ),
    Starter(
        "starter-ict-3-5-unit", "Class 3–5 ICT Unit Test",
        "MCQs, blanks, true/false, shortcut keys and very short answers.",
        "ICT", "ict", (3, 5), _COMPUTER_UNIT_3_5,
    ),
    Starter(
        "starter-ict-3-5", "Class 3–5 ICT Term Exam",
        "MCQs, tools and shortcut keys, blanks, matching and software steps.",
        "ICT", "ict", (3, 5),
        (
            _s("Section A", ("MCQ_SINGLE", 1, 5), ("TOOL_IDENTIFY", 1, 3)),
            _s("Section B", ("FILL_BLANK", 1, 5), ("TRUE_FALSE", 1, 5)),
            _s(
                "Section C",
                ("SHORTCUT_KEY", 1, 4),
                ("MATCH_FOLLOWING", 4, 1),
                ("CLASSIFY_SORT", 2, 1),
            ),
            _s("Section D", ("VSA", 2, 3), ("SOFTWARE_STEPS", 3, 2)),
        ),
    ),
    Starter(
        "starter-ict-6-8", "Class 6–8 ICT Periodic Test",
        "Shortcuts and full forms, software steps, spreadsheet formulas, an algorithm and a cyber-safety case study.",
        "ICT", "ict", (6, 8),
        (
            _s("Section A", ("MCQ_SINGLE", 1, 6), ("TOOL_IDENTIFY", 1, 2), ("MCQ_SEQUENCE", 1, 2)),
            _s("Section B", ("FILL_BLANK", 1, 4), ("SHORTCUT_KEY", 1, 3), ("FULL_FORM", 1, 3)),
            _s("Section C", ("DIFFERENTIATE", 3, 2), ("SOFTWARE_STEPS", 3, 2)),
            _s(
                "Section D",
                ("SPREADSHEET_FORMULA", 3, 1),
                ("ALGORITHM_DESIGN", 3, 1),
                ("SAFETY_PROCEDURE", 3, 1),
            ),
            _s("Section E", ("LA", 5, 1), ("CASE_STUDY", 4, 1)),
        ),
    ),
    Starter(
        "starter-ict-6-8-annual", "Class 6–8 ICT Annual Exam",
        "Sections A–E: MCQs, shortcuts and full forms, software steps, formulas and case studies.",
        "ICT", "ict", (6, 8),
        (
            _s("Section A", ("MCQ_SINGLE", 1, 12), ("TOOL_IDENTIFY", 1, 2), ("MCQ_SEQUENCE", 1, 2)),
            _s(
                "Section B",
                ("FILL_BLANK", 1, 5),
                ("TRUE_FALSE", 1, 2),
                ("FULL_FORM", 1, 3),
                ("SHORTCUT_KEY", 1, 4),
            ),
            _s("Section C", ("SA", 3, 4), ("DIFFERENTIATE", 3, 2), ("SPREADSHEET_FORMULA", 3, 1)),
            _s(
                "Section D",
                ("SOFTWARE_STEPS", 4, 1),
                ("ALGORITHM_DESIGN", 4, 1),
                ("SAFETY_PROCEDURE", 3, 1),
                ("LA", 6, 1),
            ),
            _s("Section E", ("CASE_STUDY", 4, 3)),
        ),
    ),
    Starter(
        "starter-ict-9-10-periodic", "Class 9–10 ICT Periodic Test",
        "Objective, short answers, software steps, a spreadsheet formula and a case study.",
        "ICT", "ict", (9, 10),
        (
            _s("Section A — Objective", ("MCQ_SINGLE", 1, 6), ("ASSERTION_REASON", 1, 2)),
            _s("Section B — Short Answer", ("SA", 2, 4)),
            _s("Section C — Application", ("SOFTWARE_STEPS", 3, 1), ("SPREADSHEET_FORMULA", 3, 1)),
            _s("Section D — Case Study", ("CASE_STUDY", 3, 1)),
        ),
    ),
    Starter(
        "starter-ict-9-10", "Class 9–10 ICT Annual Exam",
        "Objective, short and long answers on the CBSE Information Technology (402) pattern.",
        "ICT", "ict", (9, 10),
        (
            _s(
                "Section A — Objective",
                ("MCQ_SINGLE", 1, 16),
                ("ASSERTION_REASON", 1, 2),
                ("TOOL_IDENTIFY", 1, 2),
                ("MCQ_SEQUENCE", 1, 2),
                ("MCQ_NUMERICAL", 1, 2),
            ),
            _s("Section B — Short Answer", ("SA", 2, 6), ("DIFFERENTIATE", 2, 1)),
            _s(
                "Section C — Long Answer",
                ("SOFTWARE_STEPS", 4, 1),
                ("SPREADSHEET_FORMULA", 4, 1),
                ("CASE_STUDY", 4, 1),
            ),
        ),
    ),
)


def get_starter(template_id: str) -> Optional[Starter]:
    return next((starter for starter in STARTERS if starter.id == template_id), None)


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
