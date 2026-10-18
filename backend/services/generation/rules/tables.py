"""Tables in model output: one convention, from the prompt to the document.

A table travels as pipe rows, one row per line::

    | Class interval | Frequency |
    | --- | --- |
    | 0–10 | 5 |

The first row is a header only when a ``| --- |`` separator row follows it, as in
Markdown. The editor turns a run of such lines into a real table (``tableHeader``
and ``tableCell`` nodes, maths in the cells typeset), and the Word and PDF exports
print that table. Anything the model writes that is *meant* to be a table but is
not in this shape — rows without the outer pipes, a separator in the wrong place,
rows of different lengths, a fenced block — is bent into it here, so the editor
only ever has one shape to read.

What this module does not do is guess that prose is a table. A run becomes a table
only when it is unmistakably one: every row has the outer pipes, or a separator
row says so.

Pure string work: no Django, no I/O.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

#: Prompt text for a question writer. A raw string: the backslashes are content.
QUESTION_TABLE_RULES = r"""
Tables: whenever a question gives data in rows and columns — a frequency distribution, class intervals with frequencies, a cumulative-frequency table, a table of values, an observation table — print it as a table inside `question`, never as a sentence and never with the rows run together on one line.
Write the table as pipe rows, one row per line, the header row first and then a separator row of --- cells:
| Class interval | Frequency |
| --- | --- |
| 0–10 | 5 |
| 10–20 | 8 |
Keep the same number of cells in every row, put units in the header, and write any maths in a cell as \( ... \). Statistics questions (mean, median, mode, ogive, cumulative frequency) always give their data this way, with a column for the class interval and a column for the frequency.
"""

#: The same convention, for the working shown in an answer.
ANSWER_TABLE_RULES = r"""
Tables: when the working needs a table — cumulative frequencies, class marks, an fx column, a table of values — write it as pipe rows, one row per line, the header row first and then a separator row of --- cells:
| Class interval | Frequency | Cumulative frequency |
| --- | --- | --- |
| 0–10 | 5 | 5 |
Keep the same number of cells in every row and write maths in a cell as \( ... \). The question's own tables arrive in this same form; refer to them, do not copy them out again.
"""

_SEPARATOR_CELL = re.compile(r"^:?-{2,}:?$")
_FENCE = re.compile(r"^\s*```[\w-]*\s*$")
_BREAK_TAG = re.compile(r"<br\s*/?>", re.IGNORECASE)
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_DIGIT = re.compile(r"\d")


def split_cells(line: str) -> List[str]:
    """The cells of one pipe row.

    Pipes inside ``\\( … \\)`` / ``\\[ … \\]`` (``\\( |x| \\)``, a ``{c|c}`` column
    spec) and escaped ones (``\\|``) belong to the cell. An unclosed math span is
    not allowed to swallow the rest of the row: the row is split again without
    that protection.
    """
    for protect in (True, False):
        cells = _split(line, protect)
        if cells is not None:
            return cells
    return [line.strip()]


def _split(line: str, protect_math: bool) -> Optional[List[str]]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]

    cells: List[str] = []
    current: List[str] = []
    closing: Optional[str] = None
    i = 0
    while i < len(s):
        pair = s[i : i + 2]
        if protect_math and closing is None and pair in ("\\(", "\\["):
            closing = "\\)" if pair == "\\(" else "\\]"
            current.append(pair)
            i += 2
        elif closing is not None and pair == closing:
            closing = None
            current.append(pair)
            i += 2
        elif pair == "\\|":
            current.append(pair)
            i += 2
        elif s[i] == "|" and closing is None:
            cells.append("".join(current).strip())
            current = []
            i += 1
        else:
            current.append(s[i])
            i += 1
    if closing is not None:
        return None  # an unclosed span: retry without protection
    cells.append("".join(current).strip())
    return cells


def _has_unprotected_pipe(line: str) -> bool:
    return len(split_cells(line)) > 1 or (
        line.strip().startswith("|") and line.strip().endswith("|") and len(line.strip()) > 1
    )


def is_separator_row(cells: List[str]) -> bool:
    return bool(cells) and all(_SEPARATOR_CELL.match(c) for c in cells)


def is_edge_piped(line: str) -> bool:
    s = line.strip()
    return len(s) > 1 and s.startswith("|") and s.endswith("|") and not s.endswith("\\|")


def escape_cell(cell: str) -> str:
    """A cell's text with any bare pipe escaped, so it cannot split the row.

    Pipes inside maths spans are left alone; ``split_cells`` already protects them.
    """
    parts: List[str] = []
    cursor = 0
    for span in re.finditer(r"\\\(.+?\\\)|\\\[.+?\\\]", cell, re.DOTALL):
        parts.append(cell[cursor : span.start()].replace("\\|", "|").replace("|", "\\|"))
        parts.append(span.group(0))
        cursor = span.end()
    parts.append(cell[cursor:].replace("\\|", "|").replace("|", "\\|"))
    return "".join(parts)


def clean_cell(cell: str) -> str:
    """One cell's text: line breaks, stray bold markers and runs of space removed."""
    cell = _BREAK_TAG.sub(" ", cell)
    cell = _BOLD.sub(r"\1", cell)
    # A display equation would split the row where the editor looks for them.
    cell = cell.replace("\\[", "\\(").replace("\\]", "\\)")
    return re.sub(r"\s+", " ", cell).strip()


