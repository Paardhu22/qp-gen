"""Which question types each subject uses, and how often.

The catalogue says what a type *is*. This says which subject sets it. Types are
shared rather than owned: `MCQ_SINGLE` is one entry that every subject lists,
not one per subject. Source: "Question Types by Subject — AOS".

Each subject grades its types in three weights:

* **core** — what teachers of that subject actually set. The picker opens on
  these, so a Science teacher sees Science's types rather than a hundred.
* **occasional** — used, but not often. One click away under "Browse all".
* **rare** — offered, ranked last.

A type a subject does not list is not offered to it at all: code-writing items
are Computer's, maps are Social Science's, antonyms are a language's.

How the weights were read from the research: a type marked ● in its reuse matrix
is core, ○ occasional; a type in a subject's own exclusive table is core; a
universal type the matrix does not grade is occasional; the few it calls rare
are rare.

Two deliberate differences from the research, both because this product's
subjects are not quite its subjects:

* **Science covers Classes 1–10.** The product has no EVS subject — a Class 3
  "Science" paper is an EVS paper — so EVS's worksheet and picture types sit in
  Science. Each carries its own class range (Classes 1–5), so from Class 6 they
  drop out of the opening list on their own.
* **Social Science covers Social Studies (Classes 3–5)** for the same reason.

The class band is not repeated here: a type's own `classes` already bound it,
and the menu ranks by it. `TypeSpec.subjects` stays the hard ceiling — a
subject may never list a type that field reserves for others, which a test
holds.

Sanskrit uses Hindi's list, and the display names the Builder sends ("Computer
Science", "EVS") resolve through `SUBJECT_ALIASES`.

ICT is graded from papers rather than the research, which predates it: the CBSE
Information Technology (402) sample papers for Classes 9–10, the CBSE/NCERT ICT
strands for Classes 1–8, and Cambridge IGCSE ICT (0417) Paper 1. It differs
from Computer Science in weight, not in kind: application skills (shortcuts,
software steps, spreadsheet formulas, cyber safety) are core, writing code is
occasional.

Django-free, like the rest of the package.
"""

from __future__ import annotations

from typing import Dict, Iterable, Mapping, Optional

CORE = "core"
OCCASIONAL = "occasional"
RARE = "rare"
WEIGHTS = (CORE, OCCASIONAL, RARE)

#: Ranking order: core first.
WEIGHT_RANK: Mapping[str, int] = {weight: rank for rank, weight in enumerate(WEIGHTS)}


def _codes(text: str) -> tuple:
    return tuple(text.split())


def _grade(*, core: str, occasional: str = "", rare: str = "") -> Dict[str, str]:
    """One subject's types, each in exactly one weight."""
    graded: Dict[str, str] = {}
    for weight, text in ((CORE, core), (OCCASIONAL, occasional), (RARE, rare)):
        for code in _codes(text):
            if code in graded:
                raise ValueError(f"{code} is graded both {graded[code]} and {weight}")
            graded[code] = weight
    return graded


# ── Groups the subjects share ───────────────────────────────────────────────

#: Primary worksheet activities, answered by marking rather than writing.
_WORKSHEET = "CIRCLE_CORRECT CROSS_OUT JOIN_LINES TICK_CROSS WORD_SEARCH"

_GRAMMAR = """
    GRAMMAR_ITEM GAP_FILL_GRAMMAR ERROR_CORRECTION EDITING_OMISSION
    SENTENCE_TRANSFORM REARRANGE_WORDS REPORTED_SPEECH ACTIVE_PASSIVE
    CONNECTOR_CLAUSE PUNCTUATION
"""

_VOCABULARY = """
    VOCABULARY_ITEM SYNONYM_ANTONYM IDIOM_PHRASE HOMOPHONE PREFIX_SUFFIX
    WORD_FORM_CHANGE SPELLING OPPOSITE_WRITE RHYMING_WORDS
"""

_WRITING = """
    LETTER_WRITING EMAIL_WRITING NOTICE_WRITING MESSAGE_WRITING ESSAY_WRITING
    STORY_WRITING PARAGRAPH_WRITING ANALYTICAL_PARAGRAPH DIALOGUE_WRITING
    DIARY_ENTRY SPEECH_DEBATE PICTURE_COMPOSITION
"""


