"""The dashboard assistant: conversation, not generation.

This model talks. It does not write questions — that is the pool pipeline's
job, on POOL_MODEL, and mixing the two would put a chat-tuned model in charge
of CBSE compliance. What this does instead is the part the generator form is
bad at: a teacher says "I need a class 10 science paper on light for next
week's unit test" and something has to work out that the form still needs a
board, a mark total, a difficulty and a set count. So the assistant asks, one
or two questions at a time, and the answers accumulate into a spec the
generator can be launched with.

Two calls per turn:

1. A streamed completion, which is what the teacher reads.
2. A small structured extraction over the transcript, which updates the spec.

The extraction runs after the reply rather than as a tool call during it
because a tool call and prose are, in practice, alternatives: a turn that
calls the tool tends not to also say anything, and the teacher would watch an
empty box while the model silently filled in a form. Streaming the words first
and reconciling the spec a beat later costs one cheap call and keeps the
conversation immediate.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Iterator, List, Optional

from django.conf import settings

from apps.accounts.models import User
from services.openai_service import _record_usage, get_openai_client

logger = logging.getLogger("[CHAT]")


def _model() -> str:
    return getattr(settings, "CHAT_MODEL", "gpt-4.1-mini")


# ── The spec ────────────────────────────────────────────────────────────
#
# Field names match `formSchema` in components/generator-form.tsx exactly, so
# the handoff is a copy rather than a translation. Anything the teacher has
# not settled stays null; `spec_is_ready` decides when there is enough to
# offer the generator button.

SPEC_FIELDS = (
    "board",
    "academicClass",
    "subject",
    "difficulty",
    "marks",
    "numberOfQuestions",
    "numberOfSets",
    "chapters",
    # Free-form structure the teacher described in their own words ("5 MCQs,
    # 3 short answers of 2 marks"). Its presence is what switches the paper
    # from the CBSE blueprint to General Instructions Mode, where
    # `services/paper_design.py` reads it and lays the paper out accordingly.
    "instructions",
)

# The four the pipeline genuinely cannot start without. Question counts,
# set counts and chapter lists all have workable defaults; a subject does not.
REQUIRED_FIELDS = ("board", "academicClass", "subject", "marks")

_SPEC_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "board": {
            "type": ["string", "null"],
            "description": "Examination board, e.g. CBSE.",
        },
        "academicClass": {
            "type": ["string", "null"],
            "description": "Class/grade as a bare number string, 1 to 10.",
        },
        "subject": {
            "type": ["string", "null"],
            "description": (
                "One of: Science, Mathematics, Social Science, English, "
                "Hindi, Telugu."
            ),
        },
        "difficulty": {
            "type": ["string", "null"],
            "enum": ["easy", "medium", "hard", None],
        },
        "marks": {
            "type": ["string", "null"],
            "description": "Total marks for the paper, as a number string.",
        },
        "numberOfQuestions": {
            "type": ["string", "null"],
            "description": "Question count if the teacher named one.",
        },
        "numberOfSets": {
            "type": ["string", "null"],
            "enum": ["1", "2", "3", None],
        },
        "chapters": {
            "type": ["array", "null"],
            "items": {"type": "string"},
            "description": "Chapter or topic names the teacher named.",
        },
        "instructions": {
            "type": ["string", "null"],
            "description": (
                "The paper's structure in the teacher's OWN WORDS, verbatim, "
                "if they described one — question counts, types, marks, "
                "sections, or a named template like 'same as our weekly "
                "test'. Null if they did not describe a structure and just "
                "want a standard board-pattern paper."
            ),
        },
        "isPaperRequest": {
            "type": "boolean",
            "description": (
                "True if the teacher is asking for a question paper to be "
                "made. False for any other conversation."
            ),
        },
    },
    "required": list(SPEC_FIELDS) + ["isPaperRequest"],
}

_SYSTEM_PROMPT = """\
You are the assistant in AOS, a CBSE question-paper tool used by school \
teachers in India. You are a general assistant first: answer whatever you are \
asked, help with whatever is put in front of you — explaining a concept, \
drafting a notice to parents, checking a marking scheme, planning a term, \
arithmetic, or plain conversation. Be genuinely useful on all of it.

One thing is special. When the teacher wants a question paper made, you \
switch into setting it up. You do NOT write the questions yourself — a \
separate generation engine does that, and it starts when the teacher presses \
Generate. Your job is to pin down what it needs:

  required   board, class, subject, total marks
  helpful    chapters or an uploaded PDF, difficulty, question count, and
             how many parallel sets (1-3)

If the teacher describes the paper's SHAPE themselves — "5 MCQs and 3 short \
answers", "same as last week's test", "two sections" — that is their template, \
not a board paper. Keep their words; do not talk them into a CBSE pattern they \
did not ask for, and do not add Bloom's-taxonomy targets to it.