def looks_like_header(first: List[str], rest: List[List[str]]) -> bool:
    """Is the first row a header, when nothing says so?

    Yes when it is all words (no digit in any cell) and the rows below carry
    numbers: ``Class interval | Frequency`` over ``0–10 | 5``. A row-wise table
    (``Frequency | 5 | 8``) leads with a label *and* data, so it has a digit and
    is left alone.
    """
    if not first or any(not c for c in first):
        return False
    if any(_DIGIT.search(c) for c in first):
        return False
    return any(_DIGIT.search(c) for row in rest for c in row)


_SOLE_EQUATION = re.compile(r"^\\\(.+\\\)$", re.DOTALL)


def is_numeric_like(cell: str) -> bool:
    """A cell that holds a figure: a short run with a digit in it (a frequency,
    a class interval) or nothing but one equation (``\\( \\frac{0+10}{2} \\)``,
    whose source is long however small it prints).

    These are centred (as are header cells) so a column of figures lines up
    under its heading. The editor's converter applies the same rule.
    """
    if _SOLE_EQUATION.match(cell) and cell.count("\\(") == 1:
        return True
    return len(cell) <= 18 and bool(_DIGIT.search(cell))


class ParsedTable:
    """Rows of cells plus whether the first row is a header."""

    def __init__(self, rows: List[List[str]], header: bool):
        width = max(len(r) for r in rows)
        self.rows = [r + [""] * (width - len(r)) for r in rows]
        self.header = header

    def render(self) -> List[str]:
        lines = [self._row(self.rows[0])]
        if self.header:
            lines.append(self._row(["---"] * len(self.rows[0])))
        lines.extend(self._row(r) for r in self.rows[1:])
        return lines

    @staticmethod
    def _row(cells: List[str]) -> str:
        return "| " + " | ".join(cells) + " |"


def parse_run(lines: List[str]) -> Optional[ParsedTable]:
    """A run of pipe-row lines as a table, or None when it is not unmistakably one.

    Two or more rows are needed. They must each have the outer pipes, or a
    separator row must be present (that is what says "table" for rows written
    without them, and what keeps a pair of shell pipelines or a sentence with a
    bar in it from becoming one).
    """
    candidates = [ln for ln in lines if ln.strip()]
    if len(candidates) < 2:
        return None

    parsed = [split_cells(ln) for ln in candidates]
    separator_at = next((i for i, cells in enumerate(parsed) if is_separator_row(cells)), None)
    if not (all(is_edge_piped(ln) for ln in candidates) or separator_at is not None):
        return None

    body = [[clean_cell(c) for c in cells] for i, cells in enumerate(parsed) if not is_separator_row(cells)]
    if len(body) < 1 or max(len(r) for r in body) < 1:
        return None
    if separator_at is None and max(len(r) for r in body) < 2 and len(body) < 2:
        return None

    header = separator_at == 1 or (
        separator_at is None and len(body) > 1 and looks_like_header(body[0], body[1:])
    )
    return ParsedTable(body, header)


def _collect(lines: List[str], start: int) -> Tuple[List[str], int]:
    """Consecutive pipe-row lines from ``start`` (single blank lines between
    rows are tolerated), and the index just past the run."""
    run: List[str] = []
    i = start
    while i < len(lines):
        line = lines[i]
        if line.strip() and _has_unprotected_pipe(line) and not _FENCE.match(line):
            run.append(line)
            i += 1
            continue
        if not line.strip() and run and i + 1 < len(lines) and lines[i + 1].strip() and _has_unprotected_pipe(lines[i + 1]):
            i += 1
            continue
        break
    return run, i


def normalize_tables(text: str) -> str:
    """Rewrite every table in ``text`` as canonical pipe rows.

    Text that is not a table is returned untouched, byte for byte.
    """
    if not text or "|" not in text:
        return text

    lines = text.split("\n")
    out: List[str] = []
    i = 0
    while i < len(lines):
        # A table the model fenced in ``` ``` is still a table: drop the fences.
        if _FENCE.match(lines[i]):
            run, end = _collect(lines, i + 1)
            table = parse_run(run)
            if table and end < len(lines) and _FENCE.match(lines[end]):
                out.extend(table.render())
                i = end + 1
                continue

        run, end = _collect(lines, i)
        table = parse_run(run) if run else None
        if table is not None:
            out.extend(table.render())
            i = end
        else:
            out.append(lines[i])
            i += 1
    return "\n".join(out)
