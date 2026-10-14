"""The unit the planner produces — one question slot — plus plan summaries and slot labels."""

import re
import dataclasses
from collections import Counter
from typing import List, Dict, Any, Tuple

from services.generation.pool.schema import DEFAULT_GENERATOR as POOL_GENERATOR


@dataclasses.dataclass(frozen=True)
class QuestionGenerationSlot:
    """A deterministic, pre-LLM contract for exactly one generated question.

    The routing fields at the bottom are what make the blueprint a *routing
    engine* rather than a section labeller. `generator` names which pipeline
    owns this slot; everything downstream — whether the uploaded textbook is
    read at all, which pool may fill the slot, what Model 1's recipe covers —
    follows from it. Every routing field defaults to the pre-existing
    behaviour, so a blueprint that declares none of them (Science, Social
    Science, Mathematics, Hindi, Telugu, General Instructions mode) routes to
    the textbook pool exactly as before.
    """

    index: int
    section_title: str
    subject: str
    stream: str
    question_type: str
    legacy_type: str
    marks: int
    difficulty: str
    class_num: int
    exact_instruction: str
    retrieval_query: str
    choice_required: bool = False
    requires_figure: bool = False  # geometry/mensuration slots that MUST include an inline SVG diagram
    instruction_hint: str = ""
    # CONTENT | PASSAGE | GRAMMAR | COMPOSITION (see services.generation.blueprint.core.enums.GenerationMode).
    # Defaults to CONTENT so Science / Social Science / Mathematics behaviour is unchanged.
    generation_mode: str = "CONTENT"

    # ── Routing contract ────────────────────────────────────────────────
    #: Which generator produces this slot. `question_pool` (the default) is the
    #: uploaded-textbook pipeline; anything else is an independent generator
    #: registered in `services.generation.assets`.
    generator: str = POOL_GENERATOR
    #: The shape that generator must emit ("discursive_passage",
    #: "grammar_task_set", "formal_letter", "extract_poetry", …).
    asset_type: str = ""
    #: Generator-readable parameters: word counts, sub-question marks patterns,
    #: task counts, allowed formats. Excluded from equality/hashing because it
    #: is a mutable mapping and slots are compared by identity of contract, not
    #: by their parameter blob.
    constraints: Dict[str, Any] = dataclasses.field(
        default_factory=dict, compare=False
    )
    #: Names of rules in `services.generation.assets.validation` to run on what comes back.
    validation: Tuple[str, ...] = ()

    # ── Type identity ───────────────────────────────────────────────────
    #: The catalogue type this slot asks for. `question_type` stays the runtime
    #: shape every consumer keys on; a slot built from a shape name alone gets
    #: that shape's default type.
    type_code: str = ""
    #: Slot attributes: higher-order thinking, real-world framing.
    hots: bool = False
    competency: bool = False

    def __post_init__(self) -> None:
        if not self.type_code:
            from services.question_types import default_type_for_shape

            # The dataclass is frozen; set the derived default the way its own
            # generated __init__ would.
            object.__setattr__(
                self, "type_code", default_type_for_shape(self.question_type)
            )


def extract_mcq_options(content_text: str) -> tuple:
    """
    Extracts MCQ options from standard template text if formatted like:
    (a) Option A
    (b) Option B
    (c) Option C
    (d) Option D
    Returns the clean main question text and the list of extracted options.
    """
    pattern = re.compile(r'\(([a-d])\)\s*(.*?)(?=\s*\([a-d]\)|$)')
    matches = pattern.findall(content_text)
    if len(matches) == 4:
        main_question = re.split(r'\s*\([a-d]\)', content_text)[0].strip()
        options = [m[1].strip() for m in matches]
        return main_question, options
    return content_text, []


def _type_label(question_type: str, marks: int) -> str:
    labels = {
        "MCQ": "MCQs",
        "ASSERTION_REASON": "Assertion-Reason",
        "SHORT_ANSWER": "VSAs" if marks == 2 else "Short Answers",
        "LONG_ANSWER": "Long Answers",
        "CASE_STUDY": "Case-Based",
        "DIAGRAM": "Diagram/Map",
        "READING_COMP": "Reading Comprehension",
        "GRAMMAR": "Grammar Tasks",
        "LETTER": "Writing Tasks",
        "NUMERICAL": "Numericals",
    }
    return labels.get(question_type, question_type.replace("_", " ").title())


def summarize_question_plan(plan: List[QuestionGenerationSlot]) -> Dict[str, Any]:
    counts = Counter((slot.question_type, slot.marks) for slot in plan)
    ordered_keys: List[Tuple[str, int]] = []
    for slot in plan:
        key = (slot.question_type, slot.marks)
        if key not in ordered_keys:
            ordered_keys.append(key)
    exact_counts = [
        f"{count} {_type_label(question_type, marks)} ({marks}m)"
        for question_type, marks in ordered_keys
        for count in [counts[(question_type, marks)]]
    ]
    section_marks: Dict[str, int] = {}
    section_questions: Dict[str, int] = {}
    for slot in plan:
        section_marks[slot.section_title] = section_marks.get(slot.section_title, 0) + slot.marks
        section_questions[slot.section_title] = section_questions.get(slot.section_title, 0) + 1

    return {
        "total_questions": len(plan),
        "total_marks": sum(slot.marks for slot in plan),
        "or_choices": sum(1 for slot in plan if slot.choice_required),
        "exact_counts": exact_counts,
        "section_marks": section_marks,
        "section_questions": section_questions,
    }


def _legacy_question_type(qtype_name: str) -> str:
    """The coarse bucket a slot of this type carries, from the catalogue.

    COMPOSITION buckets as LONG. This function used to be the one place that
    said SHORT while the pipeline, the Builder and the replace path all said
    LONG — so a Builder round trip already changed it.
    """
    from services.question_types import legacy_bucket

    return legacy_bucket(qtype_name)


def _section_title_for_stream(subject_norm: str, stream_name: str, class_num: int) -> str:
    if class_num < 9:
        return "Questions"

    if subject_norm == "social science":
        titles = {
            "HISTORY": "Section A - History",
            "GEOGRAPHY": "Section B - Geography",
            "CIVICS": "Section C - Political Science",
            "ECONOMICS": "Section D - Economics",
        }
        return titles.get(stream_name, f"Section: {stream_name.title()}")

    titles = {
        "BIOLOGY": "Section A - Biology",
        "CHEMISTRY": "Section B - Chemistry",
        "PHYSICS": "Section C - Physics",
    }
    return titles.get(stream_name, f"Section: {stream_name.title()}")


def _section_title_for_question_type(subject_norm: str, class_num: int, qtype_name: str, marks: int) -> str:
    if qtype_name in {"MCQ", "ASSERTION_REASON"}:
        return "Section A - MCQ"
    if marks == 2:
        return "Section B - Very Short Answer"
    if marks == 3:
        return "Section C - Short Answer"
    if marks >= 5:
        return "Section D - Long Answer"
    if qtype_name == "CASE_STUDY" or marks == 4:
        return "Section E - Case-Based Questions"
    return "Questions"