While setting a paper up:
- Ask for ONE thing at a time. The interface renders your question as buttons \
the teacher can tap, so a single clear ask beats a paragraph of them.
- Never re-ask something already settled.
- Prefer a sensible CBSE default over an interrogation. A class 10 \
board-pattern paper is 80 marks — say so and let them correct you.
- When everything required is known, summarise the paper in two or three \
lines and tell them they can generate it.
- Supported: Science, Mathematics, Social Science, English, Hindi, Telugu, \
classes 1-10. Say plainly if you are asked for something outside that.

Always: be brief and plain. No preamble, no bullet-point walls, no emoji. If \
the teacher changes the subject away from the paper, follow them — the paper \
setup is still there when they come back.\
"""

_EXTRACTION_PROMPT = """\
Read the conversation and return the paper specification agreed so far.

Rules:
- Only record what the teacher actually stated or explicitly accepted. A \
value you proposed and they ignored is NOT agreed.
- Carry forward everything already in the current spec unless the teacher \
changed it.
- Use null for anything still unknown.
- academicClass and marks are bare number strings ("10", "80"), no words.
- instructions is the teacher's own description of the paper's structure, \
copied as they wrote it. Do not summarise, tidy or invent it.\
"""


def build_message_history(
    conversation_messages: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    """Prior turns as the chat API wants them, system prompt included."""
    history: List[Dict[str, str]] = [
        {"role": "system", "content": _SYSTEM_PROMPT}
    ]
    for message in conversation_messages:
        role = message.get("role")
        if role not in ("user", "assistant"):
            continue
        history.append({"role": role, "content": message.get("content") or ""})
    return history


def normalize_spec(raw: Any, previous: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Coerce a model-returned spec into the shape the generator form expects.

    Merges over `previous` rather than replacing it: extraction sees the whole
    transcript and should be cumulative, but a model that omits a field it
    already agreed to must not silently erase it.
    """
    spec: Dict[str, Any] = dict(previous or {})
    if not isinstance(raw, dict):
        return spec

    for field in SPEC_FIELDS:
        if field not in raw:
            continue
        value = raw.get(field)
        if value is None:
            continue

        if field == "chapters":
            if isinstance(value, list):
                chapters = [str(v).strip() for v in value if str(v).strip()]
                if chapters:
                    spec[field] = chapters
            continue

        text = str(value).strip()
        if text:
            spec[field] = text

    return spec


def spec_is_ready(spec: Optional[Dict[str, Any]]) -> bool:
    """Whether the generator has enough to run."""
    if not spec:
        return False
    return all(str(spec.get(field) or "").strip() for field in REQUIRED_FIELDS)


# ── Interactive follow-ups ──────────────────────────────────────────────
#
# The next question is derived here, not asked of the model. Every field the
# generator takes has a closed, known set of answers — six subjects, ten
# classes, three set counts — so a model has nothing to add except the chance
# of offering an eleventh class or misspelling "Social Science". The
# assistant's prose asks the question conversationally; this decides what the
# interface puts under it, and the two always agree because both are driven
# by the same spec.

_SUBJECTS = ["Science", "Mathematics", "Social Science", "English", "Hindi", "Telugu"]

_FOLLOW_UPS: List[Dict[str, Any]] = [
    {
        "field": "subject",
        "kind": "choice",
        "label": "Which subject?",
        "options": [{"value": s, "label": s} for s in _SUBJECTS],
    },
    {
        "field": "academicClass",
        "kind": "choice",
        "label": "Which class?",
        "options": [
            {"value": str(n), "label": f"Class {n}"} for n in range(1, 11)
        ],
    },
    {
        "field": "board",
        "kind": "choice",
        "label": "Which board pattern?",
        "options": [{"value": "CBSE", "label": "CBSE"}],
    },
    {
        "field": "marks",
        "kind": "choice",
        "label": "Total marks?",
        "options": [
            {"value": "80", "label": "80", "hint": "Board pattern"},
            {"value": "40", "label": "40", "hint": "Half paper"},
            {"value": "20", "label": "20", "hint": "Unit test"},
        ],
        "allowOther": True,
    },
    # Not optional, whatever it looks like. The generation endpoint rejects a
    # request with no `pdfSourceIds` and no `hsatSourceIds`
    # (apps/generation/serializers.py), so a paper with nothing to read from
    # cannot be made at all — offering to skip this would produce a Generate
    # button that fails on press.
    {
        "field": "sources",
        "kind": "files",
        "label": "Attach the chapters to draw from",
        "hint": "A textbook PDF. Questions are written from what you attach.",
    },
    {
        "field": "difficulty",
        "kind": "choice",
        "label": "How hard should it be?",
        "options": [
            {"value": "easy", "label": "Easy"},
            {"value": "medium", "label": "Medium"},
            {"value": "hard", "label": "Hard"},
        ],
        "optional": True,
    },
    {
        "field": "numberOfSets",
        "kind": "choice",
        "label": "How many parallel sets?",
        "options": [
            {"value": "1", "label": "One", "hint": "Set A"},
            {"value": "2", "label": "Two", "hint": "Sets A & B"},
            {"value": "3", "label": "Three", "hint": "Sets A, B & C"},
        ],
        "optional": True,
    },
]


