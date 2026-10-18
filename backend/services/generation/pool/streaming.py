"""Incremental JSON object extraction for streamed LLM responses.

Model 1 returns a top-level JSON *array* of question objects. That choice is
deliberate: `response_format={"type": "json_object"}` forces a single wrapping
object, which only closes on the final token — so nothing could be streamed to
the editor until the whole 80-question batch finished. With a bare array, each
question object closes as it is written and can be pushed to the client
immediately.

The extractor ignores everything before the first `{`, so a stray ```json
fence or a sentence of preamble is harmless.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from services.generation.rules.typesetting import repair_json_backslashes


def _loads_object(raw: str) -> Optional[Dict[str, Any]]:
    """One question object from JSON text, tolerating LaTeX's backslashes.

    A model that writes ``\\( x_{1} \\)`` with a single backslash produces an
    illegal JSON escape, and the whole question used to be dropped for it.
    Doubling the backslashes JSON rejects recovers it; only ``None`` means the
    object really is malformed.
    """
    for candidate in (raw, repair_json_backslashes(raw)):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        return parsed if isinstance(parsed, dict) else None
    return None


class JsonObjectStreamExtractor:
    """Emits complete JSON objects from a token stream.

    `json.loads` runs only once brace depth returns to zero, so partial buffers
    are never parsed. String state is tracked so a `{` inside a question stem
    (common in Maths: "the set {1, 2, 3}") does not corrupt the depth count.
    """

    def __init__(self) -> None:
        self._buffer: List[str] = []
        self._depth = 0
        self._in_string = False
        self._escape = False
        self._started = False

    def feed(self, text: str) -> List[Dict[str, Any]]:
        completed: List[Dict[str, Any]] = []

        for ch in text:
            if not self._started:
                if ch == "{":
                    self._started = True
                    self._depth = 1
                    self._buffer = [ch]
                continue

            self._buffer.append(ch)

            if self._escape:
                self._escape = False
                continue

            if ch == "\\" and self._in_string:
                self._escape = True
                continue

            if ch == '"':
                self._in_string = not self._in_string
                continue

            if self._in_string:
                continue

            if ch == "{":
                self._depth += 1
            elif ch == "}":
                self._depth -= 1
                if self._depth == 0:
                    raw = "".join(self._buffer)
                    self._reset()
                    # A single malformed object must not abort the batch —
                    # 79 good questions are worth more than a clean failure.
                    parsed = _loads_object(raw)
                    if parsed is not None:
                        completed.append(parsed)

        return completed

    def _reset(self) -> None:
        self._buffer = []
        self._started = False
        self._depth = 0
        self._in_string = False
        self._escape = False


def parse_question_payload(buffer: str) -> List[Dict[str, Any]]:
    """Last-resort parse of a complete response body.

    Used when streaming produced no objects (e.g. the provider buffered the
    whole response). Accepts a bare array, a `{"questions": [...]}` wrapper, or
    a single object, and tolerates markdown fences.
    """
    text = (buffer or "").strip()
    if not text:
        return []

    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text[3:]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    parsed = None
    for candidate in (text, repair_json_backslashes(text)):
        try:
            parsed = json.loads(candidate)
            break
        except json.JSONDecodeError:
            continue
    if parsed is None:
        # Salvage whatever complete objects exist in a truncated response.
        extractor = JsonObjectStreamExtractor()
        return extractor.feed(text)

    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if isinstance(parsed, dict):
        for key in ("questions", "items", "pool", "data"):
            value = parsed.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [parsed]
    return []
