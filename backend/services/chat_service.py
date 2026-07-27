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
from typing import Any, Dict, Iterator, List, Optional

from django.conf import settings

from apps.accounts.models import User
from services.openai_service import _record_usage, get_openai_client

logger = logging.getLogger("[CHAT]")


def _model() -> str:
    return getattr(settings, "CHAT_MODEL", "gpt-4o-mini")


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
    },
    "required": list(SPEC_FIELDS),
}

_SYSTEM_PROMPT = """\
You are the assistant on the dashboard of AOS, a CBSE question-paper tool \
used by school teachers in India.

Your job is to understand what paper the teacher wants and to fill the gaps \
by asking. You do NOT write questions, passages or answer keys yourself — a \
separate generation engine does that, and the teacher launches it from the \
button that appears once the requirements are settled. If you are asked for \
actual questions, say that you will set the paper up and the generator will \
write it.

To launch a generation the engine needs: board, class, subject, and total \
marks. Useful but optional: difficulty, chapters or topics, how many \
questions, and how many parallel sets (1-3).

How to behave:
- Ask at most two questions per reply. A teacher in a hurry should be able to \
answer in one line.
- Never re-ask something already settled earlier in the conversation.
- Prefer sensible CBSE defaults over interrogation. A class 10 board-pattern \
paper is 80 marks; say so and let them correct you rather than asking.
- When everything required is known, summarise the paper in two or three \
lines and tell them they can generate it.
- Be brief and plain. No preamble, no bullet-point walls, no emoji.
- Subjects supported: Science, Mathematics, Social Science, English, Hindi, \
Telugu. Classes 1 to 10. If asked for something outside that, say so plainly.

You can also answer general questions about CBSE paper patterns, blueprints, \
marking schemes and how to use the app.\
"""

_EXTRACTION_PROMPT = """\
Read the conversation and return the paper specification agreed so far.

Rules:
- Only record what the teacher actually stated or explicitly accepted. A \
value you proposed and they ignored is NOT agreed.
- Carry forward everything already in the current spec unless the teacher \
changed it.
- Use null for anything still unknown.
- academicClass and marks are bare number strings ("10", "80"), no words.\
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


def extract_spec(
    messages: List[Dict[str, str]],
    previous: Optional[Dict[str, Any]] = None,
    user: Optional[User] = None,
) -> Dict[str, Any]:
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
        return dict(previous or {})

    _record_usage(user, "chat_spec", _model(), completion.usage)

    try:
        parsed = json.loads(completion.choices[0].message.content or "{}")
    except (json.JSONDecodeError, TypeError):
        logger.warning("Spec extraction returned unparseable JSON")
        return dict(previous or {})

    return normalize_spec(parsed, previous)


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