def collect_source_ids(messages: Iterable[Any]) -> List[str]:
    """Every document the teacher attached over the whole session.

    Sources accumulate across turns rather than belonging to the message that
    carried them: a teacher who attaches chapter 3 and then, four turns later,
    chapter 4 means the paper to draw on both.
    """
    seen: List[str] = []
    for message in messages:
        for attachment in getattr(message, "attachments", None) or []:
            source_id = str((attachment or {}).get("id") or "").strip()
            if source_id and source_id not in seen:
                seen.append(source_id)
    return seen


def next_prompt(
    spec: Optional[Dict[str, Any]], source_count: int = 0
) -> Optional[Dict[str, Any]]:
    """The next thing to ask for, as a widget the interface can render.

    Fields are asked for in a fixed order, so two teachers setting up the same
    paper are asked the same questions in the same sequence. Returns None once
    nothing is left to ask, which is what stops the interface nagging.
    """
    spec = spec or {}

    def filled(field: str) -> bool:
        # Sources live on the messages, not the spec — the teacher answers
        # this one by attaching a file rather than saying a word.
        if field == "sources":
            return source_count > 0
        value = spec.get(field)
        if isinstance(value, list):
            return len(value) > 0
        return bool(str(value or "").strip())

    for prompt in _FOLLOW_UPS:
        if not filled(prompt["field"]):
            return dict(prompt)
    return None


def can_generate(spec: Optional[Dict[str, Any]], source_count: int = 0) -> bool:
    """Whether pressing Generate would actually succeed.

    Deliberately stricter than `spec_is_ready`: the blueprint only needs the
    four required fields, but the pipeline also needs something to read.
    """
    return spec_is_ready(spec) and source_count > 0


@dataclass
class Extraction:
    """What the transcript says about the paper, after one turn."""

    spec: Dict[str, Any]
    # Whether this conversation is about making a paper at all. Needed
    # separately from the spec because "make me a paper" fills no fields yet
    # is unmistakably a paper request — without it the first turn of every
    # session would get no follow-up widget.
    is_paper: bool = False


def extract_spec(
    messages: List[Dict[str, str]],
    previous: Optional[Dict[str, Any]] = None,
    user: Optional[User] = None,
) -> Extraction:
    """Re-derive the paper spec from the transcript.

    Failure here is not failure of the turn: the teacher has already read the
    reply, and a spec that is one turn stale is corrected on the next one. So
    this logs and returns what it had rather than raising into the stream.
    """
    transcript = [m for m in messages if m.get("role") in ("user", "assistant")]

    try:
        client = get_openai_client()
        completion = client.chat.completions.create(
            model=_model(),
            messages=[
                {"role": "system", "content": _EXTRACTION_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Current spec:\n{json.dumps(previous or {}, ensure_ascii=False)}"
                        "\n\nConversation:\n"
                        + "\n".join(
                            f"{m['role']}: {m.get('content') or ''}" for m in transcript
                        )
                    ),
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "paper_spec",
                    "schema": _SPEC_SCHEMA,
                    "strict": False,
                },
            },
        )
    except Exception as exc:
        logger.warning("Spec extraction failed, keeping the previous spec: %s", exc)
        return Extraction(spec=dict(previous or {}), is_paper=bool(previous))

    _record_usage(user, "chat_spec", _model(), completion.usage)

    try:
        parsed = json.loads(completion.choices[0].message.content or "{}")
    except (json.JSONDecodeError, TypeError):
        logger.warning("Spec extraction returned unparseable JSON")
        return Extraction(spec=dict(previous or {}), is_paper=bool(previous))

    spec = normalize_spec(parsed, previous)
    # A spec with anything in it is a paper session whatever the model says
    # about intent: the fields only get filled from things the teacher
    # actually asked for.
    is_paper = bool(parsed.get("isPaperRequest")) or bool(spec)
    return Extraction(spec=spec, is_paper=is_paper)


def stream_reply(
    messages: List[Dict[str, str]],
    user: Optional[User] = None,
) -> Iterator[str]:
    """Yield the assistant's reply token by token."""
    client = get_openai_client()
    stream = client.chat.completions.create(
        model=_model(),
        messages=messages,
        stream=True,
        stream_options={"include_usage": True},
    )

    for chunk in stream:
        if getattr(chunk, "usage", None):
            _record_usage(user, "chat_reply", _model(), chunk.usage)
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        text = getattr(delta, "content", None)
        if text:
            yield text


def suggest_title(first_user_message: str) -> str:
    """A short conversation title, derived locally.

    Deliberately not a model call: it would double the cost of the first turn
    to name something the teacher can rename for free.
    """
    text = " ".join((first_user_message or "").split())
    if not text:
        return "New chat"
    return text[:57] + "…" if len(text) > 58 else text
