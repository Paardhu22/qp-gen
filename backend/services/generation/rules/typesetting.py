"""Maths in model output: one contract, from the prompt to the saved document.

The editor parses exactly two delimiters: ``\\( … \\)`` for inline maths and
``\\[ … \\]`` for display maths. Anything the model writes that is meant to be
typeset has to arrive in the document as ``inlineMath`` / ``mathBlock`` nodes
carrying the LaTeX in their ``latex`` attribute, or the reader sees raw source.

This module is the answer-script side of that contract (the question pipeline
has its own prompt directive and a frontend converter). It does four things:

* ``node_text``          a TipTap node as text, maths kept as ``\\( … \\)``
* ``normalize_math_text`` model text → the contract: repairs JSON-eaten escapes,
                         ``$…$`` / ``$$…$$``, bare ``\\begin{…}`` environments
                         and bare LaTeX tokens
* ``repair_json_backslashes`` make a reply with LaTeX in it parse as JSON
* ``text_to_blocks``     contract text → TipTap paragraphs / ``mathBlock``

Everything here is pure string work: no Django, no I/O.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

from services.generation.rules.content_filters import wrap_bare_latex_tokens
from services.generation.rules.subscripts import typeset_indices
from services.generation.rules.tables import (
    ANSWER_TABLE_RULES,
    ParsedTable,
    escape_cell,
    is_edge_piped,
    is_numeric_like,
    normalize_tables,
    parse_run,
)

#: The one rule about indexed variables, for any prompt whose reply carries
#: maths. Raw: the backslashes and braces are the content.
INDEX_PROMPT_RULE = r"""A variable with an index is maths too, written with a LaTeX subscript, never as plain text: \( x_{1} \), \( y_{2} \), \( P_{1} \), \( a_{n} \), a point \( (x_{1}, y_{1}) \), a product \( x_{1}x_{2} \). Do not write x1, x_1 or x₁ in the text. A digit that is not an index stays an ordinary digit: "Class 10", "Q1", "A4", "20 m", the cell A1 of a spreadsheet, the formulae H2O and CO2."""

#: The rules a prompt must carry for the model to write maths this module can
#: place. A raw string on purpose: the backslashes are the content.
MATH_PROMPT_RULES = r"""
Mathematics and formulas (apply to every subject):
- Write every mathematical expression and physics formula in LaTeX. Inline: \( ... \). A standalone equation on its own line: \[ ... \].
- Never write maths as $...$ or $$...$$, as plain text (x^2, sqrt(3), 1/2, 3x2), or with unicode shortcuts for roots and fractions (√, ½). Put units and plain words outside the maths: "Area = \( 25\pi \) cm".
- Use the real LaTeX commands: fractions \frac{a}{b}, powers x^{2}, roots \sqrt{x} and \sqrt[3]{x}, trigonometry \sin\theta, Greek \alpha \beta \pi, integrals \int_{a}^{b} f(x)\,dx, sums \sum_{i=1}^{n}, limits \lim_{x \to 0}, matrices \begin{pmatrix} a & b \\ c & d \end{pmatrix}, degrees ^\circ, and \times \div \le \ge \ne \approx.
- @@INDEX_RULE@@
- Mix words and maths freely in one line: "Substituting \( x = 2 \), we get \( y = 7 \)."
- Show working step by step, one step per line, each step's equation in LaTeX.
- The questions below carry their maths in this same notation: copy it exactly. If the source material has maths as plain or garbled text, rewrite it in LaTeX.
- Your reply is JSON, so every backslash inside a JSON string must be doubled. Write "\\frac{1}{2}" and "\\( x^{2} \\)" in the JSON; a single backslash corrupts the maths.
"""
MATH_PROMPT_RULES = MATH_PROMPT_RULES.replace("@@INDEX_RULE@@", INDEX_PROMPT_RULE)


#: Everything an answer-writing prompt must say about maths *and* tables.
ANSWER_FORMAT_RULES = MATH_PROMPT_RULES + ANSWER_TABLE_RULES

# ── Reading: a TipTap node as text ──────────────────────────────────────

_INLINE_TYPES = {"text", "inlineMath", "hardBreak"}


def node_text(node: Dict[str, Any]) -> str:
    """Text of a TipTap node, with equations kept as ``\\( … \\)`` / ``\\[ … \\]``.

    Inline pieces (text, inline maths, line breaks) join with nothing between
    them — a bold run in the middle of a word stays one word — and blocks join
    with a space.
    """
    kind = node.get("type")
    if kind == "inlineMath":
        latex = str((node.get("attrs") or {}).get("latex") or "").strip()
        return f"\\({latex}\\)" if latex else ""
    if kind == "mathBlock":
        latex = str((node.get("attrs") or {}).get("latex") or "").strip()
        return f"\\[{latex}\\]" if latex else ""
    if kind == "hardBreak":
        return " "
    if kind == "table":
        return _table_text(node)
    if node.get("text"):
        return str(node["text"])

    out: List[str] = []
    previous_inline = False
    for child in node.get("content") or []:
        if not isinstance(child, dict):
            continue
        piece = node_text(child)
        inline = child.get("type") in _INLINE_TYPES
        if out and not (inline and previous_inline):
            out.append(" ")
        out.append(piece)
        previous_inline = inline
    return "".join(out)


def _table_text(node: Dict[str, Any]) -> str:
    """A table node as pipe rows, one per line, so the model can read the rows
    and columns (joined as plain text they are a run of unrelated numbers)."""
    rows: List[List[str]] = []
    header = False
    for index, row in enumerate(node.get("content") or []):
        cells = [
            escape_cell(re.sub(r"\s+", " ", node_text(cell)).strip())
            for cell in row.get("content") or []
        ]
        if not cells:
            continue
        rows.append(cells)
        if index == 0:
            header = all(c.get("type") == "tableHeader" for c in row.get("content") or [])
    if not rows:
        return ""
    return "\n" + "\n".join(ParsedTable(rows, header).render()) + "\n"


# ── Repair: a JSON reply that carries LaTeX ─────────────────────────────

#: Scans left to right so a legal pair such as ``\\`` or ``\"`` is consumed
#: whole; whatever backslash is left over starts an illegal escape (``\(``
#: ``\[`` ``\sqrt`` ``\pi``). ``\u`` is only legal with four hex digits, so
#: ``\underline`` / ``\upsilon`` are caught too.
_JSON_BACKSLASH = re.compile(r'\\(["\\/bfnrt]|u[0-9a-fA-F]{4})|\\')


def repair_json_backslashes(payload: str) -> str:
    """Double every backslash JSON would reject, so a reply that wrote
    ``\\(`` with one backslash inside a string still parses."""
    return _JSON_BACKSLASH.sub(
        lambda m: m.group(0) if m.group(1) else "\\\\", payload
    )


# A LaTeX command that begins with a letter JSON also uses as an escape comes
# out of a *valid* reply as a control character: ``\frac`` → form feed + "rac",
# ``\beta`` → backspace + "eta", ``\theta`` → tab + "heta", ``\neq`` → newline
# + "eq", ``\rho`` → carriage return + "ho". The two below are never legitimate
# text; the rest are restored inside maths, or when a known command follows.
_MATH_SPAN = re.compile(r"\\\(.+?\\\)|\\\[.+?\\\]", re.DOTALL)
_EATEN_STEMS = re.compile(
    r"\t(?=imes|heta|ext\{|au\b|herefore|riangle|ilde|extbf)"
    r"|\r(?=ho\b|ightarrow|ight\)|angle)"
    r"|\n(?=eq\b|abla|otin|u\b|ewline)"
)
_EATEN_TO_ESCAPE = {"\t": "\\t", "\r": "\\r", "\n": "\\n"}


def restore_eaten_escapes(text: str) -> str:
    """Put back the backslashes a JSON parse turned into control characters."""
    if not text or not re.search(r"[\x08\x0c\t\r\n]", text):
        return text
    text = text.replace("\x0c", "\\f").replace("\x08", "\\b")
    text = _EATEN_STEMS.sub(lambda m: _EATEN_TO_ESCAPE[m.group(0)], text)

    def _inside(span: "re.Match[str]") -> str:
        # A tab or carriage return inside maths is never intended.
        return span.group(0).replace("\t", "\\t").replace("\r", "\\r")

    return _MATH_SPAN.sub(_inside, text)


def restore_eaten_escapes_deep(value: Any) -> Any:
    """``restore_eaten_escapes`` over every string in a parsed JSON value.

    It has to run on the whole object before anything strips a string: a bare
    ``\\frac{1}{2}`` option parses to a form feed + ``rac{1}{2}``, and
    ``str.strip`` treats a form feed as whitespace, so the command is gone for
    good by the time a per-field step sees it.
    """
    if isinstance(value, str):
        return restore_eaten_escapes(value)
    if isinstance(value, list):
        return [restore_eaten_escapes_deep(item) for item in value]
    if isinstance(value, dict):
        return {key: restore_eaten_escapes_deep(item) for key, item in value.items()}
    return value


# ── Normalising: model text → the delimiter contract ────────────────────

_DOLLAR_DISPLAY = re.compile(r"(?<!\\)\$\$(.+?)(?<!\\)\$\$", re.DOTALL)
# Pandoc's rule keeps currency out: the opening $ is followed by non-space,
# the closing $ is preceded by non-space and is not followed by a digit, so
# "costs $5 and $10" is left alone and "$x^2$" is maths.
_DOLLAR_INLINE = re.compile(r"(?<![\\$])\$(?![\s$])([^$\n]+?)(?<![\s\\])\$(?![\d$])")
_ENVIRONMENT = re.compile(r"\\begin\{([A-Za-z]+\*?)\}.+?\\end\{\1\}", re.DOTALL)


def _outside_math(text: str, fn: Callable[[str], str]) -> str:
    """Apply ``fn`` to the stretches of ``text`` that are not already maths."""
    parts: List[str] = []
    cursor = 0
    for span in _MATH_SPAN.finditer(text):
        parts.append(fn(text[cursor : span.start()]))
        parts.append(span.group(0))
        cursor = span.end()
    parts.append(fn(text[cursor:]))
    return "".join(parts)


def _wrap_environments(segment: str) -> str:
    # A matrix / aligned / cases block is one expression: wrapping it token by
    # token (what the bare-LaTeX rescue does) would cut it to pieces.
    return _ENVIRONMENT.sub(lambda m: f"\\[{m.group(0)}\\]", segment)


def normalize_math_text(text: str, *, subject: Optional[str] = None) -> str:
    """Bring model text onto the ``\\( … \\)`` / ``\\[ … \\]`` contract.

    ``subject`` says how far ``x1`` can be trusted to be an index (see
    ``subscripts.policy_for``); without it only the unambiguous cases convert.
    """
    if not text:
        return text
    text = restore_eaten_escapes(text)
    text = _DOLLAR_DISPLAY.sub(lambda m: f"\\[{m.group(1).strip()}\\]", text)
    text = _DOLLAR_INLINE.sub(lambda m: f"\\({m.group(1)}\\)", text)
    text = _outside_math(text, _wrap_environments)
    # An escaped dollar outside maths is just a dollar.
    text = _outside_math(text, lambda seg: seg.replace("\\$", "$"))
    # Rows in their final shape before the bare-LaTeX rescue tokenises them.
    text = normalize_tables(text)
    return typeset_indices(wrap_bare_latex_tokens(text), subject=subject)


# ── Writing: contract text → TipTap nodes ───────────────────────────────

_INLINE_MATH = re.compile(r"\\\((.+?)\\\)", re.DOTALL)
_DISPLAY_MATH = re.compile(r"\\\[(.+?)\\\]", re.DOTALL)


def _inline_nodes(line: str) -> List[Dict[str, Any]]:
    nodes: List[Dict[str, Any]] = []
    cursor = 0
    for m in _INLINE_MATH.finditer(line):
        if m.start() > cursor:
            nodes.append({"type": "text", "text": line[cursor : m.start()]})
        latex = m.group(1).strip()
        if latex:
            nodes.append({"type": "inlineMath", "attrs": {"latex": latex}})
        cursor = m.end()
    if cursor < len(line):
        nodes.append({"type": "text", "text": line[cursor:]})
    return nodes


def _cell_paragraph(text: str, *, centred: bool) -> Dict[str, Any]:
    # `\|` is how a literal bar travels in a cell; outside maths it is just "|".
    text = _outside_math(text, lambda seg: seg.replace("\\|", "|"))
    paragraph: Dict[str, Any] = {"type": "paragraph"}
    if centred:
        paragraph["attrs"] = {"textAlign": "center"}
    if text:
        paragraph["content"] = _inline_nodes(text)
    return paragraph


def _table_node(table: ParsedTable) -> Dict[str, Any]:
    """A table node: header cells where the table has a header row, maths in a
    cell as ``inlineMath`` nodes, and headers and figures centred."""
    rows = []
    for index, cells in enumerate(table.rows):
        header = table.header and index == 0
        rows.append(
            {
                "type": "tableRow",
                "content": [
                    {
                        "type": "tableHeader" if header else "tableCell",
                        "content": [
                            _cell_paragraph(cell, centred=header or is_numeric_like(cell))
                        ],
                    }
                    for cell in cells
                ],
            }
        )
    return {"type": "table", "content": rows}


def _paragraphs(segment: str) -> List[Dict[str, Any]]:
    # Inline maths that spans a line break is one expression, not two lines.
    segment = _INLINE_MATH.sub(lambda m: m.group(0).replace("\n", " "), segment)
    blocks: List[Dict[str, Any]] = []
    run: List[str] = []

    def flush() -> None:
        if not run:
            return
        table = parse_run(run)
        if table is not None:
            blocks.append(_table_node(table))
        else:  # a lone barred line is prose that happens to contain a bar
            blocks.extend({"type": "paragraph", "content": _inline_nodes(ln)} for ln in run)
        run.clear()

    for line in segment.split("\n"):
        line = line.strip()
        if not line:
            continue
        if is_edge_piped(line):
            run.append(line)
            continue
        flush()
        blocks.append({"type": "paragraph", "content": _inline_nodes(line)})
    flush()
    return blocks


def text_to_blocks(text: str) -> List[Dict[str, Any]]:
    """Answer text as editor blocks: a paragraph per line, inline maths as
    ``inlineMath`` nodes, display maths as ``mathBlock`` nodes."""
    text = str(text or "")
    blocks: List[Dict[str, Any]] = []
    cursor = 0
    for m in _DISPLAY_MATH.finditer(text):
        blocks.extend(_paragraphs(text[cursor : m.start()]))
        latex = m.group(1).strip()
        if latex:
            blocks.append(
                {"type": "mathBlock", "attrs": {"latex": latex, "displayMode": True}}
            )
        cursor = m.end()
    blocks.extend(_paragraphs(text[cursor:]))
    return blocks or [{"type": "paragraph"}]
