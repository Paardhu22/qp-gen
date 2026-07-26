"""Asset dataclasses and their rendering into pool questions.

An *asset* is the structured thing a generator produces — a passage with its
paragraph map and sub-questions, a single grammar task, a writing scenario with
its rubric. A *pool question* is the flat `(question, answer, marks, options)`
shape the rest of the system speaks: the store, the SSE contract, the editor,
multi-set derivation and the answer-key service all already understand it.

Keeping both is what makes this refactor cheap. Assets give the generators a
real domain model (and give reuse something meaningful to key on), while
`to_pool_question()` renders them into a shape nothing downstream had to learn.
The structured original rides along in `metadata` so it is never lost.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from services.pool.schema import (
    PoolQuestion,
    PoolValidationError,
    compute_content_hash,
    normalize_blooms,
    normalize_difficulty,
)
from utils.ids import generate_id

#: Roman numerals for sub-question labelling, matching CBSE's own convention
#: (I, II, III … inside a question; A/B/C/D for options).
_ROMAN = [
    "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
    "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX",
]

_OPTION_LABELS = ["A", "B", "C", "D", "E", "F"]


def _roman(index: int) -> str:
    return _ROMAN[index] if index < len(_ROMAN) else str(index + 1)


def _clean(value: Any) -> str:
    return re.sub(r"[ \t]+", " ", str(value or "")).strip()


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _word_count(text: str) -> int:
    return len([w for w in re.split(r"\s+", str(text or "").strip()) if w])


# ── Sub-questions (shared by reading and any future extract asset) ──────


@dataclass
class SubQuestion:
    """One numbered part inside a composite question."""

    prompt: str
    marks: int = 1
    options: List[str] = field(default_factory=list)
    answer: str = ""
    #: Which paragraph the part is anchored to, when the asset declares a
    #: paragraph map. CBSE prints this as "(Paragraph 3)".
    paragraph: Optional[int] = None
    skill: str = ""

    @classmethod
    def from_raw(cls, raw: Any) -> "SubQuestion":
        if not isinstance(raw, dict):
            raise PoolValidationError("Sub-question must be an object")
        prompt = _clean(raw.get("question") or raw.get("prompt") or raw.get("text"))
        if not prompt:
            raise PoolValidationError("Sub-question text is empty")
        try:
            marks = int(raw.get("marks") or 1)
        except (TypeError, ValueError):
            marks = 1
        options = [_clean(o) for o in _as_list(raw.get("options")) if _clean(o)]
        paragraph = raw.get("paragraph") or raw.get("paragraph_number")
        try:
            paragraph = int(paragraph) if paragraph not in (None, "") else None
        except (TypeError, ValueError):
            paragraph = None
        return cls(
            prompt=prompt,
            marks=max(1, marks),
            options=options,
            answer=_clean(raw.get("answer")),
            paragraph=paragraph,
            skill=_clean(raw.get("skill") or raw.get("type")),
        )

    def render(self, index: int) -> str:
        head = f"{_roman(index)}. {self.prompt}"
        if self.paragraph:
            head += f"   (Paragraph {self.paragraph})"
        head += f"   [{self.marks}]"
        lines = [head]
        for position, option in enumerate(self.options):
            label = _OPTION_LABELS[position] if position < len(_OPTION_LABELS) else str(position + 1)
            lines.append(f"      {label}. {option}")
        return "\n".join(lines)

    def render_answer(self, index: int) -> str:
        return f"{_roman(index)}. {self.answer or '—'}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt": self.prompt,
            "marks": self.marks,
            "options": list(self.options),
            "answer": self.answer,
            "paragraph": self.paragraph,
            "skill": self.skill,
        }


# ── Reading ─────────────────────────────────────────────────────────────


@dataclass
class ReadingAsset:
    """An original unseen passage and everything assessed from it.

    Never derived from an upload — the generator that writes these is never
    handed chapter text. `paragraph_map` is a one-line gist per paragraph; it
    both numbers the printed passage and lets sub-questions anchor themselves
    ("(Paragraph 3)"), which is how the CBSE paper does main-idea and
    paragraph-mapping items.
    """

    passage: str
    topic: str
    questions: List[SubQuestion]
    difficulty: str = "medium"
    reading_level: str = "class_10"
    passage_style: str = "discursive"
    paragraph_map: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    asset_kind = "reading"

    @property
    def paragraphs(self) -> List[str]:
        blocks = [b.strip() for b in re.split(r"\n\s*\n", self.passage.strip()) if b.strip()]
        return blocks or [self.passage.strip()]

    @property
    def word_count(self) -> int:
        return _word_count(self.passage)

    @property
    def total_marks(self) -> int:
        return sum(int(q.marks) for q in self.questions)

    @classmethod
    def from_raw(cls, raw: Any) -> "ReadingAsset":
        if not isinstance(raw, dict):
            raise PoolValidationError("Reading asset must be an object")
        passage = str(raw.get("passage") or raw.get("text") or "").strip()
        if not passage:
            raise PoolValidationError("Reading asset has no passage")
        raw_questions = _as_list(raw.get("questions") or raw.get("sub_questions"))
        questions = [SubQuestion.from_raw(q) for q in raw_questions]
        if not questions:
            raise PoolValidationError("Reading asset has no questions")
        return cls(
            passage=passage,
            topic=_clean(raw.get("topic")) or "Unseen passage",
            questions=questions,
            difficulty=normalize_difficulty(raw.get("difficulty")) or "medium",
            reading_level=_clean(raw.get("reading_level")) or "class_10",
            passage_style=_clean(raw.get("passage_style") or raw.get("style")) or "discursive",
            paragraph_map=[_clean(p) for p in _as_list(raw.get("paragraph_map")) if _clean(p)],
            metadata={},
        )

    def render_question(self) -> str:
        lines = ["Read the following passage."]
        for position, paragraph in enumerate(self.paragraphs, start=1):
            lines.append(f"{position}   {paragraph}")
        lines.append(f"(Created for academic usage / {self.word_count} words)")
        lines.append("Answer the following questions, based on the passage above.")
        lines.extend(q.render(i) for i, q in enumerate(self.questions))
        return "\n\n".join(lines)

    def render_answer(self) -> str:
        return "\n".join(q.render_answer(i) for i, q in enumerate(self.questions))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passage": self.passage,
            "topic": self.topic,
            "difficulty": self.difficulty,
            "readingLevel": self.reading_level,
            "passageStyle": self.passage_style,
            "wordCount": self.word_count,
            "paragraphMap": list(self.paragraph_map),
            "questions": [q.to_dict() for q in self.questions],
        }


# ── Grammar ─────────────────────────────────────────────────────────────


@dataclass
class GrammarAsset:
    """One self-contained, rule-based grammar task worth one mark.

    Atomic on purpose. The CBSE paper asks twelve of these and lets the student
    attempt ten, so the reusable unit is the task, not the bundle —
    `compose_task_set` builds the bundle from whatever tasks are available,
    banked or fresh.
    """

    grammar_topic: str
    question: str
    answer: str
    options: List[str] = field(default_factory=list)
    explanation: str = ""
    difficulty: str = "medium"
    context: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    asset_kind = "grammar"

    @classmethod
    def from_raw(cls, raw: Any) -> "GrammarAsset":
        if not isinstance(raw, dict):
            raise PoolValidationError("Grammar asset must be an object")
        question = _clean(raw.get("question") or raw.get("task"))
        if not question:
            raise PoolValidationError("Grammar task text is empty")
        topic = _clean(raw.get("grammar_topic") or raw.get("topic"))
        if not topic:
            raise PoolValidationError("Grammar task has no grammar topic")
        return cls(
            grammar_topic=topic,
            question=question,
            answer=_clean(raw.get("answer")),
            options=[_clean(o) for o in _as_list(raw.get("options")) if _clean(o)],
            explanation=_clean(raw.get("explanation")),
            difficulty=normalize_difficulty(raw.get("difficulty")) or "medium",
            context=_clean(raw.get("context")),
            metadata={},
        )

    def render(self, index: int) -> str:
        lines = [f"{_roman(index)}. {self.question}"]
        for position, option in enumerate(self.options):
            label = _OPTION_LABELS[position] if position < len(_OPTION_LABELS) else str(position + 1)
            lines.append(f"      {label}. {option}")
        return "\n".join(lines)

    def render_answer(self, index: int) -> str:
        return f"{_roman(index)}. {self.answer or '—'}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "grammarTopic": self.grammar_topic,
            "question": self.question,
            "options": list(self.options),
            "answer": self.answer,
            "explanation": self.explanation,
            "difficulty": self.difficulty,
            "context": self.context,
        }


@dataclass
class GrammarTaskSet:
    """`tasks` grammar assets printed as one question, of which `attempt` count."""

    tasks: List[GrammarAsset]
    attempt: int
    difficulty: str = "medium"

    asset_kind = "grammar_task_set"

    @property
    def total_marks(self) -> int:
        return self.attempt

    def render_question(self) -> str:
        head = (
            f"Complete any {self.attempt} of {len(self.tasks)} of the following "
            "tasks, as directed."
        )
        return "\n\n".join([head] + [t.render(i) for i, t in enumerate(self.tasks)])

    def render_answer(self) -> str:
        return "\n".join(t.render_answer(i) for i, t in enumerate(self.tasks))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attempt": self.attempt,
            "taskCount": len(self.tasks),
            "grammarTopics": [t.grammar_topic for t in self.tasks],
            "tasks": [t.to_dict() for t in self.tasks],
        }


# ── Writing ─────────────────────────────────────────────────────────────


@dataclass
class WritingAsset:
    """An original writing prompt: scenario, format, word limit, rubric, model.

    The scenario is invented by the generator. It never references a prescribed
    text's characters or events, because the generator has no access to them.
    """

    scenario: str
    task_type: str
    word_limit: int = 120
    rubric: List[str] = field(default_factory=list)
    model_answer: str = ""
    role: str = ""
    audience: str = ""
    #: Stimulus blocks (excerpts, candidate profiles, data) an analytical
    #: paragraph must compare. Empty for a plain letter task.
    stimulus: List[Dict[str, str]] = field(default_factory=list)
    difficulty: str = "medium"
    metadata: Dict[str, Any] = field(default_factory=dict)

    asset_kind = "writing"

    @classmethod
    def from_raw(cls, raw: Any) -> "WritingAsset":
        if not isinstance(raw, dict):
            raise PoolValidationError("Writing asset must be an object")
        scenario = _clean(raw.get("scenario") or raw.get("prompt") or raw.get("question"))
        if not scenario:
            raise PoolValidationError("Writing asset has no scenario")
        try:
            word_limit = int(raw.get("word_limit") or raw.get("wordLimit") or 120)
        except (TypeError, ValueError):
            word_limit = 120

        stimulus: List[Dict[str, str]] = []
        for block in _as_list(raw.get("stimulus")):
            if isinstance(block, dict):
                title = _clean(block.get("title") or block.get("label") or block.get("name"))
                body = _clean(block.get("body") or block.get("text") or block.get("content"))
                if body:
                    stimulus.append({"title": title or "Excerpt", "body": body})
            elif _clean(block):
                stimulus.append({"title": "Excerpt", "body": _clean(block)})

        return cls(
            scenario=scenario,
            task_type=_clean(raw.get("task_type") or raw.get("taskType")) or "formal_letter",
            word_limit=max(30, word_limit),
            rubric=[_clean(r) for r in _as_list(raw.get("rubric")) if _clean(r)],
            model_answer=_clean(raw.get("model_answer") or raw.get("modelAnswer")),
            role=_clean(raw.get("role")),
            audience=_clean(raw.get("audience")),
            stimulus=stimulus,
            difficulty=normalize_difficulty(raw.get("difficulty")) or "medium",
            metadata={},
        )

    def render_question(self) -> str:
        parts = [self.scenario]
        for block in self.stimulus:
            parts.append(f"{block['title']}\n{block['body']}")
        if f"{self.word_limit}" not in self.scenario:
            parts.append(f"Write in about {self.word_limit} words.")
        return "\n\n".join(p for p in parts if p)

    def render_answer(self) -> str:
        parts: List[str] = []
        if self.rubric:
            parts.append(
                "Marking scheme: " + "; ".join(self.rubric)
            )
        if self.model_answer:
            parts.append("Model answer:\n" + self.model_answer)
        return "\n\n".join(parts) or "—"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario": self.scenario,
            "taskType": self.task_type,
            "wordLimit": self.word_limit,
            "rubric": list(self.rubric),
            "modelAnswer": self.model_answer,
            "role": self.role,
            "audience": self.audience,
            "stimulus": list(self.stimulus),
            "difficulty": self.difficulty,
        }


# ── Rendering into the pool contract ────────────────────────────────────


def build_pool_question(
    *,
    question: str,
    answer: str,
    marks: int,
    subject: str,
    chapter: str,
    topic: str,
    question_type: str,
    generator: str,
    asset_type: str,
    source_type: str,
    pool_id: str = "",
    options: Optional[Sequence[str]] = None,
    explanation: str = "",
    blooms: str = "UNDERSTAND",
    difficulty: str = "medium",
    asset: Optional[Any] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> PoolQuestion:
    """One place where an asset becomes a pool question.

    Provenance (`generator`, `asset_type`, `source_type`) is stamped here and
    nowhere else, so there is a single answer to "where did this question come
    from" — which is what `slot_accepts` gates on.
    """
    text = question.strip()
    if not text:
        raise PoolValidationError("Rendered asset has empty question text")

    metadata: Dict[str, Any] = {
        "generator": generator,
        "assetType": asset_type,
        "usesUploadedContent": False,
        **(extra_metadata or {}),
    }
    if asset is not None and hasattr(asset, "to_dict"):
        metadata["asset"] = asset.to_dict()

    return PoolQuestion(
        id=generate_id(),
        subject=subject,
        chapter=chapter,
        topic=topic or chapter,
        type=question_type,
        blooms=normalize_blooms(blooms) or "UNDERSTAND",
        difficulty=normalize_difficulty(difficulty) or "medium",
        marks=int(marks),
        question=text,
        options=[str(o) for o in (options or [])],
        answer=answer or "",
        explanation=explanation or "",
        generator=generator,
        asset_type=asset_type,
        source_type=source_type,
        content_hash=compute_content_hash(subject, chapter, text),
        pool_id=pool_id,
        metadata=metadata,
    )
