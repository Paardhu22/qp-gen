"""Reading a model's `options` into plain option strings.

The schema asks for a list of strings, and most responses send one. Some do
not, and every shape seen so far is a reasonable reading of "four options":

    ["many", "much", "few", "several"]                      the contract
    [{"A": "many"}, {"B": "much"}, ...]                     one label each
    [{"label": "A", "text": "many"}, ...]                   label and text
    {"A": "many", "B": "much", ...}                         one mapping

Parsers used to run each entry through `str()`, so the second shape printed
on the paper as "A. {'A': 'many'}". This turns all of them into the first —
including that stringified form, which questions banked before the fix still
carry.

A label the model wrote into the text itself ("A. many", "(b) much") is also
dropped when it matches the option's position, because the renderer prints
its own label and the paper would otherwise read "A. A. many". An option that
merely starts with a letter — "a" as an answer to an article blank — has no
separator after it and is left alone.

Django-free.
"""

from __future__ import annotations

import ast
import re
from typing import Any, List

#: Keys that hold an option's text when it arrives as an object.
_TEXT_KEYS = ("text", "option", "value", "content", "answer")
#: Keys that only ever hold the label.
_LABEL_KEYS = ("label", "key", "id", "letter")

_LEADING_LABEL = re.compile(r"^\(?\s*([A-Ha-h]|[1-8])\s*[.):\]]\s+")


#: A Python dict literal, as `str()` printed one into a banked option.
_DICT_LITERAL = re.compile(r"^\{.*\}$", re.DOTALL)


def _entry_text(entry: Any) -> str:
    if isinstance(entry, str) and _DICT_LITERAL.match(entry.strip()):
        try:
            parsed = ast.literal_eval(entry.strip())
        except (ValueError, SyntaxError):
            parsed = None
        if isinstance(parsed, dict):
            entry = parsed
    if isinstance(entry, dict):
        for key in _TEXT_KEYS:
            if key in entry and str(entry[key] or "").strip():
                return str(entry[key]).strip()
        # {"A": "many"} — the label is the key, the text its value.
        values = [
            value
            for key, value in entry.items()
            if key not in _LABEL_KEYS and str(value or "").strip()
        ]
        return " ".join(str(value).strip() for value in values)
    return str(entry if entry is not None else "").strip()


def _strip_own_label(text: str, position: int) -> str:
    match = _LEADING_LABEL.match(text)
    if not match:
        return text
    label = match.group(1)
    expected = (chr(ord("a") + position), str(position + 1))
    if label.lower() in expected:
        return text[match.end():].strip() or text
    return text


def normalize_options(raw: Any) -> List[str]:
    """Plain option strings, in order, from whatever shape the model sent."""
    if raw is None:
        return []
    if isinstance(raw, dict):
        if any(key in raw for key in _TEXT_KEYS):
            # One option object where a list was expected.
            entries: List[Any] = [raw]
        else:
            # A label → text mapping, ordered by its labels.
            entries = [value for _, value in sorted(raw.items(), key=lambda kv: str(kv[0]))]
    elif isinstance(raw, (list, tuple)):
        entries = list(raw)
    else:
        entries = [raw]

    options: List[str] = []
    for entry in entries:
        text = _entry_text(entry)
        if text:
            options.append(_strip_own_label(text, len(options)))
    return options
