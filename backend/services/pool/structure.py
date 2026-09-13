"""Structured questions: one stimulus, and parts whose marks add up.

A case study, a word-bank set or a source-based question is not one question.
It is a stimulus printed once and several parts, each with its own marks and
its own answer, and the parts' marks are the question's marks. Model 1 used to
write all of that into a single string ("…(i) … (ii) …"), which left nothing to
check: a 4-mark case study whose parts added up to 3 printed as a 4-mark case
study.

Model 1 now returns the pieces — `stimulus` and `parts` — and this module
checks them and prints them. The printed form keeps the shape the paper always
had (the stimulus, then "(i) … [1]"), so everything that reads a question's
text is unchanged. The pieces also go to the editor unglued, as
`metadata.composite`, so a long stimulus flows across pages instead of being
clipped — the same contract the reading and grammar assets already use.

Only structure is language-bearing here in one place: the instruction line,
which the model writes in the paper's own language. Nothing below injects
English into a Hindi or Telugu paper.

Django-free.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from services.content_filters import clean_question_text


class StructureError(ValueError):
    """The structure cannot be printed as a valid question."""


_ROMAN = (
    "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x",
    "xi", "xii", "xiii", "xiv", "xv", "xvi", "xvii", "xviii", "xix", "xx",
)
_OPTION_LETTERS = "abcdefgh"

#: The CBSE case-study pattern: three parts worth 1 + 1 + 2.
_CASE_STUDY_PATTERN = (1, 1, 2)


def _roman(index: int) -> str:
    return _ROMAN[index] if index < len(_ROMAN) else str(index + 1)


def _clean(value: Any) -> str:
    return clean_question_text(str(value or "").strip()).strip()


@dataclass
class Part:
    prompt: str
    marks: int = 1
    options: List[str] = field(default_factory=list)
    answer: str = ""
    #: An internal OR on this one part (Maths Section E prints one on part iii).
    alternative: str = ""

    def render(self, index: int) -> str:
        lines = [f"({_roman(index)}) {self.prompt}   [{self.marks}]"]
        for position, option in enumerate(self.options):
            letter = _OPTION_LETTERS[position] if position < len(_OPTION_LETTERS) else str(position + 1)
            lines.append(f"      ({letter}) {option}")
        if self.alternative:
            lines.extend(["      OR", f"      {self.alternative}"])
        return "\n".join(lines)


@dataclass
class Stimulus:
    """What the parts rely on, printed once above them."""

    kind: str = "PASSAGE"
    text: str = ""
    #: A table as rows of cells; the first row is its header when it has one.
    rows: List[List[str]] = field(default_factory=list)
    #: A word box shared by several blanks.
    words: List[str] = field(default_factory=list)

    def blocks(self) -> List[str]:
        """The stimulus as printable blocks, one per paragraph or table."""
        blocks = [
            paragraph.strip()
            for paragraph in re.split(r"\n\s*\n", self.text.strip())
            if paragraph.strip()
        ]
        if self.rows:
            # Pipe rows: the editor turns a run of these lines into a table.
            blocks.append("\n".join("| " + " | ".join(row) + " |" for row in self.rows))
        if self.words:
            blocks.append("[ " + "   ·   ".join(self.words) + " ]")
        return blocks

    @property
    def is_empty(self) -> bool:
        return not (self.text.strip() or self.rows or self.words)


@dataclass
class Structure:
    parts: List[Part]
    stimulus: Optional[Stimulus] = None
    #: A choice pool: the student attempts any `attempt` of the parts. Zero
    #: means every part is compulsory. Distinct from an OR group, where one slot
    #: offers alternatives and exactly one is attempted.
    attempt: int = 0

    @property
    def marks(self) -> int:
        if self.attempt:
            return self.attempt * self.parts[0].marks
        return sum(part.marks for part in self.parts)

    def render(self, instruction: str) -> Tuple[str, str, Dict[str, Any]]:
        """(question text, answer key, editor composite) for this structure."""
        preamble = instruction.strip()
        body = self.stimulus.blocks() if self.stimulus else []
        parts = [part.render(index) for index, part in enumerate(self.parts)]
        content = "\n\n".join(block for block in (preamble, *body, *parts) if block)
        answer = "\n".join(
            f"({_roman(index)}) {part.answer}" for index, part in enumerate(self.parts)
        )
        composite = {"preamble": preamble, "body": body, "subQuestions": parts}
        return content, answer, composite

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _parse_part(raw: Any, index: int) -> Part:
    if not isinstance(raw, dict):
        raise StructureError(f"part {index + 1} is not an object")
    prompt = _clean(raw.get("question") or raw.get("prompt") or raw.get("text"))
    if not prompt:
        raise StructureError(f"part {index + 1} has no question")
    try:
        marks = max(1, int(raw.get("marks") or 1))
    except (TypeError, ValueError):
        marks = 1
    options = [_clean(option) for option in (raw.get("options") or []) if _clean(option)]
    if len(options) == 1:
        raise StructureError(f"part {index + 1} offers a single option")
    answer = _clean(raw.get("answer"))
    if not answer:
        raise StructureError(f"part {index + 1} has no answer")
    alternative = _clean(raw.get("alternative") or raw.get("or"))
    return Part(prompt, marks, options, answer, alternative)


def _parse_stimulus(raw: Any, kind: str) -> Optional[Stimulus]:
    if isinstance(raw, str):
        stimulus = Stimulus(kind or "PASSAGE", text=_clean(raw))
    elif isinstance(raw, dict):
        rows = [
            [_clean(cell) for cell in row]
            for row in (raw.get("rows") or [])
            if isinstance(row, (list, tuple))
        ]
        words = [_clean(word) for word in (raw.get("words") or []) if _clean(word)]
        stimulus = Stimulus(
            str(raw.get("kind") or kind or "PASSAGE").upper(),
            text=_clean(raw.get("text")),
            rows=[row for row in rows if any(row)],
            words=words,
        )
    else:
        return None
    return None if stimulus.is_empty else stimulus


def _parse_attempt(raw: Dict[str, Any], parts: List[Part]) -> int:
    choice = raw.get("choice") if isinstance(raw.get("choice"), dict) else {}
    value = raw.get("attempt") or choice.get("attempt")
    if not value:
        return 0
    try:
        attempt = int(value)
    except (TypeError, ValueError):
        raise StructureError(f"attempt {value!r} is not a number") from None
    if not 1 <= attempt < len(parts):
        raise StructureError(f"cannot attempt {attempt} of {len(parts)} parts")
    if len({part.marks for part in parts}) != 1:
        # "Attempt any four" only has a total when every part is worth the same.
        raise StructureError("a choice pool's parts must carry equal marks")
    return attempt


def parse_structure(
    raw: Dict[str, Any],
    *,
    marks: int,
    stimulus_kind: str = "",
) -> Optional[Structure]:
    """The structure in a raw Model 1 object, or None when it is a flat question.

    Raises StructureError when the object claims a structure it cannot honour:
    fewer than two parts, a part without an answer, a required stimulus
    missing, or parts whose marks cannot be made to equal `marks`.
    """
    raw_parts = raw.get("parts") or raw.get("sub_questions") or raw.get("subQuestions")
    if not isinstance(raw_parts, list) or not raw_parts:
        return None

    parts = [_parse_part(part, index) for index, part in enumerate(raw_parts)]
    if len(parts) < 2:
        raise StructureError("a structured question needs at least two parts")

    stimulus = _parse_stimulus(raw.get("stimulus"), stimulus_kind)
    if stimulus_kind and stimulus_kind != "NONE" and stimulus is None:
        raise StructureError(f"the {stimulus_kind.lower()} the parts rely on is missing")

    structure = Structure(parts, stimulus, _parse_attempt(raw, parts))

    if structure.marks != marks:
        if (
            not structure.attempt
            and len(parts) == 3
            and marks == sum(_CASE_STUDY_PATTERN)
            and structure.marks < marks
        ):
            # Three parts that fall short of a 4-mark question — typically one
            # mark each — are the board's case study with the numbers left
            # out, not a wrong question: restore 1 + 1 + 2 rather than discard
            # it. Parts that claim MORE than the question are a real error.
            for part, value in zip(parts, _CASE_STUDY_PATTERN):
                part.marks = value
        else:
            raise StructureError(
                f"the parts are worth {structure.marks} marks but the question is worth {marks}"
            )
    return structure
