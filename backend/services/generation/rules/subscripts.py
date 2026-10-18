"""Indexed variables as maths: ``x1`` → ``\\(x_{1}\\)``.

A model that is not told otherwise writes the coordinates of a point as
``(x1, y1)``: the index is an ordinary digit, on the baseline, in the paper's
text font. The editor typesets only what sits inside ``\\( … \\)``, so the
reader sees ``x1`` where a textbook prints x₁.

The prompt asks the model for the LaTeX (``MATH_PROMPT_RULES`` in
``typesetting.py``). This module is the backstop for when it does not, and it is
deliberately *not* "any letter followed by a digit". Those tokens are everywhere
and mostly are not indices: ``A1`` is a spreadsheet cell, ``O2`` is oxygen,
``6x2`` is six x-squared, ``20 m2`` is an area, ``h1`` is an HTML heading,
``x86`` is a processor. A wrong subscript is worse than a missing one, so a
token is converted only on evidence that it is an index:

* **explicit**   ``x_1``, ``x_{12}``, ``a_n`` — the writer already said so.
* **tuple**      ``(x1, y1)`` — a bracketed list made only of indexed variables.
* **run**        ``x1x2``, ``P1P2`` — indexed variables written side by side.
* **coefficient** ``a1x`` as in ``a1x + b1y + c1 = 0`` — an indexed letter
                 followed by the variable it multiplies; the variable joins
                 the maths so the pair does not print in two different fonts.
* **family**     one letter that appears with two different indices, the
                 smallest of them 0 or 1: ``x1`` and ``x2``, ``a0``…``a2``.
                 ``x3 + x2 + x`` is a polynomial, not a family — exponents do
                 not start at 1.
* **lone**       a single lowercase ``x1`` / ``a0``, Mathematics only.

Once a letter qualifies, every indexed use of it in the text converts, so one
line never mixes ``x₁`` with a plain ``x1``.

Which of those rules may run depends on the subject (``policy_for``): Maths
trusts all of them; Science trusts them for lowercase letters, and for
uppercase ones unless the text is about chemistry (``O2`` and ``O3`` are
oxygen and ozone); Computer Science, ICT, languages and Social Science convert
only what is written explicitly; an unknown subject does the lowercase rules.

Pure string work, mirrored in ``frontend/features/editor/subscripts.ts``. Both
are tested against ``tests/subscript_cases.json`` so they cannot drift.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

# ── Policy: how much to trust "letter + digit" for a subject ─────────────


@dataclass(frozen=True)
class Policy:
    name: str
    #: May a lowercase letter be an index base (x1)?
    lower: bool
    #: May an uppercase one (P1)?
    upper: bool
    #: Is a lone ``x1`` / ``a0`` enough, with no sibling for evidence?
    lone: bool
    #: Skip uppercase element letters (O2, N2, H2) when the text is chemistry.
    chemistry_guard: bool


MATHS = Policy("maths", lower=True, upper=True, lone=True, chemistry_guard=False)
SCIENCE = Policy("science", lower=True, upper=True, lone=False, chemistry_guard=True)
DEFAULT = Policy("default", lower=True, upper=False, lone=False, chemistry_guard=False)
OFF = Policy("off", lower=False, upper=False, lone=False, chemistry_guard=False)

#: First words of subjects where ``A1``, ``h1``, ``x86`` mean something else.
_OFF_FIRST_WORDS = frozenset(
    {
        "english", "hindi", "telugu", "sanskrit", "urdu", "tamil", "kannada",
        "malayalam", "marathi", "bengali", "punjabi", "gujarati", "odia",
        "assamese", "french", "german", "spanish", "social", "history",
        "geography", "civics", "economics", "political", "computer", "computers",
        "ict", "informatics", "information", "python", "coding", "programming",
    }
)
_SCIENCE_WORDS = ("science", "physics", "chemistry", "biology")


def policy_for(subject: Optional[str]) -> Policy:
    """The trust a subject earns. ``None`` / empty is the cautious default."""
    lower = str(subject or "").strip().lower()
    if not lower:
        return DEFAULT
    if "math" in lower or "statistic" in lower:
        return MATHS
    words = lower.replace("&", " ").split()
    if words and words[0] in _OFF_FIRST_WORDS or "social" in lower:
        return OFF
    if any(word in lower for word in _SCIENCE_WORDS):
        return SCIENCE
    return DEFAULT


# ── Recognising indexed variables ────────────────────────────────────────

_MATH_SPAN = re.compile(r"\\\(.*?\\\)|\\\[.*?\\\]", re.DOTALL)

#: An index written bare: 0, or 1–99 without a leading zero.
_DIGITS = r"(?:0|[1-9]\d?)"
#: What may not touch a token on its left: it would be part of a longer word,
#: a LaTeX command, a file name, an e-mail, an HTML tag, a hex colour or a
#: price. A number may: ``3x1`` is three times x₁.
_LEFT = r"(?<![A-Za-z_\\.@#<$])"
#: Nor on the right: ``x1y`` is a word; ``x1.txt`` is a file; ``x1.5`` is a decimal.
_RIGHT = r"(?![A-Za-z0-9_]|\.[A-Za-z0-9])"

_BARE = rf"[A-Za-z]{_DIGITS}"
_EXPLICIT = rf"[A-Za-z]_(?:{_DIGITS}|\{{[A-Za-z0-9]{{1,3}}\}}|[ijkn])"
_ANY = rf"(?:{_EXPLICIT}|{_BARE})"

_PATTERN = re.compile(
    # (x1, y1) — two to four indexed variables in brackets.
    rf"(?P<tuple>\(\s*{_ANY}(?:\s*,\s*{_ANY}){{1,3}}\s*\))"
    # x1x2, P1P2 — indexed variables side by side.
    rf"|(?P<run>{_LEFT}(?:{_BARE}){{2,3}}{_RIGHT})"
    # x_1, a_n — already written as a subscript, just not typeset.
    rf"|(?P<explicit>{_LEFT}{_EXPLICIT}{_RIGHT})"
    # a1x — an indexed coefficient and its variable.
    rf"|(?P<coef>{_LEFT}{_BARE}[xyz]{_RIGHT})"
    # x1
    rf"|(?P<bare>{_LEFT}{_BARE}{_RIGHT})"
)

_BARE_TOKEN = re.compile(rf"([A-Za-z])({_DIGITS})")
_EXPLICIT_TOKEN = re.compile(rf"([A-Za-z])_(\{{[A-Za-z0-9]{{1,3}}\}}|{_DIGITS}|[ijkn])")
#: Inside an existing math span: x_1, x_{12} — evidence only, never rewritten.
_SPAN_SUBSCRIPT = re.compile(rf"(?<![A-Za-z\\])([A-Za-z])_\{{?({_DIGITS})\}}?")

#: Single-letter chemical elements, the letters ``O2`` / ``N2`` / ``H2`` share
#: with physics' ``R``, ``V``, ``I`` and maths' ``P``.
_ELEMENT_LETTERS = frozenset("HBCNOFPSKVYIWU")
_CHEMISTRY = re.compile(
    r"\b(?:molecules?|atoms?|atomic|compounds?|elements?|react\w*|"
    r"oxide|oxygen|hydrogen|nitrogen|carbon|sulphur|sulfur|chlorine|acids?|"
    r"bases?|salts?|moles?|valen\w+|bonds?|bonding|ions?|ionic|chemical|periodic|"
    r"isotopes?|allotropes?|ozone|mixture|solution|catalyst|combustion|"
    r"electrolysis|alkali)\b|→|->",
    re.IGNORECASE,
)


def _latex(token: str) -> str:
    """``x1`` / ``x_1`` / ``x_{12}`` / ``a_n`` as ``x_{1}`` / ``x_{12}`` / ``a_{n}``."""
    explicit = _EXPLICIT_TOKEN.fullmatch(token)
    if explicit:
        sub = explicit.group(2).strip("{}")
        return f"{explicit.group(1)}_{{{sub}}}"
    bare = _BARE_TOKEN.fullmatch(token)
    if bare:
        return f"{bare.group(1)}_{{{bare.group(2)}}}"
    coefficient = re.fullmatch(rf"([A-Za-z])({_DIGITS})([xyz])", token)
    if coefficient:
        return f"{coefficient.group(1)}_{{{coefficient.group(2)}}}{coefficient.group(3)}"
    return token


def _tuple_latex(group: str) -> str:
    inner = group[1:-1]
    members = [_latex(member.strip()) for member in inner.split(",")]
    return "\\(" + "(" + ", ".join(members) + ")" + "\\)"


def _letter_allowed(letter: str, policy: Policy, chemistry: bool) -> bool:
    if letter.islower():
        return policy.lower
    if not policy.upper:
        return False
    return not (policy.chemistry_guard and chemistry and letter in _ELEMENT_LETTERS)


def typeset_indices(text: str, *, subject: Optional[str] = None) -> str:
    """Rewrite indexed variables outside existing maths as ``\\( x_{1} \\)``.

    Existing ``\\( … \\)`` / ``\\[ … \\]`` spans are never touched, so the pass
    is idempotent and safe to run on text a model already typeset.
    """
    if not text or not re.search(r"[A-Za-z](?:_|\d)", text):
        return text

    policy = policy_for(subject)
    spans = list(_MATH_SPAN.finditer(text))
    outside: List[str] = []
    cursor = 0
    for span in spans:
        outside.append(text[cursor : span.start()])
        cursor = span.end()
    outside.append(text[cursor:])
    plain = "\n".join(outside)

    # What each letter has been seen indexed with, bare or already typeset.
    seen: Dict[str, Set[int]] = {}
    for match in _SPAN_SUBSCRIPT.finditer("\n".join(m.group(0) for m in spans)):
        seen.setdefault(match.group(1), set()).add(int(match.group(2)))

    chemistry = bool(_CHEMISTRY.search(text))
    #: Letters proven an index by their shape: a tuple, a run, an explicit x_1.
    structural: Set[str] = set()
    #: Letters that may be, by company (a family) or by being alone (Maths).
    soft: Set[str] = set()
    bare: List[str] = []

    for match in _PATTERN.finditer(plain):
        kind, token = match.lastgroup, match.group(0)
        if kind == "tuple":
            members = [m.strip() for m in token[1:-1].split(",")]
            if all("_" in m or _letter_allowed(m[0], policy, chemistry) for m in members):
                structural.update(m[0] for m in members)
        elif kind == "run":
            pieces = re.findall(_BARE, token)
            if all(_letter_allowed(p[0], policy, chemistry) for p in pieces):
                structural.update(p[0] for p in pieces)
        elif kind == "explicit":
            explicit = _EXPLICIT_TOKEN.fullmatch(token)
            sub = explicit.group(2).strip("{}")
            if sub.isdigit():
                seen.setdefault(explicit.group(1), set()).add(int(sub))
            structural.add(explicit.group(1))
        elif _letter_allowed(token[0], policy, chemistry):
            index = re.match(_DIGITS, token[1:]).group(0)
            seen.setdefault(token[0], set()).add(int(index))
            bare.append(token)

    for token in bare:
        letter, index = token[0], int(re.match(_DIGITS, token[1:]).group(0))
        indices = seen[letter]
        if len(indices) >= 2 and min(indices) <= 1:
            soft.add(letter)
        elif policy.lone and letter.islower() and index in (0, 1):
            soft.add(letter)

    # No guard for "6x2" being six x-squared: a family needs an index of 0 or 1
    # and no one writes x1 as an exponent, so a polynomial never gets this far.
    qualifying = structural | soft

    def rewrite(segment: str) -> str:
        def sub(match: "re.Match[str]") -> str:
            kind = match.lastgroup
            token = match.group(0)
            if kind == "tuple":
                members = [m.strip() for m in token[1:-1].split(",")]
                ok = all(
                    "_" in m or m[0] in qualifying for m in members
                )
                return _tuple_latex(token) if ok else token
            if kind == "run":
                pieces = re.findall(_BARE, token)
                if all(p[0] in qualifying for p in pieces):
                    return "\\(" + "".join(_latex(p) for p in pieces) + "\\)"
                return token
            if kind == "explicit":
                return f"\\({_latex(token)}\\)"
            return f"\\({_latex(token)}\\)" if token[0] in qualifying else token

        return _PATTERN.sub(sub, segment)

    parts: List[str] = []
    cursor = 0
    for span in spans:
        parts.append(rewrite(text[cursor : span.start()]))
        parts.append(span.group(0))
        cursor = span.end()
    parts.append(rewrite(text[cursor:]))
    return "".join(parts)