def _language(*, core: str = "", occasional: str = "") -> Dict[str, str]:
    """English, Hindi and Telugu share one structure; only a few weights move."""
    return _grade(
        core=f"""
            MCQ_SINGLE MCQ_PICTURE MCQ_FILL MCQ_ANALOGY MCQ_CASE
            FILL_BLANK FILL_BLANK_BANK TRUE_FALSE MATCH_FOLLOWING
            VSA SA LA VLA OPINION_JUSTIFY
            PASSAGE_UNSEEN EXTRACT_SEEN POETRY_APPRECIATION DIALOGUE_BASED NEWS_BASED
            {_GRAMMAR} {_VOCABULARY} {_WRITING}
            {_WORKSHEET} PHONICS_MATCH TRACE_WRITE NAME_PICTURE
            {core}
        """,
        occasional=f"""
            MCQ_MATCH MCQ_STATEMENT_EVAL MCQ_CORRECT MCQ_INCORRECT MCQ_IDENTIFY
            MCQ_ODD_ONE_OUT MCQ_MULTI MCQ_TF_COMBO MCQ_SEQUENCE
            TRUE_FALSE_CORRECT ONE_WORD NAME_FOLLOWING CLASSIFY_SORT
            SEQUENCE_WRITE ODD_ONE_OUT_JUSTIFY
            DEFINE SHORT_JUSTIFY DIFFERENTIATE COMPARE_TABLE LIST_STATE
            EXAMPLE_GIVE APPLICATION_SCENARIO PREDICT_OUTCOME
            CASE_STUDY PICTURE_BASED TABLE_COMPLETE FLOWCHART_COMPLETE IMAGE_IDENTIFY
            ARTICLE_WRITING REPORT_WRITING
            {occasional}
        """,
    )


_HINDI = _language(core="TRANSLATION")

