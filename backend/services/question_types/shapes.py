"""The runtime question shapes — the 22 codes the pipeline has always spoken.

A catalogue type (`MCQ_ODD_ONE_OUT`) is the teacher-facing identity. Its
`shape` (`MCQ`) is what the machinery keys on: whether the normaliser expects
options, which blueprint buckets may accept the question, how many tokens a
batch budgets for it, and whether the editor lays it out as one block or as a
composite run. Keeping those decisions on the shape is what lets 160 presets
flow through a pipeline that only ever learned 22 names.

Every list that used to be typed out separately — `schema.QUESTION_TYPES`,
`LEGACY_TYPE_ACCEPTS`, `OPTION_BEARING_TYPES`, the three copies of the
legacy-bucket map, the Model 1 token table — is derived from `SHAPES`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Tuple


@dataclass(frozen=True)
class Shape:
    code: str
    #: The coarse `legacy_type` a blueprint slot of this shape carries.
    bucket: str
    #: Every bucket that may be filled by a question of this shape. Wider than
    #: `bucket`: a 5-mark LONG slot is happy with a case study.
    accepted_by: Tuple[str, ...]
    #: Completion tokens one question of this shape needs, explanation included.
    tokens: int
    #: The catalogue type a bare shape name means ("MCQ" → "MCQ_SINGLE").
    default_type: str
    #: Picker label, group and default marks for the shape-level menu.
    label: str
    group: str
    default_marks: int
    option_bearing: bool = False
    #: Laid out by the editor as a head block plus a run of body paragraphs.
    composite: bool = False
    #: No longer a type — the name survives only so old data still reads.
    retired: bool = False
    #: Slot attributes a retired shape implies (HOTS → hots).
    implies: Tuple[str, ...] = ()


SHAPES: Tuple[Shape, ...] = (
    # Objective
    Shape("MCQ", "MCQ", ("MCQ",), 130, "MCQ_SINGLE", "Multiple Choice", "Objective", 1, option_bearing=True),
    Shape("ASSERTION_REASON", "ASSERTION_REASON", ("ASSERTION_REASON",), 170, "ASSERTION_REASON", "Assertion & Reason", "Objective", 1, option_bearing=True),
    Shape("TRUE_FALSE", "SHORT", ("SHORT",), 90, "TRUE_FALSE", "True / False", "Objective", 1, option_bearing=True),
    Shape("FILL_IN_THE_BLANK", "SHORT", ("SHORT",), 90, "FILL_BLANK", "Fill in the Blank", "Objective", 1),
    Shape("ONE_WORD", "SHORT", ("SHORT",), 80, "ONE_WORD", "One Word Answer", "Objective", 1),
    Shape("MATCH_THE_FOLLOWING", "SHORT", ("SHORT",), 200, "MATCH_FOLLOWING", "Match the Following", "Objective", 4, option_bearing=True),
    # Descriptive
    Shape("VERY_SHORT_ANSWER", "SHORT", ("SHORT",), 130, "VSA", "Very Short Answer", "Descriptive", 1),
    Shape("SHORT_ANSWER", "SHORT", ("SHORT",), 220, "SA", "Short Answer", "Descriptive", 2),
    Shape("LONG_ANSWER", "LONG", ("LONG",), 400, "LA", "Long Answer", "Descriptive", 5),
    Shape("HOTS", "SHORT", ("SHORT", "LONG"), 300, "SA", "Higher Order Thinking", "Descriptive", 3, retired=True, implies=("hots",)),
    Shape("COMPETENCY", "SHORT", ("SHORT",), 320, "APPLICATION_SCENARIO", "Competency Based", "Descriptive", 3, retired=True, implies=("competency",)),
    # Applied
    Shape("NUMERICAL", "SHORT", ("SHORT",), 260, "NUMERICAL", "Numerical / Calculation", "Applied", 3),
    Shape("EXPERIMENTAL", "SHORT", ("SHORT",), 260, "EXPERIMENT_BASED", "Experimental", "Applied", 3),
    Shape("DIAGRAM", "DIAGRAM", ("DIAGRAM",), 220, "DIAGRAM_DRAW", "Diagram (student draws)", "Applied", 3),
    Shape("CASE_STUDY", "CASE_STUDY", ("CASE_STUDY", "LONG"), 650, "CASE_STUDY", "Case Study", "Applied", 4, composite=True),
    # Language
    Shape("READING_COMP", "CASE_STUDY", ("CASE_STUDY",), 650, "PASSAGE_UNSEEN", "Reading Comprehension", "Language", 10, composite=True),
    Shape("EXTRACT_PROSE", "SHORT", ("SHORT",), 300, "EXTRACT_SEEN", "Prose Extract", "Language", 3, composite=True),
    Shape("EXTRACT_POETRY", "SHORT", ("SHORT",), 300, "POETRY_APPRECIATION", "Poetry Extract", "Language", 3, composite=True),
    Shape("ANALYTICAL_PARAGRAPH", "SHORT", ("SHORT",), 320, "ANALYTICAL_PARAGRAPH", "Analytical Paragraph", "Language", 5, composite=True),
    Shape("GRAMMAR", "SHORT", ("SHORT",), 120, "GRAMMAR_ITEM", "Grammar", "Language", 1, composite=True),
    Shape("LETTER", "LONG", ("LONG",), 400, "LETTER_WRITING", "Letter Writing", "Language", 5, composite=True),
    # The router used to bucket COMPOSITION as SHORT while the pipeline, the
    # Builder and the replace path all said LONG; a Builder round trip already
    # re-derived LONG. One answer now, and it is the one three of four agreed.
    Shape("COMPOSITION", "LONG", ("LONG",), 400, "ESSAY_WRITING", "Composition / Essay", "Language", 5, composite=True),
)

SHAPES_BY_CODE: Dict[str, Shape] = {shape.code: shape for shape in SHAPES}

#: Every shape code, retired ones included — old data must still normalise.
SHAPE_CODES: FrozenSet[str] = frozenset(SHAPES_BY_CODE)

OPTION_BEARING_SHAPES: FrozenSet[str] = frozenset(
    shape.code for shape in SHAPES if shape.option_bearing
)

COMPOSITE_SHAPES: FrozenSet[str] = frozenset(
    shape.code for shape in SHAPES if shape.composite
)


def _accepts_by_bucket() -> Dict[str, FrozenSet[str]]:
    buckets: Dict[str, set] = {}
    for shape in SHAPES:
        for bucket in shape.accepted_by:
            buckets.setdefault(bucket, set()).add(shape.code)
    return {bucket: frozenset(codes) for bucket, codes in buckets.items()}


#: Bucket → every shape that may fill a slot carrying that bucket.
BUCKET_ACCEPTS: Dict[str, FrozenSet[str]] = _accepts_by_bucket()

#: Synonyms a model reliably emits despite an explicit enum instruction. These
#: resolve to shapes; catalogue codes and teacher phrases resolve through
#: `registry.resolve`.
SHAPE_SYNONYMS: Dict[str, str] = {
    "MULTIPLE_CHOICE": "MCQ",
    "MULTIPLE CHOICE": "MCQ",
    "MCQS": "MCQ",
    "OBJECTIVE": "MCQ",
    "ASSERTION": "ASSERTION_REASON",
    "ASSERTION_AND_REASON": "ASSERTION_REASON",
    "ASSERTION-REASON": "ASSERTION_REASON",
    "AR": "ASSERTION_REASON",
    "CASE": "CASE_STUDY",
    "CASE_BASED": "CASE_STUDY",
    "CBQ": "CASE_STUDY",
    "SOURCE_BASED": "CASE_STUDY",
    "VSA": "VERY_SHORT_ANSWER",
    "VERY_SHORT": "VERY_SHORT_ANSWER",
    "SA": "SHORT_ANSWER",
    "SHORT": "SHORT_ANSWER",
    "LA": "LONG_ANSWER",
    "LONG": "LONG_ANSWER",
    "ESSAY": "LONG_ANSWER",
    "NUMERIC": "NUMERICAL",
    "CALCULATION": "NUMERICAL",
    "FILL_IN_THE_BLANKS": "FILL_IN_THE_BLANK",
    "FILL_IN_BLANK": "FILL_IN_THE_BLANK",
    "TRUE_OR_FALSE": "TRUE_FALSE",
    "MATCH": "MATCH_THE_FOLLOWING",
    "MATCHING": "MATCH_THE_FOLLOWING",
    "DIAGRAM_BASED": "DIAGRAM",
    "IMAGE": "DIAGRAM",
    "IMAGE_BASED": "DIAGRAM",
    "PICTURE_BASED": "DIAGRAM",
    "GRAPH": "DIAGRAM",
}


def bucket_for_shape(shape_code: str) -> str:
    """The legacy bucket for a shape; SHORT for anything unknown, as before."""
    shape = SHAPES_BY_CODE.get(shape_code)
    return shape.bucket if shape else "SHORT"