SUBJECT_TYPES: Mapping[str, Mapping[str, str]] = {
    "mathematics": _grade(
        core=f"""
            MCQ_SINGLE MCQ_ODD_ONE_OUT MCQ_DATA MCQ_MULTI MATRIX_MATCH MCQ_NUMERICAL
            FILL_BLANK TRUE_FALSE CLASSIFY_SORT
            VSA SA LA DEFINE SHORT_JUSTIFY DIFFERENTIATE COMPARE_TABLE
            APPLICATION_SCENARIO CASE_STUDY DATA_INTERPRETATION
            GRAPH_PLOT GRAPH_READ GEOM_CONSTRUCTION TABLE_COMPLETE
            NUMERICAL WORD_PROBLEM SOLVE_EQUATION SIMPLIFY_EVALUATE MISSING_NUMBER
            MENSURATION_APPLIED STATISTICS_COMPUTE NUMBER_PATTERN PROOF_DERIVATION
            PROVE_IDENTITY GRAPHICAL_SOLUTION VERIFY_CHECK ESTIMATION_ROUNDING
            CASE_STUDY_MATHS
            {_WORKSHEET} NUMBER_GRID COMPARE_QUANTITY COUNT_WRITE PATTERN_COMPLETE
            CLOCK_DRAW SYMMETRY_DRAW
        """,
        occasional="""
            MCQ_PICTURE MCQ_MATCH MCQ_FILL MCQ_STATEMENT_EVAL MCQ_CORRECT
            MCQ_INCORRECT MCQ_IDENTIFY MCQ_TF_COMBO MCQ_SEQUENCE MCQ_CASE MCQ_SERIES
            ASSERTION_REASON
            FILL_BLANK_BANK TRUE_FALSE_CORRECT ONE_WORD MATCH_FOLLOWING NAME_FOLLOWING
            NUMERIC_ENTRY SEQUENCE_WRITE ODD_ONE_OUT_JUSTIFY UNIT_SYMBOL
            LIST_STATE EXAMPLE_GIVE EXPLAIN_PROCESS PREDICT_OUTCOME
            PICTURE_BASED FLOWCHART_COMPLETE IMAGE_IDENTIFY DRAW_COLOUR
        """,
        rare="DIALOGUE_BASED OPINION_JUSTIFY MCQ_CAUSE_EFFECT",
    ),
    # Science and, for Classes 1–5, EVS.
    "science": _grade(
        core=f"""
            MCQ_SINGLE MCQ_MATCH MCQ_FILL MCQ_STATEMENT_EVAL MCQ_CORRECT
            MCQ_INCORRECT MCQ_IDENTIFY MCQ_ODD_ONE_OUT MCQ_DATA ASSERTION_REASON
            MCQ_MULTI MATRIX_MATCH MCQ_NUMERICAL MCQ_PICTURE
            FILL_BLANK FILL_BLANK_BANK TRUE_FALSE ONE_WORD MATCH_FOLLOWING
            NAME_FOLLOWING CLASSIFY_SORT SEQUENCE_WRITE UNIT_SYMBOL FULL_FORM
            VSA SA LA DEFINE SHORT_JUSTIFY DIFFERENTIATE COMPARE_TABLE
            EXPLAIN_PROCESS APPLICATION_SCENARIO PREDICT_OUTCOME
            CASE_STUDY DATA_INTERPRETATION PICTURE_BASED
            EXPERIMENT_BASED EXPERIMENT_DESIGN EXPERIMENT_OBSERVATION SAFETY_PROCEDURE
            DIAGRAM_DRAW DIAGRAM_LABEL RAY_CIRCUIT_DIAGRAM GRAPH_PLOT GRAPH_READ
            TABLE_COMPLETE FLOWCHART_COMPLETE
            {_WORKSHEET} PATTERN_COMPLETE DRAW_COLOUR CIRCLE_PICTURE
            COLOUR_INSTRUCTION TRACE_WRITE NAME_PICTURE MAZE_PATH CUT_PASTE_SORT
            SEQUENCE_PICTURES JOIN_DOTS
        """,
        occasional="""
            MCQ_ANALOGY MCQ_SERIES MCQ_CAUSE_EFFECT MCQ_DIAGRAM_LABEL MCQ_TF_COMBO
            MCQ_SEQUENCE MCQ_CASE
            TRUE_FALSE_CORRECT ODD_ONE_OUT_JUSTIFY NUMERIC_ENTRY
            NUMERICAL WORD_PROBLEM PROOF_DERIVATION
            VLA LIST_STATE EXAMPLE_GIVE OPINION_JUSTIFY
            DIALOGUE_BASED NEWS_BASED INFOGRAPHIC_BASED IMAGE_IDENTIFY TOOL_IDENTIFY
        """,
    ),
    # Social Science and, for Classes 3–5, Social Studies.
    "social science": _grade(
        core="""
            MCQ_SINGLE MCQ_MATCH MCQ_FILL MCQ_STATEMENT_EVAL MCQ_CORRECT
            MCQ_INCORRECT MCQ_IDENTIFY MCQ_DATA ASSERTION_REASON MCQ_CHRONOLOGY MCQ_MAP
            FILL_BLANK FILL_BLANK_BANK TRUE_FALSE MATCH_FOLLOWING NAME_FOLLOWING
            CLASSIFY_SORT FULL_FORM
            VSA SA LA VLA DEFINE SHORT_JUSTIFY DIFFERENTIATE COMPARE_TABLE
            EXPLAIN_PROCESS APPLICATION_SCENARIO OPINION_JUSTIFY PREDICT_OUTCOME
            CASE_STUDY DATA_INTERPRETATION SOURCE_BASED CARTOON_BASED NEWS_BASED
            MAP_SKILL GRAPH_PLOT GRAPH_READ TABLE_COMPLETE FLOWCHART_COMPLETE
        """,
        occasional=f"""
            MCQ_PICTURE MCQ_ODD_ONE_OUT MCQ_MULTI MCQ_NUMERICAL MCQ_ANALOGY
            MCQ_CAUSE_EFFECT MCQ_TF_COMBO MCQ_SEQUENCE MCQ_CASE
            TRUE_FALSE_CORRECT ONE_WORD SEQUENCE_WRITE ODD_ONE_OUT_JUSTIFY NUMERIC_ENTRY
            LIST_STATE EXAMPLE_GIVE
            DIALOGUE_BASED PICTURE_BASED INFOGRAPHIC_BASED IMAGE_IDENTIFY
            DIAGRAM_DRAW DIAGRAM_LABEL
            {_WORKSHEET}
        """,
    ),
    "english": _language(occasional="TRANSLATION"),
    "hindi": _HINDI,
    "sanskrit": _HINDI,
    "telugu": _language(core="TRANSLATION"),
    "computer science": _grade(
        core="""
            MCQ_SINGLE MCQ_CORRECT MCQ_INCORRECT MCQ_IDENTIFY MCQ_MULTI
            FILL_BLANK FILL_BLANK_BANK TRUE_FALSE MATCH_FOLLOWING NAME_FOLLOWING FULL_FORM
            VSA SA LA DEFINE COMPARE_TABLE EXPLAIN_PROCESS APPLICATION_SCENARIO
            CASE_STUDY TABLE_COMPLETE FLOWCHART_COMPLETE SAFETY_PROCEDURE
            CODE_OUTPUT CODE_DEBUG CODE_WRITE ALGORITHM_DESIGN FLOWCHART_DRAW TOOL_IDENTIFY
        """,
        occasional=f"""
            MCQ_PICTURE MCQ_MATCH MCQ_FILL MCQ_STATEMENT_EVAL MCQ_ODD_ONE_OUT MCQ_DATA
            ASSERTION_REASON MATRIX_MATCH MCQ_NUMERICAL MCQ_TF_COMBO MCQ_SEQUENCE MCQ_CASE
            TRUE_FALSE_CORRECT ONE_WORD CLASSIFY_SORT SEQUENCE_WRITE
            ODD_ONE_OUT_JUSTIFY NUMERIC_ENTRY
            SHORT_JUSTIFY DIFFERENTIATE LIST_STATE EXAMPLE_GIVE OPINION_JUSTIFY
            PREDICT_OUTCOME DATA_INTERPRETATION NEWS_BASED PICTURE_BASED
            DIAGRAM_DRAW DIAGRAM_LABEL GRAPH_PLOT GRAPH_READ IMAGE_IDENTIFY
            SHORTCUT_KEY SOFTWARE_STEPS SPREADSHEET_FORMULA
            {_WORKSHEET}
        """,
        rare="DIALOGUE_BASED",
    ),
    # Information and Communication Technology, Classes 1–10 (CBSE IT 402 in 9–10).
    "ict": _grade(
        core=f"""
            MCQ_SINGLE MCQ_FILL MCQ_IDENTIFY MCQ_CORRECT MCQ_INCORRECT MCQ_MULTI
            MCQ_SEQUENCE MCQ_PICTURE ASSERTION_REASON TOOL_IDENTIFY
            FILL_BLANK FILL_BLANK_BANK TRUE_FALSE ONE_WORD MATCH_FOLLOWING
            NAME_FOLLOWING CLASSIFY_SORT FULL_FORM SHORTCUT_KEY
            VSA SA LA DEFINE DIFFERENTIATE LIST_STATE EXAMPLE_GIVE
            APPLICATION_SCENARIO SAFETY_PROCEDURE SOFTWARE_STEPS SPREADSHEET_FORMULA
            CASE_STUDY TABLE_COMPLETE ALGORITHM_DESIGN FLOWCHART_DRAW
            DIAGRAM_LABEL IMAGE_IDENTIFY
            {_WORKSHEET} NAME_PICTURE CIRCLE_PICTURE
        """,
        occasional="""
            MCQ_MATCH MCQ_STATEMENT_EVAL MCQ_ODD_ONE_OUT MCQ_DATA MCQ_NUMERICAL
            MCQ_TF_COMBO MCQ_CASE MCQ_ANALOGY MATRIX_MATCH
            TRUE_FALSE_CORRECT SEQUENCE_WRITE ODD_ONE_OUT_JUSTIFY NUMERIC_ENTRY NUMERICAL
            VLA SHORT_JUSTIFY COMPARE_TABLE EXPLAIN_PROCESS OPINION_JUSTIFY PREDICT_OUTCOME
            DATA_INTERPRETATION GRAPH_READ NEWS_BASED PICTURE_BASED INFOGRAPHIC_BASED
            FLOWCHART_COMPLETE DIAGRAM_DRAW
            CODE_OUTPUT CODE_WRITE CODE_DEBUG
            PATTERN_COMPLETE DRAW_COLOUR MAZE_PATH SEQUENCE_PICTURES
        """,
        rare="DIALOGUE_BASED MCQ_CAUSE_EFFECT GRAPH_PLOT",
    ),
}

#: Names the Builder or a brief may send that are not a key above.
SUBJECT_ALIASES: Mapping[str, str] = {
    "computer": "computer science",
    "computers": "computer science",
    "computer applications": "computer science",
    "information and communication technology": "ict",
    "information and communications technology": "ict",
    "information & communication technology": "ict",
    "information technology": "ict",
    "evs": "science",
    "environmental studies": "science",
    "environmental science": "science",
    "social studies": "social science",
}


def subject_types(subject_key: str) -> Optional[Mapping[str, str]]:
    """The graded types for a normalised subject, or None when it has no map."""
    key = str(subject_key or "").strip().lower()
    return SUBJECT_TYPES.get(SUBJECT_ALIASES.get(key, key))


def subjects() -> Iterable[str]:
    return SUBJECT_TYPES.keys()
